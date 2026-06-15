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

    msg = Message.objects.create(
        conversation=conv, direction="in", text=inc.text,
        attachments=inc.attachments, external_id=inc.external_id,
        sender_name=inc.sender_name,
    )
    conv.unread += 1
    conv.last_message_at = msg.created_at
    conv.status = "open"
    conv.save(update_fields=["unread", "last_message_at", "status"])
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
    return msg
