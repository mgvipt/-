from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.crm.models import Funnel, Stage, Lead

User = get_user_model()


class RoleScopingTests(TestCase):
    """Проверяем ключевую логику прав: свои/все лиды и доступ к воронкам."""

    def setUp(self):
        # воронки
        self.f21 = Funnel.objects.create(name="21 Основний", order=1)
        self.f22 = Funnel.objects.create(name="22 Тестовий", order=2)
        self.s21 = Stage.objects.create(funnel=self.f21, name="Новий", order=0)
        self.s22 = Stage.objects.create(funnel=self.f22, name="Новий", order=0)

        # роли
        self.r_all = Role.objects.create(name="Руководитель", permissions=["lead.view.all"])
        self.r_own = Role.objects.create(name="Менеджер", permissions=["lead.view.own"])
        self.r_own.funnels.set([self.f21])  # менеджер видит только воронку 21

        # пользователи
        self.head = User.objects.create_user("head", password="x", role=self.r_all)
        self.m1 = User.objects.create_user("m1", password="x", role=self.r_own)
        self.m2 = User.objects.create_user("m2", password="x", role=self.r_own)

        # лиды
        Lead.objects.create(title="L1", funnel=self.f21, stage=self.s21, owner=self.m1)
        Lead.objects.create(title="L2", funnel=self.f21, stage=self.s21, owner=self.m2)
        Lead.objects.create(title="L3-other-funnel", funnel=self.f22, stage=self.s22, owner=self.m1)

    def _leads_for(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return {l["title"] for l in c.get("/api/leads/").json()["results"]}

    def test_manager_sees_only_own_and_allowed_funnel(self):
        # m1: свой лид в воронке 21 — да; свой лид в воронке 22 — нет (нет доступа к воронке)
        titles = self._leads_for(self.m1)
        self.assertEqual(titles, {"L1"})

    def test_manager_does_not_see_others_leads(self):
        self.assertNotIn("L2", self._leads_for(self.m1))

    def test_head_sees_all_leads_in_allowed_funnels(self):
        # руководитель без ограничения по воронкам и с lead.view.all видит всё
        titles = self._leads_for(self.head)
        self.assertEqual(titles, {"L1", "L2", "L3-other-funnel"})

    def test_funnel_list_filtered_by_role(self):
        c = APIClient()
        c.force_authenticate(self.m1)
        names = {f["name"] for f in c.get("/api/funnels/").json()["results"]}
        self.assertEqual(names, {"21 Основний"})
