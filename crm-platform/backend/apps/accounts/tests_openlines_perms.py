"""Відкриті лінії: права «Всі співробітники» / «Забирати чужий чат», звільнення з відкатом,
«взяв у роботу» без повторів — 17.09.2026 (випадок Олександра Лаптева).

Було: відділ продажів мав «бачити всі чати» → кожен менеджер бачив список колег і міг «Закріпити»
чат, який уже взяв інший. Помилкове «Звільнити» роздало ВСЕ (разом з виграними/програними сделками)
колегам, а повернення в «Активні» нічого не повертало. Повторне «Закріпити» рахувалось як нове «взяв».
"""
from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Department, Role, StaffTransfer, User
from apps.crm.models import ActivityLog, Contact, Deal, Funnel, Lead, Stage
from apps.crm.take_stats import taken_by_user
from apps.inbox.models import Channel, Conversation


def api(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


class OpenLinesPermsTests(TestCase):
    def setUp(self):
        self.boss = User.objects.create_superuser("olp-boss", password="x")
        dep = Department.objects.create(name="Відділ продажів", permissions=["conversation.view.all", "conversation.assign"])
        role = Role.objects.create(name="Менеджер (olp)", permissions=["inbox.view"])
        mk = lambda n: User.objects.create_user(n, password="x", role=role, department=dep, first_name=n)
        self.kirill, self.ilona, self.laptev = mk("olp-kirill"), mk("olp-ilona"), mk("olp-laptev")
        self.ch = Channel.objects.create(kind="telegram", name="TG olp")
        self.client_k = Contact.objects.create(first_name="Клієнт Кирила", owner=self.kirill)
        self.conv_k = Conversation.objects.create(channel=self.ch, contact=self.client_k, external_chat_id="k1",
                                                  assigned_to=self.kirill)
        self.free_c = Contact.objects.create(first_name="Вільний")
        self.conv_free = Conversation.objects.create(channel=self.ch, contact=self.free_c, external_chat_id="f1")

    def test_manager_cannot_take_or_transfer_colleague_chat(self):
        r = api(self.laptev).post("/api/conversations/%d/take/" % self.conv_k.id, {})
        self.assertEqual(r.status_code, 409)
        r = api(self.laptev).post("/api/conversations/%d/assign/" % self.conv_k.id, {"user_id": self.laptev.id})
        self.assertEqual(r.status_code, 403)
        self.conv_k.refresh_from_db()
        self.assertEqual(self.conv_k.assigned_to_id, self.kirill.id)

    def test_takeover_permission_and_boss_can(self):
        self.laptev.extra_permissions = ["conversation.takeover"]
        self.laptev.save(update_fields=["extra_permissions"])
        self.assertEqual(api(self.laptev).post("/api/conversations/%d/take/" % self.conv_k.id, {}).status_code, 200)
        r = api(self.boss).post("/api/conversations/%d/assign/" % self.conv_k.id, {"user_id": self.ilona.id})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(ActivityLog.objects.filter(action="Переадресував чат", object_id=self.client_k.id).exists())

    def test_free_chat_take_and_retake_logged_once(self):
        c = api(self.laptev)
        self.assertEqual(c.post("/api/conversations/%d/take/" % self.conv_free.id, {}).status_code, 200)
        self.assertEqual(c.post("/api/conversations/%d/take/" % self.conv_free.id, {}).status_code, 200)
        self.assertEqual(ActivityLog.objects.filter(action="Взяв чат", user=self.laptev).count(), 1)

    def test_staff_filter_param_needs_permission(self):
        # Лаптев відповідав у чаті Кирила — фільтр «співробітник» без права не працює (звичайний список)
        ids = lambda u: [x["id"] for x in api(u).get("/api/conversations/", {"manager": self.kirill.id, "page_size": 50}).json()["results"]]
        self.assertNotIn(self.conv_k.id, ids(self.laptev))
        self.assertIn(self.conv_k.id, ids(self.boss))
        self.laptev.extra_permissions = ["conversation.staff_filter"]
        self.laptev.save(update_fields=["extra_permissions"])
        self.assertIn(self.conv_k.id, ids(self.laptev))

    def test_perms_in_catalog(self):
        r = api(self.boss).get("/api/permissions/")
        self.assertEqual(r.status_code, 200)
        codes = {i["code"] for g in r.json()["groups"] for i in g["items"]}
        self.assertIn("conversation.staff_filter", codes)
        self.assertIn("conversation.takeover", codes)


class DismissUndoTests(TestCase):
    def setUp(self):
        self.boss = User.objects.create_superuser("dsu-boss", password="x")
        dep = Department.objects.create(name="Відділ продажів")
        mk = lambda n: User.objects.create_user(n, password="x", department=dep, first_name=n)
        self.a, self.b, self.lap = mk("dsu-a"), mk("dsu-b"), mk("dsu-lap")
        f = Funnel.objects.create(name="21 Основний продукт")
        self.st_open = Stage.objects.create(funnel=f, name="Контакт", order=1)
        self.st_won = Stage.objects.create(funnel=f, name="Успішна", order=9, is_won=True)
        self.st_lost = Stage.objects.create(funnel=f, name="Програна", order=10, is_lost=True)
        ch = Channel.objects.create(kind="telegram", name="TG dsu")
        self.contacts = [Contact.objects.create(first_name="К%d" % i, owner=self.lap) for i in range(4)]
        self.d_open = Deal.objects.create(title="open", contact=self.contacts[0], owner=self.lap, funnel=f, stage=self.st_open)
        self.d_won = Deal.objects.create(title="won", contact=self.contacts[1], owner=self.lap, funnel=f, stage=self.st_won)
        self.d_lost = Deal.objects.create(title="lost", contact=self.contacts[2], owner=self.lap, funnel=f, stage=self.st_lost)
        self.conv = Conversation.objects.create(channel=ch, contact=self.contacts[0], external_chat_id="d1", assigned_to=self.lap)
        self.conv_closed = Conversation.objects.create(channel=ch, contact=self.contacts[1], external_chat_id="d2",
                                                       assigned_to=self.lap, status="closed")

    def test_dismiss_keeps_closed_deals_and_reactivation_restores(self):
        c = api(self.boss)
        r = c.post("/api/users/%d/dismiss/" % self.lap.id, {})
        self.assertEqual(r.status_code, 200, r.content)
        self.d_open.refresh_from_db(); self.d_won.refresh_from_db(); self.d_lost.refresh_from_db()
        self.assertNotEqual(self.d_open.owner_id, self.lap.id)
        self.assertEqual(self.d_won.owner_id, self.lap.id)      # історія продажів не переїжджає
        self.assertEqual(self.d_lost.owner_id, self.lap.id)
        self.conv_closed.refresh_from_db()
        self.assertEqual(self.conv_closed.assigned_to_id, self.lap.id)
        self.assertEqual(Contact.objects.filter(owner=self.lap).count(), 0)
        self.assertTrue(StaffTransfer.objects.filter(user=self.lap).exists())
        # колега встиг змінити відповідального одного клієнта — його не чіпаємо
        moved = Contact.objects.exclude(owner=self.lap).filter(id__in=[x.id for x in self.contacts]).first()
        Contact.objects.filter(id=moved.id).update(owner=self.boss)
        r = c.post("/api/users/%d/set_status/" % self.lap.id, {"status": "active"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["restored"].get("клієнти"), 3)
        self.assertEqual(Contact.objects.filter(owner=self.lap).count(), 3)
        self.assertEqual(Contact.objects.get(id=moved.id).owner_id, self.boss.id)
        self.d_open.refresh_from_db(); self.conv.refresh_from_db()
        self.assertEqual(self.d_open.owner_id, self.lap.id)
        self.assertEqual(self.conv.assigned_to_id, self.lap.id)
        self.assertIsNotNone(StaffTransfer.objects.get(user=self.lap).restored_at)

    def test_old_dismissal_not_restored(self):
        c = api(self.boss)
        c.post("/api/users/%d/dismiss/" % self.lap.id, {})
        StaffTransfer.objects.filter(user=self.lap).update(at=timezone.now() - timedelta(days=30))
        r = c.post("/api/users/%d/set_status/" % self.lap.id, {"status": "active"})
        self.assertEqual(r.json()["restored"], {})
        self.assertEqual(Contact.objects.filter(owner=self.lap).count(), 0)


class TakeStatsTests(TestCase):
    def test_repeat_take_same_client_within_30_days_counted_once(self):
        u = User.objects.create_user("tks-u", password="x")
        now = timezone.now()
        mk = lambda oid, days_ago: ActivityLog.objects.filter(
            id=ActivityLog.objects.create(kind="contact", object_id=oid, action="Взяв чат", user=u).id
        ).update(created_at=now - timedelta(days=days_ago))
        mk(1, 1); mk(1, 0)       # той самий клієнт двічі (як після помилкового звільнення)
        mk(2, 0)                 # інший клієнт
        mk(3, 45); mk(3, 0)      # повернувся через 45 днів — нова робота
        today = timezone.localdate()
        self.assertEqual(taken_by_user(today, today).get(u.id), 2)
        self.assertEqual(taken_by_user(today - timedelta(days=2), today).get(u.id), 3)
