from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.models import Role
from .models import Channel, Conversation, Message
from .adapters import TelegramAdapter

User = get_user_model()

UPDATE = {
    "message": {
        "message_id": 11,
        "chat": {"id": 999},
        "from": {"first_name": "Ірина", "last_name": "Турок"},
        "text": "Доброго дня, цікавить покриття",
    }
}


class TelegramIngestTests(TestCase):
    def setUp(self):
        self.ch = Channel.objects.create(kind="telegram", name="Wallcov bot",
                                         config={"bot_token": "x"})

    def test_webhook_creates_conversation_contact_and_message(self):
        c = APIClient()  # вебхук публичный
        r = c.post(f"/api/inbox/telegram/webhook/{self.ch.id}/", UPDATE, format="json")
        self.assertEqual(r.status_code, 200)
        conv = Conversation.objects.get(channel=self.ch, external_chat_id="999")
        self.assertEqual(conv.messages.count(), 1)
        self.assertEqual(conv.messages.first().text, "Доброго дня, цікавить покриття")
        self.assertEqual(conv.unread, 1)
        self.assertIsNotNone(conv.contact)
        self.assertEqual(conv.contact.first_name, "Ірина Турок")

    def test_second_message_reuses_conversation(self):
        c = APIClient()
        c.post(f"/api/inbox/telegram/webhook/{self.ch.id}/", UPDATE, format="json")
        c.post(f"/api/inbox/telegram/webhook/{self.ch.id}/", UPDATE, format="json")
        self.assertEqual(Conversation.objects.filter(channel=self.ch).count(), 1)
        self.assertEqual(Conversation.objects.get().unread, 2)

    @patch.object(TelegramAdapter, "send", return_value="55")
    def test_send_outbound_records_message(self, mock_send):
        c = APIClient()
        c.post(f"/api/inbox/telegram/webhook/{self.ch.id}/", UPDATE, format="json")
        conv = Conversation.objects.get()
        admin = User.objects.create_superuser("adm", password="x")
        c.force_authenticate(admin)
        r = c.post(f"/api/conversations/{conv.id}/send/", {"text": "Від 450 грн/м²"}, format="json")
        self.assertEqual(r.status_code, 201)
        mock_send.assert_called_once_with("999", "Від 450 грн/м²")
        self.assertEqual(conv.messages.filter(direction="out").count(), 1)


class ChannelScopeTests(TestCase):
    def test_conversations_filtered_by_allowed_open_lines(self):
        tg = Channel.objects.create(kind="telegram", name="TG")
        ig = Channel.objects.create(kind="instagram", name="IG")
        Conversation.objects.create(channel=tg, external_chat_id="1", title="A")
        Conversation.objects.create(channel=ig, external_chat_id="2", title="B")
        role = Role.objects.create(name="Менеджер TG", permissions=[], open_lines=[tg.id])
        u = User.objects.create_user("m", password="x", role=role)
        c = APIClient(); c.force_authenticate(u)
        titles = {x["title"] for x in c.get("/api/conversations/").json()["results"]}
        self.assertEqual(titles, {"A"})
