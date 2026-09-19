"""19.09.2026 (Олег, сделка #66537): клієнт з «Игнор» повернувся і оплатив — сделка має повернутись
на «Оплату отримано», а повернення — бути видним у статистиці."""
from decimal import Decimal

from django.test import TestCase

from apps.inbox.views import _close_contact_deals

from .models import ActivityLog, Contact, Deal, Funnel, Payment, Stage
from .revive import REVIVE_ACTION, revive_on_return
from .views import _advance_after_payment


class ReviveTests(TestCase):
    def setUp(self):
        f = Funnel.objects.create(name="21 Основний продукт")
        self.kp = Stage.objects.create(funnel=f, name="Розрахунок здійснено (КП)", order=1)
        self.agreed = Stage.objects.create(funnel=f, name="Домовились про оплату", order=2)
        self.paid = Stage.objects.create(funnel=f, name="Оплату отримано", order=3)
        self.ignore = Stage.objects.create(funnel=f, name="Игнор", order=19, is_lost=True)
        self.contact = Contact.objects.create(first_name="Крістіна")
        self.deal = Deal.objects.create(title="Галатея", funnel=f, stage=self.kp, contact=self.contact,
                                        amount=Decimal("2261.50"))

    def test_client_writes_back_deal_returns_to_its_stage(self):
        self.assertEqual(_close_contact_deals(self.contact.id, "Не відповідає (ігнор)"), 1)
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.stage_id, self.ignore.id)
        self.assertEqual(revive_on_return(self.contact.id, "клієнт написав у закритий діалог"), 1)
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.stage_id, self.kp.id)
        self.assertIsNone(self.deal.closed_at)
        self.assertEqual(self.deal.qualification["_revived"][0]["from"], "Игнор")
        self.assertTrue(ActivityLog.objects.filter(kind="deal", object_id=self.deal.id, action=REVIVE_ACTION).exists())

    def test_manually_lost_deal_is_not_reopened_by_message(self):
        self.deal.stage = self.ignore
        self.deal.save()
        self.assertEqual(revive_on_return(self.contact.id), 0)

    def test_payment_moves_lost_deal_to_paid(self):
        _close_contact_deals(self.contact.id, "Не відповідає (ігнор)")
        self.deal.refresh_from_db()
        Payment.objects.create(deal=self.deal, provider="reqs", amount=Decimal("2261.50"), is_paid=True)
        self.assertTrue(_advance_after_payment(self.deal, "Оплата за реквізитами отримана", create_wh=False))
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.stage_id, self.paid.id)
        self.assertIn("оплата", self.deal.qualification["_revived"][-1]["why"])

    def test_normal_deal_still_moves_forward_only(self):
        self.deal.stage = self.agreed
        self.deal.save()
        _advance_after_payment(self.deal, "LiqPay", create_wh=False)
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.stage_id, self.paid.id)
        self.assertNotIn("_revived", self.deal.qualification or {})
