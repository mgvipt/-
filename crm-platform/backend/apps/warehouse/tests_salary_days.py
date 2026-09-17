"""Склад → ЗП (17.09.2026, Олег): ставка по днях місяця; «Інше» більше не ховає тонування наборів;
меню «Відвантаження» — окреме право warehouse.work."""
import datetime
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APIClient

from apps.finance.models import WorkDay
from apps.payroll.models import PayComponent, PayScheme

from .models import Product, WarehousePayrollEntry
from . import wh_views
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

    def test_day_mode_has_rate_kpi_and_all_piece_lines(self):
        """17.09.2026 (Олег): за день — ставка за вихід, KPI і всі рядки (тонування наборів не губиться)."""
        today = timezone.localdate()
        first = today.replace(day=1)
        last = first.replace(day=28) + datetime.timedelta(days=4)
        last = last - datetime.timedelta(days=last.day)
        E = WarehousePayrollEntry.objects
        E.create(employee=self.worker, work_date=today, op_type="kit_tint_cat", amount=Decimal("200"))
        E.create(employee=self.worker, work_date=today, op_type="shipment_weight", amount=Decimal("7.68"))
        WorkDay.objects.create(user=self.worker, date=today, status="worked")
        sc = PayScheme.objects.create(user=self.worker, position="Комірник", valid_from=first, valid_to=last)
        PayComponent.objects.create(scheme=sc, kind="base_by_days", title="За вихід", params={"amount": 8000})
        PayComponent.objects.create(scheme=sc, kind="piece_rate", title="Відрядно")
        nxt = PayScheme.objects.create(user=self.worker, position="Комірник", valid_from=last + datetime.timedelta(days=1))
        PayComponent.objects.create(scheme=nxt, kind="standard", title="Стандарт складу (до 3 000 ₴)", params={"max": 3000})
        c = APIClient(); c.force_authenticate(self.worker)
        r = c.get("/api/warehouse/my-salary/?date=%s" % today.isoformat())
        self.assertEqual(r.status_code, 200)
        ops = {l["op"]: l for l in r.data["lines"]}
        self.assertIn("kit_tint_cat", ops)
        self.assertEqual(sum(float(l["amount"]) for l in r.data["lines"]), float(r.data["total"]))
        day = r.data["day"]
        self.assertGreater(day["base"], 0)
        self.assertEqual(day["piece"], 207.68)
        self.assertAlmostEqual(day["total"], day["base"] + day["kpi"] + day["piece"], places=2)
        kinds = [l["op"] for l in day["lines"]]
        self.assertEqual(kinds[:2], ["base", "kpi"])
        self.assertIn("kit_tint_cat", kinds)
        self.assertFalse(r.data["kpi"]["active"])
        self.assertEqual(r.data["kpi"]["max"], 3000)
        m = c.get("/api/warehouse/my-salary/?period=calendar&which=current")
        self.assertIn("kpi", m.data)
        self.assertTrue(all("lines" in x for x in m.data["days"]))

    def test_warehouse_work_permission_in_catalog(self):
        from apps.accounts.models import PERMISSION_CHOICES
        self.assertIn("warehouse.work", dict(PERMISSION_CHOICES))


class SamplePayTests(_Base):
    """17.09.2026 (Олег): за відправлену викраску складу 50 ₴ (колір з каталогу) і 100 ₴ (індивідуальний)."""

    def test_samples_accrued_on_shipment(self):
        from .tests_wh_accrual import set_rate
        set_rate("WH_SAMPLE_CAT", "50")
        set_rate("WH_SAMPLE_IND", "100")
        sample = Product.objects.create(name="Викраска 10×30 см · Sirena Silk", price=Decimal("150"),
                                        cost=Decimal("59"), weight_kg=Decimal("0.02"))
        d = self.deal(550)
        self.item(d, sample, qty=3, price=150)                       # 3 з каталогу
        ind = self.item(d, sample, qty=1, price=150)
        ind.tint_mode = "s_ind"; ind.save(update_fields=["tint_mode"])
        j = self.job(d)
        wh_views._finalize(j, self.worker)
        self.assertEqual(sorted(self.amounts(j, "samples")), [Decimal("100.00"), Decimal("150.00")])  # 3×50 і 1×100
        self.assertEqual(self.amounts(j, "test_set"), [])            # викраска — не тест-набір
        rows = {e.op_type: e.note for e in WarehousePayrollEntry.objects.filter(job=j)}
        self.assertIn("викр.", rows["samples"])

    def test_sheet_rate_ignored_when_per_sample_rate_set(self):
        from .tests_wh_accrual import set_rate
        from . import tare_samples
        set_rate("WH_SAMPLE_SHEET", "40")
        set_rate("WH_SAMPLE_CAT", "50")
        self.assertEqual(tare_samples._rate("WH_SAMPLE_CAT"), Decimal("50"))
