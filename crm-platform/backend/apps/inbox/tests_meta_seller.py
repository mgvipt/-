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


    def test_primary_conversation_routes_without_financial_test_mode(self, *_):
        self.conv.config = {"crm_seller_primary": True, "seller_acceptance_test": False}
        self.conv.save(update_fields=["config"])
        from .ai_reply import _took_over
        from apps.knowledge.seller_state import action_blocked
        with patch("apps.inbox.ai_reply.maybe_reply") as reply:
            handle_webhook(self.payload()); reply.assert_called_once()
        self.assertTrue(_took_over(self.conv, None))
        self.assertEqual(action_blocked(self.conv), "")

    def test_quote_does_not_create_invoice_without_consent(self, *_):
        from types import SimpleNamespace
        from .models import Message
        from .ai_reply import _reply_once
        self.conv.config={"crm_seller_primary":True,"seller_acceptance_test":False}
        self.conv.save(update_fields=["config"])
        incoming=Message.objects.create(conversation=self.conv,direction="in",text="Покажи остаточний розрахунок")
        with patch('apps.knowledge.seller_state.refresh',return_value={}), \
             patch('apps.knowledge.seller_state.action_blocked',return_value=''), \
             patch('apps.inbox.ai_reply._still_current',return_value=True), \
             patch('apps.inbox.ai_reply._switch_kit',return_value=False), \
             patch('apps.inbox.ai_reply._maybe_requisites',return_value=False), \
             patch('apps.inbox.ai_reply._volume_calc',return_value=None), \
             patch('apps.knowledge.conversation_context.prompt_block',return_value=''), \
             patch('apps.knowledge.volume_calc.final_quote_reply',return_value={'text':'Порахувала: 5624 грн.','handoff':False}), \
             patch('apps.inbox.ai_reply._maybe_effect_photos'), patch('apps.inbox.ai_reply._maybe_base_photos'), \
             patch('apps.inbox.ai_reply._first_presentation'), patch('apps.inbox.ai_reply._note'), \
             patch('apps.inbox.ai_reply._takeover_channel',return_value=False), \
             patch('apps.inbox.services.send_message',return_value=SimpleNamespace(id=99999)) as send, \
             patch('apps.inbox.ai_reply._maybe_volume_doc') as document, \
             patch('apps.inbox.ai_reply._make_volume_offer') as checkout:
            _reply_once(self.conv.pk, expected_incoming_id=incoming.pk)
        send.assert_called_once()
        document.assert_not_called()
        checkout.assert_not_called()
