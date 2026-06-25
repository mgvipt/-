"""Незалежна інтеграція з ChatPlace через MCP-протокол (https://mcp.chatplace.io/mcp).
БЕЗ Бітрикса. Тягне живі IG-чати (Direct) у inbox CRM і вміє відповідати.
Ключ у .env: CHATPLACE_API_KEY (cpk_...)."""
import os, json, datetime, urllib.request

MCP_URL = os.environ.get("CHATPLACE_MCP_URL", "https://mcp.chatplace.io/mcp")
API_KEY = (os.environ.get("CHATPLACE_API_KEY", "") or "").strip()

# сторони повідомлення, які вважаємо ВИХІДНИМИ (ми/AI/оператор). Решта = вхідне (клієнт).
_STAFF_SIDES = {"ai_assistant", "operator", "manager", "bot", "system", "admin", "out"}
# службові маркери ChatPlace (не реальні повідомлення)
_SYSTEM_MARKERS = {"ActiveStatusLabel", "InactiveStatusLabel", "ReadStatusLabel"}


def configured():
    return bool(API_KEY)


def _mcp(name, arguments=None):
    """Викликати інструмент ChatPlace MCP (JSON-RPC tools/call)."""
    if not API_KEY:
        raise RuntimeError("CHATPLACE_API_KEY не налаштовано")
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": name, "arguments": arguments or {}}}
    req = urllib.request.Request(MCP_URL, data=json.dumps(payload).encode(), headers={
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": "wallcov-crm/1.0",
    })
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
        resp = json.load(r)
    if resp.get("error"):
        raise RuntimeError(f"ChatPlace MCP error: {resp['error']}")
    content = (resp.get("result") or {}).get("content") or []
    text = content[0].get("text") if content else "null"
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return text


def send(chat_id, text):
    """Відповісти клієнту в IG Direct через ChatPlace (чат має бути open/оператор)."""
    return _mcp("chats_send_message", {"chatId": chat_id, "text": text})


def sync_one_chat(conv, per_chat=40):
    """Підтягнути свіжі повідомлення ОДНОГО чату (live-оновлення відкритого діалогу)."""
    from .models import Message
    msgs = _mcp("chats_messages", {"chatId": conv.external_chat_id, "limit": per_chat})
    if isinstance(msgs, dict):
        msgs = msgs.get("items") or msgs.get("messages") or []
    new = 0
    for m in reversed(msgs or []):
        ext = str(m.get("id"))
        body = m.get("message") or m.get("text") or ""
        if not body or body in _SYSTEM_MARKERS or "StatusLabel" in str(body):
            continue
        if Message.objects.filter(conversation=conv, external_id=ext).exists():
            continue
        side = (m.get("side") or "").lower()
        direction = "out" if side in _STAFF_SIDES else "in"
        Message.objects.create(conversation=conv, direction=direction, text=str(body)[:5000],
                               external_id=ext, sender_name=("" if direction == "in" else side))
        new += 1
    return new


def sync_chats(max_chats=40, per_chat=40):
    """Підтягнути останні чати + повідомлення з ChatPlace у inbox CRM."""
    from .models import Channel, Conversation, Message
    from apps.crm.models import Contact, Lead, Funnel
    ch, _ = Channel.objects.get_or_create(name="ChatPlace · Instagram",
                                          defaults={"kind": "instagram", "config": {"chatplace": True}})
    if not (ch.config or {}).get("chatplace"):
        ch.config = {**(ch.config or {}), "chatplace": True}; ch.save(update_fields=["config"])
    data = _mcp("chats_list", {"limit": max_chats})
    items = data.get("items", []) if isinstance(data, dict) else (data or [])
    new_conv = new_msg = 0
    errors = []
    for it in items:
        cid = it.get("id")
        name = (it.get("clientName") or "Instagram").strip()
        if not cid:
            continue
        conv = (Conversation.objects.filter(channel=ch, external_chat_id=str(cid), status="open")
                .order_by("-created_at").first())
        created = conv is None
        if created:
            conv = Conversation.objects.create(channel=ch, external_chat_id=str(cid), title=name[:160])
        if created:
            new_conv += 1
            if name and not name.startswith("@"):
                parts = name.split(" ", 1)
                conv.contact = (Contact.objects.filter(first_name__iexact=parts[0]).first()
                                or Contact.objects.create(first_name=parts[0][:120],
                                                          last_name=(parts[1] if len(parts) > 1 else "")[:120],
                                                          comment="З ChatPlace IG"))
            # посилання на IG-акаунт (username з chats_get)
            try:
                if conv.contact and not conv.contact.social_link:
                    g = _mcp("chats_get", {"chatId": cid})
                    un = (g or {}).get("username") if isinstance(g, dict) else None
                    if un:
                        conv.contact.social_link = f"https://instagram.com/{un}"
                        conv.contact.save(update_fields=["social_link"])
            except Exception:
                pass
            # авто-лід у воронці "Лиды" на кожен новий вхідний IG-чат
            try:
                f = Funnel.objects.filter(name="Лиды").first() or Funnel.objects.order_by("id").first()
                st = f.stages.order_by("order").first() if f else None
                if f and st:
                    Lead.objects.create(title=(name or "Instagram")[:255], contact=conv.contact,
                                        funnel=f, stage=st, source="instagram", is_seen=False)
            except Exception:
                pass
        try:
            msgs = _mcp("chats_messages", {"chatId": cid, "limit": per_chat})
            if isinstance(msgs, dict):
                msgs = msgs.get("items") or msgs.get("messages") or []
            for m in reversed(msgs or []):
                ext = str(m.get("id"))
                body = m.get("message") or m.get("text") or ""
                if not body or body in _SYSTEM_MARKERS or "StatusLabel" in str(body):
                    continue
                if Message.objects.filter(conversation=conv, external_id=ext).exists():
                    continue
                side = (m.get("side") or "").lower()
                direction = "out" if side in _STAFF_SIDES else "in"
                Message.objects.create(conversation=conv, direction=direction, text=str(body)[:5000],
                                       external_id=ext, sender_name=("" if direction == "in" else side))
                new_msg += 1
        except Exception as e:
            errors.append(str(cid))
        ts = it.get("lastMessageAt")
        if ts:
            try:
                conv.last_message_at = datetime.datetime.fromtimestamp(int(ts), tz=datetime.timezone.utc)
            except (ValueError, OSError):
                pass
        conv.title = name[:160]
        conv.save()
    return {"chats": len(items), "new_conversations": new_conv, "new_messages": new_msg, "errors": len(errors)}
