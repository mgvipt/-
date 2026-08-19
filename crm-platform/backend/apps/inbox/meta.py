"""Незалежна Meta-інтеграція CRM (БЕЗ Бітрикса): Instagram Direct + IG-коменти +
Facebook Messenger + FB-коменти напряму через Graph API.
Вмикається коли в .env задані META_PAGE_TOKEN / META_VERIFY_TOKEN / META_APP_SECRET."""
import os, json, hmac, hashlib, urllib.parse, urllib.request

GRAPH = "https://graph.facebook.com/v21.0"
PAGE_TOKEN = os.environ.get("META_PAGE_TOKEN", "")
VERIFY_TOKEN = os.environ.get("META_VERIFY_TOKEN", "wallcov_crm_verify")
APP_SECRET = os.environ.get("META_APP_SECRET", "")
IG_ID = os.environ.get("META_IG_ID", "")
PAGE_ID = os.environ.get("META_PAGE_ID", "")


def configured():
    return bool(PAGE_TOKEN)


def verify_signature(raw_body: bytes, header_sig: str) -> bool:
    if not APP_SECRET:
        return True  # якщо секрет не заданий — не перевіряємо (dev)
    if not header_sig or not header_sig.startswith("sha256="):
        return False
    mac = hmac.new(APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, header_sig.split("=", 1)[1])


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


def send_message(recipient_id: str, text: str, platform: str = "instagram"):
    """Відповісти клієнту в Direct/Messenger. recipient_id = PSID/IGSID."""
    sender = IG_ID if platform == "instagram" and IG_ID else "me"
    return _graph("POST", f"{sender}/messages", {
        "recipient": json.dumps({"id": recipient_id}),
        "message": json.dumps({"text": text}),
        "messaging_type": "RESPONSE",
    })


def reply_comment(comment_id: str, text: str):
    """Відповісти на коментар IG/FB (публічно)."""
    return _graph("POST", f"{comment_id}/replies" if False else f"{comment_id}/comments", {"message": text})


def _kind(obj):
    return "instagram" if obj == "instagram" else "facebook"


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


def _new_meta_lead(conv, kind, sender_id):
    """Створити контакт + лід для нового вхідного чату Meta (FB/IG). Джерело = канал."""
    from apps.crm.models import Contact, Lead, Funnel
    name = _profile_name(sender_id)
    if not conv.contact_id:
        ct = Contact.objects.create(first_name=(name or kind)[:120], comment=f"З {kind} (Meta)")
        conv.contact = ct
        conv.save(update_fields=["contact"])
    try:
        f = Funnel.objects.filter(name="Лиды").first() or Funnel.objects.order_by("id").first()
        st = f.stages.order_by("order").first() if f else None
        if f and st:
            src = "instagram" if kind == "instagram" else "facebook"
            Lead.objects.create(title=(name or str(sender_id))[:255],
                                contact=conv.contact, funnel=f, stage=st, source=src, is_seen=False)
    except Exception:
        pass


def handle_webhook(payload: dict):
    """Розібрати вебхук Meta → створити/оновити Conversation+Message+Contact у CRM.
    Підтримує: IG/FB Direct (messaging) + IG/FB коменти (changes)."""
    from .models import Channel, Conversation, Message
    from apps.crm.models import Contact
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
            mid = msg.get("mid", "")
            is_echo = msg.get("is_echo")  # надіслане нами
            ext_chat = sender if not is_echo else recipient
            conv, created = Conversation.objects.get_or_create(channel=ch, external_chat_id=str(ext_chat), defaults={"title": kind})
            if created and not is_echo:
                _new_meta_lead(conv, kind, sender)
            if Message.objects.filter(conversation=conv, external_id=mid).exists():
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
            Message.objects.create(conversation=conv, direction=("out" if is_echo else "in"),
                                   text=(msg.get("text") or ("📷 Фото" if atts else ""))[:5000],
                                   attachments=atts, external_id=mid)
            conv.unread = (conv.unread or 0) + (0 if is_echo else 1)
            from django.utils import timezone
            conv.last_message_at = timezone.now()
            conv.save()
            n_msg += 1
        # 2) Коментарі (changes → field comments/feed)
        for chg in changes:
            field = chg.get("field")
            val = chg.get("value") or {}
            if field not in ("comments", "feed"):
                continue
            if val.get("item") and val.get("item") != "comment":
                continue
            cid = val.get("comment_id") or val.get("id")
            frm = val.get("from") or {}
            text = val.get("text") or val.get("message") or ""
            if not cid or not text:
                continue
            ext_chat = f"comment:{val.get('post_id') or val.get('media',{}).get('id') or cid}"
            conv, _ = Conversation.objects.get_or_create(channel=ch, external_chat_id=str(ext_chat), defaults={"title": f"{kind} коментарі"})
            if Message.objects.filter(conversation=conv, external_id=str(cid)).exists():
                continue
            Message.objects.create(conversation=conv, direction="in", text=text[:5000], external_id=str(cid),
                                   sender_name=(frm.get("name") or frm.get("username") or "")[:160])
            conv.unread = (conv.unread or 0) + 1
            from django.utils import timezone
            conv.last_message_at = timezone.now()
            conv.save()
            n_msg += 1
    return n_msg
