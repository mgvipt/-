"""16.09.2026 Розвиток v2 — «Моя ЗП»: без подвійного рахунку стандарту, без «понад план», поки плану немає,
«Що буде, якщо» рівно за формулою ЗП (engine.calc), пункти стандарту складу для себе. Лише тестова БД."""
import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import force_authenticate

from apps.crm.models import Deal, DealItem
from apps.finance.models import ManagerPlan
from apps.payroll import engine
from apps.payroll.my_views import NO_PLAN_TEXT
from apps.payroll.test_my_kpi import HOST, _Base
from apps.payroll.whatif import MyWhatIfView
from apps.warehouse.models import Product


class SplitTests(_Base):
    def test_unrated_standard_is_conditional_and_not_in_more(self):
        s = self.scheme(self.mgr, ("fixed_monthly", {"amount": 5000}), ("standard", {"max": 6000}))
        d = self.my(self.mgr).data
        self.assertEqual(d["total"], 11000)                                  # формула ЗП та сама: 5 000 + 6 000 (100%)
        self.assertEqual(d["guaranteed"], 5000)
        self.assertEqual([c["amount"] for c in d["conditional"]], [6000])
        self.assertIn("повний місяць", d["conditional"][0]["hint"])
        self.assertFalse(any(m["code"] == "standard" for m in d["more"]))   # не рахуємо двічі
        c = s.components.get(kind="standard")
        c.params = {"max": 6000, "scores": {self.today.strftime("%Y-%m"): 0.5}}
        c.save()
        d = self.my(self.mgr).data
        self.assertEqual((d["total"], d["guaranteed"], d["conditional"]), (8000, 8000, []))


class NoPlanTests(_Base):
    def main_deal(self, price=10000, disc=0, cost=4000):
        p = Product.objects.create(name="Sirena Silk мокрий шовк", cost=Decimal("0"), price=Decimal(str(price)))
        d = Deal.objects.create(title="Основне", funnel=self.main, stage=self.st_main, contact=self.contact, owner=self.mgr)
        it = DealItem.objects.create(deal=d, product=p, quantity=Decimal("1"), price=Decimal(str(price)),
                                     discount_pct=Decimal(str(disc)), cost=Decimal(str(cost)))
        d.amount = it.total
        d.save(update_fields=["amount"])
        return d

    def test_rules_do_not_promise_over_plan_without_plan(self):
        self.scheme(self.mgr, ("standard", {"max": 6000}), self.margin_comp(), self.event_comp())
        d = self.my(self.mgr, "?only=rules").data
        self.assertFalse(d["has_plan"])
        rules = {r["kind"]: r for r in d["rules"]}
        self.assertFalse(any("з частини понад план" in x for x in rules["margin_share"]["need"]))
        self.assertTrue(any(NO_PLAN_TEXT in x for x in rules["margin_share"]["need"]))
        self.assertFalse(any("ставку понад план" in x for x in rules["standard"]["need"]))
        self.assertTrue(rules["plan"]["need"][0].startswith(NO_PLAN_TEXT))
        part = next(p for p in d["scheme"]["parts"] if p["kind"] == "margin_share")
        self.assertIn(NO_PLAN_TEXT, part["plain"])
        self.assertNotIn("з частини понад план", part["plain"])
        ManagerPlan.objects.create(user=self.mgr, period=self.today.strftime("%Y-%m"), target_revenue=Decimal("50000"))
        d = self.my(self.mgr, "?only=rules").data
        self.assertTrue(d["has_plan"])
        rules = {r["kind"]: r for r in d["rules"]}
        self.assertTrue(any("з частини понад план — 20%" in x for x in rules["margin_share"]["need"]))

    def test_deal_card_without_plan_has_no_over_part(self):
        self.scheme(self.mgr, self.margin_comp())
        d = self.main_deal(cost=3700)
        r = self.kpi(self.mgr, d)
        self.assertEqual((r.data["earn"]["now"], r.data["earn"]["max"]), (630, 630))
        self.assertFalse(any(p["code"] == "over" for p in r.data["earn"]["parts"]))
        self.assertIn(NO_PLAN_TEXT, r.data["earn"]["note"])
        self.assertEqual([c["title"] for c in r.data["checks"] if c["code"] == "plan"], [NO_PLAN_TEXT])


class WhatIfTests(_Base):
    def whatif(self, user, q=""):
        req = self.rf.get("/api/payroll/my/whatif/" + q, HTTP_HOST=HOST)
        force_authenticate(req, user=user)
        return MyWhatIfView.as_view()(req)

    def deal(self, amount):
        return Deal.objects.create(title="d", funnel=self.main, stage=self.st_main, contact=self.contact, amount=amount, owner=self.mgr)

    def margin_user(self):
        self.mgr.extra_permissions = ["deal.view", "deal.margin.view"]
        self.mgr.save()

    def scen(self, r, code):
        return next(s for s in r.data["scenarios"] if s["code"] == code)

    def test_pay_scenario_equals_engine_after_real_payment(self):
        self.margin_user()
        self.scheme(self.mgr, self.margin_comp())
        self.pay(self.deal(20000), 20000)
        r = self.whatif(self.mgr, "?pay=10000&tests=0")
        self.assertEqual(r.data["total"], 1000)                       # 20 000 × маржа 50% × 10%
        s = self.scen(r, "pay")
        self.assertEqual((s["delta"], s["new_total"]), (500, 1500))
        self.pay(self.deal(10000), 10000)
        self.assertEqual(engine.calc(self.mgr, self.today.strftime("%Y-%m"))["total"], s["new_total"])

    def test_pay_scenario_with_plan_uses_over_plan_rate_like_engine(self):
        self.margin_user()
        self.scheme(self.mgr, self.margin_comp())
        ManagerPlan.objects.create(user=self.mgr, period=self.today.strftime("%Y-%m"), target_revenue=Decimal("25000"))
        self.pay(self.deal(20000), 20000)
        s = self.scen(self.whatif(self.mgr, "?pay=10000"), "pay")
        self.assertEqual(s["new_total"], 1750)                        # 15 000 × 25/30 × 10% + 15 000 × 5/30 × 20%
        self.pay(self.deal(10000), 10000)
        self.assertEqual(engine.calc(self.mgr, self.today.strftime("%Y-%m"))["total"], 1750)

    def test_without_margin_right_exact_sum_and_no_margin_numbers(self):
        # 16.09.2026 (Олег): без округлення — людина бачить точну суму; маржі й далі не видно
        self.scheme(self.mgr, self.margin_comp())
        self.pay(self.deal(20000), 20000)
        r = self.whatif(self.mgr, "?pay=10333")
        s = self.scen(r, "pay")
        self.assertEqual(s["delta"], 517)
        self.assertFalse(r.data["rounded"])
        text = json.dumps(r.data, ensure_ascii=False)
        self.assertNotIn("маржа 10", text)
        self.assertNotIn("ratio", text)
        self.assertNotIn("50%", text)
        self.margin_user()
        s2 = self.scen(self.whatif(self.mgr, "?pay=10333"), "pay")
        self.assertEqual(s2["delta"], 517)

    def test_tests_and_discount_scenarios(self):
        self.margin_user()
        self.scheme(self.mgr, self.margin_comp(), self.event_comp())
        r = self.whatif(self.mgr, "?pay=0&tests=2&avg_order=5000")
        s = self.scen(r, "tests")
        self.assertEqual(s["parts"][0]["amount"], 600)                # 2 × 300 ₴
        self.assertEqual(s["delta"], 1100)                            # + 10 000 × 50% × 10%
        p = Product.objects.create(name="Шовк", cost=Decimal("0"), price=Decimal("10000"))
        d = self.deal(9000)
        DealItem.objects.create(deal=d, product=p, quantity=Decimal("1"), price=Decimal("10000"), discount_pct=Decimal("10"))
        s3 = self.scen(self.whatif(self.mgr, "?pay=0"), "discount")
        self.assertEqual((s3["input"], s3["delta"], s3["n_deals"]), (1000, 100, 1))

    def test_other_user_forbidden_and_no_scheme(self):
        self.assertEqual(self.whatif(self.mgr, f"?user={self.other.id}").status_code, 403)
        self.assertFalse(self.whatif(self.mgr).data["available"])


class WarehousePointsTests(_Base):
    def test_warehouse_sees_own_standard_points(self):
        w = get_user_model().objects.create_user("rz-wh", "rzw@example.test", "x", first_name="Склад", last_name="Тест")
        self.scheme(w, ("fixed_monthly", {"amount": 8000}), ("piece_rate", {}))
        d = self.my(w).data
        self.assertEqual(d["wh_standard"]["total"], 8)
        self.assertFalse(d["wh_standard"]["in_scheme"])
        self.assertIn("не входить", d["wh_standard"]["note"])
        self.scheme(self.mgr, ("fixed_monthly", {"amount": 1000}))
        self.assertIsNone(self.my(self.mgr).data["wh_standard"])
