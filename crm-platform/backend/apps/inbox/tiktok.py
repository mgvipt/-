"""TikTok Direct — пряме підключення переписки TikTok до CRM (БЕЗ ChatPlace).

Офіційний TikTok Business Messaging API (TikTok API for Business, scope «TikTok Accounts»).
Схема така сама, як у meta.py для Instagram/Facebook:

    TikTok ──webhook (im_receive_msg / im_send_msg)──▶ handle_event() ──▶ Conversation + Message + Contact/Lead
    CRM ──send_text()──▶ POST /business/message/send/ ──▶ клієнту в TikTok

Блоки файлу:
  1. Налаштування (.env): TIKTOK_APP_ID / TIKTOK_APP_SECRET / TIKTOK_API_VERSION / TIKTOK_REDIRECT_URL
  2. OAuth: посилання на авторизацію → обмін коду на токени → зберігання в Channel.config
  3. Токени: access_token живе ~24 год → авто-оновлення через refresh_token (з блокуванням рядка БД)
  4. Вебхук: перевірка підпису Tiktok-Signature → розбір події → запис у CRM
  5. Відправка: текст клієнту з контролем вікна 48 год / 10 повідомлень
  6. Адаптер каналу (реєструється в adapters.ADAPTERS під kind="tiktok" без правки adapters.py)
  7. HTTP-вʼюхи: status / connect / callback / webhook / disconnect

Канал у CRM: kind="tiktok", name="TikTok · Direct", config={"tiktok_direct": True, ...токени...}.
ChatPlace-канал «ChatPlace · TikTok» (config.chatplace=True) НЕ чіпається — він лишається каналом ШІ Юлі.

Обмеження TikTok (Україна): пише першим тільки клієнт; відповісти можна 48 год після його
останнього повідомлення і не більше 10 наших повідомлень поспіль; відправка фото/відео з API
в Україні недоступна (вхідні фото скачуються і показуються в чаті).
"""
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta

from django.core import signing
from django.db import transaction
from django.utils import timezone

log = logging.getLogger(__name__)

# ============================================================================
# 1. НАЛАШТУВАННЯ
# ============================================================================
APP_ID = (os.environ.get("TIKTOK_APP_ID", "") or "").strip()
APP_SECRET = (os.environ.get("TIKTOK_APP_SECRET", "") or "").strip()
API_VERSION = (os.environ.get("TIKTOK_API_VERSION", "v1.3") or "v1.3").strip()
REDIRECT_URL = (os.environ.get("TIKTOK_REDIRECT_URL", "https://crm.wallcovdec.com.ua/api/inbox/tiktok/callback/") or "").strip()
WEBHOOK_URL = (os.environ.get("TIKTOK_WEBHOOK_URL", "https://crm.wallcovdec.com.ua/api/inbox/tiktok/webhook/") or "").strip()
PUBLIC_BASE = "https://crm.wallcovdec.com.ua"

API_BASE = "https://business-api.tiktok.com/open_api/%s" % API_VERSION
AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize"

# Права, які просимо у бізнес-акаунта. TikTok відхиляє authorize, якщо просити
# не видані app-у scope (перевірено 31.08: message.* чекають схвалення анкети Accounts API).
# Тому список можна звузити/розширити через .env TIKTOK_SCOPES (кома-список) БЕЗ перезбирання образу.
_DEFAULT_SCOPES = ("user.info.basic,user.info.username,user.info.profile,user.account.type,"
                   "message.list.read,message.list.send,message.list.manage")
SCOPES = [x.strip() for x in (os.environ.get("TIKTOK_SCOPES", "") or _DEFAULT_SCOPES).split(",") if x.strip()]

CHANNEL_NAME = "TikTok · Direct"
CHANNEL_KIND = "tiktok"
WINDOW_HOURS = 48          # вікно відповіді після останнього повідомлення клієнта
WINDOW_MAX_OUT = 10        # максимум наших повідомлень у вікні
SIGNATURE_TOLERANCE_SEC = 300
STATE_MAX_AGE_SEC = 900
_STATE_SALT = "tiktok-oauth-state"


def configured() -> bool:
    """Чи задані ключі застосунку TikTok у .env."""
    return bool(APP_ID and APP_SECRET)


def _now():
    return timezone.now()


# ============================================================================
# 2. HTTP до TikTok API
# ============================================================================
class TikTokApiError(RuntimeError):
    pass


def _request(method: str, path: str, *, token: str = "", params: dict = None, body: dict = None, timeout: int = 20) -> dict:
    """Один виклик TikTok API. GET → query, POST → JSON. Помилки TikTok (code != 0) → TikTokApiError."""
    url = API_BASE + path
    headers = {"Accept": "application/json", "User-Agent": "WallcovCRM/1.0 (+https://crm.wallcovdec.com.ua)"}
    if token:
        headers["Access-Token"] = token
    data = None
    if method == "GET":
        if params:
            url += "?" + urllib.parse.urlencode(params)
    else:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body or {}).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
            raw = r.read().decode() or "{}"
    except urllib.error.HTTPError as exc:
        raw = ""
        try:
            raw = exc.read().decode()
        except Exception:
            pass
        raise TikTokApiError("TikTok HTTP %s: %s" % (exc.code, raw[:300]))
    try:
        js = json.loads(raw)
    except Exception:
        raise TikTokApiError("TikTok: не-JSON відповідь: %s" % raw[:200])
    if isinstance(js, dict) and js.get("code") not in (0, None, "0"):
        raise TikTokApiError("TikTok %s: %s" % (js.get("code"), js.get("message") or raw[:200]))
    return js if isinstance(js, dict) else {}


# ============================================================================
# 3. OAUTH + ТОКЕНИ
# ============================================================================
def make_state(user_id: int) -> str:
    """Підписаний state для OAuth — захист від підміни callback (CSRF)."""
    return signing.dumps({"u": int(user_id), "n": secrets.token_urlsafe(8)}, salt=_STATE_SALT)


def check_state(state: str) -> dict:
    return signing.loads(state or "", salt=_STATE_SALT, max_age=STATE_MAX_AGE_SEC)


def authorize_url(state: str) -> str:
    q = {
        "client_key": APP_ID,
        "response_type": "code",
        "scope": ",".join(SCOPES),
        "redirect_uri": REDIRECT_URL,
        "state": state,
    }
    return AUTHORIZE_URL + "?" + urllib.parse.urlencode(q)


def exchange_code(auth_code: str) -> dict:
    """Код з callback → access_token + refresh_token + open_id (business_id)."""
    js = _request("POST", "/tt_user/oauth2/token/", body={
        "client_id": APP_ID, "client_secret": APP_SECRET,
        "grant_type": "authorization_code", "auth_code": auth_code,
        "redirect_uri": REDIRECT_URL,
    })
    d = js.get("data") or {}
    if not d.get("access_token") or not d.get("open_id"):
        raise TikTokApiError("TikTok не повернув токен: %s" % json.dumps(js)[:300])
    return _token_fields(d, business_id=d.get("open_id"), scope=d.get("scope", ""))


def refresh_tokens(refresh_token: str) -> dict:
    js = _request("POST", "/tt_user/oauth2/refresh_token/", body={
        "client_id": APP_ID, "client_secret": APP_SECRET,
        "grant_type": "refresh_token", "refresh_token": refresh_token,
    })
    d = js.get("data") or {}
    if not d.get("access_token"):
        raise TikTokApiError("TikTok не оновив токен: %s" % json.dumps(js)[:300])
    return _token_fields(d)


def _token_fields(d: dict, **extra) -> dict:
    now = _now()
    out = {
        "access_token": d.get("access_token", ""),
        "refresh_token": d.get("refresh_token", ""),
        "expires_at": (now + timedelta(seconds=int(d.get("expires_in") or 86400))).isoformat(),
        "refresh_expires_at": (now + timedelta(seconds=int(d.get("refresh_token_expires_in") or 30 * 86400))).isoformat(),
    }
    out.update({k: v for k, v in extra.items() if v})
    return out


def business_profile(business_id: str, token: str) -> dict:
    js = _request("GET", "/business/get/", token=token, params={
        "business_id": business_id,
        "fields": json.dumps(["username", "display_name", "profile_image"]),
    })
    d = js.get("data") or {}
    return {"username": d.get("username", ""), "display_name": d.get("display_name", ""),
            "profile_image": d.get("profile_image", "")}


def register_webhook() -> dict:
    """Сказати TikTok, куди слати події DIRECT_MESSAGE (на рівні застосунку, не акаунта)."""
    return _request("POST", "/business/webhook/update/", body={
        "app_id": APP_ID, "secret": APP_SECRET,
        "event_type": "DIRECT_MESSAGE", "callback_url": WEBHOOK_URL,
    })


def get_channel(active_only: bool = False):
    """Прямий TikTok-канал CRM (не ChatPlace)."""
    from .models import Channel
    qs = Channel.objects.filter(kind=CHANNEL_KIND, config__tiktok_direct=True)
    if active_only:
        qs = qs.filter(is_active=True)
    return qs.order_by("id").first()


def _parse_dt(s):
    from django.utils.dateparse import parse_datetime
    dt = parse_datetime(s or "")
    if dt is not None and timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.utc)
    return dt


def valid_token(channel) -> str:
    """Повернути живий access_token каналу; якщо спливає за 5 хв — оновити через refresh_token.
    Оновлення під блокуванням рядка БД, щоб 6 воркерів gunicorn не оновлювали одночасно."""
    cfg = channel.config or {}
    exp = _parse_dt(cfg.get("expires_at"))
    if cfg.get("access_token") and exp and exp - _now() > timedelta(minutes=5):
        return cfg["access_token"]
    from .models import Channel
    with transaction.atomic():
        ch = Channel.objects.select_for_update().get(pk=channel.pk)
        cfg = dict(ch.config or {})
        exp = _parse_dt(cfg.get("expires_at"))
        if cfg.get("access_token") and exp and exp - _now() > timedelta(minutes=5):
            channel.config = cfg
            return cfg["access_token"]
        rexp = _parse_dt(cfg.get("refresh_expires_at"))
        if not cfg.get("refresh_token") or (rexp and rexp <= _now()):
            raise TikTokApiError("Термін дії доступу TikTok минув — підключіть акаунт заново у Контакт-центрі")
        cfg.update(refresh_tokens(cfg["refresh_token"]))
        ch.config = cfg
        ch.save(update_fields=["config"])
        channel.config = cfg
        return cfg["access_token"]


def connect_from_code(auth_code: str, user=None):
    """Callback OAuth: обміняти код, підтягнути профіль, створити/оновити канал, зареєструвати вебхук."""
    from .models import Channel
    tok = exchange_code(auth_code)
    prof = {}
    try:
        prof = business_profile(tok["business_id"], tok["access_token"])
    except Exception as exc:  # профіль — не критично
        log.warning("TikTok business/get failed: %s", exc)
    ch = Channel.objects.filter(kind=CHANNEL_KIND, config__tiktok_direct=True).order_by("id").first()
    cfg = dict((ch.config if ch else {}) or {})
    cfg.update({"tiktok_direct": True, "scope": tok.get("scope", ""), **tok, **prof,
                "connected_at": _now().isoformat(),
                "connected_by": getattr(user, "id", None)})
    if ch is None:
        ch = Channel.objects.create(kind=CHANNEL_KIND, name=CHANNEL_NAME, config=cfg, is_active=True)
    else:
        ch.config = cfg
        ch.is_active = True
        ch.name = CHANNEL_NAME
        ch.save(update_fields=["config", "is_active", "name"])
    webhook_ok = True
    try:
        register_webhook()
    except Exception as exc:
        webhook_ok = False
        log.warning("TikTok webhook/update failed: %s", exc)
    ch.config = {**ch.config, "webhook_registered": webhook_ok}
    ch.save(update_fields=["config"])
    return ch


# ============================================================================
# 4. ВЕБХУК: підпис + розбір події
# ============================================================================
def verify_signature(raw_body: bytes, header: str, *, now_ts: int = None) -> bool:
    """Tiktok-Signature: t=<unix>,s=<hex>; s = HMAC-SHA256(app_secret, "<t>.<raw_body>")."""
    if not APP_SECRET:
        return True  # dev/тести без секрету
    if not header:
        return False
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    t, s = parts.get("t", ""), parts.get("s", "")
    if not t.isdigit() or not s:
        return False
    mac = hmac.new(APP_SECRET.encode(), (t + ".").encode() + raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, s.lower()):
        return False
    now_ts = int(now_ts if now_ts is not None else time.time())
    return abs(now_ts - int(t)) <= SIGNATURE_TOLERANCE_SEC


def _new_lead(conv, username: str, user_id: str):
    """Новий вхідний чат → контакт + лід (джерело TikTok). Як у meta._new_meta_lead."""
    from apps.crm.models import Contact, Lead, Funnel
    if not conv.contact_id:
        nick = (username or "").strip().lstrip("@")
        conv.contact = Contact.objects.create(
            first_name=(nick or "TikTok")[:120], nickname=("@" + nick)[:150] if nick else "",
            channels=["tiktok"], social_link=("https://www.tiktok.com/@" + nick) if nick else "",
            comment="З TikTok (Direct)")
        conv.save(update_fields=["contact"])
    try:
        f = Funnel.objects.filter(name="Лиды").first() or Funnel.objects.order_by("id").first()
        st = f.stages.order_by("order").first() if f else None
        if f and st:
            Lead.objects.create(title=(username or user_id or "TikTok")[:255], contact=conv.contact,
                                funnel=f, stage=st, source="tiktok", is_seen=False)
    except Exception:
        log.exception("TikTok: lead create failed")


def _download_image(channel, conversation_id: str, message_id: str, media_id: str):
    """Вхідне фото: взяти тимчасове посилання у TikTok, скачати, зберегти у SharedLink → наш URL."""
    from .models import SharedLink
    token = valid_token(channel)
    js = _request("POST", "/business/message/media/download/", token=token, body={
        "business_id": (channel.config or {}).get("business_id", ""),
        "conversation_id": conversation_id, "message_id": message_id,
        "media_id": media_id, "media_type": "IMAGE",
    })
    url = (js.get("data") or {}).get("download_url") or ""
    if not url:
        return None
    req = urllib.request.Request(url, headers={"x-user": token, "User-Agent": "WallcovCRM/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
        content = r.read()
        ctype = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
    tok = secrets.token_urlsafe(16)
    name = "tiktok_%s.%s" % (re.sub(r"[^A-Za-z0-9]", "", message_id)[:24], "png" if "png" in ctype else "jpg")
    SharedLink.objects.create(token=tok, filename=name, content_type=ctype, data=content)
    return "%s/api/f/%s/%s" % (PUBLIC_BASE, tok, name)


def handle_event(event: dict) -> int:
    """Одна подія вебхука TikTok → 1 якщо записали повідомлення, 0 якщо пропустили.
    event = {"event": "im_receive_msg"|"im_send_msg"|"im_mark_read_msg", "user_openid": <business_id>,
             "content": '{"conversation_id","message_id","type","text":{"body"},"image":{"media_id"},
                          "share_post":{"embed_url"},"from","from_user":{"id"},"to","to_user":{"id"},"timestamp"}'}"""
    from .models import Channel, Conversation, Message
    kind = str(event.get("event") or "")
    if kind not in ("im_receive_msg", "im_send_msg"):
        return 0
    content = event.get("content")
    if isinstance(content, str):
        try:
            content = json.loads(content or "{}")
        except Exception:
            return 0
    content = content or {}
    business_id = str(event.get("user_openid") or "")
    ch = (Channel.objects.filter(kind=CHANNEL_KIND, config__tiktok_direct=True, config__business_id=business_id).first()
          if business_id else None) or get_channel()
    if ch is None or not ch.is_active:
        return 0
    biz = str((ch.config or {}).get("business_id") or business_id)
    conv_id = str(content.get("conversation_id") or "")
    msg_id = str(content.get("message_id") or "")
    if not conv_id or not msg_id:
        return 0
    to_id = str((content.get("to_user") or {}).get("id") or "")
    from_id = str((content.get("from_user") or {}).get("id") or "")
    incoming = (to_id == biz) if (to_id or from_id) else (kind == "im_receive_msg")
    client_name = str((content.get("from") if incoming else content.get("to")) or "")
    client_id = from_id if incoming else to_id

    conv, created = Conversation.objects.get_or_create(
        channel=ch, external_chat_id=conv_id,
        defaults={"title": (client_name or "TikTok")[:160]})
    if created and incoming:
        _new_lead(conv, client_name, client_id)
    if conv.contact_id is None and incoming:
        _new_lead(conv, client_name, client_id)
    if Message.objects.filter(conversation=conv, external_id=msg_id).exists():
        return 0  # дубль вебхука або наше ж повідомлення, вже записане при відправці з CRM

    mtype = str(content.get("type") or "text").lower()
    text = ""
    atts = []
    if mtype == "text":
        text = str((content.get("text") or {}).get("body") or "")
    elif mtype == "image":
        media_id = str((content.get("image") or {}).get("media_id") or "")
        url = None
        if incoming and media_id:
            try:
                url = _download_image(ch, conv_id, msg_id, media_id)
            except Exception as exc:
                log.warning("TikTok image download failed: %s", exc)
        if url:
            atts.append({"type": "photo", "url": url, "name": "фото"})
            text = "📷 Фото"
        else:
            text = "📷 Клієнт надіслав фото (відкрийте TikTok, щоб побачити)" if incoming else "📷 Фото"
    elif mtype == "share_post":
        url = str((content.get("share_post") or {}).get("embed_url") or "")
        text = ("🎬 Клієнт поділився відео TikTok: " + url) if url else "🎬 Відео TikTok"
    elif mtype == "sticker":
        text = "🙂 Стікер"
    else:
        text = "[%s] непідтримуваний тип повідомлення TikTok" % mtype

    ts = content.get("timestamp")
    Message.objects.create(
        conversation=conv, direction=("in" if incoming else "out"), text=text[:5000],
        attachments=atts, external_id=msg_id,
        sender_name=("" if incoming else "ai_assistant"))  # echo без нашого Message = Юля/відповідь поза CRM
    conv.unread = (conv.unread or 0) + (1 if incoming else 0)
    conv.last_message_at = _now()
    if incoming and client_name and conv.title in ("", "TikTok"):
        conv.title = client_name[:160]
    conv.save()
    return 1


def handle_webhook(payload) -> int:
    """Тіло вебхука може бути однією подією або списком подій."""
    events = payload if isinstance(payload, list) else [payload]
    n = 0
    for ev in events:
        if isinstance(ev, dict):
            try:
                n += handle_event(ev)
            except Exception:
                log.exception("TikTok webhook event failed")
    return n


# ============================================================================
# 5. ВІДПРАВКА
# ============================================================================
def window_state(conv) -> dict:
    """Чи відкрите вікно відповіді: ≤48 год від останнього вхідного і <10 наших після нього."""
    from .models import Message
    last_in = Message.objects.filter(conversation=conv, direction="in").order_by("-created_at").first()
    if not last_in:
        return {"open": False, "reason": "Клієнт ще не писав — TikTok не дозволяє писати першими"}
    age = _now() - last_in.created_at
    if age > timedelta(hours=WINDOW_HOURS):
        return {"open": False, "reason": "Вікно 48 годин після останнього повідомлення клієнта закрите"}
    n_out = Message.objects.filter(conversation=conv, direction="out", internal=False,
                                   created_at__gt=last_in.created_at).count()
    if n_out >= WINDOW_MAX_OUT:
        return {"open": False, "reason": "Ліміт TikTok: 10 повідомлень поспіль без відповіді клієнта"}
    return {"open": True, "left": WINDOW_MAX_OUT - n_out,
            "closes_at": (last_in.created_at + timedelta(hours=WINDOW_HOURS)).isoformat()}


def send_text(channel, conversation_id: str, text: str) -> str:
    token = valid_token(channel)
    js = _request("POST", "/business/message/send/", token=token, body={
        "business_id": (channel.config or {}).get("business_id", ""),
        "recipient_type": "CONVERSATION", "recipient": conversation_id,
        "message_type": "TEXT", "text": {"body": text},
    })
    return str(((js.get("data") or {}).get("message") or {}).get("message_id") or "")


# ============================================================================
# 6. АДАПТЕР КАНАЛУ (kind="tiktok" без прапорця chatplace → сюди)
# ============================================================================
from .adapters import ADAPTERS, ChannelAdapter  # noqa: E402


class TiktokDirectAdapter(ChannelAdapter):
    """Прямий TikTok Business Messaging. Фото з CRM не відправляє — в Україні API це не дозволяє."""
    kind = "tiktok"

    def send(self, external_chat_id: str, text: str) -> str:
        from .models import Conversation, Message
        if str(external_chat_id).startswith("comment:"):
            # Відповідь на КОМЕНТАР під відео — публічно, на останній коментар клієнта в цій звʼязці
            conv = Conversation.objects.filter(channel=self.channel, external_chat_id=external_chat_id).first()
            last_in = (Message.objects.filter(conversation=conv, direction="in").order_by("-id").first()
                       if conv else None)
            if not last_in or not last_in.external_id:
                raise RuntimeError("TikTok: не знайдено коментар клієнта для відповіді")
            video_id = str(external_chat_id).split(":")[2]
            return send_comment_reply(self.channel, video_id, last_in.external_id, text)
        conv = Conversation.objects.filter(channel=self.channel, external_chat_id=external_chat_id).first()
        if conv is not None:
            st = window_state(conv)
            if not st.get("open"):
                raise RuntimeError("TikTok: " + st.get("reason", "вікно відповіді закрите"))
        return send_text(self.channel, external_chat_id, text)

    def send_media(self, external_chat_id: str, content: bytes, filename: str, kind: str) -> str:
        raise RuntimeError("TikTok не дозволяє відправляти фото/файли з API в Україні — надішліть посилання текстом")


ADAPTERS.setdefault("tiktok", TiktokDirectAdapter)


# ============================================================================
# 7. HTTP-ВʼЮХИ
# ============================================================================
from django.http import HttpResponse, HttpResponseRedirect  # noqa: E402
from rest_framework import status as http_status  # noqa: E402
from rest_framework.permissions import AllowAny  # noqa: E402
from rest_framework.response import Response  # noqa: E402
from rest_framework.views import APIView  # noqa: E402


def _can_manage(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or
                (hasattr(user, "has_perm_code") and user.has_perm_code("roles.manage")))


class TiktokStatusView(APIView):
    """GET /api/inbox/tiktok/status/ — стан прямого підключення для Контакт-центру."""

    def get(self, request):
        ch = get_channel()
        cfg = (ch.config if ch else {}) or {}
        return Response({
            "configured": configured(),
            "connected": bool(ch and ch.is_active and cfg.get("access_token")),
            "channel_id": ch.id if ch else None,
            "username": cfg.get("username", ""),
            "display_name": cfg.get("display_name", ""),
            "business_id": cfg.get("business_id", ""),
            "expires_at": cfg.get("expires_at", ""),
            "refresh_expires_at": cfg.get("refresh_expires_at", ""),
            "webhook_registered": cfg.get("webhook_registered"),
            "webhook_url": WEBHOOK_URL,
            "redirect_url": REDIRECT_URL,
            "can_manage": _can_manage(request.user),
        })


class TiktokConnectView(APIView):
    """POST /api/inbox/tiktok/connect/ → {url}: куди відправити браузер власника для авторизації."""

    def post(self, request):
        if not _can_manage(request.user):
            return Response({"detail": "Немає прав"}, status=http_status.HTTP_403_FORBIDDEN)
        if not configured():
            return Response({"detail": "TikTok App ID / Secret ще не задані в налаштуваннях сервера (.env)"},
                            status=http_status.HTTP_400_BAD_REQUEST)
        return Response({"url": authorize_url(make_state(request.user.id))})


class TiktokDisconnectView(APIView):
    def post(self, request):
        if not _can_manage(request.user):
            return Response({"detail": "Немає прав"}, status=http_status.HTTP_403_FORBIDDEN)
        ch = get_channel()
        if ch:
            ch.is_active = False
            ch.save(update_fields=["is_active"])
        return Response({"ok": True})


class TiktokCallbackView(APIView):
    """GET /api/inbox/tiktok/callback/?code=…&state=… — сюди TikTok повертає власника після дозволу."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        code = request.GET.get("code") or request.GET.get("auth_code") or ""
        state = request.GET.get("state") or ""
        if request.GET.get("error"):
            return HttpResponseRedirect("/contact-center?tiktok=denied")
        try:
            st = check_state(state)
        except signing.BadSignature:
            return HttpResponse("bad state", status=403)
        if not code:
            return HttpResponse("no code", status=400)
        try:
            from django.contrib.auth import get_user_model
            user = get_user_model().objects.filter(pk=st.get("u")).first()
            connect_from_code(code, user=user)
        except Exception as exc:
            log.exception("TikTok connect failed")
            return HttpResponseRedirect("/contact-center?tiktok=error&msg=" + urllib.parse.quote(str(exc)[:160]))
        return HttpResponseRedirect("/contact-center?tiktok=connected")


class TiktokWebhookView(APIView):
    """POST /api/inbox/tiktok/webhook/ — події TikTok. GET — перевірка доступності."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return HttpResponse("ok")

    def post(self, request):
        raw = request.body or b""
        if not verify_signature(raw, request.headers.get("Tiktok-Signature", "")):
            return HttpResponse("bad signature", status=401)
        try:
            payload = json.loads(raw or b"{}")
        except Exception:
            return HttpResponse("bad json", status=400)
        try:
            handle_webhook(payload)
        except Exception:
            log.exception("TikTok webhook failed")
        return HttpResponse("ok")


# ============================================================================
# 8. КОМЕНТАРІ ПІД ВІДЕО → Чати CRM (право comment.list + comment.list.manage)
# ============================================================================
COMMENT_POLL_VIDEOS = 15      # скільки останніх відео перевіряти
COMMENT_PAGE = 30

def send_comment_reply(channel, video_id: str, comment_id: str, text: str) -> str:
    """Публічна відповідь на коментар під нашим відео."""
    token = valid_token(channel)
    js = _request("POST", "/business/comment/reply/create/", token=token, body={
        "business_id": (channel.config or {}).get("business_id", ""),
        "video_id": str(video_id), "comment_id": str(comment_id), "text": text,
    })
    d = js.get("data") or {}
    return str(d.get("comment_id") or d.get("reply_id") or "")


def _ingest_comment(ch, video: dict, c: dict) -> int:
    """Один коментар → чат «клієнт + відео» (як Meta-коменти). Повертає 1, якщо записали."""
    from .models import Conversation, Message
    cid = str(c.get("comment_id") or "")
    if not cid:
        return 0
    ours = bool(c.get("owner"))
    username = str(c.get("username") or "")
    display = str(c.get("display_name") or username or "TikTok")[:160]
    user_key = (username or str(c.get("user_id") or cid))[:60]
    vid = str(video.get("item_id") or "")
    ext_chat = "comment:tiktok:%s:%s" % (vid, user_key.lower())
    conv, created = Conversation.objects.get_or_create(
        channel=ch, external_chat_id=ext_chat,
        defaults={"title": display or "TikTok · коментар"})
    if created:
        if not ours:
            _new_lead(conv, username or display, user_key)
        conv.config = {**(conv.config or {}), "source_card": {
            "type": "comment", "platform": "tiktok", "media_id": vid,
            "permalink": video.get("share_url") or "", "thumbnail": video.get("thumbnail_url") or "",
            "caption": (video.get("caption") or "")[:280], "is_ad": False,
        }}
        conv.save(update_fields=["config"])
    if Message.objects.filter(conversation=conv, external_id=cid).exists():
        return 0
    Message.objects.create(conversation=conv, direction=("out" if ours else "in"),
                           text=str(c.get("text") or "")[:5000], external_id=cid,
                           sender_name=("ai_assistant" if ours else (username or display)))
    # Клієнт написав телефон/пошту → у картку клієнта (як в інших каналах)
    if (not ours) and conv.contact_id:
        try:
            from apps.crm.automation import capture_contacts as _cc
            _cc(conv.contact, text or "")
        except Exception:
            pass
    conv.unread = (conv.unread or 0) + (0 if ours else 1)
    conv.last_message_at = _now()
    conv.save()
    return 1


def poll_comments() -> dict:
    """Нові коментарі останніх відео → Чати. Перший запуск по відео — лише БАЗОВА ЛІНІЯ
    (запамʼятовуємо найсвіжіший час, історію НЕ заливаємо, щоб не засмітити CRM лідами)."""
    from .models import Channel
    ch = get_channel(active_only=True)
    if ch is None:
        return {"detail": "канал не підключено"}
    token = valid_token(ch)
    biz = (ch.config or {}).get("business_id", "")
    js = _request("GET", "/business/video/list/", token=token, params={
        "business_id": biz,
        "fields": json.dumps(["item_id", "caption", "thumbnail_url", "share_url", "comments"]),
        "max_count": COMMENT_POLL_VIDEOS,
    })
    videos = (js.get("data") or {}).get("videos") or []
    state = dict((ch.config or {}).get("tt_comment_state") or {})
    n_new = 0
    baselined = 0
    for v in videos:
        vid = str(v.get("item_id") or "")
        if not vid:
            continue
        first_run = vid not in state
        known_ts = int(state.get(vid) or 0)
        newest_ts = known_ts
        cursor = None
        for _page in range(5):
            params = {"business_id": biz, "video_id": vid, "max_count": COMMENT_PAGE,
                      "sort_field": "create_time", "sort_order": "desc"}
            if cursor:
                params["cursor"] = cursor
            cjs = _request("GET", "/business/comment/list/", token=token, params=params)
            cd = cjs.get("data") or {}
            comments = cd.get("comments") or []
            stop = False
            for c in comments:
                cts = int(c.get("create_time") or 0)
                if cts <= known_ts:
                    stop = True
                    break
                newest_ts = max(newest_ts, cts)
                if not first_run:
                    n_new += _ingest_comment(ch, v, c)
            if stop or not cd.get("has_more") or first_run:
                break
            cursor = cd.get("cursor")
        state[vid] = newest_ts
        if first_run:
            baselined += 1
    Channel.objects.filter(pk=ch.pk).update(config={**ch.config, "tt_comment_state": state})
    return {"new_comments": n_new, "videos_checked": len(videos), "baselined": baselined}
