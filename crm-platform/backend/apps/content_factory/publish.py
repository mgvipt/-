"""Публікація з CRM (25.09.2026): рилс → Instagram / TikTok, карусель → Instagram. Лише за кнопкою власника з підтвердженням.

Instagram — офіційний Content Publishing API системного користувача (META_MARKETING_ACCESS_TOKEN, право instagram_content_publish),
акаунт @dekor_dlia_stin (META_IG_ID), ліміт 100 публікацій на добу. Файли беруться за публічним посиланням CRM (/api/f/<token>/).
TikTok — Business API каналу «TikTok · Direct» (id=15, право video.publish), той самий @dekor_dlia_stin.
Інші блоги поки не підключені до бізнес-менеджера — публікувати в них не можна (кнопки немає).
ШІ-кадри: у TikTok ставимо позначку is_ai_generated, в Instagram текст «ШІ-візуалізація» вже на кадрі.
"""
import json
import os
import time
import urllib.parse
import urllib.request

from django.utils import timezone

PUBLIC = "https://crm.wallcovdec.com.ua"
PUBLISHABLE_BLOGS = {"wallcov"}  # блоги, чиї акаунти підключені до бізнес-менеджера


class PublishError(Exception):
    pass


def _link(link_id):
    from apps.inbox.models import SharedLink
    tok = SharedLink.objects.filter(pk=link_id).values_list("token", flat=True).first()
    if not tok:
        raise PublishError("Файл не знайдено — перемонтуйте ролик.")
    return f"{PUBLIC}/api/f/{tok}/"


def can_publish(blog):
    return bool(blog and blog.slug in PUBLISHABLE_BLOGS)


# ── Instagram ────────────────────────────────────────────────────────────────────────────────────

def _ig(method, path, **params):
    ver = os.environ.get("META_MARKETING_GRAPH_VERSION") or "v23.0"
    tok = os.environ.get("META_MARKETING_ACCESS_TOKEN")
    if not tok:
        raise PublishError("Немає токена Meta на сервері.")
    data = urllib.parse.urlencode({**params, "access_token": tok}).encode()
    url = f"https://graph.facebook.com/{ver}/{path}"
    req = urllib.request.Request(url + ("?" + data.decode() if method == "GET" else ""), data=None if method == "GET" else data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read()).get("error", {})
            msg = err.get("error_user_msg") or err.get("message") or f"HTTP {e.code}"
        except Exception:
            msg = f"HTTP {e.code}"
        raise PublishError(f"Instagram: {msg}") from None


def _ig_wait(container_id, timeout=300):
    """Чекаємо, поки Instagram обробить файл (FINISHED). Рилс — до кількох хвилин."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = _ig("GET", container_id, fields="status_code,status").get("status_code")
        if st == "FINISHED":
            return
        if st in ("ERROR", "EXPIRED"):
            raise PublishError("Instagram не прийняв файл (формат/тривалість).")
        time.sleep(6)
    raise PublishError("Instagram довго обробляє файл — спробуйте ще раз за кілька хвилин.")


def _ig_publish(container_id):
    ig = os.environ.get("META_IG_ID")
    media_id = _ig("POST", f"{ig}/media_publish", creation_id=container_id)["id"]
    link = _ig("GET", media_id, fields="permalink").get("permalink", "")
    return {"id": media_id, "permalink": link, "at": timezone.now().isoformat()}


def ig_reel_container(reel):
    """Крок 1 (нічого не публікує): контейнер рилса, Instagram завантажує й перевіряє файл."""
    if not reel.file_id:
        raise PublishError("Немає відео — змонтуйте ролик.")
    ig = os.environ.get("META_IG_ID")
    cid = _ig("POST", f"{ig}/media", media_type="REELS", video_url=_link(reel.file_id), caption=(reel.caption or reel.title)[:2200],
              share_to_feed="true")["id"]
    _ig_wait(cid)
    return cid


def ig_carousel_container(c):
    ids = [s.get("rendered_id") for s in c.slides if s.get("rendered_id")]
    if len(ids) < 2:
        raise PublishError("Слайди ще не намальовані.")
    ig = os.environ.get("META_IG_ID")
    children = [_ig("POST", f"{ig}/media", image_url=_link(i), is_carousel_item="true")["id"] for i in ids[:20]]
    cid = _ig("POST", f"{ig}/media", media_type="CAROUSEL", children=",".join(children), caption=(c.caption or c.title)[:2200])["id"]
    _ig_wait(cid, timeout=120)
    return cid


# ── TikTok ───────────────────────────────────────────────────────────────────────────────────────

def tiktok_reel(reel, video_link_id=None):
    from apps.inbox import tiktok as tt
    ch = tt.get_channel(active_only=True)
    if not ch:
        raise PublishError("TikTok не підключено (Контакт-центр → TikTok · Direct).")
    token = tt.valid_token(ch)
    biz = (ch.config or {}).get("business_id")
    ai = any(b.get("image_id") and b.get("ai") not in ("photo", "color") for b in reel.beats)  # фото й корекція кольору — не ШІ
    body = {"business_id": biz, "video_url": _link(video_link_id or reel.file_id),
            "post_info": {"caption": (reel.caption or reel.title)[:2200], "is_ai_generated": ai,
                          "disable_comment": False, "disable_duet": False, "disable_stitch": False}}
    try:
        r = tt._request("POST", "/business/video/publish/", token=token, body=body, timeout=60)
    except tt.TikTokApiError as e:
        raise PublishError(str(e)[:300]) from None
    share = (r.get("data") or {}).get("share_id") or r.get("share_id")
    if not share:
        raise PublishError(f"TikTok: {r.get('message') or 'не прийняв відео'}")
    return {"share_id": share, "at": timezone.now().isoformat(), "ai_label": ai}


# ── Точки входу ──────────────────────────────────────────────────────────────────────────────────

def publish_reel(reel, platform):
    if not can_publish(reel.blog):
        raise PublishError("Акаунти цього блогу ще не підключені до бізнес-менеджера — публікація лише в Wallcov.")
    done = dict(reel.published or {})
    if done.get(platform):
        raise PublishError("Цей ролик уже опубліковано туди.")
    if platform == "instagram":
        done["instagram"] = _ig_publish(ig_reel_container(reel))
    elif platform == "tiktok":
        done["tiktok"] = tiktok_reel(reel, (reel.variants or {}).get("tiktok"))
    else:
        raise PublishError("Невідома мережа.")
    reel.published = done
    reel.save(update_fields=["published"])
    return done[platform]


def publish_carousel(c):
    if not can_publish(c.blog):
        raise PublishError("Акаунти цього блогу ще не підключені до бізнес-менеджера — публікація лише в Wallcov.")
    done = dict(c.published or {})
    if done.get("instagram"):
        raise PublishError("Цю карусель уже опубліковано.")
    done["instagram"] = _ig_publish(ig_carousel_container(c))
    c.published = done
    c.save(update_fields=["published"])
    return done["instagram"]
