"""19.09.2026 (Олег): «↪ Відповісти» — відповідь на конкретне повідомлення клієнта."""
from unittest import mock

from django.test import TestCase

from .models import Channel, Conversation, Message
from .services import send_message


class _FakeAdapter:
    def __init__(self):
        self.sent = []

    def send(self, chat_id, text):
        self.sent.append((text, getattr(self, "reply_to_message_id", None)))
        return "900"


class ReplyQuoteTests(TestCase):
    def _conv(self, kind, name):
        ch = Channel.objects.create(kind=kind, name=name, config={})
        return Conversation.objects.create(channel=ch, external_chat_id="380971112233")

    def _send(self, conv, text, reply_to):
        fake = _FakeAdapter()
        with mock.patch("apps.inbox.services.get_adapter", return_value=fake):
            msg = send_message(conv, text, reply_to=reply_to)
        return msg, fake

    def test_viber_gets_quote_line_and_crm_link(self):
        conv = self._conv("echat", "Viber (e-chat)")
        q = Message.objects.create(conversation=conv, direction="in", text="Скільки коштує тест-набір?", external_id="55")
        msg, fake = self._send(conv, "395 грн з дощечкою 🙂", q.id)
        self.assertEqual(fake.sent[0][0], "↪ «Скільки коштує тест-набір?»\n395 грн з дощечкою 🙂")
        self.assertIsNone(fake.sent[0][1])
        ref = msg.attachments[0]
        self.assertEqual((ref["type"], ref["target_id"], ref["outgoing"]), ("reply_ref", q.id, True))

    def test_telegram_bot_uses_native_reply(self):
        conv = self._conv("telegram", "Telegram-бот")
        q = Message.objects.create(conversation=conv, direction="in", text="А доставка?", external_id="1234")
        msg, fake = self._send(conv, "Новою Поштою, 1–3 дні", q.id)
        self.assertEqual(fake.sent[0], ("Новою Поштою, 1–3 дні", "1234"))
        self.assertTrue(msg.attachments[0]["native"])

    def test_message_from_other_chat_is_ignored(self):
        conv = self._conv("echat", "Viber (e-chat)")
        other = self._conv("echat", "Viber 2")
        q = Message.objects.create(conversation=other, direction="in", text="чужий", external_id="1")
        msg, fake = self._send(conv, "Привіт", q.id)
        self.assertEqual(fake.sent[0][0], "Привіт")
        self.assertEqual(msg.attachments, [])

    def test_reply_to_photo(self):
        conv = self._conv("echat", "Viber (e-chat)")
        q = Message.objects.create(conversation=conv, direction="in", text="", attachments=[{"type": "photo", "url": "x"}])
        _msg, fake = self._send(conv, "Гарна стіна!", q.id)
        self.assertTrue(fake.sent[0][0].startswith("↪ на Ваше фото\n"))
