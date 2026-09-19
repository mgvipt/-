"""19.09.2026: план по тижнях і днях — одне джерело грошей (як ЗП), тижні, доступ."""
from datetime import date
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.crm.models import Contact, Deal, Funnel, Stage
from apps.finance.models import Account, Category, ManagerPlan, Transaction

from . import engine
from .plan_grid import plan_grid


class PlanGridTests(TestCase):
    def setUp(self):
        self.f = Funnel.objects.create(name="21 Основний продукт")
        st = Stage.objects.create(funnel=self.f, name="Оплату отримано", order=3)
        self.u = User.objects.create_user(username="mgr_plan", password="x")
        c = Contact.objects.create(first_name="Клієнт")
        self.deal = Deal.objects.create(title="Шовк", funnel=self.f, stage=st, contact=c, owner=self.u, amount=Decimal("5000"))
        acc = Account.objects.create(name="ФОП")
        Transaction.objects.create(direction="in", amount=Decimal("5000"), amount_uah=Decimal("5000"), account=acc,
                                   deal=self.deal, date=date(2026, 9, 9))
        cat = Category.objects.create(name="Возврат денег клиенту", direction="out")
        Transaction.objects.create(direction="out", amount=Decimal("1000"), amount_uah=Decimal("1000"), account=acc,
                                   deal=self.deal, category=cat, date=date(2026, 9, 10))
        ManagerPlan.objects.create(user=self.u, period="2026-09", target_revenue=Decimal("220000"))
        pol = engine.policy()
        pol["funnels"].update({"online": [self.f.id], "main": [self.f.id], "test": [], "site": []})
        self.p = mock.patch("apps.payroll.engine.policy", return_value=pol)
        self.p.start()
        self.addCleanup(self.p.stop)

    def test_weeks_days_and_money_minus_refunds(self):
        g = plan_grid(self.u, "2026-09", today=date(2026, 9, 19))
        self.assertEqual(g["fact"], 4000.0)                        # 5000 прихід − 1000 повернення
        self.assertEqual(g["workdays"], 22)                        # вересень 2026: 22 робочі дні пн–пт
        self.assertEqual(g["per_day"], 10000.0)
        self.assertEqual(g["weeks"][0]["label"], "01.09–06.09")    # тиждень у межах місяця
        self.assertEqual(sum(w["plan"] for w in g["weeks"]), 220000.0)
        wk2 = next(w for w in g["weeks"] if w["from"] == "2026-09-07")
        self.assertEqual(wk2["fact"], 4000.0)
        self.assertEqual(wk2["mains"], 1)                          # перша оплата угоди 09.09
        self.assertIsNotNone(g["need"])
        self.assertEqual(g["need"]["left"], 216000)

    def test_other_users_plan_needs_right(self):
        other = User.objects.create_user(username="mgr_other", password="x")
        c = APIClient(); c.force_authenticate(other)
        self.assertEqual(c.get("/api/payroll/my/plan-grid/?period=2026-09&user=%s" % self.u.id).status_code, 403)
        self.assertEqual(c.get("/api/payroll/plan-team/?period=2026-09").status_code, 403)
        boss = User.objects.create_superuser(username="boss_plan", password="x")
        c.force_authenticate(boss)
        r = c.get("/api/payroll/plan-team/?period=2026-09")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["rows"][0]["fact"], 4000.0)
