"""15.09.2026 (whpay): «Як прорахувалась ЗП» — розшифровка кожного рядка = сума рядка ЗП; бачить лише власник.
Лише ізольована тестова БД; жодних зовнішніх запитів. Вʼюшку викликаємо напряму (APIRequestFactory) — маршрут
у payroll/urls.py додається вручну (див. README пакета)."""
import datetime
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.crm.models import Contact, Deal, Funnel, Stage
from apps.finance.models import Account, ManagerPlan, Transaction, WorkDay
from apps.payroll import engine, runs
from apps.payroll.detail_views import CalcDetailView
from apps.payroll.models import PayComponent, PayPolicy, PayScheme
from apps.warehouse.models import WarehouseJob, WarehousePayrollEntry

PERIOD = "2026-08"   # серпень 2026: 21 робочий день


def day(n, month=8):
    return date(2026, month, n)


class _Base(TestCase):
    def setUp(self):
        cache.clear()
        U = get_user_model()
        self.owner = U.objects.create_superuser("cd-owner", "cdo@example.test", "x")
        self.mgr = U.objects.create_user("cd-mgr", "cdm@example.test", "x", first_name="Тест", last_name="Продавець")
        self.wh = U.objects.create_user("cd-wh", "cdw@example.test", "x", first_name="Тест", last_name="Комірник")
        self.plain = U.objects.create_user("cd-plain", "cdp@example.test", "x")
        self.main = Funnel.objects.create(name="21 Основний продукт")
        self.test = Funnel.objects.create(name="22 Тестовий набір")
        self.st_main = Stage.objects.create(funnel=self.main, name="Оплату отримано", order=1)
        self.st_test = Stage.objects.create(funnel=self.test, name="Оплату отримано", order=1)
        # id воронок у тестовій базі випадкові — воронки й нормативи маржі задаємо явно
        PayPolicy.objects.update_or_create(pk=1, defaults={"params": {
            "replaced_articles": [],
            "margin_estimate_pct": {str(self.main.id): 50, str(self.test.id): 60},
            "funnels": {"online": [self.main.id, self.test.id], "test": [self.test.id], "main": [self.main.id],
                        "salon": [], "diamond": []}}})
        self.acc = Account.objects.create(name="Каса whpay", kind="cash")
        self.rf = APIRequestFactory()

    def pay(self, deal, amount, d):
        return Transaction.objects.create(direction="in", amount=Decimal(str(amount)), amount_uah=Decimal(str(amount)),
                                          date=d, deal=deal, account=self.acc)

    def detail(self, who, user_id, period=PERIOD):
        req = self.rf.get("/api/payroll/calc-detail/", {"user": user_id, "period": period})
        force_authenticate(req, user=who)
        return CalcDetailView.as_view()(req)

    def assert_lines_match(self, data, calc):
        self.assertEqual([(l["kind"], l["amount"]) for l in data["lines"]], [(l["kind"], l["amount"]) for l in calc["lines"]])
        for l in data["lines"]:
            self.assertEqual(l["total"], l["amount"], l["kind"])
            self.assertTrue(l["matches"], l["kind"])
        self.assertTrue(data["all_match"])


class SellerDetailTests(_Base):
    def setUp(self):
        super().setUp()
        s = PayScheme.objects.create(user=self.mgr, position="Менеджер", department="Продажі", valid_from=day(1, 7))
        PayComponent.objects.create(scheme=s, kind="base_by_days", title="Оклад", params={"amount": 6000})
        PayComponent.objects.create(scheme=s, kind="standard", title="Стандарт", params={"max": 2000, "scores": {PERIOD: 0.9}})
        PayComponent.objects.create(scheme=s, kind="margin_share", title="% з маржі", params={
            "funnels": [self.main.id, self.test.id], "pct_to_plan": 10, "pct_over_plan": 15, "gate_standard_min": 0.75})
        PayComponent.objects.create(scheme=s, kind="event_bonus", title="Тест-набір → основне")
        ManagerPlan.objects.create(user=self.mgr, period=PERIOD, target_revenue=Decimal("10000"))
        c1 = Contact.objects.create(first_name="Олена", last_name="Клієнтка")
        c2 = Contact.objects.create(first_name="Ігор")
        self.t1 = Deal.objects.create(title="тест", funnel=self.test, stage=self.st_test, contact=c1, amount=460, owner=self.mgr)
        self.m1 = Deal.objects.create(title="основне", funnel=self.main, stage=self.st_main, contact=c1, amount=12000, owner=self.mgr)
        self.m2 = Deal.objects.create(title="без тесту", funnel=self.main, stage=self.st_main, contact=c2, amount=2000, owner=self.mgr)
        self.pay(self.t1, 460, day(2))
        self.pay(self.m1, 6000, day(10))
        self.pay(self.m1, 6000, day(12))
        self.pay(self.m2, 2000, day(20))
        self.pay(self.m2, 999, day(1, 9))                       # інший місяць — не рахується
        other = get_user_model().objects.create_user("cd-other", "cdx@example.test", "x")
        d_other = Deal.objects.create(title="чужа", funnel=self.main, stage=self.st_main, contact=c2, amount=5000, owner=other)
        self.pay(d_other, 5000, day(15))                        # чужа угода — не рахується
        for n in range(3, 8):                                   # табель: 5 робочих + 1 вихід у вихідний + лікарняний
            WorkDay.objects.create(user=self.mgr, date=day(n), status="worked")
        WorkDay.objects.create(user=self.mgr, date=day(9), status="overtime")
        WorkDay.objects.create(user=self.mgr, date=day(11), status="sick")

    def test_every_line_detail_equals_calc_line(self):
        calc = engine.calc(self.mgr, PERIOD)
        r = self.detail(self.owner, self.mgr.id)
        self.assertEqual(r.status_code, 200)
        self.assert_lines_match(r.data, calc)
        self.assertEqual([l["kind"] for l in r.data["lines"]], ["base_by_days", "standard", "margin_share", "event_bonus"])
        self.assertIsNone(r.data["run"])

    def test_margin_rows_are_payments_with_deal_links_and_plan_split(self):
        r = self.detail(self.owner, self.mgr.id)
        m = next(l for l in r.data["lines"] if l["kind"] == "margin_share")
        self.assertEqual([(x["deal_id"], x["paid"]) for x in m["rows"]],
                         [(self.t1.id, 460.0), (self.m1.id, 6000.0), (self.m1.id, 6000.0), (self.m2.id, 2000.0)])
        self.assertEqual(m["rows"][0]["client"], "Олена Клієнтка")
        self.assertEqual((m["rows"][0]["margin_pct"], m["rows"][0]["estimate"]), (60.0, True))   # норматив воронки
        self.assertLessEqual(abs(sum(x["earn"] for x in m["rows"]) - m["total"]), 1)
        margin = 460 * 0.6 + 14000 * 0.5
        over = (14460 - 10000) / 14460                                   # оплати понад план 10 000
        self.assertEqual(m["total"], round(margin * (1 - over) * 0.10 + margin * over * 0.15))
        self.assertIn("Понад план", [s["label"] for s in m["summary"]])
        self.assertTrue(m["warnings"])                                    # маржа оцінкою — попереджено

    def test_event_bonus_rows_show_test_to_main_pair(self):
        r = self.detail(self.owner, self.mgr.id)
        ev = next(l for l in r.data["lines"] if l["kind"] == "event_bonus")
        self.assertEqual([(x["deal_id"], x["test_deal_id"], x["days"], x["bonus"]) for x in ev["rows"]],
                         [(self.m1.id, self.t1.id, 8, 300.0)])
        self.assertEqual(ev["total"], 300)
        self.assertTrue(any(f"#{self.m2.id}" in n for n in ev["notes"]))  # основне без тест-набору — пояснено

    def test_base_detail_lists_timesheet(self):
        r = self.detail(self.owner, self.mgr.id)
        b = next(l for l in r.data["lines"] if l["kind"] == "base_by_days")
        self.assertEqual(len(b["rows"]), 7)
        # 16.09.2026 (Олег): доплата лише за день ПОНАД норму місяця (подвійно, до 1); вихід у вихідний — звичайний день табеля
        self.assertEqual(b["total"], round(6000 * 6 / 21))


class WarehouseDetailTests(_Base):
    def setUp(self):
        super().setUp()
        s = PayScheme.objects.create(user=self.wh, position="Комірник", department="Склад", valid_from=day(1, 7))
        PayComponent.objects.create(scheme=s, kind="fixed_monthly", title="Ставка", params={"amount": 8000})
        PayComponent.objects.create(scheme=s, kind="piece_rate", title="Відрядно")
        c = Contact.objects.create(first_name="Марія")
        self.d1 = Deal.objects.create(title="відвантаження", funnel=self.main, stage=self.st_main, contact=c, amount=5000)
        self.d0 = Deal.objects.create(title="без ваги", funnel=self.main, stage=self.st_main, contact=c, amount=900)
        at = timezone.make_aware(datetime.datetime(2026, 8, 14, 12, 0))
        j1 = WarehouseJob.objects.create(deal=self.d1, assignee=self.wh, status="shipped", shipped_at=at, shipped_weight_kg=Decimal("10"))
        j0 = WarehouseJob.objects.create(deal=self.d0, assignee=self.wh, status="shipped", shipped_at=at, shipped_weight_kg=Decimal("0"))
        E = WarehousePayrollEntry.objects
        E.create(employee=self.wh, work_date=day(14), job=j1, deal=self.d1, op_type="shipment_weight",
                 quantity_kg=Decimal("10"), rate_applied=Decimal("1.5"), amount=Decimal("15"), note="10 кг")
        E.create(employee=self.wh, work_date=day(14), job=j1, deal=self.d1, op_type="packing", pack_tier="T10",
                 rate_applied=Decimal("13"), amount=Decimal("13"), note="1 шт")
        E.create(employee=self.wh, work_date=day(14), job=j1, deal=self.d1, op_type="tinting", base_value=Decimal("900"),
                 rate_applied=Decimal("0.2"), amount=Decimal("180"))
        E.create(employee=self.wh, work_date=day(14), job=j0, deal=self.d0, op_type="test_set", rate_applied=Decimal("50"),
                 amount=Decimal("100"), note="2 шт × 50 ₴")
        E.create(employee=self.wh, work_date=day(18), deal=self.d1, op_type="error", amount=Decimal("-30"), source="manual", note="Помилка")
        E.create(employee=self.wh, work_date=day(19), op_type="workday", rate_applied=Decimal("300"), amount=Decimal("300"))
        E.create(employee=self.wh, work_date=day(20), op_type="bonus_initiative", amount=Decimal("0.40"), source="manual")
        E.create(employee=self.wh, work_date=day(20), op_type="packing", amount=Decimal("999"), status="draft")  # не підтверджено
        E.create(employee=self.wh, work_date=day(1, 9), op_type="packing", amount=Decimal("777"))               # інший місяць
        E.create(employee=self.plain, work_date=day(14), op_type="packing", amount=Decimal("555"))              # інша людина

    def test_piece_detail_equals_line_with_types_links_and_warnings(self):
        calc = engine.calc(self.wh, PERIOD)
        r = self.detail(self.owner, self.wh.id)
        self.assertEqual(r.status_code, 200)
        self.assert_lines_match(r.data, calc)
        pc = next(l for l in r.data["lines"] if l["kind"] == "piece_rate")
        self.assertEqual(pc["total"], 578)                                   # 15+13+180+100−30+300+0,40
        self.assertEqual(len(pc["rows"]), 7)
        g = {x["op"]: x for x in pc["groups"]}
        self.assertEqual((g["test_set"]["amount"], g["error"]["amount"], g["shipment_weight"]["kg"]), (100.0, -30.0, 10.0))
        ts = next(x for x in pc["rows"] if x["op"] == "Збірка тестових наборів")
        self.assertEqual((ts["deal_id"], ts["qty"], ts["rate"]), (self.d0.id, 2.0, "50 ₴/набір"))
        self.assertEqual(next(x for x in pc["rows"] if x["op"] == "Тонування")["rate"], "20% від 900,00 ₴")
        self.assertEqual([x["deal_id"] for x in pc["links"]], [self.d0.id])  # відвантаження з вагою 0 — з посиланням
        self.assertTrue(any("1 з 2 відвантажень" in w for w in pc["warnings"]))
        self.assertTrue(any("двічі" in w for w in pc["warnings"]))          # ставка на місяць + «Робочий день»
        self.assertTrue(any("не підтверджені" in n for n in pc["notes"]))
        self.assertEqual(next(l for l in r.data["lines"] if l["kind"] == "fixed_monthly")["total"], 8000)

    def test_approved_month_shows_frozen_total_and_live_detail(self):
        runs.approve(self.wh, PERIOD, by=self.owner)                          # 8 000 + 578 = 8 578 заморожено
        comp = PayComponent.objects.get(scheme__user=self.wh, kind="fixed_monthly")
        comp.params = {"amount": 9000}
        comp.save()
        r = self.detail(self.owner, self.wh.id)
        self.assertEqual(r.data["run"]["total"], 8578)
        self.assertIn("затверджена сума — 8 578", r.data["frozen_note"])
        self.assertEqual(next(l for l in r.data["lines"] if l["kind"] == "fixed_monthly")["total"], 9000)  # наживо


class AccessTests(_Base):
    def test_without_rates_permission_403_with_it_200(self):
        self.plain.extra_permissions = ["deal.view", "warehouse.view.all", "finance.manage"]
        self.plain.save()
        self.assertEqual(self.detail(self.plain, self.mgr.id).status_code, 403)
        self.plain.extra_permissions = ["payroll.rates.view"]
        self.plain.save()
        self.assertEqual(self.detail(get_user_model().objects.get(pk=self.plain.pk), self.mgr.id).status_code, 200)

    def test_bad_params(self):
        self.assertEqual(self.detail(self.owner, "abc").status_code, 400)
        self.assertEqual(self.detail(self.owner, self.mgr.id, period="2026-13").status_code, 400)
        self.assertEqual(self.detail(self.owner, 999999).status_code, 404)

    def test_no_scheme_no_lines(self):
        r = self.detail(self.owner, self.plain.id)
        self.assertEqual((r.status_code, r.data["lines"], r.data["total"]), (200, [], 0))
