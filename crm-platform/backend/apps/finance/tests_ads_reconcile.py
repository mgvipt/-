"""Звірка реклами Meta в P&L (11.09): витрачено в Ads Manager vs оплати реклами в журналі."""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.crm.models import MetaAdDailyStat
from apps.finance.models import Account, Category, Transaction
from apps.finance.views import _meta_ads_reconcile


class AdsReconcileTests(TestCase):
    def test_gap_counts_account_level_and_ad_payments_only(self):
        MetaAdDailyStat.objects.create(date=date(2026, 8, 5), level="account", object_id="a1", account_id="a1",
                                       spend=Decimal("100"), spend_uah=Decimal("4470"))
        # рядок рівня оголошення — ті самі гроші, двічі не рахуємо
        MetaAdDailyStat.objects.create(date=date(2026, 8, 5), level="ad", object_id="ad1", account_id="a1",
                                       spend=Decimal("100"), spend_uah=Decimal("4470"))
        acc = Account.objects.create(name="Картка тест")
        cat = Category.objects.create(name="ТАРГЕТ_бюджет(Инста/Фб/Тик-ток)", direction="out")
        Transaction.objects.create(direction="out", amount=Decimal("1000"), amount_uah=Decimal("1000"),
                                   account=acc, category=cat, date=date(2026, 8, 6))
        Transaction.objects.create(direction="out", amount=Decimal("500"), amount_uah=Decimal("500"),
                                   account=acc, comment="FACEBK *ADS", date=date(2026, 8, 7))
        Transaction.objects.create(direction="out", amount=Decimal("700"), amount_uah=Decimal("700"),
                                   account=acc, comment="Нова Пошта", date=date(2026, 8, 7))
        r = _meta_ads_reconcile(date(2026, 8, 1), date(2026, 8, 31))
        self.assertEqual(r["meta_spend_uah"], 4470.0)
        self.assertEqual(r["journal_paid_uah"], 1500.0)
        self.assertEqual(r["gap_uah"], 2970.0)
        self.assertEqual(r["meta_data_since"], "2026-08-05")

    def test_empty_period(self):
        r = _meta_ads_reconcile(date(2026, 1, 1), date(2026, 1, 31))
        self.assertEqual((r["meta_spend_uah"], r["journal_paid_uah"], r["gap_uah"]), (0.0, 0.0, 0.0))
