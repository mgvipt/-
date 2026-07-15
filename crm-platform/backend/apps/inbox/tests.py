from unittest.mock import patch
import urllib.error
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.crm.models import Contact
from .models import Channel, Conversation, Message
from .adapters import EchatTelegramAdapter, EchatViberAdapter, TelegramAdapter

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


class OutboundChannelSelectionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("owner", password="x")
        self.client = APIClient(); self.client.force_authenticate(self.admin)
        self.contact = Contact.objects.create(first_name="Олег тест", phone="+380 67 000 00 01")
        self.ig = Channel.objects.create(kind="instagram", name="Instagram", config={"chatplace": True})
        self.viber1 = Channel.objects.create(kind="echat", name="Viber 1",
                                             config={"echat": True, "number": "380970000001", "api_key": "key1"})
        self.viber2 = Channel.objects.create(kind="echat", name="Viber 2",
                                             config={"echat": True, "number": "380970000002", "api_key": "key2"})
        self.telegram = Channel.objects.create(kind="echat_telegram", name="Telegram E-chat",
                                               config={"echat_telegram": True, "number": "380970000001",
                                                       "api_key": "tg-key"})
        self.conv = Conversation.objects.create(channel=self.ig, contact=self.contact,
                                                external_chat_id="ig-test", title="Олег тест")

    def test_reply_channels_exposes_both_echat_numbers_without_keys(self):
        r = self.client.get(f"/api/conversations/{self.conv.id}/reply_channels/")
        self.assertEqual(r.status_code, 200)
        rows = r.json()
        self.assertEqual({x["number"] for x in rows if x["channel_kind"] == "echat"},
                         {"380970000001", "380970000002"})
        self.assertEqual({x["number"] for x in rows if x["channel_kind"] == "echat_telegram"},
                         {"380970000001"})
        self.assertNotIn("api_key", str(rows))

    def test_use_channel_creates_one_open_viber_conversation_and_reuses_it(self):
        url = f"/api/conversations/{self.conv.id}/use_channel/"
        first = self.client.post(url, {"channel_id": self.viber2.id}, format="json")
        second = self.client.post(url, {"channel_id": self.viber2.id}, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["id"], second.json()["id"])
        selected = Conversation.objects.get(id=first.json()["id"])
        self.assertEqual(selected.external_chat_id, "380670000001")
        self.assertEqual(selected.channel, self.viber2)

    def test_use_channel_can_start_telegram_echat_by_contact_phone(self):
        r = self.client.post(f"/api/conversations/{self.conv.id}/use_channel/",
                             {"channel_id": self.telegram.id}, format="json")
        self.assertEqual(r.status_code, 200)
        selected = Conversation.objects.get(id=r.json()["id"])
        self.assertEqual(selected.external_chat_id, "380670000001")
        self.assertEqual(selected.channel, self.telegram)

    @patch.object(EchatViberAdapter, "connect", return_value={"status": "Success"})
    def test_setup_adds_second_echat_number_instead_of_overwriting_first(self, _connect):
        r = self.client.post("/api/inbox/echat/setup/",
                             {"number": "+380 97 000 00 03", "api_key": "key3"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Channel.objects.filter(kind="echat").count(), 3)
        self.assertTrue(Channel.objects.filter(kind="echat", config__number="380970000003").exists())
        listing = self.client.get("/api/inbox/echat/setup/").json()
        self.assertEqual(len(listing["channels"]), 4)

    @patch.object(EchatTelegramAdapter, "connect", return_value={"status": "SUCCESS"})
    def test_setup_adds_telegram_line_separately_from_viber(self, _connect):
        r = self.client.post("/api/inbox/echat/setup/",
                             {"platform": "telegram", "number": "+380 97 000 00 03",
                              "api_key": "tg-key-3"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["platform"], "telegram")
        self.assertTrue(Channel.objects.filter(kind="echat_telegram", is_active=True,
                                               config__number="380970000003").exists())

    def test_telegram_echat_webhook_ingests_incoming_reply(self):
        payload = {
            "direction": "incoming", "number": "380970000001",
            "sender": {"id": "77123456", "name": "Олег тест", "phone": "380670000001",
                       "username": "@machplaster"},
            "message": {"id": "m-1", "telegram_id": "123", "text": "Відповідь клієнта",
                        "type": "text"},
        }
        r = APIClient().post(f"/api/inbox/echat/webhook/{self.telegram.id}/", payload, format="json")
        self.assertEqual(r.status_code, 200)
        conv = Conversation.objects.get(channel=self.telegram, external_chat_id="77123456")
        self.assertEqual(conv.messages.get().text, "Відповідь клієнта")
        self.assertEqual(conv.contact.phone, "380670000001")

    @patch("apps.inbox.adapters.urllib.request.urlopen")
    def test_telegram_echat_send_uses_phone_for_new_contact(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = b'{"status":"SUCCESS","message_id":"tg-55"}'
        result = EchatTelegramAdapter(self.telegram).send("380670000001", "Тест")
        self.assertEqual(result, "tg-55")
        request = urlopen.call_args.args[0]
        body = __import__("json").loads(request.data.decode())
        self.assertEqual(body["user"]["number"], "380970000001")
        self.assertEqual(body["receiver"], {"phone": "380670000001"})
        self.assertEqual(request.get_header("Api"), "tg-key")

    @patch("apps.inbox.adapters.urllib.request.urlopen")
    def test_echat_request_has_user_agent_required_by_cloudflare(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = b'{"status":"Success"}'
        EchatViberAdapter(self.viber1).connect()
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("User-agent"),
                         "WallcovCRM/1.0 (+https://crm.wallcovdec.com.ua)")
        self.assertEqual(request.get_header("Accept"), "application/json")

    @patch("apps.inbox.adapters.urllib.request.urlopen")
    def test_echat_connect_treats_already_connected_as_success(self, urlopen):
        urlopen.side_effect = urllib.error.HTTPError(
            "https://e-chat.tech/api/viber/v2/channel/connect", 409, "Conflict", {}, None)
        result = EchatViberAdapter(self.viber1).connect()
        self.assertEqual(result["status"], "Success")
        self.assertEqual(result["description"], "Integration already exists")
