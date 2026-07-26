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


class ZamerClientScopingTests(TestCase):
    """Замеры и смета никогда не смешиваются между клиентами."""

    def setUp(self):
        from apps.crm.models import Contact, Deal, Estimate, ZamerProject
        self.Contact = Contact
        self.Deal = Deal
        self.ZamerProject = ZamerProject
        self.Estimate = Estimate
        self.user = User.objects.create_superuser("zamer-admin", "zamer@example.com", "x")
        self.client_a = Contact.objects.create(first_name="Клиент А", phone="+380000000001")
        self.client_b = Contact.objects.create(first_name="Клиент Б", phone="+380000000002")
        self.funnel = Funnel.objects.create(id=5, name="Покрытия для стен", order=5)
        self.stage = Stage.objects.create(funnel=self.funnel, name="Новая", order=0)
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def payload(self, client_id):
        return {
            "client_id": client_id,
            "project_uuid": "project-a",
            "device_uuid": "test-device",
            "project_name": "Квартира А",
            "rooms": [{
                "name": "Гостиная",
                "walls": [{"width_cm": 500, "height_cm": 270}],
                "openings": [],
                "gross_m2": 13.5,
                "openings_m2": 1.5,
                "net_m2": 12,
                "net_with_reserve_m2": 13.2,
                "perimeter_m": 14,
                "floor_m2": 20,
                "ceiling_m2": 20,
                "reveals_linear_m": 5.4,
                "reveals_area_m2": 1.1,
            }],
            "estimate": {"area_m2": 12, "total": 25000, "lines": []},
        }

    def test_creates_scoped_deal_and_project_for_selected_client(self):
        response = self.api.post("/api/zamer/", self.payload(self.client_a.id), format="json")
        self.assertEqual(response.status_code, 200, response.json())
        deal = self.Deal.objects.get(pk=response.json()["deal_id"])
        self.assertEqual(deal.contact_id, self.client_a.id)
        self.assertEqual(float(deal.amount), 25000)
        project = self.ZamerProject.objects.get(project_uuid="project-a")
        self.assertEqual(project.contact_id, self.client_a.id)
        self.assertEqual(project.deal_id, deal.id)
        self.assertEqual(project.payload["clientId"], self.client_a.id)
        self.assertEqual(project.payload["rooms"][0]["name"], "Гостиная")

        a = self.api.get(f"/api/contacts/{self.client_a.id}/").json()
        b = self.api.get(f"/api/contacts/{self.client_b.id}/").json()
        self.assertEqual(len(a["zamer_projects"]), 1)
        self.assertEqual(b["zamer_projects"], [])
        estimate = self.Estimate.objects.get(project=project, deal=deal)
        self.assertEqual(estimate.contact_id, self.client_a.id)
        self.assertEqual(estimate.measurement_snapshot["rooms"][0]["name"], "Гостиная")
        self.assertEqual(response.json()["estimate_id"], estimate.id)

    def test_rejects_deal_owned_by_another_client(self):
        foreign = self.Deal.objects.create(
            title="Чужая сделка", contact=self.client_b,
            funnel=self.funnel, stage=self.stage,
        )
        body = self.payload(self.client_a.id)
        body["deal_id"] = foreign.id
        response = self.api.post("/api/zamer/", body, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(foreign.contact_id, self.client_b.id)


class ZamerResponsibilityAndCalculatorTests(TestCase):
    def setUp(self):
        from apps.crm.models import Contact, Deal, Estimate
        self.Contact = Contact
        self.Deal = Deal
        self.Estimate = Estimate
        role = Role.objects.create(
            name="Замерщик",
            permissions=["zamer.access", "zamer.deal.create", "calc.access", "deal.smeta.tab"],
        )
        role_manage = Role.objects.create(
            name="Ответственный за калькулятор",
            permissions=["calc.access", "calc.settings.manage"],
        )
        self.worker = User.objects.create_user("worker", password="x", role=role)
        self.other = User.objects.create_user("other", password="x", role=role)
        self.calc_manager = User.objects.create_user("calc-manager", password="x", role=role_manage)
        self.own_contact = Contact.objects.create(first_name="Свой", phone="+380000000011", owner=self.worker)
        self.foreign_contact = Contact.objects.create(first_name="Чужой", phone="+380000000012", owner=self.other)
        self.funnel = Funnel.objects.create(id=5, name="Покрытия для стен", order=5)
        self.stage = Stage.objects.create(funnel=self.funnel, name="Новая", order=0)
        role.funnels.add(self.funnel)
        self.api = APIClient()
        self.api.force_authenticate(self.worker)

    def payload(self, contact_id, project_uuid="scoped-project"):
        return {
            "client_id": contact_id,
            "project_uuid": project_uuid,
            "device_uuid": "shared-iphone",
            "project_name": "Объект",
            "rooms": [{"name": "Комната", "walls": [], "openings": [], "net_m2": 12}],
            "estimate": {"area_m2": 12, "total": 1000, "lines": []},
        }

    def test_guessed_foreign_contact_is_not_visible(self):
        response = self.api.post("/api/zamer/", self.payload(self.foreign_contact.id), format="json")
        self.assertEqual(response.status_code, 404)

    def test_shared_device_does_not_mix_accounts(self):
        own = self.api.post("/api/zamer/", self.payload(self.own_contact.id), format="json")
        self.assertEqual(own.status_code, 200, own.json())
        rows = self.api.get("/api/zamer/projects/?device_uuid=shared-iphone").json()
        self.assertEqual([row["project_uuid"] for row in rows], ["scoped-project"])

        other_api = APIClient(); other_api.force_authenticate(self.other)
        self.assertEqual(other_api.get("/api/zamer/projects/?device_uuid=shared-iphone").json(), [])

        conflict = other_api.post(
            "/api/zamer/", self.payload(self.foreign_contact.id), format="json",
        )
        self.assertEqual(conflict.status_code, 409, conflict.json())
        self.assertFalse(self.Deal.objects.filter(contact=self.foreign_contact).exists())

    def test_calc_settings_are_delegated_by_permission(self):
        denied = self.api.patch("/api/calc-settings/", {"values": {"reserve_pct": 17}}, format="json")
        self.assertEqual(denied.status_code, 403)

        manager_api = APIClient(); manager_api.force_authenticate(self.calc_manager)
        saved = manager_api.patch("/api/calc-settings/", {"values": {"reserve_pct": 17}}, format="json")
        self.assertEqual(saved.status_code, 200, saved.json())
        self.assertEqual(saved.json()["values"]["reserve_pct"], 17)

        staff_values = self.api.get("/api/calc-settings/").json()["values"]
        self.assertEqual(staff_values["reserve_pct"], 17)
        self.assertIn("labor_wall_m2", staff_values)

    def test_estimate_patch_requires_calculator_or_deal_tab_permission(self):
        created = self.api.post(
            "/api/zamer/", self.payload(self.own_contact.id), format="json",
        )
        self.assertEqual(created.status_code, 200, created.json())
        estimate_id = created.json()["estimate_id"]
        self.worker.role.permissions = ["zamer.access", "zamer.deal.create"]
        self.worker.role.save(update_fields=["permissions"])

        denied = self.api.patch(
            f"/api/estimates/{estimate_id}/", {"status": "accepted"}, format="json",
        )
        self.assertEqual(denied.status_code, 403)

    def test_estimate_scope_excludes_deal_from_disallowed_funnel(self):
        hidden_funnel = Funnel.objects.create(name="Скрытая воронка", order=99)
        hidden_stage = Stage.objects.create(funnel=hidden_funnel, name="Новая", order=0)
        hidden_deal = self.Deal.objects.create(
            title="Скрытая сделка", contact=self.own_contact, owner=self.worker,
            funnel=hidden_funnel, stage=hidden_stage,
        )
        self.Estimate.objects.create(
            name="Скрытая смета", contact=self.own_contact,
            deal=hidden_deal, owner=self.worker,
        )

        response = self.api.get(f"/api/estimates/?deal_id={hidden_deal.id}")
        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual(response.json(), [])
