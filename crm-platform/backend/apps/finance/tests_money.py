"""19.09.2026: одне джерело «отриманих грошей» для звітів (apps.finance.money)."""
from datetime import date, datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.crm.models import Contact, Deal, Funnel, Stage

from .models import Account, Category, Transaction
from .money import JOURNAL_SINCE, deal_money, paid_deal_ids, revenue_by_deal


class OneMoneySourceTests(TestCase):
    def setUp(self):
        f = Funnel.objects.create(name="21 Основний продукт")
        self.work = Stage.objects.create(funnel=f, name="Оплату отримано", order=3)
        self.won = Stage.objects.create(funnel=f, name="Успішна угода", order=9, is_won=True)
        c = Contact.objects.create(first_name="Клієнт")
        self.acc = Account.objects.create(name="ФОП ОНЛ")
        self.in_work = Deal.objects.create(title="в роботі", funnel=f, stage=self.work, contact=c, amount=Decimal("1000"))
        self.legacy = Deal.objects.create(title="Бітрікс", funnel=f, stage=self.won, contact=c, amount=Decimal("5000"),
                                          closed_at=timezone.make_aware(datetime(2026, 3, 1)))
        Transaction.objects.create(direction="in", amount=Decimal("1000"), amount_uah=Decimal("1000"), account=self.acc,
                                   deal=self.in_work, date=date(2026, 9, 10))

    def test_paid_deal_in_work_counts_as_revenue(self):
        """Оплачена сделка «в роботі» — це виручка (раніше рахувалась лише «Успішна угода»)."""
        m = revenue_by_deal(date(2026, 9, 1), date(2026, 9, 30))
        self.assertEqual(m, {self.in_work.id: 1000.0})

    def test_legacy_before_journal_is_deal_amount(self):
        m = revenue_by_deal(date(2026, 1, 1), date(2026, 3, 31))
        self.assertEqual(m, {self.legacy.id: 5000.0})
        self.assertLess(date(2026, 3, 31), JOURNAL_SINCE)

    def test_refund_is_subtracted(self):
        cat = Category.objects.create(name="Возврат денег клиенту", direction="out")
        Transaction.objects.create(direction="out", amount=Decimal("400"), amount_uah=Decimal("400"), account=self.acc,
                                   deal=self.in_work, category=cat, date=date(2026, 9, 12))
        self.assertEqual(deal_money(date(2026, 9, 1), date(2026, 9, 30))[self.in_work.id], 600.0)

    def test_fully_refunded_deal_is_not_paid(self):
        self.assertEqual(paid_deal_ids({1: 0.0, 2: 10.0}), {2})
