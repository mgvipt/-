"""KPI складу (15.09.2026, whkpi): пункти стандарту, підказка CRM, «Як виконати план», команда нових версій.

Лише ізольована тестова БД; фото — рядки без файлів (на диск нічого не пишеться)."""
from datetime import date, datetime
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from apps.crm.models import Deal, Funnel, Stage
from apps.finance.models import WorkDay
from apps.integrations.models import IncomingDoc
from apps.payroll import engine, wh_kpi
from apps.payroll.models import PayComponent, PayPolicy, PayRateLog, PayScheme
from apps.payroll.my_views import STANDARD_SALES, MyPayrollView
from apps.warehouse.models import Product, StockDocument, StockMovement, Warehouse, WarehouseJob, WarehousePhoto

HOST = "crm.wallcovdec.com.ua"
TODAY = date(2026, 9, 15)


def at(y, m, d, hh, mm=0):
    return timezone.make_aware(datetime(y, m, d, hh, mm))


class _Base(TestCase):
    def setUp(self):
        cache.clear()
        PayPolicy.objects.update_or_create(pk=1, defaults={"params": {"replaced_articles": []}})
        U = get_user_model()
        self.owner = U.objects.create_superuser("wk-owner", "wko@example.test", "x")
        self.w = U.objects.create_user("wk-inna", "wki@example.test", "x", first_name="Інна", last_name="Тест")
        self.o = U.objects.create_user("wk-lar", "wkl@example.test", "x", first_name="Ілона", last_name="Тест")
        self.f = Funnel.objects.create(name="21 Основний продукт")
        self.st = Stage.objects.create(funnel=self.f, name="Оплату отримано", order=0)
        self.wh = Warehouse.objects.create(name="Основний", is_default=True)
        self.prod = Product.objects.create(name="Шовк 5 кг", weight_kg=Decimal("5"), price=Decimal("1000"), cost=Decimal("400"))
        self.rf = APIRequestFactory()

    def deal(self, ttn="20450000000001", kg=5, parent=None):
        return Deal.objects.create(title="T", funnel=self.f, stage=self.st, amount=Decimal("1000"), ttn=ttn,
                                   np_data={"seats": [{"kg": kg}]} if kg else {}, parent_deal=parent)

    def job(self, created, shipped=None, assignee=None, status=None, photo=True, deal=None, weight=0):
        d = deal or self.deal()
        j = WarehouseJob.objects.create(deal=d, assignee=assignee, status=status or ("shipped" if shipped else "queued"),
                                        shipped_weight_kg=Decimal(str(weight)))
        WarehouseJob.objects.filter(pk=j.pk).update(created_at=created, shipped_at=shipped)
        if photo:
            WarehousePhoto.objects.create(job=j, deal=d, employee=assignee, kind="parcel", image="warehouse_photos/t.jpg")
        return j

    def worked(self, user, *days):
        for d in days:
            WorkDay.objects.create(user=user, date=d, status="worked")

    def receipt(self, created, price, src=None):
        doc = StockDocument.objects.create(kind="in", warehouse=self.wh, source_invoice_doc=src.id if src else None)
        StockDocument.objects.filter(pk=doc.pk).update(created_at=created)
        StockMovement.objects.create(document=doc, product=self.prod, quantity=Decimal("1"), price=Decimal(str(price)))
        return doc

    def mail(self, uid, created, status="confirmed"):
        i = IncomingDoc.objects.create(mailbox="m", message_uid=uid, doc_type="supplier", status=status)
        IncomingDoc.objects.filter(pk=i.pk).update(created_at=created)
        return i

    def wh_scheme(self, user, amount=8000, vf=date(2026, 7, 1)):
        s = PayScheme.objects.create(user=user, position="Комірник", department="Склад", title="Ставка + відрядно",
                                     valid_from=vf, employment="none")
        PayComponent.objects.create(scheme=s, kind="fixed_monthly", title="Ставка", params={"amount": amount}, order=0)
        PayComponent.objects.create(scheme=s, kind="piece_rate", title="Відрядно", params={}, order=1)
        return s

    def std(self, scheme, **params):
        return PayComponent.objects.create(scheme=scheme, kind="standard", title="Стандарт складу", order=2,
                                           params={"max": 3000, "criteria": wh_kpi.WH_STANDARD_CRITERIA, **params})


class SuggestTests(_Base):
    def test_mixed_month_math(self):
        self.worked(self.w, date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5))
        self.worked(self.o, date(2026, 8, 4))
        j1 = self.job(at(2026, 8, 3, 10), at(2026, 8, 3, 17), self.w)                           # вчасно, фото, вага ТТН
        self.job(at(2026, 8, 3, 12), at(2026, 8, 4, 16), self.w, deal=self.deal(kg=0))           # наступного дня; ваги немає
        self.job(at(2026, 8, 3, 15), at(2026, 8, 4, 17), self.w, deal=self.deal(kg=0), weight=3)  # після 14:00; вага замовлення
        self.job(at(2026, 8, 4, 9), at(2026, 8, 5, 17), self.o)                                  # задача іншої (вона на зміні)
        self.job(at(2026, 8, 4, 11), None, None, photo=False)                                    # ніхто не взяв
        self.job(at(2026, 8, 3, 10, 30), at(2026, 8, 3, 17), self.w, photo=False, deal=self.deal(parent=j1.deal))  # дозамовлення
        self.job(at(2026, 8, 3, 9), None, None, status="cancelled", photo=False)                 # скасовано
        a = self.mail("1", at(2026, 8, 4, 9))
        b = self.mail("2", at(2026, 8, 5, 10))
        self.receipt(at(2026, 8, 4, 12), 400, a)       # того ж дня
        self.receipt(at(2026, 8, 6, 11), 400, b)       # наступного дня
        self.receipt(at(2026, 8, 7, 11), 0)            # без собівартості
        self.mail("3", at(2026, 8, 10, 10), status="draft")   # не оприбутковано
        with CaptureQueriesContext(connection) as q:
            r = wh_kpi.suggest_wh_standard(self.w, "2026-08", today=TODAY)
        self.assertLessEqual(len(q), 15)
        p = {x["key"]: x for x in r["points"]}
        self.assertEqual((p["ship_same_day"]["value"], p["ship_same_day"]["pass"]), (33.3, False))   # 1 з 3
        self.assertEqual((p["weight_photo"]["value"], p["weight_photo"]["pass"]), (66.7, False))     # 2 з 3
        self.assertEqual((p["queue_clean"]["value"], p["queue_clean"]["pass"]), (66.7, False))       # 05.08 — задача з 04.08
        self.assertEqual((p["receipt_same_day"]["value"], p["receipt_same_day"]["pass"]), (33.3, False))
        self.assertIn("собівартість є в 2 з 3", p["receipt_same_day"]["value_text"])
        self.assertEqual([x["n"] for x in r["points"] if x["how_measured"] == "auto"], [1, 4, 5, 6])
        self.assertEqual((r["workdays"], r["good"], r["suggested_pct"]), (3, 4, 50))
        self.assertTrue(all(x["mark"] for x in r["points"] if x["how_measured"] == "manual"))

    def test_clean_month_and_manual_marks(self):
        self.worked(self.w, date(2026, 8, 3))
        self.job(at(2026, 8, 3, 10), at(2026, 8, 3, 17), self.w)
        c = self.std(self.wh_scheme(self.w))
        r = wh_kpi.suggest_wh_standard(self.w, "2026-08", c, today=TODAY)
        self.assertEqual(r["suggested_pct"], 100)                  # приходів немає → пункт 6 не знижує
        self.assertIsNone({x["key"]: x for x in r["points"]}["receipt_same_day"]["pass"])
        c.params = {**c.params, "items": {"2026-08": {"no_damage": False}}}
        c.save()
        r = wh_kpi.suggest_wh_standard(self.w, "2026-08", c, today=TODAY)
        self.assertEqual((r["suggested_score"], r["suggested_pct"]), (0.875, 88))

    def test_current_month_only_finished_days(self):
        self.worked(self.w, date(2026, 9, 14), date(2026, 9, 15))
        self.job(at(2026, 9, 15, 10), None, self.w, status="packing")   # сьогодні — ще не оцінюємо
        r = wh_kpi.suggest_wh_standard(self.w, "2026-09", today=TODAY)
        self.assertEqual((r["to"], r["partial"]), ("2026-09-14", True))
        self.assertIsNone({x["key"]: x for x in r["points"]}["ship_same_day"]["pass"])


class CriteriaTests(_Base):
    def test_standard_amount_unchanged_detail_explains(self):
        c = self.std(self.wh_scheme(self.w), scores={"2026-09": 0.8}, items={"2026-09": {"no_damage": False}})
        ln, score = engine._c_standard(c, "2026-09")
        self.assertEqual((ln["amount"], score), (2400, 0.8))
        self.assertIn("8 пунктів", ln["detail"])
        self.assertIn("не виконано: 3", ln["detail"])
        plain = PayComponent(kind="standard", params={"max": 6000})
        ln2, s2 = engine._c_standard(plain, "2026-09")
        self.assertEqual((ln2["amount"], s2, ln2["detail"]), (6000, 1.0, "оцінка стандарту за місяць"))

    def test_criteria_saved_and_listed(self):
        s = self.wh_scheme(self.w)
        api = APIClient()
        api.force_authenticate(self.owner)
        comps = [{"kind": "base_by_days", "title": "За вихід", "params": {"amount": 5000}},
                 {"kind": "standard", "title": "Стандарт складу", "params": {"max": 3000, "criteria": wh_kpi.WH_STANDARD_CRITERIA}},
                 {"kind": "piece_rate", "title": "Відрядно", "params": {}}]
        r = api.post(f"/api/payroll/schemes/{s.id}/save/", {"valid_from": "2026-07-01", "components": comps}, format="json", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 200)
        r = api.get("/api/payroll/schemes/", HTTP_HOST=HOST)
        row = next(x for x in r.json()["schemes"] if x["id"] == s.id)
        std = next(c for c in row["components"] if c["kind"] == "standard")
        self.assertEqual([c["key"] for c in std["params"]["criteria"]], [c["key"] for c in wh_kpi.WH_STANDARD_CRITERIA])

    def test_view_get_post(self):
        s = self.wh_scheme(self.w)
        c = self.std(s)
        req = self.rf.get(f"/api/payroll/wh-kpi/?scheme={s.id}&period=2026-08", HTTP_HOST=HOST)
        force_authenticate(req, user=self.owner)
        r = wh_kpi.WhKpiView.as_view()(req)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data["points"]), 8)
        req = self.rf.get(f"/api/payroll/wh-kpi/?scheme={s.id}&period=2026-08", HTTP_HOST=HOST)
        force_authenticate(req, user=self.w)
        self.assertEqual(wh_kpi.WhKpiView.as_view()(req).status_code, 403)
        body = {"component": c.id, "period": "2026-09", "score": 0.875, "items": {"no_damage": False, "stock_accuracy": True, "zzz": False}}
        req = self.rf.post("/api/payroll/wh-kpi/", body, format="json", HTTP_HOST=HOST)
        force_authenticate(req, user=self.owner)
        r = wh_kpi.WhKpiView.as_view()(req)
        self.assertEqual(r.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.params["scores"]["2026-09"], 0.875)
        self.assertEqual(c.params["items"]["2026-09"], {"no_damage": False, "stock_accuracy": True})
        log = PayRateLog.objects.filter(scheme=s, action="mark").latest("id")
        self.assertIn("не виконано пункти 3", log.note)
        self.assertNotIn("2026-09", (log.before["params"].get("scores") or {}))
        line = next(l for l in engine.calc(self.w, "2026-09")["lines"] if l["kind"] == "standard")
        self.assertEqual(line["amount"], round(3000 * 0.875))


class RulesTests(_Base):
    def _rules(self, user):
        req = self.rf.get("/api/payroll/my/?only=rules", HTTP_HOST=HOST)
        force_authenticate(req, user=user)
        return MyPayrollView.as_view()(req).data

    def test_warehouse_standard_rules_plain_words(self):
        self.std(self.wh_scheme(self.w))
        d = self._rules(self.w)
        rule = next(r for r in d["rules"] if r["kind"] == "standard")
        self.assertEqual(len(rule["need"]), 9)
        self.assertTrue(rule["need"][0].startswith("1. Відвантаження вчасно"))
        self.assertIn("CRM рахує сама", rule["need"][0])
        self.assertIn("Відмічає керівник", rule["need"][1])
        self.assertTrue(any("«Відвантаження»" in x for x in rule["where"]))
        self.assertFalse(any(x in rule["need"] for x in STANDARD_SALES))
        part = next(p for p in d["scheme"]["parts"] if p["kind"] == "standard")
        self.assertIn("8 пунктами", part["plain"])

    def test_sales_standard_text_unchanged(self):
        s = PayScheme.objects.create(user=self.o, position="Менеджер", department="Продажі", valid_from=date(2026, 7, 1))
        PayComponent.objects.create(scheme=s, kind="standard", title="Стандарт роботи", params={"max": 6000})
        PayComponent.objects.create(scheme=s, kind="margin_share", params={"funnels": [15], "pct_to_plan": 10})
        rule = next(r for r in self._rules(self.o)["rules"] if r["kind"] == "standard")
        self.assertIn(STANDARD_SALES[0], rule["need"])


class CommandTests(_Base):
    def plan(self):
        return f"{self.w.id}:5000:3000,{self.o.id}:4400:2600"

    def counts(self):
        return PayScheme.objects.count(), PayComponent.objects.count(), PayRateLog.objects.count()

    def test_dry_writes_nothing(self):
        self.wh_scheme(self.w, 8000)
        self.wh_scheme(self.o, 7000)
        self.worked(self.w, date(2026, 8, 3))
        before = self.counts()
        out = StringIO()
        call_command("payroll_wh_kpi_apply", "--dry", "--plan", self.plan(), "--today", "2026-09-15", stdout=out)
        self.assertEqual(self.counts(), before)
        txt = out.getvalue()
        for s in ("DRY", "НОВА версія з 01.10.2026", "5 000", "4 400", "2 600", "оцінка 80%", "підказана оцінка"):
            self.assertIn(s, txt)

    def test_live_new_version_keeps_september(self):
        s1, s2 = self.wh_scheme(self.w, 8000), self.wh_scheme(self.o, 7000)
        self.worked(self.w, date(2026, 9, 1), date(2026, 9, 2))
        sep_before = [engine.calc(u, "2026-09") for u in (self.w, self.o)]
        args = ("payroll_wh_kpi_apply", "--live", "--plan", self.plan(), "--by", self.owner.username, "--today", "2026-09-15", "--no-suggest")
        call_command(*args, stdout=StringIO())
        s1.refresh_from_db()
        s2.refresh_from_db()
        self.assertEqual((s1.valid_to, s2.valid_to), (date(2026, 9, 30), date(2026, 9, 30)))
        for u, base, mx in ((self.w, 5000, 3000), (self.o, 4400, 2600)):
            new = PayScheme.objects.get(user=u, valid_from=date(2026, 10, 1))
            kinds = {c.kind: c.params for c in new.components.all()}
            self.assertEqual((kinds["base_by_days"]["amount"], kinds["standard"]["max"]), (base, mx))
            self.assertEqual(len(kinds["standard"]["criteria"]), 8)
            self.assertIn("piece_rate", kinds)
            self.assertTrue(PayRateLog.objects.filter(scheme=new, action="new_version").exists())
        self.assertEqual([engine.calc(u, "2026-09") for u in (self.w, self.o)], sep_before)   # вересень не змінився
        octo = engine.calc(self.w, "2026-10")
        self.assertEqual((octo["scheme"]["valid_from"], octo["total"]), ("2026-10-01", 8000))
        before = self.counts()
        call_command(*args, stdout=StringIO())   # повторний запуск нічого не дублює
        self.assertEqual(self.counts(), before)
