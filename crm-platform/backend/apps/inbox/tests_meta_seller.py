from copy import deepcopy
from unittest.mock import patch
from django.test import TestCase
from .models import Channel, Conversation
from .meta import handle_webhook


@patch("apps.inbox.meta.PAGE_TOKEN", "")
@patch("apps.inbox.meta.IG_TOKEN", "")
@patch("apps.inbox.meta._ma.log_webhook_entry")
@patch("apps.content_library.keyword_automation.process_keyword_message")
class MetaSellerIngressTests(TestCase):
    def setUp(self):
        self.channel = Channel.objects.create(kind="instagram", name="Meta · instagram",
            config={"meta": True, "ai_reply": True, "ai_reply_after_handoff": True})
        self.conv = Conversation.objects.create(channel=self.channel, external_chat_id="owner-test",
            config={"seller_acceptance_test": True})
        self.event = {"sender": {"id": "owner-test"}, "recipient": {"id": "business-test"},
            "timestamp": 1790935588000, "message": {"mid": "owner-new-mid", "text": "Обираю Галатею"}}

    def payload(self, key="messaging"):
        entry = {"id": "business-test"}
        entry[key] = [deepcopy(self.event)] if key != "changes" else [
            {"field": "messages", "value": deepcopy(self.event)}]
        return {"object": "instagram", "entry": [entry]}

    def test_direct_standby_and_changes_trigger_once(self, *_):
        for key in ("messaging", "standby", "changes"):
            self.event["message"]["mid"] = "owner-" + key
            with patch("apps.inbox.ai_reply.maybe_reply") as reply:
                payload = self.payload(key)
                self.assertEqual(handle_webhook(payload), 1)
                self.assertEqual(handle_webhook(payload), 0)
                reply.assert_called_once()
                self.assertEqual(reply.call_args.args[0].pk, self.conv.pk)
                self.assertEqual(reply.call_args.args[1].direction, "in")

    def test_legacy_chatplace_chat_not_started(self, *_):
        self.conv.config = {}; self.conv.save(update_fields=["config"])
        with patch("apps.inbox.ai_reply.maybe_reply") as reply:
            handle_webhook(self.payload()); reply.assert_not_called()

    def test_primary_crm_channel_started(self, *_):
        self.conv.config = {}; self.conv.save(update_fields=["config"])
        self.channel.config["crm_seller_primary"] = True
        self.channel.save(update_fields=["config"])
        with patch("apps.inbox.ai_reply.maybe_reply") as reply:
            handle_webhook(self.payload()); reply.assert_called_once()

    def test_outbound_echo_not_started(self, *_):
        self.event["sender"], self.event["recipient"] = self.event["recipient"], self.event["sender"]
        self.event["message"]["is_echo"] = True
        with patch("apps.inbox.ai_reply.maybe_reply") as reply:
            handle_webhook(self.payload()); reply.assert_not_called()

    def test_closed_owner_chat_reopened_before_queue(self, *_):
        self.conv.status = "closed"; self.conv.save(update_fields=["status"])
        with patch("apps.inbox.ai_reply.maybe_reply") as reply:
            handle_webhook(self.payload()); reply.assert_called_once()
            self.assertEqual(reply.call_args.args[0].status, "open")
