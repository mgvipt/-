"""Склад → ЗП (17.09.2026, Олег): ставка по днях місяця; «Інше» більше не ховає тонування наборів;
меню «Відвантаження» — окреме право warehouse.work."""
import datetime
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APIClient

from apps.finance.models import WorkDay
from apps.payroll.models import PayComponent, PayScheme

from .models import WarehousePayrollEntry
from .tests_wh_accrual import _Base


class SalaryDaysTests(_Base):
    def test_days_strip_and_kit_tint_not_other(self):
        first = timezone.localdate().replace(day=1)
        E = WarehousePayrollEntry.objects
        E.create(employee=self.worker, work_date=first, op_type="kit_tint_cat", amount=Decimal("50"))
        E.create(employee=self.worker, work_date=first, op_type="test_set", amount=Decimal("25"))
        WorkDay.objects.create(user=self.worker, date=first, status="worked")
        sc = PayScheme.objects.create(user=self.worker, position="Комірник", valid_from=datetime.date(2020, 1, 1))
        PayComponent.objects.create(scheme=sc, kind="base_by_days", title="За вихід", params={"amount": 8000})
        PayComponent.objects.create(scheme=sc, kind="piece_rate", title="Відрядно")
        c = APIClient(); c.force_authenticate(self.worker)
        r = c.get("/api/warehouse/my-salary/?period=calendar&which=current")
        self.assertEqual(r.status_code, 200)
        labels = {p["op"]: p["label"] for p in r.data["piece"]}
        self.assertNotIn("other", labels)
        self.assertIn("Тонування тест-наборів", labels["kit_tint_cat"])
        day1 = r.data["days"][0]
        self.assertEqual(day1["date"], first.isoformat())
        self.assertEqual(day1["status"], "worked")
        self.assertEqual(day1["piece"], 75.0)
        self.assertGreater(day1["base"], 0)
        self.assertEqual(len(r.data["days"]), (timezone.localdate() - first).days + 1)
        g = [x for x in r.data["deal_groups"] if x["tint"]]
        self.assertTrue(g and float(g[0]["tint"]) == 50.0)   # тонування набору — у колонці «Тонування»

    def test_warehouse_work_permission_in_catalog(self):
        from apps.accounts.models import PERMISSION_CHOICES
        self.assertIn("warehouse.work", dict(PERMISSION_CHOICES))
