"""Регресія 11.09: завершення чату закриває НЕОПЛАЧЕНІ угоди контакту до «Оплату отримано».

Олег: «при закритті чату угода теж має йти з канбану — щоб лишались лише актуальні».
Раніше закривався тільки лід, угоди висіли (≈ 200 угод до оплати у клієнтів з закритими чатами).
"""
from decimal import Decimal

from django.test import TestCase

from apps.crm.models import Contact, Deal, Funnel, Payment, Stage
from apps.inbox.views import _close_contact_deals


class CloseContactDealsTests(TestCase):
    def setUp(self):
        self.funnel = Funnel.objects.create(name="Основна (тест)")

        def mk(name, order, **kw):
            return Stage.objects.create(funnel=self.funnel, name=name, order=order, **kw)

        self.s_calc = mk("Данні для розрахунку", 0)
        self.s_kp = mk("Розрахунок здійснено (КП)", 1)
        self.s_paid = mk("Оплату отримано", 3)
        self.s_ship = mk("Відвантаження", 5)
        self.s_ignor = mk("Игнор", 19, is_lost=True)
        self.s_spam = mk("Спам", 24, is_lost=True)
        self.contact = Contact.objects.create(first_name="Тест", phone="+380670001122")

    def deal(self, stage):
        return Deal.objects.create(title="t", contact=self.contact, funnel=self.funnel,
                                   stage=stage, amount=Decimal("1000"))

    def test_ignore_closes_prepayment_deal(self):
        d = self.deal(self.s_kp)
        self.assertEqual(_close_contact_deals(self.contact.id, "Не відповідає (ігнор)"), 1)
        d.refresh_from_db()
        self.assertEqual(d.stage_id, self.s_ignor.id)
        self.assertIsNotNone(d.closed_at)
        self.assertEqual(d.qualification.get("_reached_stage_name"), "Розрахунок здійснено (КП)")
        self.assertEqual(d.qualification.get("close_reason"), "Не відповідає (ігнор)")

    def test_non_request_goes_to_spam(self):
        d = self.deal(self.s_calc)
        _close_contact_deals(self.contact.id, "Не звернення (коментар, спілкування)")
        d.refresh_from_db()
        self.assertEqual(d.stage_id, self.s_spam.id)

    def test_paid_deal_untouched(self):
        d = self.deal(self.s_calc)
        Payment.objects.create(deal=d, provider="liqpay", amount=Decimal("1000"), is_paid=True)
        self.assertEqual(_close_contact_deals(self.contact.id, "Не відповідає (ігнор)"), 0)
        d.refresh_from_db()
        self.assertEqual(d.stage_id, self.s_calc.id)

    def test_after_payment_stage_untouched(self):
        d = self.deal(self.s_ship)
        self.assertEqual(_close_contact_deals(self.contact.id, "Не відповідає (ігнор)"), 0)
        d.refresh_from_db()
        self.assertEqual(d.stage_id, self.s_ship.id)

    def test_defer_resolved_and_empty_reason_untouched(self):
        d = self.deal(self.s_kp)
        for reason in ["Хочу пізніше (відкласти)", "Питання вирішено / відповіли", ""]:
            self.assertEqual(_close_contact_deals(self.contact.id, reason), 0)
        d.refresh_from_db()
        self.assertEqual(d.stage_id, self.s_kp.id)

    def test_missing_target_stage_untouched(self):
        d = self.deal(self.s_kp)
        # «Дорого» у цій тестовій воронці немає — угода лишається як була
        self.assertEqual(_close_contact_deals(self.contact.id, "Дорого / бюджет"), 0)
        d.refresh_from_db()
        self.assertEqual(d.stage_id, self.s_kp.id)
