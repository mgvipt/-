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
        # 1) Direct / Messenger
        for ev in entry.get("messaging", []):
            sender = (ev.get("sender") or {}).get("id")
            recipient = (ev.get("recipient") or {}).get("id")
            msg = ev.get("message") or {}
            if not sender or not msg:
                continue
            mid = msg.get("mid", "")
            is_echo = msg.get("is_echo")  # надіслане нами
            ext_chat = sender if not is_echo else recipient
            conv, created = Conversation.objects.get_or_create(channel=ch, external_chat_id=str(ext_chat), defaults={"title": kind})
            if Message.objects.filter(conversation=conv, external_id=mid).exists():
                continue
            Message.objects.create(conversation=conv, direction=("out" if is_echo else "in"),
                                   text=(msg.get("text") or "")[:5000], external_id=mid)
            conv.unread = (conv.unread or 0) + (0 if is_echo else 1)
            from django.utils import timezone
            conv.last_message_at = timezone.now()
            conv.save()
            n_msg += 1
        # 2) Коментарі (changes → field comments/feed)
        for chg in entry.get("changes", []):
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
