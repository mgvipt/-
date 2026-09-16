"""Мите відро і викраски з А3 (16.09.2026, Олег). Лише ізольована тестова БД."""
from decimal import Decimal

from rest_framework.test import APIClient

from .models import (Product, SampleRecipe, StockDocument, StockMovement, WarehousePayrollEntry, WarehousePhoto, WashedTare)
from .tests_wh_accrual import _Base, set_rate


class WashedBucketTests(_Base):
    def setUp(self):
        super().setUp()
        set_rate("WH_WASHED_PCT", "30")
        self.tare = Product.objects.create(name="Тара 5,5л", unit="шт", price=Decimal("69"), cost=Decimal("35.64"), track_stock=True)
        self.tare_w = Product.objects.create(name="Тара 5,5л · мите відро", unit="шт", price=Decimal("69"), cost=Decimal("0"), track_stock=True)
        WashedTare.objects.create(new=self.tare, washed=self.tare_w)
        self.c = APIClient(); self.c.force_authenticate(self.worker)
        from django.contrib.auth.models import Permission  # noqa: F401  (права — суперкористувач нижче)
        self.worker.is_superuser = True; self.worker.save(update_fields=["is_superuser"])

    def test_wash_then_ship_writes_off_washed_and_pays_30pct(self):
        r = self.c.post("/api/warehouse/washed/", {"product": self.tare.id, "qty": 3}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.tare_w.stock(), Decimal("3"))
        d = self.deal(1100)
        self.item(d, self.paint, qty=1, price=1000)
        self.item(d, self.tare, qty=2, price=69)
        j = self.job(d)
        r = self.c.post("/api/warehouse/jobs/%d/washed/" % j.id, {"product": self.tare.id, "qty": 5}, format="json")
        self.assertEqual(r.status_code, 400)                      # більше, ніж у замовленні
        r = self.c.post("/api/warehouse/jobs/%d/washed/" % j.id, {"product": self.tare.id, "qty": 2}, format="json")
        self.assertEqual(r.status_code, 200)
        for k in ("buckets", "parcel", "invoice"):
            WarehousePhoto.objects.create(job=j, deal=d, employee=self.worker, kind=k, image="warehouse_photos/t_%s.jpg" % k)
        r = self.c.post("/api/warehouse/jobs/%d/ship/" % j.id, {}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.tare_w.stock(), Decimal("1"))       # 3 помили − 2 поїхали
        self.assertEqual(self.tare.stock(), Decimal("0"))         # нова тара не списалась
        e = WarehousePayrollEntry.objects.get(job=j, op_type="washed_bucket")
        self.assertEqual(e.amount, Decimal("21.38"))              # 35,64 × 30% × 2

    def test_cannot_mark_more_washed_than_in_stock(self):
        d = self.deal(200)
        self.item(d, self.tare, qty=2, price=69)
        j = self.job(d)
        r = self.c.post("/api/warehouse/jobs/%d/washed/" % j.id, {"product": self.tare.id, "qty": 1}, format="json")
        self.assertEqual(r.status_code, 400)                      # митих на складі 0


class SamplesTests(_Base):
    def setUp(self):
        super().setUp()
        self.worker.is_superuser = True; self.worker.save(update_fields=["is_superuser"])
        self.c = APIClient(); self.c.force_authenticate(self.worker)
        self.silk = Product.objects.create(name="Sirena Silk", unit="кг", cost=Decimal("400"), track_stock=True)
        self.under = Product.objects.create(name="Second Layer", unit="кг", cost=Decimal("80"), track_stock=True)
        self.paper = Product.objects.create(name="Папір А3 для викрасок", unit="шт", cost=Decimal("6"), track_stock=True)
        self.sample = Product.objects.create(name="Викраска Мокрий шовк", unit="шт", price=Decimal("50"), track_stock=True)
        self.r = SampleRecipe.objects.create(name="Мокрий шовк", target=self.sample, per_sheet=4, paper=self.paper,
                                             lines=[{"product": self.silk.id, "kg": 0.05}, {"product": self.under.id, "kg": 0.05}])

    def test_produce_samples_consumes_material_and_adds_stock(self):
        r = self.c.post("/api/warehouse/samples/", {"recipe": self.r.id, "sheets": 2}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.sample.stock(), Decimal("8"))       # 2 аркуші × 4
        self.assertEqual(self.silk.stock(), Decimal("-0.1"))
        self.assertEqual(self.paper.stock(), Decimal("-2"))
        self.sample.refresh_from_db()
        self.assertEqual(self.sample.cost, Decimal("7.50"))       # (0,1×400 + 0,1×80 + 2×6) / 8
        self.assertFalse(WarehousePayrollEntry.objects.filter(op_type="samples").exists())  # ставку не увімкнено
        set_rate("WH_SAMPLE_SHEET", "20")
        r = self.c.post("/api/warehouse/samples/", {"recipe": self.r.id, "sheets": 1, "lines": [{"product": self.silk.id, "kg": 0.1}]}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.silk.stock(), Decimal("-0.2"))      # грами поправили на 100 г
        self.assertEqual(WarehousePayrollEntry.objects.get(op_type="samples").amount, Decimal("20.00"))
