"""18.09.2026 (Олег): «щоб у картці сделки відображалась помилка платежу LiqPay і менеджеру приходило
сповіщення — він одразу скине реквізити»."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.inbox.models import Channel, Conversation, Message, Notification

from .models import Contact, Deal, Funnel, PayLink, Payment, Stage
from .serializers import DealDetailSerializer
from .views import liqpay_not_paid, liqpay_reason


class LiqPayFailTests(TestCase):
    def setUp(self):
        self.mgr = User.objects.create_user(username="mgr_pay", password="x")
        f = Funnel.objects.create(name="22 Тестовий набір")
        st = Stage.objects.create(funnel=f, name="Домовились про оплату", order=2)
        self.contact = Contact.objects.create(first_name="Ірина")
        self.deal = Deal.objects.create(title="Тест", funnel=f, stage=st, contact=self.contact,
                                        amount=Decimal("430"), owner=self.mgr)
        self.pl = PayLink.objects.create(code="AbC1234", deal=self.deal, target="https://liqpay.ua/x")
        ch = Channel.objects.create(kind="echat", name="Viber (e-chat)", config={})
        self.conv = Conversation.objects.create(channel=ch, external_chat_id="380971112233", contact=self.contact)
        self.order = "WCCRM-%s-%s" % (self.deal.id, self.pl.code)

    def test_failure_marks_card_notifies_and_notes_chat(self):
        r = liqpay_not_paid(self.order, "failure", {"amount": 430, "err_code": "limit", "err_description": "Limit"})
        self.assertEqual(r["deal"], self.deal.id)
        self.pl.refresh_from_db()
        self.assertEqual(self.pl.status, "failure")
        self.assertIn("ліміт", self.pl.error)
        n = Notification.objects.get(user=self.mgr)
        self.assertIn("#%s" % self.deal.id, n.text)
        self.assertIn("реквізити", n.text)
        note = Message.objects.get(conversation=self.conv, internal=True)
        self.assertIn("не пройшла", note.text)
        self.conv.refresh_from_db()
        self.assertEqual(self.conv.unread, 1)
        problem = DealDetailSerializer(self.deal).data["pay_problem"]
        self.assertEqual(problem["code"], "AbC1234")

    def test_repeat_callback_does_not_spam(self):
        liqpay_not_paid(self.order, "failure", {"amount": 430, "err_code": "limit"})
        liqpay_not_paid(self.order, "failure", {"amount": 430, "err_code": "limit"})
        self.assertEqual(Notification.objects.filter(user=self.mgr).count(), 1)

    def test_intermediate_status_is_silent(self):
        liqpay_not_paid(self.order, "wait_secure", {"amount": 430})
        self.assertFalse(Notification.objects.exists())
        self.assertIsNone(DealDetailSerializer(self.deal).data["pay_problem"])

    def test_payment_after_failure_hides_banner(self):
        liqpay_not_paid(self.order, "failure", {"amount": 430, "err_code": "limit"})
        PayLink.objects.filter(id=self.pl.id).update(status_at=timezone.now() - timedelta(minutes=5))
        Payment.objects.create(deal=self.deal, provider="reqs", amount=Decimal("430"), is_paid=True)
        self.assertIsNone(DealDetailSerializer(self.deal).data["pay_problem"])

    def test_foreign_order_ignored(self):
        self.assertIsNone(liqpay_not_paid("AUTO-1-xx", "failure", {}))
        self.assertIsNone(liqpay_not_paid("WCCRM-999999-zz", "failure", {}))

    def test_reason_is_human(self):
        self.assertEqual(liqpay_reason({"err_code": "9859"}), "недостатньо коштів на картці")
        self.assertEqual(liqpay_reason({"err_description": "Card expired"}), "Card expired")
        self.assertEqual(liqpay_reason({}), "банк відхилив платіж")
