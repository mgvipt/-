"""Read-only Meta Marketing/Instagram Insights synchronisation.

The module intentionally has no create/update/delete calls against Meta. It
copies reporting data into CRM so dashboards stay fast and tokens never reach
the browser.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone as dt_timezone
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import MetaAdDailyStat, MetaContentStat


class MetaGraphError(RuntimeError):
    def __init__(self, message, *, code=None, subcode=None):
        super().__init__(message)
        self.code = code
        self.subcode = subcode


def _graph_version():
    return (os.environ.get("META_MARKETING_GRAPH_VERSION")
            or os.environ.get("META_API_VERSION") or "v21.0").strip()


def _token():
    value = (os.environ.get("META_MARKETING_ACCESS_TOKEN")
             or os.environ.get("META_ACCESS_TOKEN") or "").strip()
    if not value:
        raise MetaGraphError("META_MARKETING_ACCESS_TOKEN is not configured")
    return value


def configured_ad_accounts():
    raw = os.environ.get("META_AD_ACCOUNT_IDS", "").strip()
    if raw:
        items = raw.replace(";", ",").split(",")
    else:
        items = [os.environ.get("META_AD_ACCOUNT_ID", ""), os.environ.get("META_AD_ACCOUNT_ID_2", "")]
    result = []
    for item in items:
        value = str(item or "").strip()
        if value:
            value = value if value.startswith("act_") else f"act_{value}"
            if value not in result:
                result.append(value)
    return result


def configured_ig_account():
    return (os.environ.get("META_IG_ACCOUNT_ID") or os.environ.get("META_IG_ID") or "").strip()


def graph_get(path, params=None, *, timeout=45):
    query = dict(params or {})
    query["access_token"] = _token()
    url = f"https://graph.facebook.com/{_graph_version()}/{path.lstrip('/')}?{urllib.parse.urlencode(query)}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
            error = body.get("error") or {}
        except Exception:
            error = {}
        raise MetaGraphError(
            str(error.get("message") or f"Meta HTTP {exc.code}")[:500],
            code=error.get("code"), subcode=error.get("error_subcode"),
        ) from exc


def graph_pages(path, params=None, *, max_pages=100):
    payload = graph_get(path, params)
    pages = 0
    while True:
        pages += 1
        for row in payload.get("data") or []:
            yield row
        next_url = (payload.get("paging") or {}).get("next")
        if not next_url or pages >= max_pages:
            break
        # Paging URL already includes the token. It is consumed server-side and
        # never logged or returned from this module.
        try:
            with urllib.request.urlopen(next_url, timeout=45) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            raise MetaGraphError(f"Meta paging HTTP {exc.code}") from exc


def _int(value):
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _decimal(value):
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _action_map(rows):
    result = {}
    for row in rows or []:
        key = str(row.get("action_type") or "")
        if key:
            result[key] = _int(row.get("value"))
    return result


def _pick(actions, keys):
    for key in keys:
        if key in actions:
            return actions[key]
    return 0


def _catalog(account_id):
    campaigns = {}
    for row in graph_pages(account_id + "/campaigns", {
        "fields": "id,name,objective,effective_status", "limit": 100,
    }):
        campaigns[str(row.get("id") or "")] = row

    ads = {}
    fields = (
        "id,name,campaign_id,adset_id,effective_status,preview_shareable_link,"
        "creative{id,name,thumbnail_url,object_story_id,effective_instagram_media_id,instagram_permalink_url}"
    )
    # Meta rejects large pages when creative fields are expanded. Small pages are
    # slower, but reliable and keep the historical sync read-only/idempotent.
    for row in graph_pages(account_id + "/ads", {"fields": fields, "limit": 25}):
        ads[str(row.get("id") or "")] = row
    return campaigns, ads


def _insight_rows(account_id, level, since, until):
    common = (
        "account_id,account_name,date_start,date_stop,spend,impressions,reach,clicks,"
        "outbound_clicks,cpc,cpm,ctr,frequency,actions,action_values,video_play_actions"
    )
    hierarchy = "" if level == "account" else ",campaign_id,campaign_name,adset_id,adset_name,ad_id,ad_name"
    return graph_pages(account_id + "/insights", {
        "fields": common + hierarchy,
        "level": level,
        "time_increment": 1,
        "time_range": json.dumps({"since": since.isoformat(), "until": until.isoformat()}),
        "action_report_time": "conversion",
        "limit": 500,
    })


def _date_chunks(since: date, until: date, days=7):
    """Small windows avoid Graph error #1 on active ad accounts."""
    cursor = since
    while cursor <= until:
        chunk_until = min(until, cursor + timedelta(days=max(1, days) - 1))
        yield cursor, chunk_until
        cursor = chunk_until + timedelta(days=1)


def sync_ads(since: date, until: date):
    accounts = configured_ad_accounts()
    if not accounts:
        raise MetaGraphError("META_AD_ACCOUNT_IDS is not configured")
    written = 0
    for account_id in accounts:
        account = graph_get(account_id, {"fields": "id,name,currency,account_status"})
        campaigns, ads = _catalog(account_id)
        for level in ("account", "ad"):
            for chunk_since, chunk_until in _date_chunks(since, until):
                for row in _insight_rows(account_id, level, chunk_since, chunk_until):
                    written += _save_ad_insight(
                        row, level=level, account_id=account_id, account=account,
                        campaigns=campaigns, ads=ads,
                    )
    return {"accounts": len(accounts), "rows": written}


def _save_ad_insight(row, *, level, account_id, account, campaigns, ads):
    ad_id = str(row.get("ad_id") or "")
    campaign_id = str(row.get("campaign_id") or "")
    ad = ads.get(ad_id) or {}
    campaign = campaigns.get(campaign_id) or {}
    creative = ad.get("creative") or {}
    actions = _action_map(row.get("actions"))
    outbound = _action_map(row.get("outbound_clicks"))
    videos = _action_map(row.get("video_play_actions"))
    object_id = str(row.get("account_id") or account_id.removeprefix("act_")) if level == "account" else ad_id
    MetaAdDailyStat.objects.update_or_create(
        date=date.fromisoformat(row["date_start"]), level=level,
        account_id=account_id, object_id=object_id,
        defaults={
            "account_name": row.get("account_name") or account.get("name") or "",
            "currency": account.get("currency") or "USD",
            "campaign_id": campaign_id,
            "campaign_name": row.get("campaign_name") or campaign.get("name") or "",
            "campaign_objective": campaign.get("objective") or "",
            "adset_id": str(row.get("adset_id") or ad.get("adset_id") or ""),
            "adset_name": row.get("adset_name") or "",
            "ad_id": ad_id,
            "ad_name": row.get("ad_name") or ad.get("name") or "",
            "effective_status": ad.get("effective_status") or campaign.get("effective_status") or "",
            "creative_id": str(creative.get("id") or ""),
            "media_id": str(creative.get("effective_instagram_media_id") or ""),
            "thumbnail_url": creative.get("thumbnail_url") or "",
            "permalink_url": creative.get("instagram_permalink_url") or ad.get("preview_shareable_link") or "",
            "spend": _decimal(row.get("spend")),
            "impressions": _int(row.get("impressions")),
            "reach": _int(row.get("reach")),
            "clicks": _int(row.get("clicks")),
            "outbound_clicks": _pick(outbound, ("outbound_click",)) or sum(outbound.values()),
            "messages_started": _pick(actions, (
                "onsite_conversion.messaging_conversation_started_7d",
                "messaging_conversation_started_7d",
            )),
            "meta_leads": _pick(actions, ("lead", "onsite_conversion.lead_grouped", "leadgen_grouped")),
            "purchases": _pick(actions, ("purchase", "omni_purchase", "offsite_conversion.fb_pixel_purchase")),
            "video_views": _pick(videos, ("video_view",)) or sum(videos.values()),
            "actions": actions,
        },
    )
    return 1


def _metric_value(media_id, metric):
    try:
        data = graph_get(media_id + "/insights", {"metric": metric}).get("data") or []
    except MetaGraphError as exc:
        # Code 100 means the metric is not defined for this media type. It must
        # remain NULL rather than becoming a misleading zero.
        if exc.code in (100, 10):
            return None
        raise
    if not data:
        return None
    values = data[0].get("values") or []
    value = values[-1].get("value") if values else data[0].get("total_value", {}).get("value")
    return _int(value) if value is not None else None


def _parse_published(value):
    parsed = parse_datetime(value or "")
    if parsed is None:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, dt_timezone.utc)
    return parsed


def _media_rows(ig_account_id, edge, since):
    fields = (
        "id,caption,media_type,media_product_type,permalink,thumbnail_url,media_url,"
        "timestamp,like_count,comments_count"
    )
    for row in graph_pages(ig_account_id + "/" + edge, {"fields": fields, "limit": 100}):
        published = _parse_published(row.get("timestamp"))
        if edge == "media" and published.date() < since:
            break
        yield row, published


def sync_content(since: date):
    ig_account_id = configured_ig_account()
    if not ig_account_id:
        raise MetaGraphError("META_IG_ACCOUNT_ID is not configured")
    written = 0
    seen = set()
    for edge in ("media", "stories"):
        try:
            rows = _media_rows(ig_account_id, edge, since)
            for row, published in rows:
                media_id = str(row.get("id") or "")
                if not media_id or media_id in seen:
                    continue
                seen.add(media_id)
                metrics = {}
                for metric in (
                    "reach", "views", "saved", "shares", "total_interactions",
                    "follows", "profile_visits",
                ):
                    metrics[metric] = _metric_value(media_id, metric)
                    time.sleep(0.03)
                MetaContentStat.objects.update_or_create(
                    media_id=media_id,
                    defaults={
                        "ig_account_id": ig_account_id,
                        "caption": row.get("caption") or "",
                        "media_type": row.get("media_type") or "",
                        "media_product_type": row.get("media_product_type") or ("STORY" if edge == "stories" else ""),
                        "permalink": row.get("permalink") or "",
                        "thumbnail_url": row.get("thumbnail_url") or row.get("media_url") or "",
                        "published_at": published,
                        "like_count": _int(row.get("like_count")),
                        "comments_count": _int(row.get("comments_count")),
                        "reach": metrics["reach"],
                        "views": metrics["views"],
                        "saved": metrics["saved"],
                        "shares": metrics["shares"],
                        "total_interactions": metrics["total_interactions"],
                        "follows": metrics["follows"],
                        "profile_visits": metrics["profile_visits"],
                        "metrics": metrics,
                    },
                )
                written += 1
        except MetaGraphError as exc:
            # Expired stories or an unavailable edge must not block feed/reels.
            if edge == "stories" and exc.code in (10, 100, 190):
                continue
            raise
    return {"media": written}


def sync_all(since: date, until: date):
    return {"ads": sync_ads(since, until), "content": sync_content(since)}
