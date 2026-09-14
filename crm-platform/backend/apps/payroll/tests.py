"""Ставки співробітників (план v9, 14.09): версії не переписують минуле, гарантія лише з підтвердженням умов,
вартість для компанії з податками, точка беззбитковості за ATM з вакансією «що якщо», акти обʼєктів, права."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.crm.models import Contact, Deal, Funnel, Stage
from apps.finance.models import Account, FinModelArticle, Transaction
from apps.payroll import engine
from apps.payroll.models import ObjectAct, PayComponent, PayScheme

HOST = "crm.wallcovdec.com.ua"


class PayrollEngineTests(TestCase):
    def setUp(self):
        cache.clear()  # частки й квартал кешуються на 5 хв
        U = get_user_model()
        self.owner = U.objects.create_superuser("pr-owner", "pro@example.test", "x")
        self.mgr = U.objects.create_user("pr-mgr", "prm@example.test", "x", first_name="Тест", last_name="Менеджер")
        self.funnel = Funnel.objects.create(name="21 Основний продукт")
        self.st = Stage.objects.create(funnel=self.funnel, name="Оплату отримано", order=0)
        # у тестовій базі id статей фінмоделі випадкові — жодних «замінених» статей
        from apps.payroll.models import PayPolicy
        PayPolicy.objects.update_or_create(pk=1, defaults={"params": {"replaced_articles": []}})
        self.acc = Account.objects.create(name="Каса тест ЗП", kind="cash")

    def _scheme(self, **kw):
        s = PayScheme.objects.create(user=kw.pop("user", self.mgr), position="Менеджер", valid_from=kw.pop("valid_from", date(2026, 9, 1)),
                                     employment=kw.pop("employment", "none"), **kw)
        return s

    def test_base_prorated_from_start_day_without_timesheet(self):
        s = self._scheme(valid_from=date(2026, 9, 14))
        PayComponent.objects.create(scheme=s, kind="base_by_days", params={"amount": 6000})
        r = engine.calc(self.mgr, "2026-09")
        # вересень 2026: 22 робочі дні, з 14-го — 13
        self.assertEqual(r["total"], round(6000 * 13 / 22))
        self.assertTrue(r["warnings"])

    def test_new_version_does_not_touch_past_month(self):
        s = self._scheme(valid_from=date(2026, 8, 1))
        PayComponent.objects.create(scheme=s, kind="fixed_monthly", params={"amount": 10000})
        c = APIClient()
        c.force_authenticate(self.owner)
        r = c.post(f"/api/payroll/schemes/{s.id}/save/", {"valid_from": "2026-10-01", "components": [
            {"kind": "fixed_monthly", "params": {"amount": 12000}}]}, format="json", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(engine.calc(self.mgr, "2026-09")["total"], 10000)
        self.assertEqual(engine.calc(self.mgr, "2026-10")["total"], 12000)
        s.refresh_from_db()
        self.assertEqual(s.valid_to, date(2026, 9, 30))

    def test_guarantee_only_after_conditions_confirmed(self):
        s = self._scheme(valid_from=date(2026, 9, 1))
        PayComponent.objects.create(scheme=s, kind="base_by_days", params={"amount": 6000})
        g = PayComponent.objects.create(scheme=s, kind="guarantee", params={"amount": 15000, "months": 2, "start": "2026-09-01"})
        r = engine.calc(self.mgr, "2026-09")
        self.assertEqual(r["total"], 6000)
        g.params["checks"] = {"2026-09": {"ok": True}}
        g.save()
        self.assertEqual(engine.calc(self.mgr, "2026-09")["total"], 15000)
        self.assertEqual(engine.calc(self.mgr, "2026-11")["total"], 6000)  # гарантія скінчилась

    def test_margin_share_from_payments(self):
        s = self._scheme()
        PayComponent.objects.create(scheme=s, kind="margin_share", params={"funnels": [self.funnel.id], "pct_to_plan": 10})
        contact = Contact.objects.create(first_name="К")
        d = Deal.objects.create(title="d", funnel=self.funnel, stage=self.st, contact=contact, amount=10000, owner=self.mgr)
        Transaction.objects.create(direction="in", amount=Decimal("10000"), amount_uah=Decimal("10000"), date=date(2026, 9, 5), deal=d, account=self.acc)
        r = engine.calc(self.mgr, "2026-09")
        # без товарів — норматив воронки 50% → маржа 5 000, 10% = 500
        self.assertEqual(r["total"], 500)

    def test_employer_cost_labor(self):
        self.assertAlmostEqual(engine.employer_cost(20000, "labor"), 20000 / 0.77 * 1.22, places=0)
        self.assertEqual(engine.employer_cost(20000, "none"), 20000)

    def test_breakeven_vacancy_what_if(self):
        FinModelArticle.objects.all().update(active=False)  # у тестовій базі є стартові статті з міграцій
        FinModelArticle.objects.create(category="fixed", name="Оренда", value=Decimal("20000"), value_type="fixed_sum_per_month")
        FinModelArticle.objects.create(category="revenue_fund", name="Постачальники", value=Decimal("50"), value_type="percent")
        v = PayScheme.objects.create(position="Вакансія", valid_from=date(2026, 11, 1), is_vacancy=True, in_plan=False,
                                     employment="none", planned_start=date(2026, 11, 1))
        PayComponent.objects.create(scheme=v, kind="fixed_monthly", params={"amount": 10000})
        base = engine.breakeven_atm(today=date(2026, 9, 14))
        self.assertEqual(base["breakeven"], 40000)  # (20 000) / (1 − 0,5) — те саме число, що у Фінансах
        self.assertEqual(base["vacancies"][0]["delta_breakeven"], 20000)
        self.assertEqual(base["breakeven_with"], 40000)
        with_v = engine.breakeven_atm(extra_ids=(v.id,), today=date(2026, 9, 14))
        self.assertEqual(with_v["breakeven"], 40000)
        self.assertEqual(with_v["breakeven_with"], 60000)
        from apps.finance.services import compute_breakeven
        self.assertEqual(compute_breakeven(date(2026, 9, 1), date(2026, 9, 30))["breakeven"], base["breakeven"])

    def test_fund_changes_only_by_owner_click(self):
        FinModelArticle.objects.all().update(active=False)
        f = FinModelArticle.objects.create(category="fixed", name="ФОТ офіс тест", value=Decimal("1000"), value_type="fixed_sum_per_month")
        s = self._scheme(department="Продажі", options={"fund_article_id": f.id})
        PayComponent.objects.create(scheme=s, kind="fixed_monthly", params={"amount": 7000})
        row = next(r for r in engine.breakeven_atm()["fot"] if r["fund_id"] == f.id)
        self.assertEqual(row["suggested"], 7000)
        f.refresh_from_db()
        self.assertEqual(float(f.value), 1000)  # розрахунок фонд не чіпає
        c = APIClient()
        c.force_authenticate(self.mgr)
        self.assertEqual(c.post("/api/payroll/funds/sync/", {"fund_id": f.id}, format="json", HTTP_HOST=HOST).status_code, 403)
        c.force_authenticate(self.owner)
        self.assertEqual(c.post("/api/payroll/funds/sync/", {"fund_id": f.id}, format="json", HTTP_HOST=HOST).status_code, 200)
        f.refresh_from_db()
        self.assertEqual(float(f.value), 7000)

    def test_act_close_owner_only_and_idempotent(self):
        s = self._scheme()
        PayComponent.objects.create(scheme=s, kind="revenue_share", params={"basis": "object_acts", "pct": 2})
        a = ObjectAct.objects.create(title="Обʼєкт", act_date=date(2026, 9, 10), amount_total=Decimal("100000"), manager=self.mgr)
        c = APIClient()
        c.force_authenticate(self.mgr)
        self.assertEqual(c.post(f"/api/payroll/acts/{a.id}/close/", HTTP_HOST=HOST).status_code, 403)
        c.force_authenticate(self.owner)
        r1 = c.post(f"/api/payroll/acts/{a.id}/close/", HTTP_HOST=HOST).json()
        r2 = c.post(f"/api/payroll/acts/{a.id}/close/", HTTP_HOST=HOST).json()
        self.assertEqual(r1["commission_amount"], 2000.0)
        self.assertEqual(r1["closed_at"], r2["closed_at"])
        period = r1["payroll_period"]
        self.assertEqual(engine.calc(self.mgr, period)["total"], 2000)

    def test_manager_cannot_see_rates(self):
        c = APIClient()
        c.force_authenticate(self.mgr)
        self.assertEqual(c.get("/api/payroll/schemes/", HTTP_HOST=HOST).status_code, 403)
        self.assertEqual(c.get("/api/payroll/calc/?period=2026-09", HTTP_HOST=HOST).status_code, 403)


class PayrollRunTests(TestCase):
    """Відомість: затверджений місяць не змінюється від нових ставок; перевідкрити → версія 2; привʼязка виплат; права."""
    def setUp(self):
        cache.clear()  # частки й квартал кешуються на 5 хв
        U = get_user_model()
        self.owner = U.objects.create_superuser("run-owner", "ro@example.test", "x")
        self.mgr = U.objects.create_user("run-mgr", "rm@example.test", "x", first_name="Тест", last_name="Відомість")
        from apps.payroll.models import PayPolicy
        from apps.finance.models import Category
        self.cat = Category.objects.create(name="ЗП оклади тест", direction="out")
        PayPolicy.objects.update_or_create(pk=1, defaults={"params": {"replaced_articles": [], "payout_categories": [self.cat.id]}})
        self.acc = Account.objects.create(name="Каса ЗП тест", kind="cash")
        self.s = PayScheme.objects.create(user=self.mgr, position="Менеджер", valid_from=date(2026, 8, 1), employment="none")
        self.c = PayComponent.objects.create(scheme=self.s, kind="fixed_monthly", params={"amount": 10000})
        self.api = APIClient()
        self.api.force_authenticate(self.owner)

    def test_approve_freezes_and_reopen_versions(self):
        r = self.api.post("/api/payroll/runs/approve/", {"period": "2026-08", "user_id": self.mgr.id}, format="json", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["total"], 10000)
        self.c.params = {"amount": 12000}
        self.c.save()
        team = self.api.get("/api/payroll/runs/?period=2026-08", HTTP_HOST=HOST).json()
        row = [x for x in team["rows"] if x["user_id"] == self.mgr.id][0]
        self.assertEqual(row["run"]["total"], 10000)
        self.assertEqual(row["run"]["live_total"], 12000)
        again = self.api.post("/api/payroll/runs/approve/", {"period": "2026-08", "user_id": self.mgr.id}, format="json", HTTP_HOST=HOST)
        self.assertEqual(again.status_code, 400)
        rid = r.json()["id"]
        self.api.post(f"/api/payroll/runs/{rid}/reopen/", {}, format="json", HTTP_HOST=HOST)
        r2 = self.api.post("/api/payroll/runs/approve/", {"period": "2026-08", "user_id": self.mgr.id}, format="json", HTTP_HOST=HOST).json()
        self.assertEqual((r2["version"], r2["total"]), (2, 12000))

    def test_link_payouts(self):
        r = self.api.post("/api/payroll/runs/approve/", {"period": "2026-08", "user_id": self.mgr.id}, format="json", HTTP_HOST=HOST).json()
        t = Transaction.objects.create(direction="out", amount=Decimal("6000"), amount_uah=Decimal("6000"), date=date(2026, 9, 3),
                                       account=self.acc, category=self.cat, counterparty="Тест Відомість")
        cands = self.api.get(f"/api/payroll/runs/{r['id']}/candidates/", HTTP_HOST=HOST).json()["results"]
        self.assertEqual([c["id"] for c in cands], [t.id])
        out = self.api.post(f"/api/payroll/runs/{r['id']}/link/", {"transaction_ids": [t.id]}, format="json", HTTP_HOST=HOST).json()
        self.assertEqual((out["paid"], out["remaining"]), (6000, 4000))
        self.assertEqual(self.api.get(f"/api/payroll/runs/{r['id']}/candidates/", HTTP_HOST=HOST).json()["results"], [])

    def test_quarter_check_only_quarter_end(self):
        from apps.payroll import runs
        self.assertIsNone(runs.quarter_check("2026-08"))
        q = runs.quarter_check("2026-09")
        self.assertIn("pct", q)

    def test_manager_cannot_approve(self):
        c = APIClient()
        c.force_authenticate(self.mgr)
        self.assertEqual(c.post("/api/payroll/runs/approve/", {"period": "2026-08", "user_id": self.mgr.id}, format="json", HTTP_HOST=HOST).status_code, 403)
