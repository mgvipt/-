"""15.09.2026: «Моя ЗП → Як прорахувалось» — лише свої дані; без права «маржа угоди» колонок і сум маржі немає.
Лише ізольована тестова БД; вʼюшку викликаємо напряму (APIRequestFactory)."""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.crm.models import Funnel
from apps.payroll.models import PayComponent, PayPolicy, PayScheme
from apps.payroll.my_views import MyDetailView

HOST = "crm.wallcovdec.com.ua"


class MyDetailTests(TestCase):
    def setUp(self):
        cache.clear()
        U = get_user_model()
        today = timezone.localdate()
        self.owner = U.objects.create_superuser("md-owner", "mdo@example.test", "x")
        self.mgr = U.objects.create_user("md-mgr", "mdm@example.test", "x", first_name="Тест", last_name="Менеджер")
        f = Funnel.objects.create(name="21 Основний продукт")
        PayPolicy.objects.update_or_create(pk=1, defaults={"params": {
            "replaced_articles": [], "margin_estimate_pct": {str(f.id): 50},
            "funnels": {"online": [f.id], "test": [], "main": [f.id], "salon": [], "diamond": []}}})
        for u in (self.owner, self.mgr):
            s = PayScheme.objects.create(user=u, position="Менеджер", department="Продажі", valid_from=today.replace(day=1), employment="none")
            PayComponent.objects.create(scheme=s, kind="margin_share", title="% з маржі", params={"pct_to_plan": 10, "funnels": [f.id]})
        self.rf = APIRequestFactory()

    def get(self, user, qs=""):
        r = self.rf.get("/api/payroll/my/detail/" + qs, HTTP_HOST=HOST)
        force_authenticate(r, user=user)
        return MyDetailView.as_view()(r)

    def test_only_own_data(self):
        self.assertEqual(self.get(self.mgr, "?user=%d" % self.owner.id).status_code, 403)

    def test_manager_sees_earnings_without_margin(self):
        r = self.get(self.mgr)
        self.assertEqual(r.status_code, 200)
        ms = [ln for ln in r.data["lines"] if ln["kind"] == "margin_share"]
        self.assertEqual(len(ms), 1)
        keys = [c["k"] for c in ms[0]["columns"]]
        self.assertIn("earn", keys)
        self.assertFalse({"margin", "margin_pct", "source"} & set(keys))
        self.assertFalse(any("маржа" in (str(s["label"]) + str(s["value"])).lower() for s in ms[0]["summary"]))
        self.assertTrue(r.data["margin_hidden"])

    def test_owner_sees_margin(self):
        r = self.get(self.owner)
        ms = [ln for ln in r.data["lines"] if ln["kind"] == "margin_share"][0]
        self.assertIn("margin", [c["k"] for c in ms["columns"]])
        self.assertFalse(r.data["margin_hidden"])
