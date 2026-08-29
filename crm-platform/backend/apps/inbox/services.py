from django.utils import timezone
from apps.crm.models import Contact
from .adapters import IncomingMessage, get_adapter
from .models import Channel, Conversation, Message


def _phone_variants(raw: str) -> set[str]:
    """Поширені записи одного UA-номера: 097…, 38097…, +38097…"""
    import re
    value = str(raw or "").strip()
    digits = re.sub(r"\D", "", value)
    variants = {value, digits}
    if digits:
        variants.add("+" + digits)
    local = intl = ""
    if len(digits) == 10 and digits.startswith("0"):
        local = digits                 # 0XXXXXXXXX
        intl = "38" + digits           # -> 380XXXXXXXXX
    elif len(digits) == 12 and digits.startswith("380"):
        intl = digits                  # 380XXXXXXXXX
        local = "0" + digits[3:]       # -> 0XXXXXXXXX (виправлено: без подвійного 0)
    elif len(digits) == 11 and digits.startswith("80"):
        intl = "3" + digits            # 80XXXXXXXXX -> 380XXXXXXXXX
        local = "0" + digits[2:]
    if local:
        variants.update({local, "+" + local})
    if intl:
        variants.update({intl, "+" + intl})
    return {item for item in variants if item}


def _find_contact(inc: IncomingMessage) -> Contact | None:
    """Знайти єдину картку клієнта за основним або додатковим месенджером/телефоном."""
    from django.db.models import Q
    link = str(inc.social_link or "").strip()
    phone = str(getattr(inc, "phone", "") or "").strip()
    if link:
        contact = Contact.objects.filter(
            Q(social_link__iexact=link) | Q(messengers__contains=[link])
        ).order_by("id").first()
        if contact:
            return contact
    if phone:
        return Contact.objects.filter(phone__in=_phone_variants(phone)).order_by("id").first()
    return None


def _attach_contact_channel(contact: Contact, channel: Channel, inc: IncomingMessage):
    """Дописати новий канал у картку контакту, не перетираючи Instagram/інші зв'язки."""
    update_fields = []
    channel_name = {"echat": "viber", "echat_telegram": "telegram", "echat_whatsapp": "whatsapp"}.get(channel.kind, channel.kind)
    channels = list(contact.channels or [])
    if channel_name and channel_name not in channels:
        channels.append(channel_name)
        contact.channels = channels
        update_fields.append("channels")
    link = str(inc.social_link or "").strip()
    messengers = list(contact.messengers or [])
    if link and link not in messengers:
        messengers.append(link)
        contact.messengers = messengers
        update_fields.append("messengers")
    if link and not contact.social_link:
        contact.social_link = link
        update_fields.append("social_link")
    phone = str(getattr(inc, "phone", "") or "").strip()
    if phone and not contact.phone:
        contact.phone = phone
        update_fields.append("phone")
    if update_fields:
        contact.save(update_fields=update_fields)


def ingest(channel: Channel, inc: IncomingMessage) -> Message:
    """Принять входящее сообщение: создать/найти диалог и контакт, записать сообщение."""
    # Беремо лише ВІДКРИТИЙ діалог. Якщо менеджер завершив попередній — новий лист
    # від клієнта створює НОВИЙ діалог (і новий лід нижче).
    conv = (Conversation.objects.filter(channel=channel, external_chat_id=inc.external_chat_id, status="open")
            .order_by("-created_at").first())
    contact = conv.contact if conv else _find_contact(inc)
    # Перший вихідний E-chat-діалог створюється за телефоном, але webhook повертає
    # стабільний sender.id. Якщо контакт той самий — це той самий чат, а не новий лід.
    if conv is None and contact is not None:
        conv = (Conversation.objects.filter(channel=channel, contact=contact, status="open")
                .order_by("-last_message_at", "-created_at").first())
        if conv and conv.external_chat_id != inc.external_chat_id:
            conv.external_chat_id = inc.external_chat_id
            conv.save(update_fields=["external_chat_id"])
    created = conv is None
    if created:
        conv = Conversation.objects.create(channel=channel, external_chat_id=inc.external_chat_id,
                                           title=inc.sender_name or "")
    contact_created = False
    if contact is None:
        contact = _find_contact(inc)
    if contact is None:
        _link = str(inc.social_link or "").strip()
        _phone = str(getattr(inc, "phone", "") or "").strip()
        contact = Contact.objects.create(first_name=inc.sender_name, channels=[], social_link=_link, phone=_phone)
        contact_created = True
    if conv.contact_id != contact.id:
        conv.contact = contact
        conv.save(update_fields=["contact"])
    _attach_contact_channel(contact, channel, inc)
    if created:
        # Telegram: одразу попросити номер кнопкою (request_contact) у нового клієнта
        if (channel.kind == "telegram" and getattr(inc, "direction", "in") == "in"
                and (channel.config or {}).get("ask_phone", True) and not contact.phone):
            try:
                get_adapter(channel).request_phone(inc.external_chat_id)
            except Exception:
                pass
        # авто-лід у воронці "Лиды" з джерелом = канал (розділення лідів по каналах)
        try:
            from apps.crm.models import Lead, Funnel
            f = Funnel.objects.filter(name="Лиды").first() or Funnel.objects.order_by("id").first()
            st = f.stages.order_by("order").first() if f else None
            if f and st and contact_created:
                src = channel.kind if channel.kind in dict(Lead.SOURCES) else "other"
                from apps.crm.lead_routing import make_lead_for_contact
                make_lead_for_contact(contact, f, src)
        except Exception:
            pass

    # RBAC-привязка: чат → ответственному клиента (owner контакта либо owner его
    # последней активной сделки). None = «Не призначені» — НЕ fallback на чужого юзера.
    contact = conv.contact
    if conv.assigned_to_id is None and contact is not None and not created:
        from apps.crm.models import Deal
        owner_id = contact.owner_id or (
            Deal.objects.filter(contact=contact).exclude(stage__is_lost=True)
            .order_by("-created_at").values_list("owner_id", flat=True).first())
        if owner_id:
            conv.assigned_to_id = owner_id
    if contact is not None and contact.pk:
        contact.last_touch_at = timezone.now()
        contact.save(update_fields=["last_touch_at"])

    _dir = getattr(inc, "direction", "in") or "in"
    msg = Message.objects.create(
        conversation=conv, direction=_dir, text=inc.text,
        attachments=inc.attachments, external_id=inc.external_id,
        sender_name=inc.sender_name,
    )
    if _dir == "in":
        conv.unread += 1
    conv.last_message_at = msg.created_at
    conv.status = "open"
    conv.save(update_fields=["unread", "last_message_at", "status", "assigned_to"])
    try:
        from apps.crm.automation import on_incoming, on_outgoing
        if _dir == "in":
            on_incoming(contact, inc.text)
        else:
            on_outgoing(contact)
    except Exception:
        pass
    return msg


def _resolve_chatplace_chat_id(conv):
    """Знайти chat_id ChatPlace для клієнта цього Meta-IG діалогу (той самий контакт
    або той самий нік у ChatPlace-каналі), щоб маршрутизувати відповідь через ChatPlace.
    Повертає "" якщо не знайдено."""
    try:
        qs = (Conversation.objects.filter(channel__config__chatplace=True)
              .exclude(external_chat_id__startswith="comment:"))
        cand = None
        if conv.contact_id:
            cand = qs.filter(contact_id=conv.contact_id).order_by("-last_message_at").first()
        if not cand and conv.contact_id:
            nick = (conv.contact.nickname or "").strip()
            if nick:
                cand = qs.filter(contact__nickname__iexact=nick).order_by("-last_message_at").first()
        if cand and cand.external_chat_id:
            return str(cand.external_chat_id)
        # 2) спитати ChatPlace напряму (chats_list) — знайти чат по @ніку АБО по ПОВНОМУ
        # імені (ChatPlace для IG часто дає clientName=імʼя, а username=None).
        nick = (conv.contact.nickname or "").strip().lower() if conv.contact_id else ""
        fullname = str(conv.contact).strip().lower() if conv.contact_id else ""
        _parts = fullname.split()
        swapped = " ".join(reversed(_parts)) if len(_parts) == 2 else ""
        if nick or fullname:
            from .chatplace import _mcp
            data = _mcp("chats_list", {"limit": 200})
            items = data.get("items", []) if isinstance(data, dict) else (data or [])
            found = set()
            for it in (items or []):
                cid = it.get("id")
                if not cid:
                    continue
                un = str(it.get("username") or "").strip().lower()
                cn = str(it.get("clientName") or "").strip().lstrip("@").lower()
                if (nick and (un == nick or cn == nick)) or (fullname and cn and cn in (fullname, swapped)):
                    found.add(str(cid))
            if len(found) == 1:  # тільки при ОДНОЗНАЧНОМУ збігу (без ризику переплутати)
                return next(iter(found))
            # 3) клієнт лише з @ніком (Meta не дав реального імені) — chats_list НЕ віддає
            # username, а chats_get — віддає. Клієнт активний → його чат зверху списку:
            # перевіряємо ТОП-10 свіжих чатів через chats_get і матчимо по @ніку.
            if nick:
                for it in (items or [])[:10]:
                    cid = it.get("id")
                    if not cid:
                        continue
                    try:
                        g = _mcp("chats_get", {"chatId": str(cid)})
                        un = str((g or {}).get("username") or "").strip().lstrip("@").lower()
                        if un and un == nick:
                            return str(cid)
                    except Exception:
                        break  # ChatPlace лагає/бан — не довбимо далі
        return ""
    except Exception:
        return ""


def send_message(conv: Conversation, text: str, user=None) -> Message:
    """Отправить исходящее сообщение через адаптер канала и записать его."""
    cfg = conv.config or {}
    route = cfg.get("outbound_chatplace") or {}
    is_meta_instagram_direct = bool(
        conv.channel.kind == "instagram"
        and (conv.channel.config or {}).get("meta")
        and not str(conv.external_chat_id or "").startswith("comment:")
    )
    if is_meta_instagram_direct:
        chat_id = str(route.get("chat_id") or "").strip()
        if not chat_id:
            # спробувати знайти чат ChatPlace того ж клієнта і закріпити привʼязку
            chat_id = _resolve_chatplace_chat_id(conv)
            if chat_id:
                _cfg = conv.config or {}
                _cfg["outbound_chatplace"] = {"chat_id": chat_id, "match": "resolve_on_send"}
                conv.config = _cfg
                conv.save(update_fields=["config"])
        if chat_id:
            # ChatPlace володіє Direct-веткою і Юлею: open ставить AI на паузу,
            # send доставляє відповідь менеджера в той самий Instagram-чат.
            from .chatplace import send as chatplace_send
            result = chatplace_send(chat_id, text)
            ext_id = str((result or {}).get("id") or "") if isinstance(result, dict) else ""
        else:
            # Немає чату ChatPlace → шлемо НАПРЯМУ через Meta, щоб повідомлення таки пішло
            # (у межах 24-год вікна). Раніше тут була жорстка відмова — менеджер не міг відповісти.
            adapter = get_adapter(conv.channel)
            ext_id = adapter.send(conv.external_chat_id, text)
    else:
        adapter = get_adapter(conv.channel)
        ext_id = adapter.send(conv.external_chat_id, text)
    status = "sent"
    if conv.channel.kind in ("instagram", "facebook"):
        last_in = Message.objects.filter(conversation=conv, direction="in").order_by("-created_at").first()
        if not last_in or (timezone.now() - last_in.created_at).total_seconds() > 24 * 3600:
            status = "window_risk"  # вікно Meta 24г закрите — ChatPlace прийняв, але IG міг не доставити
    elif conv.channel.kind in ("echat", "viber", "whatsapp"):
        # Viber/WhatsApp-бізнес (через e-chat) можна писати ТІЛЬКИ якщо клієнт сам звертався
        # (є сесія). Якщо вхідних НЕ було — «холодне» повідомлення НЕ доходить, хоча e-chat
        # може відрапортувати «delivered».
        if not Message.objects.filter(conversation=conv, direction="in").exists():
            status = "window_risk"
    msg = Message.objects.create(
        conversation=conv, direction="out", text=text,
        external_id=ext_id, sender=user,
        sender_name=(user.get_full_name() if user else "") or "", status=status,
    )
    conv.last_message_at = msg.created_at
    conv.save(update_fields=["last_message_at"])
    try:
        from apps.crm.automation import on_outgoing
        on_outgoing(conv.contact)
    except Exception:
        pass
    return msg
