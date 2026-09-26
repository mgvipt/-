"""Ролики власних TikTok-акаунтів блогів — напряму з офіційного TikTok API for Business, без Virale (27.09.2026, Олег:
«навіщо мій TikTok через Virale, зроби автономно»).

- @dekor_dlia_stin (Wallcov) уже підключений у Контакт-центрі — його токен беремо звідти.
- Інші акаунти (напр. @.stiny_v_shotsi) власник один раз авторизує кнопкою в профілі блогу: вхід на сторінці TikTok,
  пароль у CRM не потрапляє; токени зберігаються в ContentChannel.api (окремо від каналу Контакт-центру — його не чіпаємо).
- Ролики з переглядами, лайками, коментарями, репостами й середнім часом перегляду пишуться у FeedItem (is_own=True):
  їх бачать «Активні зараз» у профілі блогу, Агент заводу й Аналітик. Раз на добу (крон) і кнопкою.
"""
import json
import secrets
from datetime import datetime, timedelta, timezone as dt_tz

from django.core import signing
from django.utils import timezone

FIELDS = ["item_id", "create_time", "caption", "thumbnail_url", "share_url", "video_views", "likes", "comments", "shares",
          "reach", "average_time_watched", "full_video_watched_rate", "video_duration"]


def _tt():
    from apps.inbox import tiktok
    return tiktok


def start_url(cc, user):
    """Посилання на авторизацію TikTok для акаунта блогу (state з позначкою контент-заводу)."""
    tt = _tt()
    state = signing.dumps({"u": int(user.id), "n": secrets.token_urlsafe(8), "cf": int(cc.id)}, salt=tt._STATE_SALT)
    return tt.authorize_url(state)


def connect(code, cc_id):
    """Callback: код → токени акаунта; зберегти в ContentChannel.api. Повертає (cc, попередження)."""
    from .models import ContentChannel
    tt = _tt()
    cc = ContentChannel.objects.get(pk=cc_id)
    tok = tt.exchange_code(code)
    prof = {}
    try:
        prof = tt.business_profile(tok["business_id"], tok["access_token"])
    except Exception:
        pass
    cc.api = {**tok, **prof, "connected_at": timezone.now().isoformat()}
    cc.save(update_fields=["api"])
    got = (prof.get("username") or "").lower().lstrip(".")
    warn = "" if not got or got == cc.handle.lower().lstrip(".") else f"Авторизовано акаунт @{got}, а в блозі вказано @{cc.handle}."
    return cc, warn


def _token(cc):
    """(access_token, business_id) для акаунта або (None, None)."""
    tt = _tt()
    api = dict(cc.api or {})
    if api.get("access_token"):
        exp = tt._parse_dt(api.get("expires_at"))
        if exp and exp - tt._now() > timedelta(minutes=5):
            return api["access_token"], api.get("business_id")
        if api.get("refresh_token"):
            api.update(tt.refresh_tokens(api["refresh_token"]))
            cc.api = api
            cc.save(update_fields=["api"])
            return api["access_token"], api.get("business_id")
        return None, None
    ch = tt.get_channel(active_only=True)  # акаунт Контакт-центру (Wallcov)
    if ch and (ch.config or {}).get("username", "").lower().lstrip(".") == cc.handle.lower().lstrip("."):
        return tt.valid_token(ch), (ch.config or {}).get("business_id")
    return None, None


def connected(cc):
    try:
        return bool(_token(cc)[0])
    except Exception:
        return False


def sync(cc, limit=60):
    """Забрати ролики акаунта в FeedItem. Повертає кількість."""
    from .models import FeedItem
    tt = _tt()
    token, biz = _token(cc)
    if not token:
        raise RuntimeError(f"TikTok @{cc.handle} не підключено — натисніть «Підключити TikTok» у профілі блогу.")
    videos, cursor = [], None
    while len(videos) < limit:
        params = {"business_id": biz, "fields": json.dumps(FIELDS), "max_count": 20}
        if cursor:
            params["cursor"] = cursor
        d = tt._request("GET", "/business/video/list/", token=token, params=params).get("data") or {}
        videos += d.get("videos") or []
        if not d.get("has_more") or not d.get("cursor"):
            break
        cursor = d.get("cursor")
    user = cc.handle.lower().lstrip(".")
    n = 0
    for v in videos[:limit]:
        vid = str(v.get("item_id") or "")
        if not vid:
            continue
        views = int(v.get("video_views") or 0)
        likes, comments, shares = int(v.get("likes") or 0), int(v.get("comments") or 0), int(v.get("shares") or 0)
        try:
            ts = datetime.fromtimestamp(int(v.get("create_time")), tz=dt_tz.utc)
        except (TypeError, ValueError):
            ts = None
        FeedItem.objects.update_or_create(external_id=f"tt:{vid}", defaults={
            "username": user, "platform": "tiktok", "url": (v.get("share_url") or f"https://www.tiktok.com/@{cc.handle}/video/{vid}")[:2000],
            "preview_url": (v.get("thumbnail_url") or "")[:2000], "caption": v.get("caption") or "", "media_type": "video",
            "duration": v.get("video_duration"), "views": views, "likes": likes, "comments": comments,
            "engagement": round((likes + comments + shares) / views * 100, 2) if views else None,
            "is_own": True, "published_at": ts,
        })
        n += 1
    api = dict(cc.api or {})
    api["synced_at"], api["synced_n"] = timezone.now().isoformat(), n
    cc.api = api
    cc.save(update_fields=["api"])
    return n


def sync_all():
    """Усі власні TikTok-акаунти блогів, які можна прочитати. {handle: n або помилка}."""
    from .models import ContentChannel
    out = {}
    for cc in ContentChannel.objects.filter(platform="tiktok", role=ContentChannel.Role.OWN, is_active=True):
        try:
            out[cc.handle] = sync(cc)
        except Exception as e:
            out[cc.handle] = f"помилка: {str(e)[:120]}"
    return out
