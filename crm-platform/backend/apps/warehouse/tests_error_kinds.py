"""19.09.2026: типи помилок складу і доступ до списку помилок."""
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User

from .models import WarehouseError


class ErrorKindsTests(TestCase):
    def setUp(self):
        self.inna = User.objects.create_user(username="wh_inna", password="x")
        self.ilona = User.objects.create_user(username="wh_ilona", password="x")
        self.boss = User.objects.create_superuser(username="wh_boss", password="x")

    def _c(self, u):
        c = APIClient(); c.force_authenticate(u); return c

    def test_kind_is_saved_and_unknown_becomes_other(self):
        self._c(self.inna).post("/api/warehouse/errors/", {"kind": "lid_tape", "description": "без скотчу"}, format="json")
        self._c(self.inna).post("/api/warehouse/errors/", {"kind": "hack", "description": "?"}, format="json")
        self.assertEqual(sorted(WarehouseError.objects.values_list("kind", flat=True)), ["lid_tape", "other"])

    def test_employee_sees_only_own_errors(self):
        WarehouseError.objects.create(kind="no_board", blamed_user=self.ilona, reported_by=self.boss)
        WarehouseError.objects.create(kind="sticker_miss", blamed_user=self.inna, reported_by=self.boss)
        mine = self._c(self.inna).get("/api/warehouse/errors/").data
        self.assertEqual([e["kind"] for e in mine], ["Не наклеєна наклейка"])
        self.assertEqual(len(self._c(self.boss).get("/api/warehouse/errors/").data), 2)

    def test_kinds_list_for_picker(self):
        kinds = {k["code"] for k in self._c(self.inna).get("/api/warehouse/errors/?kinds=1").data}
        self.assertTrue({"no_board", "sticker_bad", "sticker_miss", "lid_tape", "wrong_tint"} <= kinds)
