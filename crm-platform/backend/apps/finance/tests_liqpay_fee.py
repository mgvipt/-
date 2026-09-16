"""16.09.2026: комісія LiqPay при імпорті банку — по конкретній оплаті, а не «перша оплата − зарахування»."""
from decimal import Decimal
from unittest import mock

from django.test import TestCase

from apps.crm.models import Deal, Funnel, Payment, Stage
from apps.finance import views as fv


class LiqpayFeeTests(TestCase):
    def setUp(self):
        f = Funnel.objects.create(name="21 Основний продукт")
        st = Stage.objects.create(funnel=f, name="Нова", order=0)
        self.deal = Deal.objects.create(title="T", funnel=f, stage=st, amount=Decimal("776.60"))
        Payment.objects.create(deal=self.deal, provider="liqpay", amount=Decimal("395"), is_paid=True, external_id="2897036685")
        Payment.objects.create(deal=self.deal, provider="liqpay", amount=Decimal("381.60"), is_paid=True, external_id="2897169052")

    def test_second_payment_matched_and_fee_from_liqpay(self):
        with mock.patch.object(fv, "_liqpay_commission", return_value=4.96) as m:
            fee, ext, src = fv._liqpay_fee_for_credit(self.deal.id, 376.64)
        m.assert_called_once_with("2897169052")
        self.assertEqual((round(fee, 2), ext, src), (4.96, "2897169052", "LiqPay"))   # раніше було 18,36

    def test_reserve_is_not_fee(self):
        # #66395: 430 ₴, LiqPay взяв 5,59 і утримав резерв 145,29 → зарахування 279,12; комісія — лише 5,59
        Payment.objects.create(deal=self.deal, provider="liqpay", amount=Decimal("430"), is_paid=True, external_id="2914024928")
        with mock.patch.object(fv, "_liqpay_status", return_value={"fee": 5.59, "reserve": 145.29, "amount": 430.0}):
            fee, ext, src = fv._liqpay_fee_for_credit(self.deal.id, 279.12)
        self.assertEqual((round(fee, 2), ext), (5.59, "2914024928"))
        self.assertIn("резерв", src)

    def test_bundled_payout_does_not_invent_fee(self):
        with mock.patch.object(fv, "_liqpay_status", return_value=None):
            fee, ext, src = fv._liqpay_fee_for_credit(self.deal.id, 279.12)
        self.assertIsNone(fee)                                                           # раніше було 150,88
        self.assertEqual(ext, "")

    def test_fallback_difference_when_api_unavailable(self):
        with mock.patch.object(fv, "_liqpay_commission", return_value=None):
            fee, ext, src = fv._liqpay_fee_for_credit(self.deal.id, 389.86)
        self.assertEqual((round(fee, 2), ext, src), (5.14, "2897036685", "різниця"))
