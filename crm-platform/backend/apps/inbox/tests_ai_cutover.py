from unittest.mock import patch
from django.test import TestCase, override_settings
from django.core.cache import cache
from .models import Channel, Conversation, Message
from . import ai_reply, ai_reply_claim, yulia_toggle, tiktok
from .tests_tiktok import _event, BIZ


@override_settings(AI_CLAIM_TEST_LOCK=True)
class SellerClaimTests(TestCase):
    def setUp(self):
        cache.clear()
        self.ch = Channel.objects.create(kind="instagram", name="Test", config={"ai_reply": True})
        self.conv = Conversation.objects.create(channel=self.ch, external_chat_id="test")
        self.msg = Message.objects.create(conversation=self.conv, direction="in", text="Пробник Галатея")
        self.close = patch.object(ai_reply_claim, "close_old_connections").start()
        self.addCleanup(patch.stopall)

    @patch.object(ai_reply, "MIN_SECONDS", 0)
    def test_same_input_runs_only_once(self):
        with patch.object(ai_reply, "_reply_once") as reply:
            reply.return_value = None
            ai_reply.reply_now(self.conv.pk)
            ai_reply.reply_now(self.conv.pk)
        reply.assert_called_once_with(self.conv.pk, expected_incoming_id=self.msg.pk)
        self.conv.refresh_from_db()
        self.assertEqual(self.conv.config["ai_claim_state"], "finished")

    @patch.object(ai_reply, "MIN_SECONDS", 0)
    def test_new_input_is_not_lost_to_old_cache_gate(self):
        cache.set("ai_reply_%s" % self.conv.pk, 1, 20)
        with patch.object(ai_reply, "_reply_once", return_value=None) as reply:
            ai_reply.reply_now(self.conv.pk)
            newer = Message.objects.create(conversation=self.conv, direction="in", text="З дощечкою")
            ai_reply.reply_now(self.conv.pk)
        self.assertEqual(reply.call_count, 2)
        self.assertEqual(reply.call_args.kwargs["expected_incoming_id"], newer.pk)

    @patch.object(ai_reply, "MIN_SECONDS", 0)
    def test_exception_is_visible_and_never_replayed(self):
        with patch.object(ai_reply, "_reply_once", side_effect=RuntimeError("test")) as reply:
            ai_reply.reply_now(self.conv.pk)
            ai_reply.reply_now(self.conv.pk)
        self.assertEqual(reply.call_count, 1)
        self.conv.refresh_from_db()
        self.assertEqual(self.conv.config["ai_claim_state"], "failed")
        self.assertTrue(self.conv.messages.filter(internal=True, text__contains="помилкою").exists())

    def test_merge_preserves_new_config_fields(self):
        Conversation.objects.filter(pk=self.conv.pk).update(config={"manager_setting": True})
        ai_reply_claim.set_state(self.conv.pk, ai_claim_state="claimed")
        self.conv.refresh_from_db()
        self.assertTrue(self.conv.config["manager_setting"])

    def test_queue_waits_for_commit_and_does_not_claim_gate(self):
        with patch.object(ai_reply.threading, "Thread") as thread:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                self.assertTrue(ai_reply.maybe_reply(self.conv, self.msg))
                thread.assert_not_called()
            self.assertEqual(len(callbacks), 1)
            self.assertIsNone(cache.get("ai_reply_%s" % self.conv.pk))

    def test_inactive_channel_never_queues(self):
        self.ch.is_active = False; self.ch.save()
        self.conv.refresh_from_db()
        self.assertFalse(ai_reply.maybe_reply(self.conv, self.msg))

    def test_disabled_channel_never_queues(self):
        self.ch.config = {}; self.ch.save()
        self.conv.refresh_from_db()
        self.assertFalse(ai_reply.maybe_reply(self.conv, self.msg))

    def test_shift_does_not_reenable_crm_owned_bot(self):
        self.ch.config.update(crm_seller_primary=True, crm_seller_chatplace_bot_id=yulia_toggle.YULIA_IG_BOT_ID)
        self.ch.save()
        with patch("apps.inbox.chatplace._mcp") as cp:
            result = yulia_toggle._cp_update(yulia_toggle.YULIA_IG_BOT_ID, False)
        cp.assert_not_called()
        self.assertEqual(result["managed_by"], "crm")
        self.assertTrue(yulia_toggle._check(result, False))

    def test_inactive_crm_owner_does_not_restore_external_seller(self):
        self.ch.config.update(crm_seller_primary=True, crm_seller_chatplace_bot_id=yulia_toggle.YULIA_IG_BOT_ID)
        self.ch.is_active = False
        self.ch.save()
        with patch("apps.inbox.chatplace._mcp") as cp:
            yulia_toggle._cp_update(yulia_toggle.YULIA_IG_BOT_ID, False)
        cp.assert_not_called()

    @patch.object(ai_reply, "MIN_SECONDS", 0)
    def test_crash_claim_with_new_input_is_not_overwritten(self):
        from django.utils import timezone
        ai_reply_claim.set_state(self.conv.pk, ai_claim_state="claimed", ai_last_claimed_incoming_id=self.msg.pk,
                                 ai_claimed_at=timezone.now().isoformat())
        Message.objects.create(conversation=self.conv, direction="in", text="Що з замовленням?")
        with patch.object(ai_reply, "_reply_once") as reply:
            ai_reply.reply_now(self.conv.pk)
            ai_reply.reply_now(self.conv.pk)
        reply.assert_not_called()
        self.conv.refresh_from_db()
        self.assertEqual(self.conv.config["ai_claim_state"], "interrupted")
        self.assertEqual(self.conv.config["ai_last_claimed_incoming_id"], self.msg.pk)
        self.assertEqual(self.conv.messages.filter(internal=True, text__contains="перервалася").count(), 1)

    def test_legacy_bot_keeps_shift_behavior(self):
        with patch("apps.inbox.chatplace._mcp", return_value={}) as cp:
            yulia_toggle._cp_update(yulia_toggle.YULIA_TT_BOT_ID, True)
        self.assertTrue(cp.call_args.args[1]["answerOnMessageEnabled"])


class TikTokSellerTriggerTests(TestCase):
    def setUp(self):
        self.ch = Channel.objects.create(kind="tiktok", name="Test", config={"tiktok_direct": True, "business_id": BIZ})

    def test_incoming_only_and_no_duplicate(self):
        with patch.object(ai_reply, "maybe_reply") as reply:
            tiktok.handle_event(_event())
            tiktok.handle_event(_event())
            tiktok.handle_event(_event("im_send_msg", mid="echo", frm_id=BIZ, to_id="client"))
        self.assertEqual(reply.call_count, 1)
        self.assertEqual(reply.call_args.args[1].direction, "in")
