from unittest.mock import patch
import urllib.error
from io import StringIO
from django.test import TestCase
from django.core.management import call_command
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.crm.models import Contact, Lead
from .models import Channel, Conversation, Message
from .adapters import EchatTelegramAdapter, EchatViberAdapter, TelegramAdapter

User = get_user_model()


class _WebChatAiResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b'{"confidence": 0.91, "answer": "AI answer", "reasoning": "kb"}'


class WebChatLandingTests(TestCase):
    origin = "https://wallcov-dlia-stin.olegwallcov.chatgpt.site"

    def _post(self, payload):
        return self.client.post(
            "/api/inbox/web-chat/", data=payload, content_type="application/json", HTTP_ORIGIN=self.origin,
        )

    def test_start_message_and_manager_poll_share_one_crm_conversation(self):
        from apps.inbox.services import send_message

        started = self._post({"action": "start", "visitor_id": "visitor-1"})
        self.assertEqual(started.status_code, 200)
        token = started.json()["token"]
        self.assertEqual(Channel.objects.filter(kind="web").count(), 1)
        with patch("apps.inbox.webchat.urllib.request.urlopen", return_value=_WebChatAiResponse()):
            sent = self._post({
                "action": "message", "token": token, "text": "Яка ціна Сирени?", "client_message_id": "m-1",
            })
        self.assertEqual(sent.status_code, 200)
        self.assertEqual([m["text"] for m in sent.json()["messages"]][-2:], ["Яка ціна Сирени?", "AI answer"])
        conv = Conversation.objects.get(pk=started.json()["conversation_id"])
        send_message(conv, "Відповідь менеджера")
        polled = self._post({"action": "poll", "token": token})
        self.assertEqual(polled.json()["messages"][-1]["text"], "Відповідь менеджера")

    def test_quiz_creates_landing_deal_and_applies_test_kit_minimum(self):
        from apps.crm.models import Deal, Funnel, Stage
        funnel = Funnel.objects.create(name="Лендинг · wallcovdliastin.com.ua")
        Stage.objects.create(funnel=funnel, name="Новая заявка", order=0)
        started = self._post({"action": "start", "visitor_id": "visitor-2"})
        lead = self._post({
            "action": "lead", "token": started.json()["token"], "name": "Тест",
            "phone": "0970000011", "preferred": "telegram", "consent": True,
            "room": "bedroom", "area": 1, "product": "mermi", "analytics": {"utm_source": "test"},
        })
        self.assertEqual(lead.status_code, 200)
        deal = Deal.objects.get(pk=lead.json()["deal_id"])
        self.assertEqual(str(deal.amount), "220.00")
        self.assertEqual(deal.qualification["product"], "Шовк · Мерми")
        self.assertEqual(deal.qualification["minimum_order"], "220.00")
        self.assertEqual(deal.funnel, funnel)

    def test_unknown_origin_is_rejected(self):
        response = self.client.post(
            "/api/inbox/web-chat/", data={"action": "start"}, content_type="application/json",
            HTTP_ORIGIN="https://evil.example",
        )
        self.assertEqual(response.status_code, 403)

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


@patch("apps.inbox.meta.PAGE_TOKEN", "")
class MetaWebhookIngestTests(TestCase):
    def setUp(self):
        self.channel = Channel.objects.create(kind="facebook", name="Meta · facebook",
                                              config={"meta": True, "platform": "page"})
        self.payload = {
            "object": "page",
            "entry": [{
                "id": "101010628568079",
                "standby": [{
                    "sender": {"id": "test-psid"},
                    "recipient": {"id": "101010628568079"},
                    "timestamp": 1787151972000,
                    "message": {"mid": "meta-test-mid", "text": "ТЕСТ CRM"},
                }],
            }],
        }

    def test_standby_message_creates_facebook_conversation(self):
        from .meta import handle_webhook

        self.assertEqual(handle_webhook(self.payload), 1)
        conv = Conversation.objects.get(channel=self.channel, external_chat_id="test-psid")
        self.assertEqual(conv.unread, 1)
        self.assertIsNotNone(conv.contact)
        self.assertEqual(conv.messages.get().direction, "in")
        self.assertEqual(conv.messages.get().text, "ТЕСТ CRM")

    def test_standby_message_is_idempotent(self):
        from .meta import handle_webhook

        handle_webhook(self.payload)
        self.assertEqual(handle_webhook(self.payload), 0)
        self.assertEqual(Message.objects.filter(conversation__channel=self.channel).count(), 1)

    def test_messaging_message_keeps_canonical_format_working(self):
        from .meta import handle_webhook

        event = dict(self.payload["entry"][0]["standby"][0])
        event["sender"] = {"id": "messaging-psid"}
        event["message"] = {"mid": "messaging-mid", "text": "Звичайне повідомлення"}
        payload = {"object": "page", "entry": [{"id": "101010628568079", "messaging": [event]}]}
        self.assertEqual(handle_webhook(payload), 1)
        self.assertEqual(Conversation.objects.get(external_chat_id="messaging-psid").messages.get().text,
                         "Звичайне повідомлення")

    def test_messages_change_creates_facebook_conversation(self):
        from .meta import handle_webhook

        event = dict(self.payload["entry"][0]["standby"][0])
        event["sender"] = {"id": "changes-psid"}
        event["message"] = {"mid": "changes-mid", "text": "Повідомлення через changes"}
        payload = {"object": "page", "entry": [{
            "id": "101010628568079",
            "changes": [{"field": "messages", "value": event}],
        }]}
        self.assertEqual(handle_webhook(payload), 1)
        self.assertEqual(Conversation.objects.get(external_chat_id="changes-psid").messages.get().text,
                         "Повідомлення через changes")

    def test_echo_is_outgoing_and_does_not_increment_unread(self):
        from .meta import handle_webhook

        event = dict(self.payload["entry"][0]["standby"][0])
        event["sender"] = {"id": "101010628568079"}
        event["recipient"] = {"id": "echo-psid"}
        event["message"] = {"mid": "echo-mid", "text": "Вихідне", "is_echo": True}
        payload = {"object": "page", "entry": [{"id": "101010628568079", "messaging": [event]}]}
        self.assertEqual(handle_webhook(payload), 1)
        conv = Conversation.objects.get(external_chat_id="echo-psid")
        self.assertEqual(conv.unread, 0)
        self.assertEqual(conv.messages.get().direction, "out")

    def test_service_event_without_message_is_ignored(self):
        from .meta import handle_webhook

        payload = {"object": "page", "entry": [{
            "id": "101010628568079",
            "messaging": [{"sender": {"id": "service-psid"}, "delivery": {"mids": ["x"]}}],
        }]}
        self.assertEqual(handle_webhook(payload), 0)
        self.assertFalse(Conversation.objects.filter(external_chat_id="service-psid").exists())

    @patch("apps.inbox.meta._graph")
    def test_profile_name_falls_back_to_page_conversation_participant(self, graph):
        from .meta import _profile_name

        graph.side_effect = [
            RuntimeError("direct PSID profile is unavailable"),
            {"data": [{"participants": {"data": [
                {"id": "page-id", "name": "Page"},
                {"id": "normal-user", "name": "Олег Кріжевські"},
            ]}}]},
        ]
        with patch("apps.inbox.meta.PAGE_TOKEN", "token"), \
                patch("apps.inbox.meta.PAGE_ID", "page-id"):
            self.assertEqual(_profile_name("normal-user"), "Олег Кріжевські")
        self.assertEqual(graph.call_args_list[1].args, (
            "GET", "page-id/conversations",
            {"user_id": "normal-user", "fields": "participants", "limit": 1},
        ))

    @patch("apps.inbox.meta._meta_profile", return_value=("Марія Іваненко", "maria.wall"))
    def test_existing_instagram_chat_enriches_placeholder_contact(self, _profile):
        from .meta import handle_webhook

        channel = Channel.objects.create(kind="instagram", name="Meta · instagram")
        contact = Contact.objects.create(first_name="Instagram")
        conv = Conversation.objects.create(
            channel=channel, contact=contact, external_chat_id="178900001", title="instagram",
        )
        payload = {"object": "instagram", "entry": [{"messaging": [{
            "sender": {"id": "178900001"}, "recipient": {"id": "our-ig"},
            "message": {"mid": "ig-enrich-1", "text": "Добрий день"},
        }]}]}

        self.assertEqual(handle_webhook(payload), 1)
        conv.refresh_from_db(); contact.refresh_from_db()
        self.assertEqual(conv.contact_id, contact.id)
        self.assertEqual(Contact.objects.filter(id=contact.id).count(), 1)
        self.assertEqual(contact.first_name, "Марія")
        self.assertEqual(contact.last_name, "Іваненко")
        self.assertEqual(contact.nickname, "maria.wall")
        self.assertEqual(contact.social_link, "https://instagram.com/maria.wall")

    @patch("apps.inbox.meta._meta_profile", return_value=("Олена", ""))
    def test_numeric_platform_id_is_not_saved_as_username(self, _profile):
        from .meta import handle_webhook

        channel = Channel.objects.create(kind="instagram", name="Meta · instagram")
        payload = {"object": "instagram", "entry": [{"changes": [{
            "field": "comments", "value": {
                "id": "comment-1", "text": "Ціна?", "post_id": "post-1",
                "from": {"id": "178900002"},
            },
        }]}]}

        self.assertEqual(handle_webhook(payload), 1)
        conv = Conversation.objects.get(channel=channel)
        self.assertEqual(conv.contact.first_name, "Олена")
        self.assertEqual(conv.contact.nickname, "")

    @patch("apps.inbox.management.commands.backfill_meta_instagram_identities._resolve_meta_identity",
           return_value=("Ірина Коваль", "iryna.wall"))
    def test_identity_backfill_defaults_to_dry_run(self, _resolve):
        channel = Channel.objects.create(kind="instagram", name="Meta · instagram")
        contact = Contact.objects.create(first_name="Instagram")
        Conversation.objects.create(channel=channel, contact=contact,
                                    external_chat_id="178900003", title="instagram")
        output = StringIO()

        call_command("backfill_meta_instagram_identities", stdout=output)

        contact.refresh_from_db()
        self.assertEqual(contact.first_name, "Instagram")
        self.assertIn("DRY_RUN: checked=1", output.getvalue())

    @patch("apps.inbox.management.commands.backfill_meta_instagram_identities._resolve_meta_identity",
           return_value=("Ірина Коваль", "iryna.wall"))
    def test_identity_backfill_apply_updates_exact_conversation(self, _resolve):
        channel = Channel.objects.create(kind="instagram", name="Meta · instagram")
        contact = Contact.objects.create(first_name="Instagram")
        conv = Conversation.objects.create(channel=channel, contact=contact,
                                           external_chat_id="178900004", title="instagram")

        call_command("backfill_meta_instagram_identities", "--apply",
                     "--conversation-id", str(conv.id), stdout=StringIO())

        contact.refresh_from_db()
        self.assertEqual((contact.first_name, contact.last_name), ("Ірина", "Коваль"))
        self.assertEqual(contact.nickname, "iryna.wall")


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

    @patch.object(EchatViberAdapter, "send", side_effect=["first-1", "first-2"])
    def test_start_channel_sends_first_message_and_reuses_chat_without_new_lead(self, send):
        self.conv.delete()
        leads_before = Lead.objects.count()
        listing = self.client.get(f"/api/conversations/start_channels/?contact={self.contact.id}")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual({row["channel_id"] for row in listing.json()},
                         {self.viber1.id, self.viber2.id, self.telegram.id})
        self.assertNotIn("api_key", str(listing.json()))

        url = "/api/conversations/start_channel/"
        first = self.client.post(url, {
            "contact_id": self.contact.id, "channel_id": self.viber1.id,
            "text": "Перше повідомлення",
        }, format="json")
        second = self.client.post(url, {
            "contact_id": self.contact.id, "channel_id": self.viber1.id,
            "text": "Друге повідомлення",
        }, format="json")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        selected = Conversation.objects.get(channel=self.viber1, contact=self.contact)
        self.assertEqual(first.json()["conversation"]["id"], selected.id)
        self.assertEqual(second.json()["conversation"]["id"], selected.id)
        self.assertEqual(selected.external_chat_id, "380670000001")
        self.assertEqual(list(selected.messages.values_list("text", flat=True)),
                         ["Перше повідомлення", "Друге повідомлення"])
        self.assertEqual(Lead.objects.count(), leads_before)
        self.contact.refresh_from_db()
        self.assertIn("viber", self.contact.channels)
        self.assertEqual(send.call_count, 2)

    def test_start_channels_requires_contact_phone(self):
        self.conv.delete()
        self.contact.phone = ""
        self.contact.save(update_fields=["phone"])
        listing = self.client.get(f"/api/conversations/start_channels/?contact={self.contact.id}")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json(), [])
        started = self.client.post("/api/conversations/start_channel/", {
            "contact_id": self.contact.id, "channel_id": self.viber1.id, "text": "Тест",
        }, format="json")
        self.assertEqual(started.status_code, 400)

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

    def test_telegram_reply_reuses_phone_started_chat_and_existing_contact(self):
        self.contact.phone = "0972382295"
        self.contact.social_link = "https://instagram.com/OlegKri"
        self.contact.messengers = ["https://instagram.com/OlegKri", "https://t.me/OlegKri"]
        self.contact.save(update_fields=["phone", "social_link", "messengers"])
        started = Conversation.objects.create(
            channel=self.telegram, contact=self.contact,
            external_chat_id="380972382295", title="Олег",
        )
        leads_before = Lead.objects.count()
        payload = {
            "direction": "incoming", "number": "380970000001",
            "sender": {"id": "495051750", "name": "Олег Крижевски",
                       "phone": "+380972382295", "username": "@OlegKri"},
            "message": {"id": "m-reply", "telegram_id": "5041", "text": "Про", "type": "text"},
        }

        r = APIClient().post(f"/api/inbox/echat/webhook/{self.telegram.id}/", payload, format="json")

        self.assertEqual(r.status_code, 200)
        started.refresh_from_db()
        self.contact.refresh_from_db()
        self.assertEqual(Conversation.objects.filter(channel=self.telegram).count(), 1)
        self.assertEqual(started.external_chat_id, "495051750")
        self.assertEqual(started.messages.get().text, "Про")
        self.assertEqual(Contact.objects.filter(phone__in=["0972382295", "+380972382295"]).count(), 1)
        self.assertEqual(Lead.objects.count(), leads_before)
        self.assertEqual(self.contact.social_link, "https://instagram.com/OlegKri")
        self.assertIn("telegram", self.contact.channels)
        self.assertIn("https://t.me/OlegKri", self.contact.messengers)

    def test_telegram_username_matches_additional_messenger_without_phone(self):
        self.contact.social_link = "https://instagram.com/OlegKri"
        self.contact.messengers = ["https://instagram.com/OlegKri", "https://t.me/OlegKri"]
        self.contact.save(update_fields=["social_link", "messengers"])
        contacts_before = Contact.objects.count()
        leads_before = Lead.objects.count()
        payload = {
            "direction": "incoming", "number": "380970000001",
            "sender": {"id": "495051750", "name": "Олег Крижевски", "username": "@OlegKri"},
            "message": {"id": "m-link", "telegram_id": "5042", "text": "Ще відповідь", "type": "text"},
        }

        r = APIClient().post(f"/api/inbox/echat/webhook/{self.telegram.id}/", payload, format="json")

        self.assertEqual(r.status_code, 200)
        conv = Conversation.objects.get(channel=self.telegram, external_chat_id="495051750")
        self.contact.refresh_from_db()
        self.assertEqual(conv.contact_id, self.contact.id)
        self.assertEqual(Contact.objects.count(), contacts_before)
        self.assertEqual(Lead.objects.count(), leads_before)
        self.assertIn("telegram", self.contact.channels)

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
