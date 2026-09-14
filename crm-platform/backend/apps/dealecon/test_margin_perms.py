"""14.09.2026 (margin-perms): хто бачить маржу угоди і «Економіку угоди»; матеріали пакування — % фонду Олега.
Лише ізольована тестова БД (Postgres); жодних зовнішніх запитів і повідомлень."""
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import PERMISSION_CHOICES, User
from apps.crm.models import Deal, DealItem, Funnel, Stage
from apps.finance.models import FinModelArticle
from apps.warehouse.models import Product, WarehousePayrollEntry

from . import services
from .services import compute

BASE_PERMS = ["deal.view", "deal.view.all"]


class _Base(TestCase):
    def setUp(self):
        services._TABLES.clear()
        # детерміновано: без фонду пакування, поки тест сам його не створить
        FinModelArticle.objects.filter(name__icontains="упаков").update(active=False)
        self.f = Funnel.objects.create(name="21 Основний продукт")
        self.st = Stage.objects.create(funnel=self.f, name="Нова", order=0)
        self.goods = Product.objects.create(name="Шовк", cost=Decimal("100"), price=Decimal("300"))
        self.svc = Product.objects.create(name="Алмазне свердління", track_stock=False, cost_pct=Decimal("40"),
                                          price=Decimal("1000"))
        self.owner = User.objects.create_superuser(username="owner", password="x", email="o@example.com")
        self.d = Deal.objects.create(title="T", funnel=self.f, stage=self.st, amount=Decimal("1000"))
        DealItem.objects.create(deal=self.d, product=self.goods, quantity=Decimal("1"), price=Decimal("1000"),
                                cost=Decimal("400"))
        self.c = APIClient()

    def user(self, name, perms):
        u = User.objects.create_user(username=name, password="x")
        u.extra_permissions = perms
        u.save()
        return u

    def get(self, user, url):
        self.c.force_authenticate(user)
        return self.c.get(url)


class CatalogueTests(_Base):
    def test_new_codes_in_catalogue_owner_has_manager_not(self):
        codes = dict(PERMISSION_CHOICES)
        self.assertIn("deal.margin.view", codes)
        self.assertIn("deal.economics.view", codes)
        self.assertTrue({"deal.margin.view", "deal.economics.view"} <= self.owner.effective_permissions())
        mgr = self.user("m0", BASE_PERMS + ["product.cost.view"])
        self.assertFalse(mgr.has_perm_code("deal.margin.view"))
        self.assertFalse(mgr.has_perm_code("deal.economics.view"))


class DealCardMarginTests(_Base):
    def test_manager_sees_only_earnings_owner_and_rop_see_margin(self):
        url = "/api/deals/%d/" % self.d.pk
        r = self.get(self.owner, url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["margin"], 600.0)
        self.assertIn("from_margin", r.data["bonus"])
        owner_total = r.data["bonus"]["total"]

        mgr = self.user("ilona_t", BASE_PERMS + ["product.cost.view"])    # собівартість ≠ маржа
        r = self.get(mgr, url)
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.data["margin"])
        self.assertNotIn("from_margin", r.data["bonus"])
        self.assertNotIn("margin_pct", r.data["bonus"])
        self.assertEqual(r.data["bonus"]["total"], owner_total)             # заробіток той самий, що бачить власник

        rop = self.user("rop_t", BASE_PERMS + ["deal.margin.view"])
        r = self.get(rop, url)
        self.assertEqual(r.data["margin"], 600.0)
        self.assertIn("from_margin", r.data["bonus"])

        denied = self.user("denied_t", BASE_PERMS + ["deal.margin.view"])
        denied.denied_permissions = ["deal.margin.view"]                     # заборона сильніша за видачу
        denied.save()
        self.assertIsNone(self.get(denied, url).data["margin"])


class EconomicsApiPermTests(_Base):
    def test_economics_api_requires_new_perm(self):
        url = "/api/deal-economics/%d/" % self.d.pk
        cost_only = self.user("cost_t", BASE_PERMS + ["product.cost.view", "deal.margin.view"])
        econ = self.user("econ_t", BASE_PERMS + ["deal.economics.view"])
        self.assertEqual(self.get(cost_only, url).status_code, 403)
        self.assertEqual(self.get(cost_only, "/api/deal-economics/settings/").status_code, 403)
        r = self.get(econ, url)
        self.assertEqual((r.status_code, r.data["margin"]), (200, 600.0))
        self.assertEqual(self.get(econ, "/api/deal-economics/settings/").status_code, 200)
        self.assertEqual(self.get(self.owner, url).status_code, 200)
        r = self.get(self.owner, "/api/deal-economics/settings/")
        self.assertIsNone(r.data["pack_material_fund_pct"])                  # фонду немає → запасна норма
        self.assertEqual(r.data["pack_material_per_shipment"], 22.0)


class PackagingFundTests(_Base):
    def test_material_is_fund_pct_of_goods_revenue_read_live(self):
        fund = FinModelArticle.objects.create(category="revenue_fund", name="Упаковка (матеріали)",
                                              value=Decimal("1.92"), value_type="percent", unit="%")
        DealItem.objects.create(deal=self.d, product=self.svc, quantity=Decimal("1"), price=Decimal("500"),
                                cost=Decimal("200"))                         # послуга: без матеріалів
        emp = User.objects.create_user(username="pack", password="x")
        WarehousePayrollEntry.objects.create(employee=emp, work_date=timezone.localdate(), deal=self.d,
                                             op_type="packing", amount=Decimal("13"))
        r = compute(self.d)
        # 13 ₴ відрядно (факт) + 1,92% × 1000 ₴ виручки товарів = 19,20 ₴ (оцінка); послуга 500 ₴ не рахується
        self.assertEqual(r["packaging"], Decimal("32.20"))
        src = r["sources"]["packaging"]
        self.assertEqual(src["kind"], "mixed")
        self.assertEqual(src["parts"]["material_src"], "fund")
        self.assertEqual(src["parts"]["material"], 19.2)
        self.assertIn("1,92% фонду «Упаковка (матеріали)»", src["uk"])
        self.assertEqual(r["version"], 2)
        FinModelArticle.objects.filter(pk=fund.pk).update(value=Decimal("3"))   # змінили фонд → змінилась економіка
        self.assertEqual(compute(self.d)["packaging"], Decimal("43.00"))
        r = self.get(self.owner, "/api/deal-economics/settings/")
        self.assertEqual((r.data["pack_material_fund_pct"], r.data["pack_material_fund_name"]),
                         (3.0, "Упаковка (матеріали)"))

    def test_other_funds_ignored_and_no_fund_falls_back_to_norm(self):
        FinModelArticle.objects.create(category="variable", name="ФОТ упаковка/тонування/відгрузка",
                                       value=Decimal("16546"), value_type="fixed_sum_per_month")
        FinModelArticle.objects.create(category="revenue_fund", name="Упаковка (матеріали)", active=False,
                                       value=Decimal("1.92"), value_type="percent")
        d = Deal.objects.create(title="P", funnel=self.f, stage=self.st, amount=Decimal("3000"), ttn="4001")
        r = compute(d)
        self.assertEqual(r["packaging"], Decimal("22.00"))                   # стара норма, раз на посилку
        self.assertEqual(r["sources"]["packaging"]["parts"]["material_src"], "norm")
