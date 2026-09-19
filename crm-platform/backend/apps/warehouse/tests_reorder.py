"""19.09.2026: перевірка наявності і заявка на дозамовлення зі складу."""
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.crm.models import Contact, Task

from .models import Product, ReorderRequest, StockDocument, StockMovement, Warehouse
from .reorder import low_stock, suggest_qty


class ReorderTests(TestCase):
    def setUp(self):
        self.boss = User.objects.create_superuser(username="ro_boss", password="x")
        self.wh_user = User.objects.create_user(username="ro_wh", password="x", account_kind="staff",
                                                extra_permissions=["warehouse.work"])
        self.sup_a = Contact.objects.create(first_name="Мадекс", kinds=["supplier"])
        self.sup_b = Contact.objects.create(first_name="Капарол", kinds=["supplier"])
        w = Warehouse.objects.create(name="Основний", is_default=True)
        self.tape = Product.objects.create(name="Скотч пакувальний", unit="шт", min_stock=Decimal("10"), reorder_qty=Decimal("6"),
                                           supplier=self.sup_a)
        self.silk = Product.objects.create(name="Мокрий шовк Bianco", unit="кг", min_stock=Decimal("20"))
        self.ok = Product.objects.create(name="Грунт", unit="кг", min_stock=Decimal("5"))
        doc = StockDocument.objects.create(kind="in", number="ПР-1", warehouse=w, supplier=self.sup_b, posted=True)
        StockMovement.objects.create(document=doc, product=self.tape, quantity=Decimal("4"), price=Decimal("50"))
        StockMovement.objects.create(document=doc, product=self.silk, quantity=Decimal("8"), price=Decimal("400"))
        StockMovement.objects.create(document=doc, product=self.ok, quantity=Decimal("30"), price=Decimal("60"))

    def test_low_stock_appears_by_itself(self):
        names = {x["name"]: x for x in low_stock()}
        self.assertEqual(set(names), {"Скотч пакувальний", "Мокрий шовк Bianco"})
        self.assertEqual(names["Мокрий шовк Bianco"]["suggest"], 32.0)   # до мінімуму ×2: 40 − 8
        self.assertEqual(suggest_qty(self.tape, Decimal("4")), Decimal("18"))  # треба 16 → кратно 6 → 18

    def test_request_splits_tasks_by_supplier(self):
        c = APIClient(); c.force_authenticate(self.wh_user)
        r = c.post("/api/warehouse/reorder/", {"lines": [{"product": self.tape.id, "qty": 18},
                                                         {"product": self.silk.id, "qty": 32, "note": "Bianco"}]}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["tasks"], 2)
        titles = sorted(Task.objects.values_list("title", flat=True))
        self.assertTrue(titles[0].startswith("🛒 Дозамовлення · Капарол"))    # шовк — з останнього приходу
        self.assertTrue(titles[1].startswith("🛒 Дозамовлення · Мадекс"))     # скотч — з картки товару
        self.assertEqual(set(Task.objects.values_list("assignee_id", flat=True)), {self.boss.id})
        self.assertEqual(ReorderRequest.objects.get().created_by, self.wh_user)

    def test_staff_view_has_no_suppliers_and_outsiders_refused(self):
        c = APIClient(); c.force_authenticate(self.wh_user)
        low = c.get("/api/warehouse/reorder/").data["low"]
        self.assertNotIn("supplier", low[0])
        outsider = User.objects.create_user(username="ro_out", password="x")
        c.force_authenticate(outsider)
        self.assertEqual(c.get("/api/warehouse/reorder/").status_code, 403)
