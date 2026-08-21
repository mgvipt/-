"""Незалежна Meta-інтеграція CRM (БЕЗ Бітрикса): Instagram Direct + IG-коменти +
Facebook Messenger + FB-коменти напряму через Graph API.
Вмикається коли в .env задані META_PAGE_TOKEN / META_VERIFY_TOKEN / META_APP_SECRET."""
import os, json, hmac, hashlib, urllib.parse, urllib.request, re

GRAPH = "https://graph.facebook.com/v21.0"
# Instagram-вхід (IG-личка) шле/приймає через ОКРЕМИЙ домен + свій токен
IG_GRAPH = "https://graph.instagram.com/v21.0"
IG_TOKEN = os.environ.get("META_IG_TOKEN", "")
PAGE_TOKEN = os.environ.get("META_PAGE_TOKEN", "")
VERIFY_TOKEN = os.environ.get("META_VERIFY_TOKEN", "wallcov_crm_verify")
APP_SECRET = os.environ.get("META_APP_SECRET", "")
# Instagram-вхід (IG-личка) йде через ОКРЕМИЙ Instagram-застосунок зі СВОЇМ секретом —
# його вебхуки підписані іншим ключем, тому перевіряємо підпис проти ОБОХ секретів.
IG_APP_SECRET = os.environ.get("META_IG_APP_SECRET", "")
IG_ID = os.environ.get("META_IG_ID", "")
PAGE_ID = os.environ.get("META_PAGE_ID", "")
# Наші власні ідентифікатори — щоб відрізнити відповідь ШІ Юлі / менеджера (наш акаунт)
# від повідомлення клієнта у коментарях та Direct.
_OUR_IDS = {x for x in (IG_ID, PAGE_ID) if x}


def _is_us(author_id):
    """author_id належить нашому бізнес-акаунту (сторінка/IG) → це наша відповідь, не клієнт."""
    return bool(author_id) and str(author_id) in _OUR_IDS


def configured():
    return bool(PAGE_TOKEN)


def verify_signature(raw_body: bytes, header_sig: str) -> bool:
    secrets = [s for s in (APP_SECRET, IG_APP_SECRET) if s]
    if not secrets:
        return True  # якщо жоден секрет не заданий — не перевіряємо (dev)
    if not header_sig or not header_sig.startswith("sha256="):
        return False
    got = header_sig.split("=", 1)[1]
    for sec in secrets:  # підпис від основного АБО Instagram-застосунку
        mac = hmac.new(sec.encode(), raw_body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(mac, got):
            return True
    return False


def _graph(method, path, params=None):
    url = f"{GRAPH}/{path}"
    body = None
    if method == "POST":
        body = urllib.parse.urlencode({**(params or {}), "access_token": PAGE_TOKEN}).encode()
        req = urllib.request.Request(url, data=body)
    else:
        url += "?" + urllib.parse.urlencode({**(params or {}), "access_token": PAGE_TOKEN})
        req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
        return json.load(r)


def _ig_post(path, params):
    """POST через graph.instagram.com з IG-токеном (Instagram-вхід)."""
    body = urllib.parse.urlencode({**params, "access_token": IG_TOKEN}).encode()
    req = urllib.request.Request(f"{IG_GRAPH}/{path}", data=body)
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
        return json.load(r)


def send_message(recipient_id: str, text: str, platform: str = "instagram"):
    """Відповісти клієнту в Direct/Messenger. recipient_id = PSID/IGSID.
    Instagram-личка йде через graph.instagram.com + IG-токен; Facebook — через Page."""
    if platform == "instagram" and IG_TOKEN:
        return _ig_post("me/messages", {
            "recipient": json.dumps({"id": recipient_id}),
            "message": json.dumps({"text": text}),
        })
    return _graph("POST", "me/messages", {
        "recipient": json.dumps({"id": recipient_id}),
        "message": json.dumps({"text": text}),
        "messaging_type": "RESPONSE",
    })


def send_attachment(recipient_id: str, url: str, atype: str = "image", platform: str = "instagram"):
    """Надіслати клієнту медіа (фото/відео/аудіо/файл) НАТИВНО в Direct/Messenger по URL.
    atype: image|video|audio|file. Клієнт бачить картинку/відео у переписці, а не текстове посилання."""
    mtype = atype if atype in ("image", "video", "audio", "file") else "file"
    att_msg = json.dumps({"attachment": {"type": mtype, "payload": {"url": url, "is_reusable": False}}})
    if platform == "instagram" and IG_TOKEN:
        return _ig_post("me/messages", {
            "recipient": json.dumps({"id": recipient_id}),
            "message": att_msg,
        })
    return _graph("POST", "me/messages", {
        "recipient": json.dumps({"id": recipient_id}),
        "message": att_msg,
        "messaging_type": "RESPONSE",
    })


def reply_comment(comment_id: str, text: str):
    """Відповісти на коментар IG/FB (публічно)."""
    return _graph("POST", f"{comment_id}/comments", {"message": text})


def _kind(obj):
    return "instagram" if obj == "instagram" else "facebook"


def _media_card(media_id, kind):
    """Картка джерела: підтягнути дані публікації/ролика/реклами, на яку відповів клієнт.
    Повертає dict {media_type, permalink, thumbnail, caption} або порожній dict при помилці/без прав."""
    if not media_id or not PAGE_TOKEN:
        return {}
    try:
        if kind == "instagram":
            d = _graph("GET", str(media_id),
                       {"fields": "media_type,media_url,thumbnail_url,permalink,caption"})
            return {
                "media_type": (d.get("media_type") or "").upper(),  # IMAGE/VIDEO/CAROUSEL_ALBUM/REEL
                "permalink": d.get("permalink") or "",
                "thumbnail": d.get("thumbnail_url") or d.get("media_url") or "",
                "caption": (d.get("caption") or "")[:280],
            }
        # facebook post
        d = _graph("GET", str(media_id),
                   {"fields": "permalink_url,message,full_picture,attachments{media_type}"})
        att = (((d.get("attachments") or {}).get("data") or [{}])[0]) if d.get("attachments") else {}
        return {
            "media_type": (att.get("media_type") or "").upper(),
            "permalink": d.get("permalink_url") or "",
            "thumbnail": d.get("full_picture") or "",
            "caption": (d.get("message") or "")[:280],
        }
    except Exception:
        return {}


def _profile_name(sender_id):
    """Return a sender name without making it a prerequisite for ingestion."""
    if not PAGE_TOKEN:
        return ""
    try:
        profile = _graph("GET", str(sender_id), {"fields": "name"})
        name = str((profile or {}).get("name") or "").strip()
        if name:
            return name
    except Exception:
        pass
    # Meta may deny the direct PSID profile edge for a normal Page user while
    # still exposing that participant through the Page conversation itself.
    if PAGE_ID:
        try:
            result = _graph("GET", f"{PAGE_ID}/conversations", {
                "user_id": str(sender_id), "fields": "participants", "limit": 1,
            })
            for conversation in (result or {}).get("data", []):
                for participant in (conversation.get("participants") or {}).get("data", []):
                    if str(participant.get("id")) == str(sender_id):
                        return str(participant.get("name") or "").strip()
        except Exception:
            pass
    return ""


def _ig_get(path, params=None):
    """GET через graph.instagram.com з IG-токеном (Instagram-вхід)."""
    url = f"{IG_GRAPH}/{path}?" + urllib.parse.urlencode({**(params or {}), "access_token": IG_TOKEN})
    with urllib.request.urlopen(urllib.request.Request(url), timeout=15) as r:  # noqa: S310
        return json.load(r)


def _meta_profile(sender_id, kind):
    """Повертає (повне_ім'я, нік) автора Meta. Instagram → graph.instagram.com (name+username);
    Facebook → Page (тільки name)."""
    if kind == "instagram" and IG_TOKEN:
        try:
            d = _ig_get(str(sender_id), {"fields": "name,username"})
            return (str((d or {}).get("name") or "").strip(), str((d or {}).get("username") or "").strip())
        except Exception:
            pass
    return (_profile_name(sender_id), "")


_PLACEHOLDER_NAMES = {"", "instagram", "facebook", "client", "customer", "клиент", "клієнт"}


def _clean_username(value):
    """Повернути справжній username, але не платформний числовий ID/плейсхолдер."""
    username = str(value or "").strip().lstrip("@").strip()
    if not username or username.isdigit() or username.lower() in _PLACEHOLDER_NAMES:
        return ""
    return username[:150]


def _resolve_meta_identity(sender_id, kind, name="", username=""):
    """Доповнити передані ім'я/username даними профілю Meta, не замінюючи кращі значення."""
    clean_name = str(name or "").strip()
    clean_username = _clean_username(username)
    if sender_id and (not clean_name or not clean_username):
        fetched_name, fetched_username = _meta_profile(sender_id, kind)
        clean_name = clean_name or str(fetched_name or "").strip()
        clean_username = clean_username or _clean_username(fetched_username)
    return clean_name[:240], clean_username


def _contact_identity_changes(contact, kind, name="", username=""):
    """Порахувати лише безпечні дозаповнення контакту. Реальні дані менеджера не перезаписуємо."""
    name = str(name or "").strip()
    username = _clean_username(username)
    current_name = " ".join(x for x in (
        str(contact.first_name or "").strip(), str(contact.last_name or "").strip()
    ) if x)
    current_nick = _clean_username(getattr(contact, "nickname", ""))
    placeholder_name = (not current_name or current_name.lower() in _PLACEHOLDER_NAMES
                        or current_name.isdigit())
    changes = {}
    if placeholder_name and (name or username):
        parts = (name or username).split(None, 1)
        changes["first_name"] = (parts[0] if parts else username)[:120]
        changes["last_name"] = (parts[1] if len(parts) > 1 else "")[:120]
    if username and not current_nick:
        changes["nickname"] = username
    channels = list(getattr(contact, "channels", None) or [])
    if kind and kind not in channels:
        changes["channels"] = channels + [kind]
    if kind == "instagram" and username:
        link = f"https://instagram.com/{username}"
        if not str(getattr(contact, "social_link", "") or "").strip():
            changes["social_link"] = link
        messengers = list(getattr(contact, "messengers", None) or [])
        if link not in messengers:
            changes["messengers"] = messengers + [link]
    return changes


def _enrich_contact(contact, kind, sender_id, name="", username=""):
    """Дозаповнити контакт з Meta. Повертає список реально змінених полів."""
    name, username = _resolve_meta_identity(sender_id, kind, name, username)
    changes = _contact_identity_changes(contact, kind, name, username)
    if changes:
        for field, value in changes.items():
            setattr(contact, field, value)
        contact.save(update_fields=list(changes))
    return list(changes)


def _get_or_make_contact(kind, sender_id, name="", username=""):
    """Знайти/створити контакт для автора Meta. Тягне ім'я+нік (IG через graph.instagram.com).
    Заголовок чату = «Ім'я Прізвище (@нік)»."""
    from apps.crm.models import Contact
    name, username = _resolve_meta_identity(sender_id, kind, name, username)
    parts = (name or "").split(None, 1)
    fn = ((parts[0] if parts else "") or username or kind)[:120]
    ln = (parts[1] if len(parts) > 1 else "")[:120]
    link = f"https://instagram.com/{username}" if kind == "instagram" and username else ""
    return Contact.objects.create(
        first_name=fn, last_name=ln, nickname=username,
        channels=[kind] if kind else [], social_link=link,
        messengers=([link] if link else []), comment=f"З {kind} (Meta)",
    )


def _new_meta_lead(conv, kind, sender_id, name="", username=""):
    """Створити контакт + лід для нового вхідного чату Meta (FB/IG). Джерело = канал."""
    from apps.crm.models import Lead, Funnel
    name, username = _resolve_meta_identity(sender_id, kind, name, username)
    if not conv.contact_id:
        conv.contact = _get_or_make_contact(kind, sender_id, name, username)
        conv.save(update_fields=["contact"])
    else:
        _enrich_contact(conv.contact, kind, sender_id, name, username)
    try:
        f = Funnel.objects.filter(name="Лиды").first() or Funnel.objects.order_by("id").first()
        st = f.stages.order_by("order").first() if f else None
        if f and st:
            src = "instagram" if kind == "instagram" else "facebook"
            Lead.objects.create(title=(name or str(sender_id))[:255],
                                contact=conv.contact, funnel=f, stage=st, source=src, is_seen=False)
    except Exception:
        pass


def _story_ref(msg):
    """Витягнути посилання на історію з Direct-повідомлення (відповідь на історію / згадка в історії).
    Повертає dict для attachments або None."""
    reply_to = msg.get("reply_to") or {}
    story = reply_to.get("story") or {}
    if story.get("url") or story.get("id"):
        return {"type": "story_ref", "kind": "reply", "url": story.get("url", ""),
                "story_id": story.get("id", ""), "name": "Відповідь на історію"}
    for a in (msg.get("attachments") or []):
        if ((a or {}).get("type") or "").lower() == "story_mention":
            url = (((a or {}).get("payload") or {}).get("url") or "")
            return {"type": "story_ref", "kind": "mention", "url": url, "name": "Згадка в історії"}
    return None


def _relink_manager_echo(conv, mid, text, event_timestamp=None):
    """Прив'язати Meta echo до щойно надісланого менеджером повідомлення.

    ChatPlace і Meta використовують різні ID одного відправлення. Об'єднуємо лише
    рівно один кандидат у тому самому діалозі, з тим самим текстом і в межах 10 с
    від platform timestamp. Повторні однакові повідомлення не вгадуємо.
    """
    from .models import Message
    from django.utils import timezone
    from datetime import datetime, timedelta, timezone as dt_timezone

    body = str(text or "")
    if not mid or not body:
        return False
    center = timezone.now()
    try:
        if event_timestamp:
            center = datetime.fromtimestamp(float(event_timestamp) / 1000.0, tz=dt_timezone.utc)
    except (TypeError, ValueError, OSError):
        pass
    candidates = list(
        Message.objects.filter(
            conversation=conv, direction="out", internal=False,
            sender__isnull=False, text=body,
            created_at__gte=center - timedelta(seconds=10),
            created_at__lte=center + timedelta(seconds=10),
        ).order_by("-id")[:2]
    )
    if len(candidates) != 1:
        return False
    candidates[0].external_id = str(mid)[:128]
    candidates[0].save(update_fields=["external_id"])
    return True


def handle_webhook(payload: dict):
    """Розібрати вебхук Meta → створити/оновити Conversation+Message+Contact у CRM.
    Підтримує: IG/FB Direct (messaging, story reply/mention) + IG/FB коменти (changes).
    Коментарі групуються по «клієнт + публікація» (окремий чат на кожну зв'язку)."""
    from .models import Channel, Conversation, Message
    obj = payload.get("object")
    n_msg = 0
    for entry in payload.get("entry", []):
        kind = _kind(obj)
        ch, _ = Channel.objects.get_or_create(name=f"Meta · {kind}", defaults={"kind": kind, "config": {"meta": True, "platform": obj}})
        # 1) Direct / Messenger. Conversation Routing може передавати події
        # застосунку, який не володіє потоком, у верхньорівневому standby.
        # Новий Page Webhooks UI також загортає messages у changes[].value.
        changes = list(entry.get("changes") or [])
        direct_events = (list(entry.get("messaging") or [])
                         + list(entry.get("standby") or [])
                         + [(chg.get("value") or {}) for chg in changes if chg.get("field") == "messages"])
        for ev in direct_events:
            sender = (ev.get("sender") or {}).get("id")
            recipient = (ev.get("recipient") or {}).get("id")
            msg = ev.get("message") or {}
            if not sender or not msg:
                continue
            mid = (msg.get("mid", "") or "")[:128]  # Instagram-вхід дає ДОВГИЙ mid — поле max 128
            is_echo = msg.get("is_echo")  # надіслане нами (менеджер АБО ШІ Юля через ChatPlace)
            ext_chat = str(sender if not is_echo else recipient)[:128]
            conv, created = Conversation.objects.get_or_create(channel=ch, external_chat_id=str(ext_chat), defaults={"title": kind})
            if not is_echo:
                if created or not conv.contact_id:
                    _new_meta_lead(conv, kind, sender)
                else:
                    # Старий чат міг створитися до появи профільного lookup. Нове повідомлення
                    # повинно дозаповнити ім'я/прізвище/username, не створюючи нового контакту.
                    _enrich_contact(conv.contact, kind, sender)
            if Message.objects.filter(conversation=conv, external_id=mid).exists():
                continue
            if is_echo and _relink_manager_echo(
                    conv, mid, msg.get("text") or "", ev.get("timestamp")):
                continue
            # вкладення (фото/відео/аудіо/файл) з Instagram/Messenger-вебхука
            atts = []
            for a in (msg.get("attachments") or []):
                url = (((a or {}).get("payload") or {}).get("url") or "").strip()
                if not url:
                    continue
                atyp = ((a or {}).get("type") or "").lower()
                attachment_kind = "photo" if atyp in ("image", "photo") else ("video" if atyp == "video" else ("voice" if atyp in ("audio", "voice") else "file"))
                atts.append({"type": attachment_kind, "url": url,
                             "name": ("фото" if attachment_kind == "photo" else attachment_kind)})
            # відповідь на історію / згадка в історії — картка історії в повідомленні
            sref = _story_ref(msg)
            if sref:
                atts.append(sref)
            # echo = надіслане з нашого акаунту. Якщо менеджер відповів через CRM — те саме mid
            # вже записане з sender=менеджер і дедуплікується вище. Значить echo, що дійшло сюди,
            # надіслала ШІ Юля через ChatPlace → позначаємо «ai_assistant» (щоб менеджер бачив ХТО відповів).
            Message.objects.create(conversation=conv, direction=("out" if is_echo else "in"),
                                   text=(msg.get("text") or ("📷 Фото" if atts else ""))[:5000],
                                   attachments=atts, external_id=mid,
                                   sender_name=("ai_assistant" if is_echo else ""))
            conv.unread = (conv.unread or 0) + (0 if is_echo else 1)
            from django.utils import timezone
            conv.last_message_at = timezone.now()
            conv.save()
            n_msg += 1
        # 2) Коментарі (changes → field comments/feed): чат = «клієнт + публікація»
        for chg in changes:
            field = chg.get("field")
            val = chg.get("value") or {}
            if field not in ("comments", "feed"):
                continue
            if val.get("item") and val.get("item") != "comment":
                continue
            cid = val.get("comment_id") or val.get("id")
            frm = val.get("from") or {}
            author_id = str(frm.get("id") or "")
            author_username = (frm.get("username") or "").strip()
            author_name = (frm.get("name") or frm.get("username") or "")[:160]
            text = val.get("text") or val.get("message") or ""
            if not cid or not text:
                continue
            post_id = str(val.get("post_id") or (val.get("media") or {}).get("id") or cid)
            parent_id = str((val.get("parent") or {}).get("id") or val.get("parent_id") or "")
            is_ad = bool(val.get("is_ad") or (val.get("media") or {}).get("ad_id") or val.get("ad_id"))

            # ХТО написав: наш акаунт (відповідь ШІ Юлі) чи клієнт?
            ours = _is_us(author_id)
            target = None            # знайдений чат (для нашої відповіді через parent)
            if ours:
                # відповідь Юлі — клієнт це @нік на початку тексту («@koa2108 ...»)
                mm = re.match(r"\s*@([A-Za-z0-9._]+)", text)
                client_key = (mm.group(1) if mm else "").lower()
                if not client_key and parent_id:
                    pm = Message.objects.filter(external_id=parent_id).first()
                    if pm:
                        target = pm.conversation
                direction = "out"
                sname = "ai_assistant"      # серіалізатор покаже «Юля (AI)»
                client_name = client_key or author_name
            else:
                # коментар клієнта
                client_key = (author_username or author_id).lower()
                direction = "in"
                sname = author_username or author_name  # у чаті видно НІК КЛІЄНТА, не наш канал
                client_name = author_username or author_name

            # чат = «клієнт + публікація». Шукаємо існуючий: (1) по username-ключу; (2) по ніку
            # контакту під цим постом — легасі-чати створювались по author_id, щоб клієнт не роздвоювався.
            created = False
            if target is None:
                if not client_key:
                    client_key = (author_id or cid).lower()
                ext_chat = f"comment:{kind}:{post_id}:{client_key}"[:128]
                target = Conversation.objects.filter(channel=ch, external_chat_id=str(ext_chat)).first()
                if target is None:
                    target = (Conversation.objects.filter(channel=ch, external_chat_id__startswith=f"comment:{kind}:{post_id}:")
                              .filter(contact__first_name__iexact=client_key)
                              .exclude(external_chat_id__endswith=(IG_ID or "\x00"))
                              .exclude(external_chat_id__endswith=(PAGE_ID or "\x00")).first())
                if target is None:
                    target, created = Conversation.objects.get_or_create(
                        channel=ch, external_chat_id=str(ext_chat),
                        defaults={"title": f"{kind} · коментар"})
            conv = target

            if created or (not ours and not conv.contact_id):
                # контакт = КЛІЄНТ (нік лида), НЕ наш акаунт
                _new_meta_lead(conv, kind, author_id or client_key, client_name,
                               username=author_username)
            elif not ours:
                _enrich_contact(conv.contact, kind, author_id, author_name,
                                username=author_username)
            if created:
                card = _media_card((val.get("media") or {}).get("id") or val.get("post_id"), kind)
                conv.config = {**(conv.config or {}), "source_card": {
                    "type": "comment",
                    "platform": kind,
                    "media_id": post_id,
                    "media_type": card.get("media_type", "") or ("AD" if is_ad else ""),
                    "permalink": card.get("permalink", ""),
                    "thumbnail": card.get("thumbnail", ""),
                    "caption": card.get("caption", ""),
                    "is_ad": is_ad,
                    "parent_id": parent_id,
                    "ad_id": str(val.get("ad_id") or (val.get("media") or {}).get("ad_id") or ""),
                }}
                conv.save(update_fields=["config"])
            if Message.objects.filter(conversation=conv, external_id=str(cid)[:128]).exists():
                continue
            Message.objects.create(conversation=conv, direction=direction, text=text[:5000],
                                   external_id=str(cid)[:128], sender_name=sname)
            conv.unread = (conv.unread or 0) + (0 if ours else 1)  # наша відповідь не додає «непрочитане»
            from django.utils import timezone
            conv.last_message_at = timezone.now()
            conv.save()
            n_msg += 1
    return n_msg
