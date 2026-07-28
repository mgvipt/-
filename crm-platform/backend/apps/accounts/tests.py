from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.accounts.models import Department, Invite, Role, User
from apps.crm.models import (
    ActivityLog, Contact, Deal, Estimate, Funnel, Lead, Stage,
    ZamerProject, ZamerStageReview,
)


class ClientAccountSecurityTests(TestCase):
    """Security regression tests for public client accounts and their own data."""

    def registration_payload(self, **overrides):
        data = {
            "name": "Тестовый Клиент",
            "phone": "+380671110001",
            "email": "client1@example.test",
            "password": "ClientPass123!",
        }
        data.update(overrides)
        return data

    def make_client(self, suffix):
        phone = f"+38067112{suffix:04d}"
        user = User.objects.create_user(
            username=phone,
            password="ClientPass123!",
            phone=phone,
            account_kind=User.AccountKind.CLIENT,
            role=None,
            department=None,
            extra_permissions=[],
            denied_permissions=[],
            is_staff=False,
            is_superuser=False,
        )
        contact = Contact.objects.create(
            first_name=f"Клиент {suffix}", phone=phone, kinds=["client"],
            source="app_zamer", portal_user=user,
        )
        token = Token.objects.create(user=user)
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return user, contact, api

    def test_public_registration_creates_client_and_new_portal_contact(self):
        existing = Contact.objects.create(
            first_name="Существующий CRM контакт", phone="+380671110001",
        )
        response = APIClient().post(
            "/api/auth/register/", self.registration_payload(), format="json",
            REMOTE_ADDR="10.10.0.1",
        )
        self.assertEqual(response.status_code, 201, response.json())
        user = User.objects.get(phone="+380671110001")
        contact = Contact.objects.get(portal_user=user)
        self.assertEqual(user.account_kind, User.AccountKind.CLIENT)
        self.assertIsNone(user.role_id)
        self.assertIsNone(user.department_id)
        self.assertEqual(user.extra_permissions, [])
        self.assertEqual(user.denied_permissions, [])
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertNotEqual(contact.id, existing.id)
        self.assertEqual(response.json()["contact_id"], contact.id)
        self.assertEqual(response.json()["profile"]["account_kind"], "client")
        self.assertEqual(response.json()["profile"]["contact_id"], contact.id)
        self.assertTrue(response.json()["token"])

    def test_public_registration_rejects_privilege_payload(self):
        payload = self.registration_payload(
            role=1,
            department=1,
            account_kind="staff",
            is_superuser=True,
            extra_permissions=["roles.manage"],
        )
        response = APIClient().post(
            "/api/auth/register/", payload, format="json", REMOTE_ADDR="10.10.0.2",
        )
        self.assertEqual(response.status_code, 400, response.json())
        self.assertFalse(User.objects.filter(phone="+380671110001").exists())

    def test_client_token_is_blocked_from_every_internal_api(self):
        _, _, api = self.make_client(1)
        self.assertEqual(api.get("/api/me/").status_code, 200)
        for path in (
            "/api/users/",
            "/api/contacts/",
            "/api/deals/",
            "/api/finance/dashboard/",
            "/api/conversations/",
            "/api/calc-settings/",
        ):
            with self.subTest(path=path):
                self.assertEqual(api.get(path).status_code, 403)

    def test_client_session_has_the_same_boundary(self):
        user, _, _ = self.make_client(2)
        api = APIClient()
        api.force_login(user)
        self.assertEqual(api.get("/api/me/").status_code, 200)
        self.assertEqual(api.get("/api/contacts/").status_code, 403)
        self.assertEqual(api.get("/api/inbox/ping/").status_code, 403)

    def test_two_client_accounts_never_share_projects_on_one_device(self):
        user_a, contact_a, api_a = self.make_client(3)
        _, contact_b, api_b = self.make_client(4)
        body = {
            "device_uuid": "shared-iphone",
            "project_uuid": "client-project-a",
            "title": "Моя комната",
            "payload": {"rooms": []},
        }
        created = api_a.post("/api/zamer/projects/", body, format="json")
        self.assertEqual(created.status_code, 200, created.json())
        project = ZamerProject.objects.get(user=user_a, project_uuid="client-project-a")
        self.assertEqual(project.contact_id, contact_a.id)
        self.assertIsNone(project.deal_id)
        self.assertEqual(api_b.get("/api/zamer/projects/?device_uuid=shared-iphone").json(), [])

        conflict = api_b.post("/api/zamer/projects/", body, format="json")
        self.assertEqual(conflict.status_code, 409, conflict.json())
        own_b = dict(body, project_uuid="client-project-b")
        self.assertEqual(api_b.post("/api/zamer/projects/", own_b, format="json").status_code, 200)
        self.assertEqual(
            ZamerProject.objects.get(project_uuid="client-project-b").contact_id,
            contact_b.id,
        )

    def test_client_project_rejects_arbitrary_contact_and_deal_ids(self):
        _, _, api = self.make_client(5)
        foreign = Contact.objects.create(first_name="Чужой", phone="+380670000000")
        funnel = Funnel.objects.create(name="Тестовая воронка")
        stage = Stage.objects.create(funnel=funnel, name="Новая", order=0)
        deal = Deal.objects.create(title="Чужая сделка", contact=foreign, funnel=funnel, stage=stage)
        base = {
            "device_uuid": "client-device",
            "project_uuid": "no-foreign-links",
            "title": "Комната",
            "payload": {"rooms": []},
        }
        attempts = [
            {**base, "client_id": foreign.id},
            {**base, "deal_id": deal.id},
            {**base, "payload": {"rooms": [], "clientId": foreign.id}},
            {**base, "payload": {"rooms": [], "dealId": deal.id}},
        ]
        for payload in attempts:
            with self.subTest(payload=payload):
                response = api.post("/api/zamer/projects/", payload, format="json")
                self.assertEqual(response.status_code, 400, response.json())
        self.assertFalse(ZamerProject.objects.filter(project_uuid="no-foreign-links").exists())

    def test_client_project_revision_conflict_never_overwrites_fresh_payload(self):
        user, _, api = self.make_client(19)
        body = {
            "device_uuid": "revision-device",
            "project_uuid": "revision-project",
            "title": "Комната",
            "payload": {"rooms": [], "marker": "initial"},
        }
        created = api.post("/api/zamer/projects/", body, format="json")
        self.assertEqual(created.status_code, 200, created.json())
        self.assertEqual(created.json()["revision"], 1)

        fresh = {
            **body,
            "base_revision": 1,
            "payload": {"rooms": [], "marker": "fresh"},
        }
        updated = api.post("/api/zamer/projects/", fresh, format="json")
        self.assertEqual(updated.status_code, 200, updated.json())
        self.assertEqual(updated.json()["revision"], 2)

        stale = {
            **body,
            "base_revision": 1,
            "payload": {"rooms": [], "marker": "stale"},
        }
        conflict = api.post("/api/zamer/projects/", stale, format="json")
        self.assertEqual(conflict.status_code, 409, conflict.json())
        self.assertEqual(conflict.json(), {
            "error": "project_revision_conflict", "revision": 2,
        })
        project = ZamerProject.objects.get(user=user, project_uuid=body["project_uuid"])
        self.assertEqual(project.revision, 2)
        self.assertEqual(project.payload["marker"], "fresh")

        missing_revision = api.post("/api/zamer/projects/", body, format="json")
        self.assertEqual(missing_revision.status_code, 409, missing_revision.json())
        project.refresh_from_db()
        self.assertEqual(project.revision, 2)
        self.assertEqual(project.payload["marker"], "fresh")

    def test_authenticated_client_zamer_registration_uses_own_contact(self):
        user, own_contact, api = self.make_client(6)
        foreign = Contact.objects.create(first_name="Чужой", phone="+380679999999")
        funnel = Funnel.objects.get(pk=1)
        Stage.objects.get_or_create(funnel=funnel, order=0, defaults={"name": "Новая"})
        response = api.post("/api/zamer/register/", {
            "name": "Чужое имя",
            "phone": foreign.phone,
            "walls": [],
            "net_m2": 10,
            "net_with_reserve_m2": 11,
        }, format="json")
        self.assertEqual(response.status_code, 200, response.json())
        lead = Lead.objects.get(pk=response.json()["lead_id"])
        self.assertEqual(lead.contact_id, own_contact.id)
        self.assertEqual(own_contact.portal_user_id, user.id)

    def test_only_roles_manager_can_promote_client(self):
        client, _, _ = self.make_client(7)
        client.extra_permissions = ["roles.manage"]
        client.save(update_fields=["extra_permissions"])
        employee_role = Role.objects.create(name="Замерщик", permissions=["zamer.access"])
        admin_role = Role.objects.create(name="Администратор", permissions=["roles.manage"])
        department = Department.objects.create(name="Замеры")
        ordinary = User.objects.create_user("ordinary", password="x", account_kind="staff")
        admin = User.objects.create_user("admin-role", password="x", role=admin_role, account_kind="staff")

        denied_api = APIClient()
        denied_api.force_authenticate(ordinary)
        self.assertEqual(denied_api.get("/api/users/?account_kind=client").status_code, 403)
        self.assertEqual(
            denied_api.post(f"/api/users/{client.id}/promote/", {"role": employee_role.id}, format="json").status_code,
            403,
        )
        self.assertEqual(
            denied_api.patch(f"/api/users/{client.id}/", {"role": employee_role.id}, format="json").status_code,
            403,
        )

        admin_api = APIClient()
        admin_api.force_authenticate(admin)
        promoted = admin_api.post(
            f"/api/users/{client.id}/promote/",
            {"role": employee_role.id, "department": department.id},
            format="json",
        )
        self.assertEqual(promoted.status_code, 200, promoted.json())
        client.refresh_from_db()
        self.assertEqual(client.account_kind, User.AccountKind.STAFF)
        self.assertEqual(client.role_id, employee_role.id)
        self.assertEqual(client.department_id, department.id)
        self.assertEqual(client.extra_permissions, [])
        self.assertFalse(client.is_superuser)

    def test_invite_creates_staff_and_legacy_default_remains_staff(self):
        role = Role.objects.create(name="Сотрудник", permissions=[])
        invite = Invite.objects.create(
            email="invite@example.test",
            first_name="Иван",
            role=role,
            token="staff-invite-token",
            status="pending",
            expires_at=timezone.now() + timedelta(hours=1),
        )
        response = APIClient().post(
            f"/api/invite/{invite.token}/", {"password": "InvitePass123!"}, format="json",
        )
        self.assertEqual(response.status_code, 201, response.json())
        invited = User.objects.get(email="invite@example.test")
        self.assertEqual(invited.account_kind, User.AccountKind.STAFF)
        self.assertEqual(invited.role_id, role.id)

        legacy = User.objects.create_user("legacy-default", password="x")
        self.assertEqual(legacy.account_kind, User.AccountKind.STAFF)

    def test_user_list_defaults_to_staff_and_has_client_queue(self):
        client, _, _ = self.make_client(8)
        admin = User.objects.create_superuser("list-admin", "list-admin@example.test", "x")
        api = APIClient()
        api.force_authenticate(admin)
        default_ids = {row["id"] for row in api.get("/api/users/?page_size=500").json()["results"]}
        client_ids = {
            row["id"] for row in api.get("/api/users/?account_kind=client&page_size=500").json()["results"]
        }
        self.assertNotIn(client.id, default_ids)
        self.assertIn(client.id, client_ids)

    def test_token_login_accepts_username_and_unique_client_phone_or_email(self):
        client, _, _ = self.make_client(9)
        client.email = "cabinet@example.test"
        client.save(update_fields=["email"])
        staff = User.objects.create_user("existing-staff-login", password="StaffPass123!")
        api = APIClient()

        staff_login = api.post("/api/auth/token/", {
            "username": staff.username, "password": "StaffPass123!",
        }, format="json", REMOTE_ADDR="10.10.1.1")
        self.assertEqual(staff_login.status_code, 200, staff_login.json())

        phone_login = api.post("/api/auth/token/", {
            "username": client.phone.replace("+38", ""), "password": "ClientPass123!",
        }, format="json", REMOTE_ADDR="10.10.1.2")
        self.assertEqual(phone_login.status_code, 200, phone_login.json())

        email_login = api.post("/api/auth/token/", {
            "login": "CABINET@example.test", "password": "ClientPass123!",
        }, format="json", REMOTE_ADDR="10.10.1.3")
        self.assertEqual(email_login.status_code, 200, email_login.json())
        self.assertEqual(phone_login.json()["token"], email_login.json()["token"])

    def test_token_login_uses_one_generic_error(self):
        client, _, _ = self.make_client(10)
        client.email = "generic-error@example.test"
        client.save(update_fields=["email"])
        api = APIClient()
        responses = [
            api.post("/api/auth/token/", {
                "username": "does-not-exist", "password": "WrongPass!",
            }, format="json", REMOTE_ADDR="10.10.2.1"),
            api.post("/api/auth/token/", {
                "username": client.email, "password": "WrongPass!",
            }, format="json", REMOTE_ADDR="10.10.2.2"),
            api.post("/api/auth/token/", {
                "username": "", "password": "",
            }, format="json", REMOTE_ADDR="10.10.2.3"),
        ]
        self.assertTrue(all(response.status_code == 400 for response in responses))
        self.assertEqual(responses[0].json(), responses[1].json())
        self.assertEqual(responses[1].json(), responses[2].json())

    def test_staff_analytics_never_exposes_client_accounts(self):
        client, _, _ = self.make_client(11)
        role = Role.objects.create(name="Аналитик", permissions=["roles.manage"])
        analyst = User.objects.create_user(
            "staff-analyst", password="x", role=role, account_kind=User.AccountKind.STAFF,
        )
        ordinary_staff = User.objects.create_user(
            "visible-staff", password="x", account_kind=User.AccountKind.STAFF,
        )
        api = APIClient()
        api.force_authenticate(analyst)

        analytics = api.get("/api/staff/analytics/?status=all")
        self.assertEqual(analytics.status_code, 200, analytics.json())
        ids = {row["id"] for row in analytics.json()["rows"]}
        self.assertIn(ordinary_staff.id, ids)
        self.assertNotIn(client.id, ids)

        hidden_activity = api.get(f"/api/staff/activity/?user={client.id}")
        self.assertEqual(hidden_activity.status_code, 404, hidden_activity.json())

    def test_client_self_estimate_upserts_only_own_project(self):
        user, contact, api = self.make_client(12)
        project_body = {
            "device_uuid": "self-estimate-device",
            "project_uuid": "self-estimate-project",
            "title": "Квартира клиента",
            "payload": {"clientId": contact.id, "rooms": [{"name": "Зал", "net_m2": 20}]},
        }
        project_response = api.post("/api/zamer/projects/", project_body, format="json")
        self.assertEqual(project_response.status_code, 200, project_response.json())

        estimate_body = {
            "project_uuid": project_body["project_uuid"],
            "name": "Мой расчёт",
            "lines": [{
                "title": "Материал", "role": "material", "quantity": 20,
                "unit": "м²", "cost": 15000,
            }],
            "totals": {"area_m2": 20, "subtotal": 15000, "discount": 500, "total": 14500},
        }
        created = api.post("/api/zamer/self-estimate/", estimate_body, format="json")
        self.assertEqual(created.status_code, 201, created.json())
        row = Estimate.objects.get(pk=created.json()["id"])
        self.assertEqual(row.owner_id, user.id)
        self.assertEqual(row.contact_id, contact.id)
        self.assertIsNone(row.deal_id)
        self.assertEqual(row.status, "draft")
        self.assertEqual(row.measurement_snapshot, project_body["payload"])
        self.assertEqual(row.version, 1)

        estimate_body["totals"]["total"] = 14000
        updated = api.post("/api/zamer/self-estimate/", estimate_body, format="json")
        self.assertEqual(updated.status_code, 200, updated.json())
        self.assertEqual(updated.json()["id"], row.id)
        self.assertEqual(updated.json()["version"], 2)
        self.assertEqual(Estimate.objects.filter(project=row.project, deal__isnull=True).count(), 1)

    def test_client_self_estimate_rejects_other_account_staff_and_unsafe_numbers(self):
        owner, contact, owner_api = self.make_client(13)
        project = ZamerProject.objects.create(
            user=owner, contact=contact, device_uuid="owner-device",
            project_uuid="owner-only-project", title="Личный", payload={"rooms": []},
        )
        _, _, other_api = self.make_client(14)
        staff = User.objects.create_user("estimate-staff", password="x", account_kind=User.AccountKind.STAFF)
        staff_api = APIClient(); staff_api.force_authenticate(staff)
        body = {
            "project_uuid": project.project_uuid,
            "lines": [{
                "title": "Работа", "role": "labor", "quantity": 1,
                "unit": "шт", "cost": 100,
            }],
            "totals": {"total": 100},
        }
        self.assertEqual(other_api.post("/api/zamer/self-estimate/", body, format="json").status_code, 404)
        self.assertEqual(staff_api.post("/api/zamer/self-estimate/", body, format="json").status_code, 403)

        body["lines"][0]["cost"] = 1_000_000_001
        unsafe = owner_api.post("/api/zamer/self-estimate/", body, format="json")
        self.assertEqual(unsafe.status_code, 400, unsafe.json())
        self.assertFalse(Estimate.objects.filter(project=project).exists())

    def test_client_zamer_registration_records_own_project_and_stage(self):
        user, contact, api = self.make_client(15)
        project = ZamerProject.objects.create(
            user=user, contact=contact, device_uuid="journey-device",
            project_uuid="journey-project", title="Зал", payload={"rooms": []},
        )
        funnel = Funnel.objects.get(pk=1)
        Stage.objects.get_or_create(funnel=funnel, order=0, defaults={"name": "Новая"})
        response = api.post("/api/zamer/register/", {
            "walls": [], "net_m2": 10, "net_with_reserve_m2": 11,
            "project_uuid": project.project_uuid, "stage_id": "prepare-walls",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.json())
        lead = Lead.objects.get(pk=response.json()["lead_id"])
        card = {item["label"]: item["value"] for item in lead.card_fields}
        self.assertEqual(card["Проект приложения"], project.project_uuid)
        self.assertEqual(card["Этап клиента"], "prepare-walls")
        activity = ActivityLog.objects.filter(kind="lead", object_id=lead.id).order_by("-id").first()
        self.assertIsNotNone(activity)
        self.assertIn(f"project_uuid={project.project_uuid}", activity.detail)
        self.assertIn("stage_id=prepare-walls", activity.detail)

        other, other_contact, _ = self.make_client(16)
        foreign = ZamerProject.objects.create(
            user=other, contact=other_contact, device_uuid="foreign-device",
            project_uuid="foreign-journey-project", payload={"rooms": []},
        )
        rejected = api.post("/api/zamer/register/", {
            "walls": [], "project_uuid": foreign.project_uuid,
        }, format="json")
        self.assertEqual(rejected.status_code, 400, rejected.json())

    def test_stage_review_is_owned_by_client_and_only_manager_can_decide(self):
        owner, contact, owner_api = self.make_client(17)
        project = ZamerProject.objects.create(
            user=owner, contact=contact, device_uuid="review-device",
            project_uuid="review-project", title="Квартира", payload={"rooms": []},
        )
        created = owner_api.post("/api/zamer/reviews/", {
            "project_uuid": project.project_uuid,
            "stage_id": "prepare-walls",
            "title": "Подготовка стен",
        }, format="json")
        self.assertEqual(created.status_code, 201, created.json())
        review = ZamerStageReview.objects.get(pk=created.json()["id"])
        self.assertEqual(review.requested_by_id, owner.id)
        self.assertEqual(review.contact_id, contact.id)
        self.assertEqual(review.status, "pending")

        _, _, other_api = self.make_client(18)
        self.assertEqual(other_api.get("/api/zamer/reviews/").json(), [])
        foreign_create = other_api.post("/api/zamer/reviews/", {
            "project_uuid": project.project_uuid,
            "stage_id": "prepare-walls",
            "title": "Чужой проект",
        }, format="json")
        self.assertEqual(foreign_create.status_code, 404, foreign_create.json())

        client_accept = owner_api.patch(
            f"/api/zamer/reviews/{review.id}/",
            {"status": "accepted", "note": "Сам подтвердил"}, format="json",
        )
        self.assertEqual(client_accept.status_code, 403)
        review.refresh_from_db()
        self.assertEqual(review.status, "pending")

        ordinary = User.objects.create_user(
            "review-ordinary", password="x", account_kind=User.AccountKind.STAFF,
        )
        ordinary_api = APIClient(); ordinary_api.force_authenticate(ordinary)
        self.assertEqual(ordinary_api.get("/api/zamer/reviews/?status=pending").status_code, 403)
        self.assertEqual(ordinary_api.patch(
            f"/api/zamer/reviews/{review.id}/", {"status": "accepted"}, format="json",
        ).status_code, 403)

        manager_role = Role.objects.create(name="Ответственный", permissions=["roles.manage"])
        manager = User.objects.create_user(
            "review-manager", password="x", role=manager_role,
            account_kind=User.AccountKind.STAFF,
        )
        manager_api = APIClient(); manager_api.force_authenticate(manager)
        queue = manager_api.get("/api/zamer/reviews/?status=pending")
        self.assertEqual(queue.status_code, 200, queue.json())
        self.assertEqual([item["id"] for item in queue.json()], [review.id])
        accepted = manager_api.patch(
            f"/api/zamer/reviews/{review.id}/",
            {"status": "accepted", "note": "Этап выполнен правильно"}, format="json",
        )
        self.assertEqual(accepted.status_code, 200, accepted.json())
        self.assertEqual(accepted.json()["status"], "accepted")
        self.assertEqual(accepted.json()["reviewed_by_id"], manager.id)
        review.refresh_from_db()
        self.assertEqual(review.status, "accepted")
        self.assertEqual(review.reviewed_by_id, manager.id)
        self.assertIsNotNone(review.reviewed_at)

        second = owner_api.post("/api/zamer/reviews/", {
            "project_uuid": project.project_uuid,
            "stage_id": "prepare-walls",
            "title": "Повторная проверка",
        }, format="json")
        self.assertEqual(second.status_code, 201, second.json())
        rework = manager_api.post(
            f"/api/zamer/reviews/{second.json()['id']}/",
            {"status": "rework", "note": "Нужно исправить угол"}, format="json",
        )
        self.assertEqual(rework.status_code, 200, rework.json())
        self.assertEqual(rework.json()["status"], "rework")

    def test_stage_review_project_filter_separates_same_stage_between_projects(self):
        owner, contact, owner_api = self.make_client(20)
        project_a = ZamerProject.objects.create(
            user=owner, contact=contact, device_uuid="review-filter-device-a",
            project_uuid="review-filter-project-a", title="Квартира A", payload={"rooms": []},
        )
        project_b = ZamerProject.objects.create(
            user=owner, contact=contact, device_uuid="review-filter-device-b",
            project_uuid="review-filter-project-b", title="Квартира B", payload={"rooms": []},
        )
        created_a = owner_api.post("/api/zamer/reviews/", {
            "project_uuid": project_a.project_uuid,
            "stage_id": "prepare-walls",
            "title": "Подготовка стен A",
        }, format="json")
        created_b = owner_api.post("/api/zamer/reviews/", {
            "project_uuid": project_b.project_uuid,
            "stage_id": "prepare-walls",
            "title": "Подготовка стен B",
        }, format="json")
        self.assertEqual(created_a.status_code, 201, created_a.json())
        self.assertEqual(created_b.status_code, 201, created_b.json())

        own_filtered = owner_api.get(
            f"/api/zamer/reviews/?project_uuid={project_a.project_uuid}",
        )
        self.assertEqual(own_filtered.status_code, 200, own_filtered.json())
        self.assertEqual(
            [row["project_uuid"] for row in own_filtered.json()],
            [project_a.project_uuid],
        )

        manager_role = Role.objects.create(
            name="Ответственный фильтра проверок", permissions=["roles.manage"],
        )
        manager = User.objects.create_user(
            "review-filter-manager", password="x", role=manager_role,
            account_kind=User.AccountKind.STAFF,
        )
        manager_api = APIClient()
        manager_api.force_authenticate(manager)
        manager_filtered = manager_api.get(
            f"/api/zamer/reviews/?project_uuid={project_b.project_uuid}&status=pending",
        )
        self.assertEqual(manager_filtered.status_code, 200, manager_filtered.json())
        self.assertEqual(
            [row["project_uuid"] for row in manager_filtered.json()],
            [project_b.project_uuid],
        )
        self.assertEqual(owner_api.get(
            "/api/zamer/reviews/?project_uuid=",
        ).status_code, 400)
        self.assertEqual(manager_api.get(
            f"/api/zamer/reviews/?project_uuid={'x' * 65}",
        ).status_code, 400)

    def test_staff_revision_protocol_one_requires_exact_base_revision(self):
        role = Role.objects.create(
            name="Замерщик с ревизиями", permissions=["zamer.access"],
        )
        staff = User.objects.create_user(
            "revision-protocol-staff", password="x", role=role,
            account_kind=User.AccountKind.STAFF,
        )
        api = APIClient()
        api.force_authenticate(staff)
        body = {
            "device_uuid": "staff-revision-device",
            "project_uuid": "staff-revision-project",
            "title": "Первый замер",
            "payload": {"rooms": [], "marker": "first"},
        }
        created = api.post("/api/zamer/projects/", body, format="json")
        self.assertEqual(created.status_code, 200, created.json())
        self.assertEqual(created.json()["revision"], 1)

        legacy = api.post("/api/zamer/projects/", {
            **body,
            "title": "Legacy обновление",
            "payload": {"rooms": [], "marker": "legacy"},
        }, format="json")
        self.assertEqual(legacy.status_code, 200, legacy.json())
        self.assertEqual(legacy.json()["revision"], 2)

        missing = api.post("/api/zamer/projects/", {
            **body,
            "revision_protocol": 1,
            "payload": {"rooms": [], "marker": "missing"},
        }, format="json")
        self.assertEqual(missing.status_code, 409, missing.json())
        self.assertEqual(missing.json(), {
            "error": "project_revision_conflict", "revision": 2,
        })

        stale = api.post("/api/zamer/projects/", {
            **body,
            "revision_protocol": 1,
            "base_revision": 1,
            "payload": {"rooms": [], "marker": "stale"},
        }, format="json")
        self.assertEqual(stale.status_code, 409, stale.json())
        exact = api.post("/api/zamer/projects/", {
            **body,
            "revision_protocol": 1,
            "base_revision": 2,
            "payload": {"rooms": [], "marker": "exact"},
        }, format="json")
        self.assertEqual(exact.status_code, 200, exact.json())
        self.assertEqual(exact.json()["revision"], 3)
        project = ZamerProject.objects.get(user=staff, project_uuid=body["project_uuid"])
        self.assertEqual(project.payload["marker"], "exact")
        active_rows = api.get("/api/zamer/projects/").json()
        self.assertEqual(len(active_rows), 1)
        self.assertFalse(active_rows[0]["deleted"])

    def test_soft_delete_tombstone_blocks_resurrection_and_active_client_actions(self):
        user, contact, api = self.make_client(21)
        body = {
            "device_uuid": "soft-delete-device",
            "project_uuid": "soft-delete-project",
            "title": "Удаляемая квартира",
            "payload": {"clientId": contact.id, "rooms": [], "marker": "active"},
        }
        created = api.post("/api/zamer/projects/", body, format="json")
        self.assertEqual(created.status_code, 200, created.json())
        self.assertEqual(created.json()["revision"], 1)
        queued_review = api.post("/api/zamer/reviews/", {
            "project_uuid": body["project_uuid"],
            "stage_id": "prepare-walls",
            "title": "Подготовка стен до удаления",
        }, format="json")
        self.assertEqual(queued_review.status_code, 201, queued_review.json())
        project = ZamerProject.objects.get(user=user, project_uuid=body["project_uuid"])
        funnel = Funnel.objects.create(name="Сделка удаляемого замера")
        stage = Stage.objects.create(funnel=funnel, name="Новая", order=0)
        deal = Deal.objects.create(
            title="Сделка удаляемого замера", contact=contact, funnel=funnel, stage=stage,
        )
        project.deal = deal
        project.save(update_fields=["deal", "updated_at"])

        deleted = api.delete(
            "/api/zamer/projects/"
            f"?device_uuid={body['device_uuid']}&project_uuid={body['project_uuid']}",
        )
        self.assertEqual(deleted.status_code, 200, deleted.json())
        self.assertEqual(deleted.json()["revision"], 2)
        project.refresh_from_db()
        self.assertIsNotNone(project.deleted_at)
        self.assertEqual(project.payload, {})
        self.assertEqual(project.title, "")
        self.assertIsNone(project.deal_id)
        self.assertEqual(project.revision, 2)

        missing_revision = api.post("/api/zamer/projects/", body, format="json")
        self.assertEqual(missing_revision.status_code, 410, missing_revision.json())
        self.assertEqual(missing_revision.json(), {
            "error": "project_deleted", "revision": 2,
        })
        stale = api.post("/api/zamer/projects/", {
            **body, "base_revision": 1, "payload": {"rooms": [], "marker": "stale"},
        }, format="json")
        self.assertEqual(stale.status_code, 410, stale.json())
        project.refresh_from_db()
        self.assertEqual(project.payload, {})
        self.assertEqual(project.revision, 2)

        projects = api.get("/api/zamer/projects/")
        self.assertEqual(projects.status_code, 200, projects.json())
        tombstone = next(
            row for row in projects.json() if row["project_uuid"] == body["project_uuid"]
        )
        self.assertEqual(set(tombstone), {
            "project_uuid", "deleted", "revision", "updated_at",
        })
        self.assertTrue(tombstone["deleted"])
        self.assertEqual(tombstone["revision"], 2)

        repeated = api.delete(
            "/api/zamer/projects/"
            f"?device_uuid={body['device_uuid']}&project_uuid={body['project_uuid']}",
        )
        self.assertEqual(repeated.status_code, 200, repeated.json())
        self.assertEqual(repeated.json()["revision"], 2)

        estimate = api.post("/api/zamer/self-estimate/", {
            "project_uuid": body["project_uuid"],
            "lines": [],
            "totals": {"total": 0},
        }, format="json")
        self.assertEqual(estimate.status_code, 404, estimate.json())
        review = api.post("/api/zamer/reviews/", {
            "project_uuid": body["project_uuid"],
            "stage_id": "prepare-walls",
            "title": "Подготовка стен",
        }, format="json")
        self.assertEqual(review.status_code, 404, review.json())
        manager_role = Role.objects.create(
            name="Ответственный удалённого проекта", permissions=["roles.manage"],
        )
        manager = User.objects.create_user(
            "deleted-review-manager", password="x", role=manager_role,
            account_kind=User.AccountKind.STAFF,
        )
        manager_api = APIClient()
        manager_api.force_authenticate(manager)
        hidden_queue = manager_api.get(
            f"/api/zamer/reviews/?project_uuid={body['project_uuid']}&status=pending",
        )
        self.assertEqual(hidden_queue.status_code, 200, hidden_queue.json())
        self.assertEqual(hidden_queue.json(), [])
        hidden_decision = manager_api.patch(
            f"/api/zamer/reviews/{queued_review.json()['id']}/",
            {"status": "accepted"}, format="json",
        )
        self.assertEqual(hidden_decision.status_code, 404, hidden_decision.json())
        register = api.post("/api/zamer/register/", {
            "walls": [], "project_uuid": body["project_uuid"],
        }, format="json")
        self.assertEqual(register.status_code, 400, register.json())

    def test_delete_before_create_persists_idempotent_tombstone(self):
        user, _, api = self.make_client(22)
        device_uuid = "delete-first-device"
        project_uuid = "delete-first-project"
        deleted = api.delete(
            "/api/zamer/projects/"
            f"?device_uuid={device_uuid}&project_uuid={project_uuid}",
        )
        self.assertEqual(deleted.status_code, 200, deleted.json())
        self.assertEqual(deleted.json()["revision"], 1)
        project = ZamerProject.objects.get(user=user, project_uuid=project_uuid)
        self.assertIsNotNone(project.deleted_at)
        self.assertEqual(project.payload, {})

        late_create = api.post("/api/zamer/projects/", {
            "device_uuid": device_uuid,
            "project_uuid": project_uuid,
            "title": "Запоздавшее создание",
            "payload": {"rooms": [], "marker": "late"},
        }, format="json")
        self.assertEqual(late_create.status_code, 410, late_create.json())
        self.assertEqual(late_create.json(), {
            "error": "project_deleted", "revision": 1,
        })

        repeated = api.delete(
            "/api/zamer/projects/"
            f"?device_uuid={device_uuid}&project_uuid={project_uuid}",
        )
        self.assertEqual(repeated.status_code, 200, repeated.json())
        self.assertEqual(repeated.json()["revision"], 1)
        project.refresh_from_db()
        self.assertEqual(project.revision, 1)
        self.assertEqual(project.payload, {})

    def test_deleted_project_is_rejected_by_zamer_submission(self):
        admin = User.objects.create_superuser(
            "deleted-zamer-admin", "deleted-zamer@example.test", "x",
        )
        contact = Contact.objects.create(
            first_name="Клиент удалённого замера", phone="+380671120023",
        )
        project = ZamerProject.objects.create(
            user=admin,
            contact=contact,
            device_uuid="deleted-zamer-device",
            project_uuid="deleted-zamer-project",
            title="",
            payload={},
            revision=4,
            deleted_at=timezone.now(),
        )
        api = APIClient()
        api.force_authenticate(admin)
        response = api.post("/api/zamer/", {
            "client_id": contact.id,
            "device_uuid": project.device_uuid,
            "project_uuid": project.project_uuid,
            "project_name": "Нельзя восстановить",
            "rooms": [{"name": "Комната", "walls": [], "openings": [], "net_m2": 10}],
        }, format="json")
        self.assertEqual(response.status_code, 410, response.json())
        self.assertEqual(response.json(), {
            "error": "project_deleted", "revision": 4,
        })
        self.assertFalse(Deal.objects.filter(contact=contact).exists())
