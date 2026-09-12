"""seed_finmodel (12.09): без явних прапорців команда НЕ видаляє наявну фінмодель."""
from datetime import date
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.finance.management.commands.seed_finmodel import ARTICLES
from apps.finance.models import Account, FinModelArticle, FundAllocation, Transaction


class SeedFinmodelGuardTests(TestCase):
    def setUp(self):
        self.art = FinModelArticle.objects.create(category="salary", name="ЗП тест: оклад", code="salary_test",
                                                  value=Decimal("15000"), value_type="fixed_sum_per_month")
        self.alloc = FundAllocation.objects.create(fund=self.art, amount=Decimal("1000"), period="2026-09")
        acc = Account.objects.create(name="Каса тест")
        self.tx = Transaction.objects.create(direction="out", amount=Decimal("500"), amount_uah=Decimal("500"),
                                             account=acc, fin_article=self.art, date=date(2026, 9, 1))
        self.before = FinModelArticle.objects.count()

    def run_cmd(self, *args):
        out = StringIO()
        call_command("seed_finmodel", *args, stdout=out)
        return out.getvalue()

    def assert_existing_intact(self):
        self.assertTrue(FinModelArticle.objects.filter(pk=self.art.pk, value=Decimal("15000")).exists())
        self.assertTrue(FundAllocation.objects.filter(pk=self.alloc.pk).exists())
        self.tx.refresh_from_db()
        self.assertEqual(self.tx.fin_article_id, self.art.pk)

    def test_no_flags_refuses_and_deletes_nothing(self):
        with self.assertRaises(CommandError):
            self.run_cmd()
        self.assertEqual(FinModelArticle.objects.count(), self.before)
        self.assert_existing_intact()

    def test_force_reset_needs_both_flags(self):
        for args in (["--force-reset"], ["--i-understand"]):
            with self.assertRaises(CommandError):
                self.run_cmd(*args)
        self.assertEqual(FinModelArticle.objects.count(), self.before)
        self.assert_existing_intact()

    def test_dry_run_reports_impact_and_changes_nothing(self):
        out = self.run_cmd("--force-reset", "--i-understand", "--dry-run")
        self.assertIn("DRY-RUN", out)
        self.assertIn("finance.FundAllocation.fund: 1", out)
        self.assertIn("finance.Transaction.fin_article: 1", out)
        self.assertEqual(FinModelArticle.objects.count(), self.before)
        self.assert_existing_intact()

    def test_missing_only_adds_without_touching_existing(self):
        # перейменована в проді стаття складу з тим самим code — дубль не створюється
        FinModelArticle.objects.create(category="warehouse_rate", name="Тонування (% від ціни тонування)",
                                       code="WH_TINT_PCT", value=Decimal("25"))
        self.run_cmd("--missing-only")
        self.assert_existing_intact()
        self.assertFalse(FinModelArticle.objects.filter(category="warehouse_rate", name="Тонування").exists())
        after = FinModelArticle.objects.count()
        self.run_cmd("--missing-only")  # повторно — нічого нового
        self.assertEqual(FinModelArticle.objects.count(), after)

    def test_empty_table_seeds_all(self):
        FinModelArticle.objects.all().delete()
        self.run_cmd()
        self.assertEqual(FinModelArticle.objects.count(), len(ARTICLES))
        self.assertTrue(FinModelArticle.objects.filter(code="WH_PACK_5").exists())

    def test_force_reset_with_confirmation_recreates(self):
        self.run_cmd("--force-reset", "--i-understand")
        self.assertEqual(FinModelArticle.objects.count(), len(ARTICLES))
        self.assertFalse(FundAllocation.objects.filter(pk=self.alloc.pk).exists())
        self.tx.refresh_from_db()
        self.assertIsNone(self.tx.fin_article_id)
