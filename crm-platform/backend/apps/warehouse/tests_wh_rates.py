"""15.09.2026 (whpay): склад рахує і показує ставки ЛИШЕ з Фінмоделі (ті самі, що в «Ставках співробітників»),
без запасних чисел у коді. Лише ізольована тестова БД."""
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.crm.models import Deal, DealItem, Funnel, Stage
from apps.finance.models import FinModelArticle

from . import wh_views
from .models import Product, Warehouse, WarehouseJob, WarehousePayrollEntry
from .tests_wh_accrual import RATES, set_rate


class LiveRatesTests(TestCase):
    def setUp(self):
        Warehouse.objects.create(name="Основний", is_default=True)
        for code, val in RATES:
            set_rate(code, val)
        self.f = Funnel.objects.create(name="21 Основний продукт")
        self.st = Stage.objects.create(funnel=self.f, name="Нова", order=0)
        self.worker = User.objects.create_user(username="whr_worker", password="x")
        self.owner = User.objects.create_superuser("whr_owner", "whr@example.test", "x")
        self.paint = Product.objects.create(name="Шовк 5 кг", weight_kg=Decimal("5"), price=Decimal("1000"), cost=Decimal("400"))

    def ship(self, qty=2):
        d = Deal.objects.create(title="T", funnel=self.f, stage=self.st, amount=Decimal("2000"), qualification={"kits": []})
        DealItem.objects.create(deal=d, product=self.paint, quantity=Decimal(qty), price=Decimal("1000"))
        j = WarehouseJob.objects.create(deal=d, assignee=self.worker, status="packing")
        wh_views._finalize(j, self.worker)
        return {e.op_type: e for e in WarehousePayrollEntry.objects.filter(job=j)}

    def rates(self, client, url="/api/warehouse/my-salary/?period=month"):
        r = client.get(url)
        self.assertEqual(r.status_code, 200)
        return r.data["rates"]

    def test_accrual_follows_live_article_values(self):
        e = self.ship()                                                   # 10 кг × 1,5; одне місце ≤10 кг → 13
        self.assertEqual((e["shipment_weight"].amount, e["packing"].amount), (Decimal("15.00"), Decimal("13.00")))
        set_rate("WH_RATE_KG", "2")                                      # змінили в «Ставках співробітників» / Фінмоделі
        set_rate("WH_PACK_10", "15")
        e2 = self.ship()
        self.assertEqual((e2["shipment_weight"].amount, e2["packing"].amount), (Decimal("20.00"), Decimal("15.00")))
        self.assertEqual(e2["shipment_weight"].rate_applied, Decimal("2"))
        e["shipment_weight"].refresh_from_db()
        self.assertEqual(e["shipment_weight"].amount, Decimal("15.00"))  # старий запис не переписано

    def test_disabled_or_missing_article_pays_zero_no_hidden_defaults(self):
        set_rate("WH_RATE_KG", "1.5", active=False)                      # вимкнено у Фінмоделі
        FinModelArticle.objects.filter(code="WH_PACK_10").delete()        # статті немає
        e = self.ship()
        self.assertEqual((e["shipment_weight"].amount, e["packing"].amount), (Decimal("0.00"), Decimal("0.00")))
        c = APIClient()
        c.force_authenticate(self.worker)
        rt = self.rates(c)
        w = " ".join(rt["warnings"])
        self.assertIn("вимкнено", w)
        self.assertIn("немає у Фінмоделі", w)
        kg = next(x for x in rt["items"] if x["code"] == "WH_RATE_KG")
        self.assertEqual((kg["value"], kg["active"], kg["found"]), (0.0, False, True))

    def test_salary_tabs_show_live_rates_and_edit_link_only_for_owner(self):
        c = APIClient()
        c.force_authenticate(self.worker)
        rt = self.rates(c)
        vals = {x["code"]: x["value"] for x in rt["items"]}
        self.assertEqual((vals["WH_RATE_KG"], vals["WH_PACK_5"], vals["bundle_assembly"], vals["WH_RATE_DAY"]), (1.5, 8.0, 50.0, 300.0))
        self.assertFalse(rt["can_edit"])
        self.assertIn("7 × 1,5 + 13 = 23,5", rt["example"])
        set_rate("WH_TINT_PCT", "25")
        rt2 = self.rates(c, "/api/warehouse/my-salary/?period=calendar&which=current")
        self.assertEqual(next(x for x in rt2["items"] if x["code"] == "WH_TINT_PCT")["value"], 25.0)
        self.assertIn("25% = 250", rt2["example"])
        o = APIClient()
        o.force_authenticate(self.owner)
        rt3 = self.rates(o, "/api/warehouse/dashboard/?period=month")
        self.assertTrue(rt3["can_edit"])
        self.assertEqual(rt3["edit_url"], "/settings?tab=payrates")

    def test_day_close_uses_live_day_rate(self):
        set_rate("WH_RATE_DAY", "400")
        c = APIClient()
        c.force_authenticate(self.worker)
        self.assertEqual(c.post("/api/warehouse/day/start/", {}, format="json").status_code, 200)
        self.assertEqual(c.post("/api/warehouse/day/close/", {}, format="json").status_code, 200)
        e = WarehousePayrollEntry.objects.get(employee=self.worker, op_type="workday")
        self.assertEqual((e.amount, e.rate_applied), (Decimal("400.00"), Decimal("400")))
        self.assertIn("день 400 ₴", wh_views.rates_short())
