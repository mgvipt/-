# -*- coding: utf-8 -*-
"""Команда «Юля ChatPlace → продавець CRM» (21.09.2026, Олег).

Instagram веде Юля з ChatPlace. Продавець CRM мовчить, поки не дійшло до оформлення;
тоді він бере чат на себе на 10 годин. Живий менеджер у чаті — продавець CRM мовчить.
"""
from django.core.cache import cache
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.inbox.ai_reply import should_reply, TAKEOVER_HOURS
from apps.inbox.models import Channel, Conversation, Message


class TakeoverTests(TestCase):
    def setUp(self):
        cache.clear()
        self.ch = Channel.objects.create(name="Meta · instagram", kind="instagram",
                                         config={"ai_reply": True, "ai_reply_after_handoff": True})

    def _conv(self, ext):
        return Conversation.objects.create(channel=self.ch, external_chat_id=ext, status="open")

    def _in(self, conv, text):
        return Message.objects.create(conversation=conv, direction="in", text=text)

    def test_silent_while_chatplace_leads(self):
        conv = self._conv("c1")
        Message.objects.create(conversation=conv, direction="out",
                               text="Патера дає матову кам'яну фактуру 😊 Для якої кімнати підбираєте?")
        self.assertFalse(should_reply(conv, self._in(conv, "А скільки коштує?")))

    def test_takes_over_after_chatplace_handoff(self):
        conv = self._conv("c2")
        Message.objects.create(conversation=conv, direction="out",
                               text="Зафіксувала остаточний вибір і передала дані менеджеру для оформлення.")
        self.assertTrue(should_reply(conv, self._in(conv, "Ок")))
        conv.refresh_from_db()
        self.assertTrue(conv.config.get("ai_takeover_until"))
        self.assertTrue(Message.objects.filter(conversation=conv, internal=True).exists())

    def test_takes_over_on_buy_intent(self):
        conv = self._conv("c3")
        self.assertTrue(should_reply(conv, self._in(conv, "Беру, куди оплатити?")))

    def test_keeps_chat_after_takeover(self):
        conv = self._conv("c4")
        self.assertTrue(should_reply(conv, self._in(conv, "Оформляйте будь ласка")))
        cache.clear()
        self.assertTrue(should_reply(conv, self._in(conv, "А коли відправите?")))

    def test_manager_reply_stops_crm_seller(self):
        u = get_user_model().objects.create(username="kirill")
        conv = self._conv("c5")
        self.assertTrue(should_reply(conv, self._in(conv, "Беру, куди оплатити?")))
        Message.objects.create(conversation=conv, direction="out", sender=u, text="Вітаю, зараз допоможу")
        cache.clear()
        self.assertFalse(should_reply(conv, self._in(conv, "Дякую")))

    def test_other_channels_reply_as_before(self):
        ch = Channel.objects.create(name="Viber", kind="echat", config={"ai_reply": True})
        conv = Conversation.objects.create(channel=ch, external_chat_id="v1", status="open")
        self.assertTrue(should_reply(conv, Message.objects.create(conversation=conv, direction="in",
                                                                  text="Доброго дня, розкажіть про шовк")))

    def test_window_is_ten_hours(self):
        self.assertEqual(TAKEOVER_HOURS, 10)
