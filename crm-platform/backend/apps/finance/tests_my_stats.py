"""16.09.2026: своя статистика місяця — у кожного (/api/finance/salary/deals/); чужу без прав не видно."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.finance.views import ManagerDealsView

HOST = "crm.wallcovdec.com.ua"


class MyStatsAccessTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.owner = U.objects.create_superuser("st-owner", "sto@example.test", "x")
        self.mgr = U.objects.create_user("st-mgr", "stm@example.test", "x", first_name="Тест", last_name="Менеджер")
        self.other = U.objects.create_user("st-other", "sto2@example.test", "x", first_name="Інший", last_name="Менеджер")
        self.rf = APIRequestFactory()

    def get(self, who, qs=""):
        r = self.rf.get("/api/finance/salary/deals/" + qs, HTTP_HOST=HOST)
        force_authenticate(r, user=who)
        return ManagerDealsView.as_view()(r)

    def test_own_stats_without_finance_right(self):
        r = self.get(self.mgr, "?user=%d" % self.mgr.id)
        self.assertEqual(r.status_code, 200)
        self.assertIn("by_day", r.data)
        self.assertEqual(self.get(self.mgr, "?user=me").status_code, 200)

    def test_other_person_forbidden(self):
        self.assertEqual(self.get(self.mgr, "?user=%d" % self.other.id).status_code, 403)

    def test_owner_sees_anyone(self):
        self.assertEqual(self.get(self.owner, "?user=%d" % self.mgr.id).status_code, 200)
