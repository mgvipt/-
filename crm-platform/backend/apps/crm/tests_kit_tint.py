"""Тонування тест-набору в угоді (16.09.2026, Олег): галочка на рядку набору → доплата окремим рядком."""
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.finance.models import FinModelArticle
from apps.warehouse.models import Product, ProductComponent

from .models import Deal, DealItem, Funnel, Stage


class KitTintLineTests(TestCase):
    def setUp(self):
        for code, val in (("KIT_TINT_PRICE_IND", "200"), ("KIT_TINT_PRICE_RICH", "250")):
            FinModelArticle.objects.create(code=code, category="warehouse_rate", name=code,
                                           value=Decimal(val), value_type="fixed_per_deal", active=True)
        self.u = User.objects.create_superuser(username="boss", password="x")
        self.f = Funnel.objects.create(name="21 Основний продукт")
        self.st = Stage.objects.create(funnel=self.f, name="Нова", order=0)
        self.svc = Product.objects.create(name="Послуга тонування", track_stock=False, price=Decimal("190"))
        comp = Product.objects.create(name="Pattera Fine (FF 0102)", unit="кг", cost=Decimal("100"))
        self.kit = Product.objects.create(name="Травертин «Тестовий набір Pattera Fine»", price=Decimal("340"))
        ProductComponent.objects.create(bundle=self.kit, component=comp, quantity=Decimal("0.25"))
        self.deal = Deal.objects.create(title="T", funnel=self.f, stage=self.st, amount=Decimal("340"))
        self.item = DealItem.objects.create(deal=self.deal, product=self.kit, quantity=1, price=Decimal("340"))
        self.c = APIClient(); self.c.force_authenticate(self.u)

    def _set(self, mode, item=None):
        return self.c.post("/api/deals/%d/set_item_tint/" % self.deal.id,
                           {"item": (item or self.item).id, "mode": mode}, format="json")

    def test_individual_adds_line_and_removing_takes_it_away(self):
        r = self._set("ind")
        self.assertEqual(r.status_code, 200)
        auto = self.deal.items.filter(tint_mode="auto_ind").first()
        self.assertIsNotNone(auto)
        self.assertEqual(auto.product_id, self.svc.id)
        self.assertEqual(auto.price, Decimal("200"))
        self.assertEqual(auto.quantity, Decimal("1"))
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.amount, Decimal("540"))      # 340 набір + 200 доплата
        self._set("")
        self.assertFalse(self.deal.items.filter(tint_mode="auto_ind").exists())
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.amount, Decimal("340"))

    def test_rich_is_more_expensive_and_quantity_follows_kits(self):
        self._set("rich")
        auto = self.deal.items.get(tint_mode="auto_rich")
        self.assertEqual(auto.price, Decimal("250"))
        self.c.post("/api/deals/%d/update_item/" % self.deal.id, {"item": self.item.id, "quantity": "3"}, format="json")
        auto.refresh_from_db()
        self.assertEqual(auto.quantity, Decimal("3"))           # 3 набори → доплата за 3
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.amount, Decimal("1770"))     # 3×340 + 3×250

    def test_auto_line_cannot_be_ticked_itself(self):
        self._set("ind")
        auto = self.deal.items.get(tint_mode="auto_ind")
        r = self._set("rich", item=auto)
        self.assertEqual(r.status_code, 400)
