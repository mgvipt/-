"""Склад: нарахування за відвантаження (14.09.2026, wh-accrual).
Лише ізольована тестова БД. Фото відвантаження — рядки без файлів (на диск нічого не пишеться)."""
import datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.crm.models import Deal, DealItem, Funnel, Stage
from apps.finance.models import FinModelArticle

from . import wh_views
from .models import Product, ProductComponent, Warehouse, WarehouseJob, WarehousePayrollEntry, WarehousePhoto

RATES = [("WH_RATE_KG", "1.5"), ("WH_PACK_5", "8"), ("WH_PACK_10", "13"), ("WH_PACK_20", "20"),
         ("WH_TINT_PCT", "20"), ("WH_RATE_DAY", "300"), ("bundle_assembly", "50")]


def set_rate(code, value, active=True):
    qs = FinModelArticle.objects.filter(code=code)
    if qs.exists():
        qs.update(value=Decimal(value), active=active)
    else:
        FinModelArticle.objects.create(code=code, category="warehouse_rate", name=code, value=Decimal(value),
                                       value_type="fixed_per_deal", active=active)


class _Base(TestCase):
    def setUp(self):
        Warehouse.objects.create(name="Основний", is_default=True)
        for code, val in RATES:
            set_rate(code, val)
        self.f = Funnel.objects.create(name="21 Основний продукт")
        self.st = Stage.objects.create(funnel=self.f, name="Нова", order=0)
        self.worker = User.objects.create_user(username="wh_inna", password="x")
        self.other = User.objects.create_user(username="wh_larionova", password="x")
        self.tint = Product.objects.create(name="Послуга тонування", track_stock=False, price=0)
        self.paint = Product.objects.create(name="Шовк 5 кг", weight_kg=Decimal("5"), price=Decimal("1000"),
                                            cost=Decimal("400"))
        self.noweight = Product.objects.create(name="Second Layer (FL 1006)", price=Decimal("200"), cost=Decimal("50"))
        comp = Product.objects.create(name="Pattera Fine (FF 0102)", cost=Decimal("100"))
        self.ts = Product.objects.create(name="Травертин «Набір Pattera» (з тонуванням)", price=Decimal("460"))
        ProductComponent.objects.create(bundle=self.ts, component=comp, quantity=Decimal("0.8"))  # набір без «тестов» у назві

    def deal(self, amount=1000, kits=None):
        return Deal.objects.create(title="T", funnel=self.f, stage=self.st, amount=Decimal(str(amount)),
                                   qualification={"kits": kits or []})

    def item(self, deal, product, qty=1, price=0, discount_pct=0):
        return DealItem.objects.create(deal=deal, product=product, quantity=Decimal(str(qty)),
                                       price=Decimal(str(price)), discount_pct=Decimal(str(discount_pct)))

    def job(self, deal, tinted=None):
        return WarehouseJob.objects.create(deal=deal, assignee=self.worker, status="packing", tinted_kits=tinted or [])

    def amounts(self, job, op):
        return [e.amount for e in WarehousePayrollEntry.objects.filter(job=job, op_type=op).order_by("id")]


class TintingTests(_Base):
    def test_tinting_from_service_line_without_manual_mark(self):
        d = self.deal(5000)
        self.item(d, self.paint, qty=2, price=1000)                 # 10 кг
        self.item(d, self.tint, qty=1, price=1000, discount_pct=10)  # рядок 1000 − 10% = 900
        j = self.job(d)                                              # ручної позначки немає
        wh_views._finalize(j, self.worker)
        self.assertEqual(self.amounts(j, "tinting"), [Decimal("180.00")])   # 20% × 900
        e = WarehousePayrollEntry.objects.get(job=j, op_type="tinting")
        self.assertEqual(e.base_value, Decimal("900.00"))
        # вага і упаковка — як і раніше
        self.assertEqual(self.amounts(j, "shipment_weight"), [Decimal("15.00")])  # 10 кг × 1.5
        self.assertEqual(self.amounts(j, "packing"), [Decimal("13.00")])          # одне місце ≤10 кг
        j.refresh_from_db()
        self.assertEqual(j.done_snapshot["tint_source"], "service_line")
        self.assertEqual(j.tintings_base, Decimal("900.00"))

    def test_service_line_and_manual_mark_not_double_counted(self):
        d = self.deal(5000, kits=[{"material": "A", "tint": True}, {"material": "B", "tint": True}])
        self.item(d, self.tint, qty=1, price=1000)
        j = self.job(d, tinted=[0, 1])                               # і позначка, і рядок
        wh_views._finalize(j, self.worker)
        self.assertEqual(self.amounts(j, "tinting"), [Decimal("200.00")])   # лише рядок: 20% × 1000

    def test_manual_mark_still_works_without_service_line(self):
        d = self.deal(1000, kits=[{"tint": True}, {"tint": False}])
        j = self.job(d, tinted=[0])
        d.refresh_from_db()
        wh_views._finalize(j, self.worker)
        expected = (d.amount / 2 * Decimal("0.2")).quantize(Decimal("0.01"))
        self.assertEqual(self.amounts(j, "tinting"), [expected])
        j.refresh_from_db()
        self.assertEqual(j.done_snapshot["tint_source"], "manual")


class TestSetTests(_Base):
    def test_test_set_uses_live_article_value(self):
        d = self.deal(920)
        self.item(d, self.ts, qty=2, price=460)
        j = self.job(d)
        wh_views._finalize(j, self.worker)
        self.assertEqual(self.amounts(j, "test_set"), [Decimal("100.00")])     # 2 × 50
        set_rate("bundle_assembly", "70")                                     # Олег змінив ставку
        d2 = self.deal(460)
        self.item(d2, self.ts, qty=1, price=460)
        j2 = self.job(d2)
        wh_views._finalize(j2, self.worker)
        self.assertEqual(self.amounts(j2, "test_set"), [Decimal("70.00")])
        self.assertEqual(self.amounts(j, "test_set"), [Decimal("100.00")])    # старий запис не переписано
        self.assertEqual(WarehousePayrollEntry.objects.get(job=j2, op_type="test_set").get_op_type_display(),
                         "Збірка тестового набору")

    def test_test_set_by_name_and_disabled_article(self):
        by_name = Product.objects.create(name="Тестовий набір")               # без компонентів
        d = self.deal(300)
        self.item(d, by_name, qty=1, price=300)
        j = self.job(d)
        wh_views._finalize(j, self.worker)
        self.assertEqual(self.amounts(j, "test_set"), [Decimal("50.00")])
        set_rate("bundle_assembly", "50", active=False)                       # статтю вимкнено → не нараховуємо
        d2 = self.deal(300)
        self.item(d2, by_name, qty=1, price=300)
        j2 = self.job(d2)
        wh_views._finalize(j2, self.worker)
        self.assertEqual(self.amounts(j2, "test_set"), [])


class WeightlessTests(_Base):
    def test_weightless_list_in_job_detail_and_ship_not_blocked(self):
        d = self.deal(1000)
        self.item(d, self.noweight, qty=3, price=200)
        self.item(d, self.tint, qty=1, price=100)     # послуга — не в списку
        self.item(d, self.ts, qty=1, price=460)       # тест-набір — оплачується за набір, не в списку
        j = self.job(d)
        c = APIClient()
        c.force_authenticate(self.worker)
        r = c.get("/api/warehouse/jobs/%d/" % j.id)
        self.assertEqual(r.status_code, 200)
        self.assertEqual([w["product_id"] for w in r.data["weightless"]], [self.noweight.id])
        self.assertEqual(r.data["weightless"][0]["qty"], "3.00")
        self.assertTrue(r.data["weightless_zero_total"])
        WarehousePhoto.objects.create(job=j, deal=d, employee=self.worker, kind="buckets", image="warehouse_photos/t_b.jpg")
        WarehousePhoto.objects.create(job=j, deal=d, employee=self.worker, kind="parcel", image="warehouse_photos/t_p.jpg")
        r = c.post("/api/warehouse/jobs/%d/ship/" % j.id, {}, format="json")
        self.assertEqual(r.status_code, 200)                                  # НЕ блокується
        self.assertEqual(r.data["status"], "shipped")
        self.assertEqual([w["product_id"] for w in r.data["weightless"]], [self.noweight.id])
        self.assertFalse(WarehousePayrollEntry.objects.filter(job=j, op_type__in=["shipment_weight", "packing"]).exists())
        self.assertEqual({a["op"] for a in r.data["accrued"]}, {"tinting", "test_set"})

    def test_partial_weight_is_not_zero_total(self):
        d = self.deal(1000)
        self.item(d, self.paint, qty=1, price=1000)
        self.item(d, self.noweight, qty=1, price=200)
        j = self.job(d)
        c = APIClient()
        c.force_authenticate(self.worker)
        r = c.get("/api/warehouse/jobs/%d/" % j.id)
        self.assertEqual(len(r.data["weightless"]), 1)
        self.assertFalse(r.data["weightless_zero_total"])


class CalendarMonthTests(_Base):
    def test_calendar_month_only_own_data_with_scheme(self):
        from apps.payroll.models import PayComponent, PayScheme
        first = timezone.localdate().replace(day=1)
        prev = first - datetime.timedelta(days=1)
        E = WarehousePayrollEntry.objects
        E.create(employee=self.worker, work_date=first, op_type="test_set", amount=Decimal("100"))
        E.create(employee=self.worker, work_date=first, op_type="tinting", amount=Decimal("40"))
        E.create(employee=self.worker, work_date=first, op_type="error", amount=Decimal("-30"))
        E.create(employee=self.worker, work_date=prev, op_type="workday", amount=Decimal("300"))
        E.create(employee=self.other, work_date=first, op_type="test_set", amount=Decimal("999"))
        sc = PayScheme.objects.create(user=self.worker, position="Комірник", valid_from=datetime.date(2020, 1, 1))
        PayComponent.objects.create(scheme=sc, kind="fixed_monthly", title="Ставка", params={"amount": 8000})
        PayComponent.objects.create(scheme=sc, kind="piece_rate", title="Відрядно")

        c = APIClient()
        c.force_authenticate(self.worker)
        r = c.get("/api/warehouse/my-salary/?period=calendar&which=current&user=%d&employee=%d" % (self.other.id, self.other.id))
        self.assertEqual(r.status_code, 200)
        ops = {p["op"]: Decimal(p["amount"]) for p in r.data["piece"]}
        self.assertEqual(ops, {"test_set": Decimal("100.00"), "tinting": Decimal("40.00"), "error": Decimal("-30.00")})
        self.assertEqual(Decimal(r.data["piece_total"]), Decimal("110.00"))
        self.assertEqual([l["amount"] for l in r.data["base_lines"]], [8000])
        self.assertEqual(r.data["total"], 8110)                       # ставка + відрядні, без подвійного
        self.assertEqual(r.data["period"], first.strftime("%Y-%m"))

        r2 = c.get("/api/warehouse/my-salary/?period=calendar&which=prev")
        self.assertEqual({p["op"] for p in r2.data["piece"]}, {"workday"})

        self.assertEqual(c.get("/api/warehouse/my-salary/?period=calendar&which=2020-01").status_code, 400)

        c2 = APIClient()
        c2.force_authenticate(self.other)
        r3 = c2.get("/api/warehouse/my-salary/?period=calendar")
        self.assertEqual(Decimal(r3.data["piece_total"]), Decimal("999.00"))
        self.assertIsNone(r3.data["scheme"])
        self.assertEqual(r3.data["total"], 999)                       # схеми немає → лише відрядні

    def test_old_30_day_view_unchanged_and_lists_test_set(self):
        WarehousePayrollEntry.objects.create(employee=self.worker, work_date=timezone.localdate(),
                                             op_type="test_set", amount=Decimal("50"))
        c = APIClient()
        c.force_authenticate(self.worker)
        r = c.get("/api/warehouse/my-salary/?period=month")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["period"], "month")
        self.assertEqual([l["op"] for l in r.data["lines"]], ["test_set"])
