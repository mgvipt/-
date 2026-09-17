"""ІІ у каналах CRM (17.09.2026): за замовчуванням мовчить, вмикається по каналу, не заважає менеджеру."""
from datetime import timedelta
from unittest import mock

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


class AiOrderTests(TestCase):
    """18.09.2026 (Олег): клієнт погодився на тест-набір → CRM сама оформлює сделку і шле посилання на оплату."""

    def setUp(self):
        cache.clear()
        from apps.crm.models import Contact, Funnel, Stage
        from apps.warehouse.models import Product
        self.ch = Channel.objects.create(kind="echat", name="Viber (e-chat)", config={"ai_reply": True})
        self.contact = Contact.objects.create(first_name="Клієнт")
        self.conv = Conversation.objects.create(channel=self.ch, external_chat_id="380971112233", contact=self.contact)
        f = Funnel.objects.create(name="22 Тестовий набір")
        Stage.objects.create(funnel=f, name="Данні для розрахунку", order=0)
        Stage.objects.create(funnel=f, name="Розрахунок здійснено (КП)", order=1)
        Stage.objects.create(funnel=f, name="Домовились про оплату", order=2)
        self.prod = Product.objects.create(name="Sirena Silk — тестовий набір (з дощечкою та тонуванням)",
                                           price=395, cost=100, unit="шт")

    def test_offer_created_and_deal_has_item(self):
        from apps.crm.models import Deal
        ai_reply._make_kit_offer(self.conv, {"product": self.prod.name, "qty": 1})
        d = Deal.objects.filter(contact=self.contact).first()
        self.assertIsNotNone(d)
        self.assertEqual(d.items.count(), 1)
        self.assertEqual(float(d.amount), 395.0)
        note = Message.objects.filter(conversation=self.conv, internal=True).last()
        self.assertIn("оформив сделку", note.text)

    def test_no_duplicate_offer(self):
        from apps.crm.models import Deal
        ai_reply._make_kit_offer(self.conv, {"product": self.prod.name, "qty": 1})
        ai_reply._make_kit_offer(self.conv, {"product": self.prod.name, "qty": 1})   # друге «так» клієнта
        self.assertEqual(Deal.objects.filter(contact=self.contact).count(), 1)       # другої сделки немає
        note = Message.objects.filter(conversation=self.conv, internal=True).last()
        self.assertIn("вже оформлене", note.text)

    def test_repeat_resends_same_link(self):
        """18.09 (Олег, WhatsApp): вибір той самий — ІІ надсилає клієнту ТЕ САМЕ посилання, а не мовчить."""
        from apps.crm.models import PayLink
        ai_reply._make_kit_offer(self.conv, {"product": self.prod.name, "qty": 1})
        pl = PayLink.objects.order_by("-id").first()
        with mock.patch.object(ai_reply, "_send") as send:
            ai_reply._make_kit_offer(self.conv, {"product": self.prod.name, "qty": 1})
        self.assertEqual(send.call_count, 1)
        self.assertIn(pl.code, send.call_args[0][1])

    def test_unknown_product_only_note(self):
        from apps.crm.models import Deal
        ai_reply._make_kit_offer(self.conv, {"product": "Набір якого немає", "qty": 1})
        self.assertEqual(Deal.objects.count(), 0)
        note = Message.objects.filter(conversation=self.conv, internal=True).last()
        self.assertIn("немає в номенклатурі", note.text)

    def test_too_expensive_not_auto(self):
        from apps.crm.models import Deal
        from apps.warehouse.models import Product
        big = Product.objects.create(name="Великий тестовий набір", price=5000, cost=1000, unit="шт")
        ai_reply._make_kit_offer(self.conv, {"product": big.name, "qty": 1})
        self.assertEqual(Deal.objects.count(), 0)


class AiRequisitesTests(TestCase):
    """18.09.2026 (Олег): «якщо клієнт скаже — може, у вас є реквізити, — надсилаємо реквізити,
    щоб клієнт не пропав»."""

    def setUp(self):
        cache.clear()
        from apps.knowledge.models import KnowledgeItem
        self.ch = Channel.objects.create(kind="echat", name="Viber (e-chat)", config={"ai_reply": True})
        self.conv = Conversation.objects.create(channel=self.ch, external_chat_id="380971112233")
        KnowledgeItem.objects.create(title="Реквізити для оплати (рахунок ФОП)", status="approved", kind="template",
                                     topic="Оплата", audience=["yulia_web"], source="manual",
                                     text="Ось реквізити 👇\nIBAN: UA98\nПризначення: Оплата замовлення №{номер}\nСума: {сума} грн")

    def _ask(self, text):
        msg = Message.objects.create(conversation=self.conv, direction="in", text=text)
        return ai_reply._maybe_requisites(self.conv, msg)

    def test_sends_requisites_on_request(self):
        self.assertTrue(self._ask("а може у вас є реквізити?"))
        out = Message.objects.filter(conversation=self.conv, direction="out", internal=False).last()
        self.assertIn("IBAN", out.text)
        self.assertNotIn("{номер}", out.text)          # рядки без сделки прибрані

    def test_ignores_payment_confirmation(self):
        self.assertFalse(self._ask("я вже оплатив на рахунок, ось квитанція"))
        self.assertFalse(Message.objects.filter(conversation=self.conv, direction="out").exists())

    def test_ignores_prorahunok(self):
        self.assertFalse(self._ask("зробіть, будь ласка, прорахунок на 20 м2"))
