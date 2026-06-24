from django.utils import timezone
from apps.crm.models import Contact
from .adapters import IncomingMessage, get_adapter
from .models import Channel, Conversation, Message


def ingest(channel: Channel, inc: IncomingMessage) -> Message:
    """Принять входящее сообщение: создать/найти диалог и контакт, записать сообщение."""
    conv, created = Conversation.objects.get_or_create(
        channel=channel, external_chat_id=inc.external_chat_id,
        defaults={"title": inc.sender_name},
    )
    if created:
        # на канале без телефона (Telegram) заводим контакт по имени и помечаем канал
        contact = Contact.objects.create(first_name=inc.sender_name, channels=[channel.kind])
        conv.contact = contact
        conv.save(update_fields=["contact"])
        # авто-лід у воронці "Лиды" з джерелом = канал (розділення лідів по каналах)
        try:
            from apps.crm.models import Lead, Funnel
            f = Funnel.objects.filter(name="Лиды").first() or Funnel.objects.order_by("id").first()
            st = f.stages.order_by("order").first() if f else None
            if f and st:
                src = channel.kind if channel.kind in dict(Lead.SOURCES) else "other"
                Lead.objects.create(title=(inc.sender_name or channel.kind)[:255],
                                    contact=contact, funnel=f, stage=st, source=src, is_seen=False)
        except Exception:
            pass

    # RBAC-привязка: чат → ответственному клиента (owner контакта либо owner его
    # последней активной сделки). None = «Не призначені» — НЕ fallback на чужого юзера.
    contact = conv.contact
    if conv.assigned_to_id is None and contact is not None:
        from apps.crm.models import Deal
        owner_id = contact.owner_id or (
            Deal.objects.filter(contact=contact).exclude(stage__is_lost=True)
            .order_by("-created_at").values_list("owner_id", flat=True).first())
        if owner_id:
            conv.assigned_to_id = owner_id
    if contact is not None and contact.pk:
        contact.last_touch_at = timezone.now()
        contact.save(update_fields=["last_touch_at"])

    msg = Message.objects.create(
        conversation=conv, direction="in", text=inc.text,
        attachments=inc.attachments, external_id=inc.external_id,
        sender_name=inc.sender_name,
    )
    conv.unread += 1
    conv.last_message_at = msg.created_at
    conv.status = "open"
    conv.save(update_fields=["unread", "last_message_at", "status", "assigned_to"])
    try:
        from apps.crm.automation import on_incoming
        on_incoming(contact, inc.text)
    except Exception:
        pass
    return msg


def send_message(conv: Conversation, text: str, user=None) -> Message:
    """Отправить исходящее сообщение через адаптер канала и записать его."""
    adapter = get_adapter(conv.channel)
    ext_id = adapter.send(conv.external_chat_id, text)
    msg = Message.objects.create(
        conversation=conv, direction="out", text=text,
        external_id=ext_id, sender=user,
        sender_name=(user.get_full_name() if user else "") or "",
    )
    conv.last_message_at = msg.created_at
    conv.save(update_fields=["last_message_at"])
    try:
        from apps.crm.automation import on_outgoing
        on_outgoing(conv.contact)
    except Exception:
        pass
    return msg
