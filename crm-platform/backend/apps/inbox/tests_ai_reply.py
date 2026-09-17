"""ІІ у каналах CRM (17.09.2026): за замовчуванням мовчить, вмикається по каналу, не заважає менеджеру."""
from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User

from . import ai_reply
from .models import Channel, Conversation, Message


class AiReplyGateTests(TestCase):
    def setUp(self):
        cache.clear()
        self.ch = Channel.objects.create(kind="echat", name="Viber (e-chat)", config={})
        self.conv = Conversation.objects.create(channel=self.ch, external_chat_id="380971112233", title="Клієнт")
        self.msg = Message.objects.create(conversation=self.conv, direction="in", text="Скільки коштує шовк?")

    def test_off_by_default(self):
        self.assertFalse(ai_reply.should_reply(self.conv, self.msg))

    def test_on_when_channel_enabled(self):
        self.ch.config = {"ai_reply": True}; self.ch.save()
        self.conv.refresh_from_db()
        self.assertTrue(ai_reply.should_reply(self.conv, self.msg))

    def test_only_listed_chats_when_testing(self):
        self.ch.config = {"ai_reply": True, "ai_reply_only_chats": ["380970000000"]}; self.ch.save()
        self.conv.refresh_from_db()
        self.assertFalse(ai_reply.should_reply(self.conv, self.msg))
        self.ch.config = {"ai_reply": True, "ai_reply_only_chats": ["380971112233"]}; self.ch.save()
        self.conv.refresh_from_db()
        cache.clear()
        self.assertTrue(ai_reply.should_reply(self.conv, self.msg))

    def test_silent_when_manager_in_dialog(self):
        self.ch.config = {"ai_reply": True}; self.ch.save()
        self.conv.refresh_from_db()
        u = User.objects.create_user(username="mgr_ai", password="x")
        Message.objects.create(conversation=self.conv, direction="out", text="Вітаю!", sender=u)
        self.assertFalse(ai_reply.should_reply(self.conv, self.msg))

    def test_silent_for_assigned_closed_and_empty(self):
        self.ch.config = {"ai_reply": True}; self.ch.save()
        self.conv.refresh_from_db()
        empty = Message.objects.create(conversation=self.conv, direction="in", text="")
        self.assertFalse(ai_reply.should_reply(self.conv, empty))
        cache.clear()
        self.conv.status = "closed"; self.conv.save()
        self.assertFalse(ai_reply.should_reply(self.conv, self.msg))

    def test_throttle_one_reply_per_20s(self):
        self.ch.config = {"ai_reply": True}; self.ch.save()
        self.conv.refresh_from_db()
        self.assertTrue(ai_reply.should_reply(self.conv, self.msg))
        self.assertFalse(ai_reply.should_reply(self.conv, self.msg))   # одразу вдруге — ні

    def test_daily_limit(self):
        self.ch.config = {"ai_reply": True}; self.ch.save()
        self.conv.refresh_from_db()
        for i in range(ai_reply.MAX_PER_DAY):
            Message.objects.create(conversation=self.conv, direction="out", text="відповідь %d" % i,
                                   sender_name="%s · Viber" % ai_reply.NOTE_PREFIX)
        cache.clear()
        self.assertFalse(ai_reply.should_reply(self.conv, self.msg))
