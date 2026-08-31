"""Збирач аналітики TikTok. Використовує токен прямого каналу з apps.inbox.tiktok.

sync_daily(days)  — добові метрики акаунта + аудиторія + активність → TtDailyStat/TtAccountSnapshot
sync_videos(max)  — метрики відео (пагінація cursor) → TtVideo
trending(query)   — живі трендові пошукові фрази (не зберігаємо, віддаємо як є)
"""
import json
import logging
from datetime import date, datetime, timedelta

from django.utils import timezone

log = logging.getLogger(__name__)

# Поля /business/get/ (повний дозволений список TikTok — перевірено live 31.08.2026)
DAILY_FIELDS = [
    "daily_total_followers", "daily_new_followers", "daily_lost_followers",
    "profile_views", "video_views", "unique_video_views",
    "likes", "comments", "shares", "engagement_rate",
    "bio_link_clicks", "email_clicks", "phone_number_clicks", "address_clicks",
    "lead_submissions",
]
SNAPSHOT_FIELDS = [
    "username", "display_name", "profile_image", "bio_description", "profile_deep_link",
    "is_verified", "followers_count", "following_count", "total_likes", "videos_count",
    "audience_ages", "audience_genders", "audience_countries", "audience_cities",
    "audience_activity", "average_views", "average_likes", "average_comments",
    "average_shares", "followers_growth_rate", "completion_rate", "engaged_audience",
]
VIDEO_FIELDS = [
    "item_id", "caption", "create_time", "thumbnail_url", "share_url", "video_duration",
    "video_views", "reach", "likes", "comments", "shares",
    "average_time_watched", "full_video_watched_rate", "total_time_watched",
    "impression_sources", "audience_countries",
]


def _channel_and_token():
    from apps.inbox import tiktok as tt
    ch = tt.get_channel(active_only=True)
    if ch is None:
        raise RuntimeError("Прямий TikTok-канал не підключено (Контакт-центр → TikTok)")
    return ch, tt.valid_token(ch), (ch.config or {}).get("business_id", "")


def _get(path, params):
    from apps.inbox import tiktok as tt
    ch, token, biz = _channel_and_token()
    params = {"business_id": biz, **params}
    return tt._request("GET", path, token=token, params=params)


def sync_daily(days: int = 30) -> dict:
    """Тягне добові метрики за останні `days` днів (TikTok віддає максимум ~60) + зріз акаунта."""
    from .models import TtDailyStat, TtAccountSnapshot
    end = date.today() - timedelta(days=1)          # «по вчора» — сьогоднішній день неповний
    start = end - timedelta(days=min(days, 60) - 1)
    js = _get("/business/get/", {
        "fields": json.dumps(DAILY_FIELDS),
        "start_date": start.isoformat(), "end_date": end.isoformat(),
    })
    data = js.get("data") or {}
    rows = 0
    for m in (data.get("metrics") or []):
        d = m.get("date") or m.get("stat_date")
        if not d:
            continue
        try:
            day = datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        TtDailyStat.objects.update_or_create(date=day, defaults={
            "followers_total": int(m.get("daily_total_followers") or 0),
            "followers_gained": int(m.get("daily_new_followers") or 0),
            "followers_lost": int(m.get("daily_lost_followers") or 0),
            "profile_views": int(m.get("profile_views") or 0),
            "video_views": int(m.get("video_views") or 0),
            "unique_video_views": int(m.get("unique_video_views") or 0),
            "likes": int(m.get("likes") or 0),
            "comments": int(m.get("comments") or 0),
            "shares": int(m.get("shares") or 0),
            "engagement_rate": float(m.get("engagement_rate") or 0),
            "bio_link_clicks": int(m.get("bio_link_clicks") or 0),
            "email_clicks": int(m.get("email_clicks") or 0),
            "phone_clicks": int(m.get("phone_number_clicks") or 0),
            "address_clicks": int(m.get("address_clicks") or 0),
            "lead_submissions": int(m.get("lead_submissions") or 0),
            "raw": m,
        })
        rows += 1

    # аудиторія/активність повертаються лише із діапазоном дат — беремо останні 7 днів
    snap_js = _get("/business/get/", {"fields": json.dumps(SNAPSHOT_FIELDS),
                                      "start_date": (end - timedelta(days=6)).isoformat(),
                                      "end_date": end.isoformat()})
    sd = snap_js.get("data") or {}
    _sm = (sd.get("metrics") or [{}])
    for _row in _sm:
        for _k in ("audience_ages", "audience_genders", "audience_countries", "audience_cities",
                   "audience_activity", "average_views", "average_likes", "average_comments",
                   "average_shares", "followers_growth_rate", "completion_rate", "engaged_audience"):
            if sd.get(_k) is None and _row.get(_k) is not None:
                sd[_k] = _row[_k]
    snap, _ = TtAccountSnapshot.objects.update_or_create(pk=1, defaults={
        "followers_count": int(sd.get("followers_count") or 0),
        "total_likes": int(sd.get("total_likes") or 0),
        "videos_count": int(sd.get("videos_count") or 0),
        "audience_ages": sd.get("audience_ages") or [],
        "audience_genders": sd.get("audience_genders") or [],
        "audience_countries": sd.get("audience_countries") or [],
        "audience_cities": sd.get("audience_cities") or [],
        "audience_activity": sd.get("audience_activity") or [],
        "averages": {k: sd.get(k) for k in ("average_views", "average_likes", "average_comments",
                                            "average_shares", "followers_growth_rate",
                                            "completion_rate", "engaged_audience") if sd.get(k) is not None},
        "profile": {k: sd.get(k) for k in ("username", "display_name", "profile_image",
                                           "bio_description", "profile_deep_link", "is_verified",
                                           "following_count") if sd.get(k) is not None},
    })
    return {"daily_rows": rows, "followers": snap.followers_count}


def sync_videos(max_videos: int = 200) -> dict:
    """Всі відео з метриками (пагінація). Оновлює наявні, додає нові."""
    from .models import TtVideo
    saved = 0
    cursor = None
    while saved < max_videos:
        params = {"fields": json.dumps(VIDEO_FIELDS), "max_count": 20}
        if cursor:
            params["cursor"] = cursor
        js = _get("/business/video/list/", params)
        data = js.get("data") or {}
        for v in (data.get("videos") or []):
            item_id = str(v.get("item_id") or "")
            if not item_id:
                continue
            ct = None
            try:
                ct = datetime.fromtimestamp(int(v.get("create_time") or 0), tz=timezone.utc)
            except Exception:
                pass
            TtVideo.objects.update_or_create(item_id=item_id, defaults={
                "caption": (v.get("caption") or "")[:5000],
                "create_time": ct,
                "thumbnail_url": v.get("thumbnail_url") or "",
                "share_url": v.get("share_url") or "",
                "duration": float(v.get("video_duration") or 0),
                "views": int(v.get("video_views") or 0),
                "reach": int(v.get("reach") or 0),
                "likes": int(v.get("likes") or 0),
                "comments": int(v.get("comments") or 0),
                "shares": int(v.get("shares") or 0),
                "average_time_watched": float(v.get("average_time_watched") or 0),
                "full_video_watched_rate": float(v.get("full_video_watched_rate") or 0),
                "total_time_watched": float(v.get("total_time_watched") or 0),
                "impression_sources": v.get("impression_sources") or [],
                "audience_countries": v.get("audience_countries") or [],
                "raw": v,
            })
            saved += 1
        if not data.get("has_more"):
            break
        cursor = data.get("cursor")
        if not cursor:
            break
    return {"videos": saved}


def trending(query: str, country: str = "UA") -> list:
    js = _get("/discovery/trending/search/keyword/", {"query": query, "country_code": country})
    return (js.get("data") or {}).get("search_keywords") or []
