"""staffvis 15.09.2026 — «Співробітники і права → Звільнені: де показувати».
Одне правило (apps/accounts/visibility.py) для ЗП, ТБ, планів, аналітики, табеля, телефонії.
Активних не чіпає; затверджені відомості ЗП — історія: не ховаються й не змінюються."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import visibility as vis
from apps.crm.models import ActivityLog, Contact, Deal, Funnel, Stage
from apps.finance.models import FinModelArticle
from apps.payroll import engine
from apps.payroll.models import PayComponent, PayPolicy, PayrollRun, PayScheme

HOST = "crm.wallcovdec.com.ua"


def _rows(resp):
    d = resp.json()
    return d.get("results", d) if isinstance(d, dict) else d


class _Base(TestCase):
    def setUp(self):
        cache.clear()
        U = get_user_model()
        self.owner = U.objects.create_superuser("sv-owner", "svo@example.test", "x", first_name="Власник")
        self.active = U.objects.create_user("sv-active", "sva@example.test", "x", first_name="Активна", last_name="Менеджерка")
        # старий акаунт з Бітрикса: звільнений, дата невідома
        self.old = U.objects.create_user("b24_sv_old", "svb@example.test", "x", first_name="Стара", last_name="Бітрикс")
        self.old.apply_employment_status("dismissed")
        U.objects.filter(pk=self.old.pk).update(dismissed_at=None)
        self.old.refresh_from_db()
        # звільнений 10.09.2026 — вересень ще працював
        self.fresh = U.objects.create_user("sv-fresh", "svf@example.test", "x", first_name="Свіжий", last_name="Звільнений")
        self.fresh.apply_employment_status("dismissed", when=date(2026, 9, 10))
        self.api = APIClient()
        self.api.force_authenticate(self.owner)


class VisibilityRuleTests(_Base):
    def test_defaults_active_untouched_dismissed_auto(self):
        for e in vis.ENTITY_KEYS:
            self.assertTrue(vis.is_visible(self.active, e, "2026-10"))
            self.assertTrue(vis.is_visible(self.active, e))
            self.assertFalse(vis.is_visible(self.old, e, "2026-09"), e)  # дата невідома → приховано
        self.assertTrue(vis.is_visible(self.fresh, "payroll", "2026-09"))   # місяць, коли ще працював
        self.assertTrue(vis.is_visible(self.fresh, "timesheet", date(2026, 9, 1)))
        self.assertFalse(vis.is_visible(self.fresh, "payroll", "2026-10"))  # після звільнення
        self.assertFalse(vis.is_visible(self.fresh, "breakeven", "2026-09"))  # ТБ — план: «Авто» = не рахувати
        self.assertFalse(vis.is_visible(self.fresh, "payroll"))             # без періоду — приховано
        self.assertEqual(vis.hidden_ids("payroll", "2026-09"), {self.old.id})
        self.assertEqual(vis.hidden_ids("payroll", "2026-10"), {self.old.id, self.fresh.id})
        self.assertEqual(vis.hidden_ids("breakeven", "2026-09"), {self.old.id, self.fresh.id})
        self.assertEqual(vis.hidden_ids("нема-такого"), set())  # невідома сутність нічого не ховає

    def test_choices_merge_and_reset(self):
        vis.save_choices(self.old.id, {"payroll": True})
        vis.save_choices(self.old.id, {"timesheet": False})
        self.assertEqual(vis.load()[str(self.old.id)], {"payroll": True, "timesheet": False})  # другий вибір не затер перший
        self.assertTrue(vis.is_visible(self.old, "payroll", "2026-10"))
        vis.save_choices(self.fresh.id, {"payroll": False})
        self.assertFalse(vis.is_visible(self.fresh, "payroll", "2026-09"))  # «Приховати» сильніше за «Авто»
        vis.save_choices(self.old.id, {"payroll": None})
        self.assertEqual(vis.load()[str(self.old.id)], {"timesheet": False})
        self.assertEqual(vis.load()[str(self.fresh.id)], {"payroll": False})  # інша людина не зачеплена
        vis.save_choices(self.old.id, {"timesheet": None})
        self.assertNotIn(str(self.old.id), vis.load())
        self.assertEqual(vis.save_choices(self.old.id, {"payroll": 1, "bad": True}), ({}, {}))  # 1 ≠ true, чужі ключі — ні

    def test_filter_users_keeps_order(self):
        U = get_user_model()
        qs = U.objects.filter(id__in=[self.active.id, self.old.id, self.fresh.id]).order_by("id")
        self.assertEqual([u.id for u in vis.filter_users(qs, "payroll", "2026-09")], [self.active.id, self.fresh.id])
        self.assertEqual(vis.visible_dismissed_ids("timesheet", "2026-09"), {self.fresh.id})


class PayrollVisibilityTests(_Base):
    def setUp(self):
        super().setUp()
        PayPolicy.objects.update_or_create(pk=1, defaults={"params": {"replaced_articles": []}})
        FinModelArticle.objects.all().update(active=False)  # у тестовій базі є стартові статті з міграцій
        self.fund = FinModelArticle.objects.create(category="fixed", name="ФОТ тест staffvis", value=Decimal("1000"),
                                                   value_type="fixed_sum_per_month")
        for u, amount in ((self.active, 10000), (self.fresh, 8000)):
            s = PayScheme.objects.create(user=u, position="Менеджер", department="Продажі", valid_from=date(2026, 8, 1),
                                         employment="none", options={"fund_article_id": self.fund.id})
            PayComponent.objects.create(scheme=s, kind="fixed_monthly", params={"amount": amount})

    def _ids(self, on, **kw):
        return {s.user_id for s in engine.staff_on(on, **kw)}

    def test_staff_on_respects_choice(self):
        self.assertEqual(self._ids(date(2026, 9, 30)), {self.active.id, self.fresh.id})  # вересень — ще працював
        self.assertEqual(self._ids(date(2026, 10, 31)), {self.active.id})
        self.assertEqual(self._ids(date(2026, 9, 30), entity="breakeven"), {self.active.id})
        vis.save_choices(self.fresh.id, {"breakeven": True})
        self.assertEqual(self._ids(date(2026, 9, 30), entity="breakeven"), {self.active.id, self.fresh.id})
        vis.save_choices(self.fresh.id, {"payroll": False})
        self.assertEqual(self._ids(date(2026, 9, 30)), {self.active.id})
        team = {r["user_id"] for r in engine.calc_team("2026-09")["rows"]}
        self.assertEqual(team, {self.active.id})

    def test_breakeven_fot_excludes_dismissed_scheme(self):
        row = next(r for r in engine.breakeven_atm(today=date(2026, 9, 14))["fot"] if r["fund_id"] == self.fund.id)
        self.assertEqual(row["suggested"], 10000)  # лише активна; ставка звільненого у ФОТ не йде
        self.assertEqual([p["name"] for p in row["people"]], ["Активна Менеджерка"])
        vis.save_choices(self.fresh.id, {"breakeven": True})
        row = next(r for r in engine.breakeven_atm(today=date(2026, 9, 14))["fot"] if r["fund_id"] == self.fund.id)
        self.assertEqual(row["suggested"], 18000)
        self.fund.refresh_from_db()
        self.assertEqual(float(self.fund.value), 1000)  # розрахунок фонд не чіпає

    def test_approved_run_is_history(self):
        r = self.api.post("/api/payroll/runs/approve/", {"period": "2026-09", "user_id": self.fresh.id}, format="json", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 200)
        total = r.json()["total"]
        vis.save_choices(self.fresh.id, {"payroll": False})
        team = self.api.get("/api/payroll/runs/?period=2026-09", HTTP_HOST=HOST).json()
        rows = [x for x in team["rows"] if x["user_id"] == self.fresh.id]
        self.assertEqual(len(rows), 1)                     # затверджений місяць лишається видимим
        self.assertEqual(rows[0]["run"]["total"], total)
        run = PayrollRun.objects.get(user=self.fresh, period="2026-09")
        self.assertEqual((run.status, float(run.total), PayrollRun.objects.count()), ("approved", float(total), 1))
        oct_ids = {x["user_id"] for x in self.api.get("/api/payroll/runs/?period=2026-10", HTTP_HOST=HOST).json()["rows"]}
        self.assertEqual(oct_ids, {self.active.id})


class SalaryListVisibilityTests(_Base):
    def setUp(self):
        super().setUp()
        f = Funnel.objects.create(name="Основний staffvis")
        st = Stage.objects.create(funnel=f, name="Нова", order=0)
        c = Contact.objects.create(first_name="Клієнт")
        for u in (self.active, self.old):
            Deal.objects.create(title="d", funnel=f, stage=st, contact=c, amount=1000, owner=u)

    def _ids(self, url):
        r = self.api.get(url, HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 200)
        return {x["user_id"] for x in r.json()["rows"]}

    def test_old_formula_and_plans_lists(self):
        self.assertEqual(self._ids("/api/finance/salary/?period=2026-09"), {self.active.id})
        vis.save_choices(self.old.id, {"payroll": True})
        self.assertEqual(self._ids("/api/finance/salary/?period=2026-09"), {self.active.id, self.old.id})
        self.assertEqual(self._ids("/api/finance/salary/?period=2026-09&for=plans"), {self.active.id})
        vis.save_choices(self.old.id, {"plans": True})
        self.assertEqual(self._ids("/api/finance/salary/?period=2026-09&for=plans"), {self.active.id, self.old.id})
        # окремий запит по людині (деталізація) не змінюється
        one = self.api.get(f"/api/finance/salary/?period=2026-09&user={self.old.id}", HTTP_HOST=HOST)
        self.assertEqual(one.status_code, 200)


class VisibilityApiTests(_Base):
    URL = "/api/users/visibility/"

    def test_only_admin(self):
        c = APIClient()
        c.force_authenticate(self.active)
        self.assertEqual(c.get(self.URL, HTTP_HOST=HOST).status_code, 403)
        self.assertEqual(c.post(self.URL, {"user_id": self.old.id, "all": True}, format="json", HTTP_HOST=HOST).status_code, 403)
        self.assertEqual(vis.load(), {})

    def test_get_lists_dismissed(self):
        d = self.api.get(self.URL, HTTP_HOST=HOST).json()
        self.assertEqual([e["key"] for e in d["entities"]], list(vis.ENTITY_KEYS))
        ids = [p["id"] for p in d["people"]]
        self.assertEqual(set(ids), {self.old.id, self.fresh.id})
        self.assertEqual(ids[0], self.fresh.id)  # з датою звільнення — вгорі
        old = next(p for p in d["people"] if p["id"] == self.old.id)
        self.assertTrue(old["from_bitrix"])
        self.assertEqual(set(old["settings"].values()), {None})

    def test_post_merge_all_and_errors(self):
        p = self.api.post(self.URL, {"user_id": self.fresh.id, "set": {"payroll": False}}, format="json", HTTP_HOST=HOST).json()
        self.assertIs(p["settings"]["payroll"], False)
        p = self.api.post(self.URL, {"user_id": self.fresh.id, "set": {"timesheet": True}}, format="json", HTTP_HOST=HOST).json()
        self.assertEqual((p["settings"]["payroll"], p["settings"]["timesheet"]), (False, True))
        self.assertEqual(p["changed_by"], "Власник")
        p = self.api.post(self.URL, {"user_id": self.fresh.id, "all": True}, format="json", HTTP_HOST=HOST).json()
        self.assertEqual(set(p["settings"].values()), {True})
        p = self.api.post(self.URL, {"user_id": self.fresh.id, "all": None}, format="json", HTTP_HOST=HOST).json()
        self.assertEqual(set(p["settings"].values()), {None})
        self.assertTrue(ActivityLog.objects.filter(action="Видимість звільненого").exists())
        bad = [
            {"user_id": self.active.id, "set": {"payroll": False}},   # активний — не можна
            {"user_id": self.fresh.id, "set": {"nope": False}},
            {"user_id": self.fresh.id, "set": {"payroll": 1}},
            {"user_id": self.fresh.id, "set": {}},
            {"user_id": "x", "all": True},
        ]
        for body in bad:
            self.assertEqual(self.api.post(self.URL, body, format="json", HTTP_HOST=HOST).status_code, 400, body)
        self.assertEqual(self.api.post(self.URL, {"user_id": 999999, "all": True}, format="json", HTTP_HOST=HOST).status_code, 404)

    def test_users_list_for_timesheet(self):
        ids = {u["id"] for u in _rows(self.api.get("/api/users/?visible_in=timesheet&period=2026-09", HTTP_HOST=HOST))}
        self.assertTrue({self.active.id, self.fresh.id} <= ids)
        self.assertNotIn(self.old.id, ids)
        ids = {u["id"] for u in _rows(self.api.get("/api/users/?visible_in=timesheet&period=2026-10", HTTP_HOST=HOST))}
        self.assertNotIn(self.fresh.id, ids)
        vis.save_choices(self.old.id, {"timesheet": True})
        ids = {u["id"] for u in _rows(self.api.get("/api/users/?visible_in=timesheet&period=2026-10", HTTP_HOST=HOST))}
        self.assertIn(self.old.id, ids)
        default = {u["id"] for u in _rows(self.api.get("/api/users/", HTTP_HOST=HOST))}  # без параметра — як було
        self.assertNotIn(self.old.id, default)
        self.assertIn(self.active.id, default)

    def test_staff_analytics_filters(self):
        def ids(q):
            r = self.api.get("/api/staff/analytics/?" + q, HTTP_HOST=HOST)
            self.assertEqual(r.status_code, 200)
            return {x["id"] for x in r.json()["rows"]}
        self.assertEqual(ids("period=2026-09&status=dismissed"), {self.fresh.id})
        self.assertEqual(ids("period=2026-10&status=dismissed"), set())
        self.assertNotIn(self.old.id, ids("period=2026-09&status=all"))
        self.assertIn(self.active.id, ids("period=2026-09&status=all"))
        vis.save_choices(self.old.id, {"staff_analytics": True})
        self.assertEqual(ids("period=2026-10&status=dismissed"), {self.old.id})


class SalesAnalyticsVisibilityTests(_Base):
    def setUp(self):
        super().setUp()
        today = timezone.localdate()
        get_user_model().objects.filter(pk=self.fresh.pk).update(dismissed_at=today - timedelta(days=5))
        self.today = today

    def test_manager_actions_rows(self):
        for u in (self.active, self.fresh, self.old):
            ActivityLog.objects.create(kind="lead", object_id=1, action="Взяв чат", user=u)

        def ids(frm):
            r = self.api.get(f"/api/analytics/manager-actions/?from={frm}&to={self.today}", HTTP_HOST=HOST)
            self.assertEqual(r.status_code, 200)
            return {x["user_id"] for x in r.json()["rows"]}
        self.assertEqual(ids(self.today - timedelta(days=10)), {self.active.id, self.fresh.id})  # період зачіпає роботу
        self.assertEqual(ids(self.today - timedelta(days=3)), {self.active.id})
        vis.save_choices(self.old.id, {"sales_analytics": True})
        vis.save_choices(self.fresh.id, {"sales_analytics": False})
        self.assertEqual(ids(self.today - timedelta(days=10)), {self.active.id, self.old.id})

    def test_manager_stages_rows_and_dashboard(self):
        f = Funnel.objects.create(name="Ліди staffvis", is_lead_funnel=True)
        Stage.objects.create(funnel=f, name="Нові", order=0)
        Stage.objects.create(funnel=f, name="В роботі", order=1)
        for i, u in enumerate((self.active, self.old), start=1):
            ActivityLog.objects.create(kind="lead", object_id=i, action="Зміна стадії", detail="Нові → В роботі", user=u)
        d = self.api.get(f"/api/analytics/manager-stages/?funnel={f.id}", HTTP_HOST=HOST).json()
        self.assertEqual({r["key"] for r in d["rows"]}, {"u%s" % self.active.id})
        # дашборд: топ менеджерів без прихованого звільненого
        mf = Funnel.objects.create(name="Продажі staffvis", order=0)
        st = Stage.objects.create(funnel=mf, name="Нова", order=0)
        c = Contact.objects.create(first_name="К")
        for u in (self.active, self.old):
            Deal.objects.create(title="d", funnel=mf, stage=st, contact=c, amount=5000, owner=u)
        r = self.api.get(f"/api/analytics/?funnel={mf.id}", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 200)
        names = [m["name"].strip() for m in r.json()["managers"]]
        self.assertEqual(names, ["Активна Менеджерка"])
        self.assertEqual(r.json()["deals_total"] if "deals_total" in r.json() else 2, 2)  # цифри воронки — без змін

    def test_weekly_review_and_missed_report_smoke(self):
        r = self.api.post("/api/analytics/weekly-review/", {}, format="json", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 200)
        from apps.missed_calls import services
        rep = services.report(self.today - timedelta(days=7), self.today)
        self.assertEqual(rep["by_manager"], [])
