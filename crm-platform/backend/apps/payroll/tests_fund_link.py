"""fm-link (14.09.2026): фонди Фінмоделі, звʼязані зі «Ставками співробітників», і регресія
«Оренда салону: змінюю число у Фінмоделі — воно повертається до 20 003»."""
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from apps.finance.models import FinModelArticle
from apps.finance.serializers import FinModelArticleSerializer
from apps.payroll.fund_link import WHERE_RATES, FundLinksView, linked_ids, set_linked, sync_linked
from apps.payroll.models import PayComponent, PayPolicy, PayRateLog, PayScheme

HOST = "crm.wallcovdec.com.ua"


class FundLinkTests(TestCase):
    def setUp(self):
        cache.clear()  # частки продажників кешуються на 5 хв
        U = get_user_model()
        self.owner = U.objects.create_superuser("fl-owner", "flo@example.test", "x")
        self.mgr = U.objects.create_user("fl-mgr", "flm@example.test", "x", first_name="Тест", last_name="Менеджер")
        self.mgr2 = U.objects.create_user("fl-mgr2", "flm2@example.test", "x", first_name="Тест", last_name="Склад")
        self.mgr3 = U.objects.create_user("fl-mgr3", "flm3@example.test", "x", first_name="Тест", last_name="Бухгалтер")
        PayPolicy.objects.update_or_create(pk=1, defaults={"params": {"replaced_articles": []}})
        FinModelArticle.objects.all().update(active=False)  # у тестовій базі — лише наші статті
        # явні id, щоб не збігтися з «жорсткими» id рушія (46 — % продажу, 55 — відрядна склад)
        self.office = FinModelArticle.objects.create(id=91001, category="fixed", name="ФОТ офіс тест",
                                                     value=Decimal("1000"), value_type="fixed_sum_per_month")
        self.other = FinModelArticle.objects.create(id=91002, category="fixed", name="ФОТ склад тест",
                                                    value=Decimal("500"), value_type="fixed_sum_per_month")
        self.rent = FinModelArticle.objects.create(id=91003, category="fixed", name="Оренда салону", unit="грн/міс",
                                                   value=Decimal("20003"), value_type="fixed_sum_per_month")
        self.vf = timezone.localdate().replace(day=1)
        self.s1 = self._scheme(self.mgr, self.office, 7000)
        self.s2 = self._scheme(self.mgr2, self.other, 3000)
        self.c = APIClient()
        self.c.force_authenticate(self.owner)

    def _scheme(self, user, fund, amount):
        s = PayScheme.objects.create(user=user, position="Менеджер", department="Продажі", valid_from=self.vf,
                                     employment="none", options={"fund_article_id": fund.id})
        PayComponent.objects.create(scheme=s, kind="fixed_monthly", params={"amount": amount})
        return s

    def _links(self, user, data=None):
        rf = APIRequestFactory()
        if data is None:
            req = rf.get("/api/payroll/funds/links/", HTTP_HOST=HOST)
        else:
            req = rf.post("/api/payroll/funds/links/", data, format="json", HTTP_HOST=HOST)
        force_authenticate(req, user=user)
        return FundLinksView.as_view()(req)

    def _val(self, a):
        a.refresh_from_db()
        return float(a.value)

    def _save_scheme(self, s, amount):
        with self.captureOnCommitCallbacks(execute=True):
            r = self.c.post(f"/api/payroll/schemes/{s.id}/save/", {"components": [
                {"kind": "fixed_monthly", "params": {"amount": amount}}]}, format="json", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 200, getattr(r, "data", r))
        return r

    # ── нічого не звʼязано, доки власник не увімкне ──
    def test_nothing_linked_by_default(self):
        self.assertEqual(linked_ids(), [])
        self.assertEqual(sync_linked(), [])
        self._save_scheme(self.s1, 9000)
        self.assertEqual(self._val(self.office), 1000)
        r = self._links(self.owner)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["can_edit"])
        self.assertFalse(any(f["linked"] for f in r.data["funds"]))

    # ── права: менеджер не бачить і не вмикає ──
    def test_manager_cannot_view_or_toggle_link(self):
        self.assertEqual(self._links(self.mgr).status_code, 403)
        self.assertEqual(self._links(self.mgr, {"fund_id": self.office.id, "linked": True}).status_code, 403)
        self.assertEqual(linked_ids(), [])
        self.assertEqual(self._val(self.office), 1000)

    # ── увімкнення одразу підставляє суму, з історією; вимкнення число не чіпає ──
    def test_toggle_on_syncs_immediately_with_history(self):
        r = self._links(self.owner, {"fund_id": self.office.id, "linked": True})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["changed"], [{"fund_id": self.office.id, "name": "ФОТ офіс тест", "unit": "₴",
                                              "before": 1000.0, "after": 7000.0}])
        self.assertEqual(self._val(self.office), 7000)
        self.assertEqual(self._val(self.other), 500)
        self.assertEqual(self._val(self.rent), 20003)
        log = PayRateLog.objects.filter(action="fund_sync").first()
        self.assertIn("авто зі Ставок", log.note)
        self.assertTrue(PayRateLog.objects.filter(action="fund_link").exists())
        r = self._links(self.owner, {"fund_id": self.office.id, "linked": False})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(linked_ids(), [])
        self.assertEqual(self._val(self.office), 7000)

    def test_fund_not_only_salaries_cannot_be_linked(self):
        smm = FinModelArticle.objects.create(id=91004, category="variable", name="Маркетинг СММ тест",
                                             value=Decimal("15000"), value_type="fixed_sum_per_month")
        self._scheme(self.mgr3, smm, 14000)
        r = self._links(self.owner, {"fund_id": smm.id, "linked": True})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(linked_ids(), [])
        self.assertEqual(self._val(smm), 15000)

    # ── синхронізація пише лише звʼязані фонди ──
    def test_sync_writes_only_linked_funds(self):
        set_linked(self.office.id, True, self.owner)
        res = sync_linked(user=self.owner)
        self.assertEqual([x["fund_id"] for x in res], [self.office.id])
        self.assertEqual(self._val(self.office), 7000)
        self.assertEqual(self._val(self.other), 500)   # за ставками 3000, але не звʼязаний
        self.assertEqual(self._val(self.rent), 20003)
        self.assertEqual(sync_linked(), [])            # вдруге — нічого не змінилось, нічого не пишемо
        self.assertEqual(PayRateLog.objects.filter(action="fund_sync").count(), 1)

    # ── збереження / створення / архівування ставки перераховує лише звʼязані фонди ──
    def test_scheme_save_triggers_sync_of_linked_only(self):
        set_linked(self.office.id, True, self.owner)
        self._save_scheme(self.s1, 9000)
        self.assertEqual(self._val(self.office), 9000)
        self.assertEqual(self._val(self.other), 500)
        self._save_scheme(self.s2, 4000)
        self.assertEqual(self._val(self.other), 500)
        self.assertEqual(self._val(self.office), 9000)
        self.assertEqual(self._val(self.rent), 20003)

    def test_scheme_create_and_archive_trigger_sync(self):
        set_linked(self.office.id, True, self.owner)
        with self.captureOnCommitCallbacks(execute=True):
            r = self.c.post("/api/payroll/schemes/", {
                "user_id": self.mgr3.id, "position": "Бухгалтер", "department": "Офіс", "valid_from": self.vf.isoformat(),
                "options": {"fund_article_id": self.office.id},
                "components": [{"kind": "fixed_monthly", "params": {"amount": 2000}}]}, format="json", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self._val(self.office), 9000)   # 7000 + 2000
        with self.captureOnCommitCallbacks(execute=True):
            r2 = self.c.post(f"/api/payroll/schemes/{r.data['id']}/archive/", {}, format="json", HTTP_HOST=HOST)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(self._val(self.office), 7000)
        self.assertEqual(self._val(self.other), 500)

    def test_sync_error_never_breaks_scheme_save(self):
        set_linked(self.office.id, True, self.owner)
        with mock.patch("apps.payroll.fund_link.fot_rows", side_effect=RuntimeError("boom")):
            self._save_scheme(self.s1, 9000)
        self.assertEqual(self.s1.components.first().params["amount"], 9000)
        self.assertEqual(self._val(self.office), 1000)

    # ── два місця не «бʼються»: звʼязане число у Фінмоделі не редагується ──
    def test_patch_linked_article_value_rejected_other_fields_ok(self):
        set_linked(self.office.id, True, self.owner)
        r = self.c.patch(f"/api/finmodel-articles/{self.office.id}/", {"value": 1234}, format="json", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 400)
        self.assertIn("Ставок співробітників", str(r.data))
        self.assertEqual(self._val(self.office), 1000)
        r = self.c.patch(f"/api/finmodel-articles/{self.office.id}/", {"name": "ФОТ офіс (перейменовано)"}, format="json", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 200)
        r = self.c.patch(f"/api/finmodel-articles/{self.office.id}/", {"value": "1000.00"}, format="json", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 200)  # те саме число — не зміна
        self.assertTrue(r.data["linked"])
        self.assertEqual(r.data["configured_in"], WHERE_RATES)

    # ── РЕГРЕСІЯ: «Оренда салону» зберігається і більше не повертається ──
    def test_rent_value_saves_and_stays(self):
        r = self.c.patch(f"/api/finmodel-articles/{self.rent.id}/", {"value": "17 500,50"}, format="json", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(Decimal(str(r.data["value"])), Decimal("17500.50"))
        self.assertFalse(r.data["linked"])
        self.assertEqual(r.data["configured_in"], "тут, у Фінмоделі")
        g = self.c.get(f"/api/finmodel-articles/{self.rent.id}/", HTTP_HOST=HOST)
        self.assertEqual(Decimal(str(g.data["value"])), Decimal("17500.50"))
        # ставки й автосинхронізація фондів оренду не чіпають
        set_linked(self.office.id, True, self.owner)
        self._save_scheme(self.s1, 9000)
        call_command("payroll_sync_funds", stdout=StringIO())
        self.assertEqual(self._val(self.rent), 17500.5)
        r = self.c.patch(f"/api/finmodel-articles/{self.rent.id}/", {"value": 18000}, format="json", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._val(self.rent), 18000)

    def test_configured_in_rules(self):
        mk = lambda i, **kw: FinModelArticle.objects.create(id=i, name=f"т{i}", value=Decimal("1"), **kw)  # noqa: E731
        cases = [
            (mk(91101, category="variable", value_type="auto_meta_ads"), "Автоматично з Meta Ads"),
            (mk(91102, category="warehouse_rate", value_type="fixed_per_deal"),
             "Налаштування → Ставки співробітників → Склад — відрядно (ті самі ставки)"),
            (mk(91103, category="salary", value_type="fixed_sum_per_month"),
             "застарілі ставки старої формули (не впливають на ЗП за ставками)"),
            (mk(91104, category="payment_fee", value_type="fixed_per_deal"), "тут, ₴ за угоду"),
            (mk(91105, category="payment_fee", value_type="percent"), "тут, у Фінмоделі"),
            (self.rent, "тут, у Фінмоделі"),
        ]
        for a, want in cases:
            self.assertEqual(FinModelArticleSerializer(a).data["configured_in"], want, a.name)
        set_linked(self.office.id, True, self.owner)
        d = FinModelArticleSerializer(self.office).data
        self.assertTrue(d["linked"])
        self.assertEqual(d["configured_in"], WHERE_RATES)

    def test_command_dry_then_live(self):
        out = StringIO()
        call_command("payroll_sync_funds", "--dry", stdout=out)
        self.assertIn("Звʼязаних фондів немає", out.getvalue())
        set_linked(self.office.id, True, self.owner)
        out = StringIO()
        call_command("payroll_sync_funds", "--dry", stdout=out)
        self.assertIn("DRY", out.getvalue())
        self.assertEqual(self._val(self.office), 1000)
        call_command("payroll_sync_funds", stdout=StringIO())
        self.assertEqual(self._val(self.office), 7000)
