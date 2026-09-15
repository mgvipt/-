"""14.09.2026 (my-kpi): «Моя ЗП і KPI» — лише свої дані; «KPI угоди» — заробіток без маржі, різні поради для
тест-набору й основного, втрата заробітку від знижки. Лише ізольована тестова БД; жодних зовнішніх запитів.
Вʼюшки викликаємо напряму (APIRequestFactory) — маршрути в payroll/urls.py додаються вручну (див. README пакета)."""
import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.crm.models import Contact, Deal, DealItem, Funnel, Stage
from apps.finance.models import Account, Transaction
from apps.payroll.models import PayComponent, PayPolicy, PayScheme
from apps.payroll.my_views import DealKpiView, MyPayrollView
from apps.warehouse.models import Product

HOST = "crm.wallcovdec.com.ua"


def _keys(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from _keys(v)
    elif isinstance(o, list):
        for v in o:
            yield from _keys(v)


class _Base(TestCase):
    def setUp(self):
        cache.clear()
        U = get_user_model()
        self.today = timezone.localdate()
        self.owner = U.objects.create_superuser("mk-owner", "mko@example.test", "x")
        self.mgr = U.objects.create_user("mk-mgr", "mkm@example.test", "x", first_name="Тест", last_name="Менеджер")
        self.mgr.extra_permissions = ["deal.view"]
        self.mgr.save()
        self.other = U.objects.create_user("mk-other", "mko2@example.test", "x", first_name="Інша", last_name="Людина")
        self.main = Funnel.objects.create(name="21 Основний продукт")
        self.test = Funnel.objects.create(name="22 Тестовий набір")
        self.st_main = Stage.objects.create(funnel=self.main, name="Розрахунок здійснено (КП)", order=1)
        self.st_test = Stage.objects.create(funnel=self.test, name="Оплату отримано", order=3)
        # id воронок у тестовій базі випадкові (можуть збігтися з «15»/«16» нормативів) — норматив маржі задаємо явно
        PayPolicy.objects.update_or_create(pk=1, defaults={"params": {
            "replaced_articles": [],
            "margin_estimate_pct": {str(self.main.id): 50, str(self.test.id): 50},
            "funnels": {"online": [self.main.id, self.test.id], "test": [self.test.id], "main": [self.main.id],
                        "salon": [], "diamond": []}}})
        self.acc = Account.objects.create(name="Каса my-kpi", kind="cash")
        self.contact = Contact.objects.create(first_name="Клієнт", last_name="Тестовий")
        self.rf = APIRequestFactory()

    def scheme(self, user, *comps):
        s = PayScheme.objects.create(user=user, position="Менеджер", department="Продажі",
                                     valid_from=self.today.replace(day=1), employment="none")
        for kind, params in comps:
            PayComponent.objects.create(scheme=s, kind=kind, params=params)
        return s

    def margin_comp(self):
        return ("margin_share", {"funnels": [self.main.id, self.test.id], "pct_to_plan": 10, "pct_over_plan": 20,
                                 "gate_standard_min": 0.75})

    def event_comp(self):
        return ("event_bonus", {"tiers": {"fast": 300, "slow": 200, "small": 100, "fast_days": 30, "min_order": 3000}})

    def pay(self, deal, amount, days_ago=0):
        return Transaction.objects.create(direction="in", amount=Decimal(str(amount)), amount_uah=Decimal(str(amount)),
                                          date=self.today - timedelta(days=days_ago), deal=deal, account=self.acc)

    def my(self, user, query=""):
        req = self.rf.get("/api/payroll/my/" + query, HTTP_HOST=HOST)
        force_authenticate(req, user=user)
        return MyPayrollView.as_view()(req)

    def kpi(self, user, deal):
        req = self.rf.get(f"/api/payroll/deal-kpi/{deal.id}/", HTTP_HOST=HOST)
        force_authenticate(req, user=user)
        return DealKpiView.as_view()(req, deal_id=deal.id)


class MyPayrollTests(_Base):
    def test_only_own_data_other_user_param_forbidden(self):
        self.scheme(self.mgr, ("fixed_monthly", {"amount": 10000}))
        self.scheme(self.other, ("fixed_monthly", {"amount": 55555}))
        r = self.my(self.mgr)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["total"], 10000)
        self.assertEqual(r.data["user_name"], "Тест Менеджер")
        text = json.dumps(r.data, ensure_ascii=False, default=str)
        self.assertNotIn("55 555", text)
        self.assertNotIn("Інша", text)
        self.assertEqual(self.my(self.mgr, f"?user={self.other.id}").status_code, 403)
        self.assertEqual(self.my(self.mgr, f"?user={self.mgr.id}").status_code, 200)

    def test_manager_without_scheme_gets_friendly_message(self):
        r = self.my(self.other)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["has_scheme"])
        self.assertIn("ставку", r.data["message"])
        self.assertEqual(r.data["lines"], [])

    def test_margin_amount_removed_from_line_detail(self):
        self.scheme(self.mgr, self.margin_comp())
        d = Deal.objects.create(title="d", funnel=self.main, stage=self.st_main, contact=self.contact, amount=10000, owner=self.mgr)
        self.pay(d, 10000)
        r = self.my(self.mgr)
        self.assertEqual(r.data["total"], 500)   # без товарів — норматив 50% → маржа 5 000, 10% = 500
        line = [l for l in r.data["lines"] if l["kind"] == "margin_share"][0]
        self.assertIn("оплати 10 000 ₴", line["detail"])
        self.assertNotIn("маржа 5 000", line["detail"])
        self.assertNotIn("basis", line)

    def test_test_set_opportunity_with_deadline_until_main_paid(self):
        self.scheme(self.mgr, self.margin_comp(), self.event_comp())
        t = Deal.objects.create(title="Тест", funnel=self.test, stage=self.st_test, contact=self.contact, amount=500, owner=self.mgr)
        self.pay(t, 500, days_ago=5)
        r = self.my(self.mgr)
        opp = r.data["opportunities"]
        self.assertEqual([o["deal_id"] for o in opp], [t.id])
        self.assertEqual(opp[0]["deadline"], (self.today - timedelta(days=5) + timedelta(days=30)).isoformat())
        self.assertEqual((opp[0]["fast"], opp[0]["slow"], opp[0]["small"]), (300, 200, 100))
        self.assertTrue(any(m["code"] == "tests" and m["amount"] == 300 for m in r.data["more"]))
        m = Deal.objects.create(title="Основне", funnel=self.main, stage=self.st_main, contact=self.contact, amount=8000, owner=self.mgr)
        self.pay(m, 8000)
        self.assertEqual(self.my(self.mgr).data["opportunities"], [])

    def test_rules_only_mode_has_standard_and_guarantee_conditions(self):
        self.scheme(self.mgr, ("standard", {"max": 6000}), self.margin_comp(), self.event_comp(),
                    ("guarantee", {"amount": 15000, "months": 2, "start": self.today.replace(day=1).isoformat()}))
        r = self.my(self.mgr, "?only=rules")
        self.assertEqual(r.status_code, 200)
        kinds = [s["kind"] for s in r.data["rules"]]
        self.assertIn("standard", kinds)
        std = [s for s in r.data["rules"] if s["kind"] == "standard"][0]
        self.assertTrue(any("15 хвилин" in x for x in std["need"]))
        g = [s for s in r.data["rules"] if s["kind"] == "guarantee"][0]
        self.assertGreaterEqual(len(g["need"]), 8)
        self.assertNotIn("lines", r.data)

    def test_guarantee_conditions_status(self):
        s = self.scheme(self.mgr, ("base_by_days", {"amount": 6000}),
                        ("guarantee", {"amount": 15000, "months": 2, "start": self.today.replace(day=1).isoformat()}))
        r = self.my(self.mgr)
        g = r.data["guarantee"]
        self.assertTrue(g["active"])
        self.assertFalse(g["confirmed"])
        self.assertTrue(all(c["ok"] is None for c in g["conditions"]))
        c = s.components.get(kind="guarantee")
        c.params["checks"] = {self.today.strftime("%Y-%m"): {"ok": True}}
        c.save()
        g2 = self.my(self.mgr).data["guarantee"]
        self.assertTrue(g2["confirmed"])
        self.assertTrue(all(x["ok"] for x in g2["conditions"]))


class DealKpiTests(_Base):
    def main_deal(self, price=10000, disc=0, cost=4000, name="Sirena Silk мокрий шовк"):
        p = Product.objects.create(name=name, cost=Decimal("0"), price=Decimal(str(price)))
        d = Deal.objects.create(title="Основне", funnel=self.main, stage=self.st_main, contact=self.contact, owner=self.mgr)
        it = DealItem.objects.create(deal=d, product=p, quantity=Decimal("1"), price=Decimal(str(price)),
                                     discount_pct=Decimal(str(disc)), cost=Decimal(str(cost)))
        d.amount = it.total
        d.save(update_fields=["amount"])
        return d

    def test_hides_margin_fields_and_amount(self):
        self.scheme(self.mgr, self.margin_comp())
        from apps.finance.models import ManagerPlan  # 16.09 Розвиток v2: «понад план» обіцяємо лише коли план на місяць є
        ManagerPlan.objects.create(user=self.mgr, period=self.today.strftime("%Y-%m"), target_revenue=Decimal("50000"))
        d = self.main_deal(cost=3700)  # 10 000 − собівартість 3 700 → маржа 6 300 (63%)
        r = self.kpi(self.mgr, d)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(any("margin" in k for k in _keys(r.data)))
        text = json.dumps(r.data, ensure_ascii=False, default=str)
        self.assertNotIn("6300", text)
        self.assertNotIn("6 300", text)
        self.assertNotIn("63%", text)
        self.assertNotIn("3700", text)                                # і собівартість не світимо
        self.assertEqual(r.data["earn"]["now"], 630)                  # 10% від маржі 6 300
        self.assertEqual(r.data["earn"]["max"], 1260)                 # понад план 20%
        self.assertTrue(r.data["show_money"])

    def test_test_set_vs_main_recommendations(self):
        self.scheme(self.mgr, self.margin_comp(), self.event_comp())
        t = Deal.objects.create(title="Тест", funnel=self.test, stage=self.st_test, contact=self.contact, amount=500, owner=self.mgr)
        self.pay(t, 500, days_ago=3)
        r = self.kpi(self.mgr, t)
        self.assertEqual(r.data["kind"], "test")
        codes = {c["code"] for c in r.data["checks"]}
        self.assertTrue({"pay", "event", "touch"} <= codes)
        ev = [c for c in r.data["checks"] if c["code"] == "event"][0]
        self.assertIn("+300", ev["title"])
        self.assertEqual(ev["date"], (self.today - timedelta(days=3) + timedelta(days=30)).isoformat())
        self.assertTrue(any(p["code"] == "event" and p["amount"] == 300 for p in r.data["earn"]["parts"]))
        self.assertIn("фокус", r.data["focus"])

        m = self.main_deal(price=5000, cost=2000)
        rm = self.kpi(self.mgr, m)
        self.assertEqual(rm.data["kind"], "main")
        mcodes = {c["code"] for c in rm.data["checks"]}
        self.assertTrue({"discount", "delivery", "prepay", "area", "touch"} <= mcodes)
        dl = [c for c in rm.data["checks"] if c["code"] == "delivery"][0]
        self.assertEqual(dl["status"], "todo")
        self.assertIn("1 000 ₴", dl["title"])                         # 6 000 − 5 000 до безкоштовної доставки
        pp = [c for c in rm.data["checks"] if c["code"] == "prepay"][0]
        self.assertIn("20%", pp["title"])                             # до 5 000 ₴ — 20%
        self.assertFalse(any(c["code"] == "event" for c in rm.data["checks"]))

    def test_discount_loss_in_hryvnias(self):
        self.scheme(self.mgr, self.margin_comp())
        d = self.main_deal(price=10000, disc=20, cost=3000)           # сума 8 000, собівартість 3 000
        r = self.kpi(self.mgr, d)
        self.assertEqual(r.data["earn"]["now"], 500)                  # (8 000 − 3 000) × 10%
        part = [p for p in r.data["earn"]["parts"] if p["code"] == "discount"][0]
        self.assertEqual(part["amount"], 200)                         # без знижки (10 000 − 3 000) × 10% = 700
        chk = [c for c in r.data["checks"] if c["code"] == "discount"][0]
        self.assertIn("200 ₴", chk["title"])
        self.assertEqual(chk["status"], "warn")                       # 20% > порогу 15%

    def test_other_viewer_sees_checklist_without_money_and_stranger_forbidden(self):
        self.scheme(self.mgr, self.margin_comp())
        d = self.main_deal()
        self.assertEqual(self.kpi(self.other, d).status_code, 403)    # немає deal.view і не власник
        self.other.extra_permissions = ["deal.view", "deal.view.all"]
        self.other.save()
        r = self.kpi(self.other, d)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["show_money"])
        self.assertIsNone(r.data["earn"])
        self.assertTrue(r.data["checks"])
        disc = [c for c in r.data["checks"] if c["code"] == "discount"][0]
        self.assertNotIn("заробіт", disc["title"])

    def test_owner_without_scheme_flag(self):
        d = self.main_deal()
        r = self.kpi(self.mgr, d)
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.data["earn"])
        self.assertTrue(r.data["no_scheme"])
