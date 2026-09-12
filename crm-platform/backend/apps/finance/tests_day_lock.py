"""Закриті дні (12.09): після «Закрити день» менеджер не змінює суму/дату/рахунок/тип і не видаляє операції
закритих днів; категорію/коментар — може; бухгалтер (finance.day.edit_closed) — може все."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.finance.day_close import close_day
from apps.finance.models import Account, Category, Transaction

D = date(2026, 9, 10)
HOST = "crm.wallcovdec.com.ua"
MANAGER_PERMS = ["finance.view", "finance.tab.journal", "finance.tx.edit", "finance.day.close"]


class DayLockTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.acc = Account.objects.create(name="Каса тест", kind="cash")
        self.acc2 = Account.objects.create(name="ФОП тест")
        self.cat = Category.objects.create(name="Продажі тест", direction="in")
        self.cat2 = Category.objects.create(name="Інше тест", direction="in")
        self.tx = Transaction.objects.create(direction="in", amount=Decimal("1500"), amount_uah=Decimal("1500"),
                                             account=self.acc, category=self.cat, date=D)
        self.mgr = U.objects.create_user("dl-mgr", password="x")
        self.mgr.extra_permissions = MANAGER_PERMS
        self.mgr.save()
        self.acct = U.objects.create_user("dl-acct", password="x")
        self.acct.extra_permissions = MANAGER_PERMS + ["finance.day.edit_closed"]
        self.acct.save()
        close_day(D)
        self.c = APIClient()
        self.c.force_authenticate(self.mgr)

    def _patch(self, client, body):
        return client.patch("/api/transactions/%s/" % self.tx.id, body, format="json", HTTP_HOST=HOST)

    def test_manager_cannot_change_money_fields(self):
        self.assertEqual(self._patch(self.c, {"amount": "1200"}).status_code, 403)
        self.assertEqual(self._patch(self.c, {"account": self.acc2.id}).status_code, 403)
        self.assertEqual(self._patch(self.c, {"date": (D - timedelta(days=1)).isoformat()}).status_code, 403)
        self.tx.refresh_from_db()
        self.assertEqual(self.tx.amount, Decimal("1500"))

    def test_manager_can_change_soft_fields_with_same_money_in_body(self):
        r = self._patch(self.c, {"category": self.cat2.id, "comment": "ок", "amount": "1500.00",
                                 "date": D.isoformat(), "account": self.acc.id, "direction": "in"})
        self.assertIn(r.status_code, (200, 202), r.content[:200])
        self.tx.refresh_from_db()
        self.assertEqual(self.tx.category_id, self.cat2.id)

    def test_manager_cannot_delete_or_create_in_closed_day(self):
        r = self.c.delete("/api/transactions/%s/" % self.tx.id, HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 403)
        r = self.c.post("/api/transactions/", {"direction": "in", "amount": "100", "account": self.acc.id,
                                               "date": D.isoformat()}, format="json", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 403)
        r = self.c.post("/api/transactions/", {"direction": "in", "amount": "100", "account": self.acc.id,
                                               "date": timezone.localdate().isoformat()}, format="json", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 201, r.content[:200])

    def test_accountant_can_edit_closed_day(self):
        c = APIClient()
        c.force_authenticate(self.acct)
        self.assertIn(self._patch(c, {"amount": "1200"}).status_code, (200, 202))
        self.tx.refresh_from_db()
        self.assertEqual(self.tx.amount, Decimal("1200"))

    def test_bulk_edit_skips_closed_for_account(self):
        r = self.c.post("/api/transactions/bulk-edit/", {"ids": [self.tx.id], "set": {"account": self.acc2.id}},
                        format="json", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.json()["updated"], r.json()["locked_skipped"]), (0, 1))
        r = self.c.post("/api/transactions/bulk-edit/", {"ids": [self.tx.id], "set": {"comment": "м'яке поле"}},
                        format="json", HTTP_HOST=HOST)
        self.assertEqual(r.json()["updated"], 1)

    def test_period_lock_reports_day_state(self):
        r = self.c.get("/api/transactions/period-lock/", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["day_closed_until"], D.isoformat())
        self.assertFalse(r.json()["can_edit_closed_day"])
