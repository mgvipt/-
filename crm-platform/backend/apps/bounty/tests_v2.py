"""Біржа задач v2 (15.09.2026): міграція 0002 на даних 0001, `bounty_seed --update` (не чіпає змінене власником,
нічого не вмикає, додає нове), підзадачі з відмітками, редактор прайсу, права. Жодних зовнішніх запитів."""
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from apps.bounty import seed_data, seed_v1
from apps.bounty.models import TaskCategory, TaskClaim, TaskOffer

HOST = "crm.wallcovdec.com.ua"


class MigrationOn0001DataTests(TransactionTestCase):
    def test_0002_applies_on_existing_0001_rows(self):
        ex = MigrationExecutor(connection)
        ex.migrate([("bounty", "0001_initial")])
        apps_old = ex.loader.project_state([("bounty", "0001_initial")]).apps
        U = get_user_model()
        u = U.objects.create_user("mig-u", "mig@example.test", "x")
        Cat, Off, Cl = (apps_old.get_model("bounty", n) for n in ("TaskCategory", "TaskOffer", "TaskClaim"))
        cat = Cat.objects.create(department="salon", name="Салон")
        off = Off.objects.create(category=cat, title="Стара задача", how_to="крок 1\nкрок 2", price=Decimal("100"))
        cl = Cl.objects.create(offer=off, user_id=u.id, price=Decimal("100"), status="taken")
        ex = MigrationExecutor(connection)
        ex.loader.build_graph()
        ex.migrate(ex.loader.graph.leaf_nodes("bounty"))
        o = TaskOffer.objects.get(pk=off.pk)
        self.assertEqual((o.title, o.how_to, o.price, o.active), ("Стара задача", "крок 1\nкрок 2", Decimal("100.00"), False))
        self.assertEqual((o.why, o.expected_result, o.subtasks), ("", "", []))
        c = TaskClaim.objects.get(pk=cl.pk)
        self.assertEqual((c.status, c.subtasks, c.subtasks_done), ("taken", [], []))


def seed_v1_like_prod():
    """Стан проду 14.09: прайс v1, усе неактивне, примітка «ціна для обговорення»."""
    for i, (dep, cat_name, offers) in enumerate(seed_v1.SEED):
        cat = TaskCategory.objects.create(department=dep, name=cat_name, order=(i + 1) * 10)
        for j, o in enumerate(offers):
            TaskOffer.objects.create(category=cat, title=o["title"], how_to=o["how_to"], done_criteria=o["done_criteria"],
                                     proof_type=o["proof_type"], price=Decimal(str(o["price"])), unit=o["unit"],
                                     unit_label=o["unit_label"], monthly_limit_qty=o["monthly_limit_qty"],
                                     max_per_person=o["max_per_person"], max_takers=o["max_takers"], due_days=o["due_days"],
                                     active=False, note=seed_v1.NOTE, order=(j + 1) * 10)


def snapshot():
    return sorted(TaskOffer.objects.values_list("id", "title", "how_to", "done_criteria", "price", "active", "archived",
                                                "note", "why", "expected_result", "subtasks", "category_id", "order"))


class SeedUpdateTests(TestCase):
    def setUp(self):
        cache.clear()
        seed_v1_like_prod()
        self.n_v1 = TaskOffer.objects.count()
        self.n_v2 = sum(len(x[2]) for x in seed_data.SEED)
        self.edited = TaskOffer.objects.get(title="Ведення TikTok (тиждень)")
        self.edited.how_to = "Своя інструкція власника"
        self.edited.save()
        self.priced = TaskOffer.objects.get(title="Збір відгуку від клієнта")
        self.priced.price = Decimal("55")
        self.priced.save()
        self.gone = TaskOffer.objects.get(title="Субтитри до готового відео")
        self.gone.archived = True
        self.gone.save()
        self.live = TaskOffer.objects.get(title="Обробка пропущених дзвінків")
        self.live.active = True
        self.live.save()
        self.touched = TaskOffer.objects.get(title="Підсобні роботи на обʼєкті")
        self.touched.save()  # як id 60 на проді: збережено без зміни значень

    def test_dry_changes_nothing_and_reports(self):
        before = snapshot()
        n_cat = TaskCategory.objects.count()
        out = StringIO()
        call_command("bounty_seed", "--update", "--dry", stdout=out)
        self.assertEqual(snapshot(), before)
        self.assertEqual(TaskCategory.objects.count(), n_cat)
        t = out.getvalue()
        self.assertIn("нічого не записано", t)
        self.assertIn("змінено власником — пропущено 1", t)
        self.assertIn(f"#{self.edited.id} Ведення TikTok (тиждень)", t)
        self.assertIn("ціни/ліміти власника лишено 1", t)
        self.assertIn(f"оновлено {self.n_v1 - 2}", t)

    def test_update_respects_owner_adds_new_activates_nothing(self):
        out = StringIO()
        call_command("bounty_seed", "--update", stdout=out)
        self.assertEqual(TaskOffer.objects.count(), self.n_v1 + 42)  # 79 з 14.09 (разом з видаленою) + 42 нові
        self.assertEqual(self.n_v1 + 42, self.n_v2)
        self.assertEqual(TaskOffer.objects.filter(active=True).count(), 1)
        self.assertTrue(TaskOffer.objects.get(pk=self.live.pk).active)
        e = TaskOffer.objects.get(pk=self.edited.pk)
        self.assertEqual((e.how_to, e.why, e.subtasks), ("Своя інструкція власника", "", []))
        g = TaskOffer.objects.get(pk=self.gone.pk)
        self.assertTrue(g.archived)
        self.assertEqual(g.subtasks, [])
        p = TaskOffer.objects.get(pk=self.priced.pk)
        self.assertEqual(p.price, Decimal("55.00"))
        self.assertTrue(p.subtasks and p.expected_result and p.why)
        t = TaskOffer.objects.get(pk=self.touched.pk)
        self.assertGreaterEqual(len(t.subtasks), 3)
        kit = TaskOffer.objects.get(title="Еталон тест-набору: фото і чек-лист комплектації")
        self.assertIn("відрядно", kit.note)
        for o in TaskOffer.objects.filter(archived=False).exclude(pk=self.edited.pk):
            self.assertTrue(3 <= len(o.subtasks) <= 7 and o.expected_result and o.why, o.title)
            self.assertTrue(o.note.startswith("ціна для обговорення"), o.title)
        self.assertEqual(set(TaskCategory.objects.values_list("department", flat=True)),
                         {"marketing", "sales", "warehouse", "salon", "objects", "content", "ai_crm", "hr", "office"})
        self.assertEqual(TaskCategory.objects.count(), len(seed_data.SEED))
        out2 = StringIO()
        call_command("bounty_seed", "--update", stdout=out2)
        self.assertIn("нових напрямів 0, нових задач 0, оновлено 0", out2.getvalue())

    def test_plain_seed_after_v1_only_adds(self):
        before = {r[0]: r for r in snapshot()}
        call_command("bounty_seed", stdout=StringIO())
        for r in snapshot():
            if r[0] in before:
                self.assertEqual(r, before[r[0]])
        self.assertEqual(TaskOffer.objects.count(), self.n_v1 + 42)
        self.assertEqual(TaskOffer.objects.filter(active=True).count(), 1)


class SubtasksTests(TestCase):
    def setUp(self):
        cache.clear()
        U = get_user_model()
        self.owner = U.objects.create_superuser("v2-owner", "o@example.test", "x")
        self.mgr = U.objects.create_user("v2-mgr", "m@example.test", "x")
        self.mgr.extra_permissions = ["bounty.manage"]
        self.mgr.save()
        self.e1 = U.objects.create_user("v2-e1", "e1@example.test", "x", first_name="Олена")
        self.e2 = U.objects.create_user("v2-e2", "e2@example.test", "x")
        self.cat = TaskCategory.objects.create(department="hr", name="Відбір")
        self.off = TaskOffer.objects.create(
            category=self.cat, title="Скрипт", price=Decimal("300"), active=True, proof_type="text", why="Щоб відсіяти",
            expected_result="Погоджений скрипт", subtasks=[{"title": "Питання", "how": "10 штук"},
                                                          {"title": "Прапорці", "how": "що відсікає"},
                                                          {"title": "Погодити", "how": "з власником"}])

    def c(self, u):
        cl = APIClient()
        cl.force_authenticate(u)
        return cl

    def post(self, u, url, data=None):
        return self.c(u).post(url, data or {}, format="json", HTTP_HOST=HOST)

    def test_checkbox_flow_submit_with_unfinished_and_checker_sees(self):
        r = self.post(self.e1, f"/api/bounty/offers/{self.off.id}/take/")
        self.assertEqual(r.status_code, 201, r.content)
        cl = r.data["claim"]
        self.assertEqual((cl["subtasks_total"], cl["subtasks_done_count"], cl["can_check"]), (3, 0, True))
        self.assertEqual(cl["expected_result"], "Погоджений скрипт")
        cid = cl["id"]
        # власник змінює підзадачі після «Беру» — у взятій задачі знімок
        self.c(self.mgr).patch(f"/api/bounty/offers/{self.off.id}/", {"subtasks": [{"title": "Інше", "how": ""}]},
                               format="json", HTTP_HOST=HOST)
        r = self.post(self.e1, f"/api/bounty/claims/{cid}/subtasks/", {"done": [0, 2]})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual([s["title"] for s in r.data["subtasks"]], ["Питання", "Прапорці", "Погодити"])
        self.assertEqual([s["done"] for s in r.data["subtasks"]], [True, False, True])
        self.assertEqual(r.data["subtasks_done_count"], 2)
        self.assertEqual(self.post(self.e2, f"/api/bounty/claims/{cid}/subtasks/", {"done": [1]}).status_code, 403)
        self.assertEqual(self.post(self.mgr, f"/api/bounty/claims/{cid}/subtasks/", {"done": [1]}).status_code, 403)
        self.assertEqual(self.post(self.e1, f"/api/bounty/claims/{cid}/subtasks/", {"done": [5]}).status_code, 400)
        self.assertEqual(self.post(self.e1, f"/api/bounty/claims/{cid}/subtasks/", {"done": "x"}).status_code, 400)
        r = self.post(self.e1, f"/api/bounty/claims/{cid}/submit/", {"proof_text": "скрипт у документі"})
        self.assertEqual(r.status_code, 200, r.content)  # здати можна з невідміченими
        self.assertIn("підзадачі 2/3, не відмічено № 2", r.data["history"][-1]["note"])
        self.assertFalse(r.data["can_check"])
        self.assertEqual(self.post(self.e1, f"/api/bounty/claims/{cid}/subtasks/", {"done": [0, 1, 2]}).status_code, 409)
        rev = self.c(self.mgr).get("/api/bounty/claims/?scope=review", HTTP_HOST=HOST).data["results"]
        self.assertEqual([s["done"] for s in rev[0]["subtasks"]], [True, False, True])
        self.assertEqual(self.post(self.mgr, f"/api/bounty/claims/{cid}/accept/").status_code, 200)

    def test_claim_taken_before_v2_uses_offer_subtasks(self):
        c = TaskClaim.objects.create(offer=self.off, user=self.e1, price=Decimal("300"), status="taken")
        r = self.post(self.e1, f"/api/bounty/claims/{c.id}/subtasks/", {"done": [1]})
        self.assertEqual(r.status_code, 200)
        c.refresh_from_db()
        self.assertEqual((len(c.subtasks), c.subtasks_done), (3, [1]))

    def test_price_editor_subtasks_and_permissions(self):
        url = f"/api/bounty/offers/{self.off.id}/"
        body = {"subtasks": [{"title": " Крок А ", "how": "як"}, {"title": "", "how": "порожнє — відкидаємо"}, "Крок Б"],
                "expected_result": "Результат", "why": "Навіщо"}
        self.assertEqual(self.c(self.e1).patch(url, body, format="json", HTTP_HOST=HOST).status_code, 403)
        r = self.c(self.mgr).patch(url, body, format="json", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["subtasks"], [{"title": "Крок А", "how": "як"}, {"title": "Крок Б", "how": ""}])
        self.assertEqual((r.data["expected_result"], r.data["why"]), ("Результат", "Навіщо"))
        too_many = [{"title": f"к{i}", "how": ""} for i in range(13)]
        self.assertEqual(self.c(self.mgr).patch(url, {"subtasks": too_many}, format="json", HTTP_HOST=HOST).status_code, 400)
        self.assertEqual(self.c(self.mgr).patch(url, {"subtasks": 5}, format="json", HTTP_HOST=HOST).status_code, 400)
        b = self.c(self.e1).get("/api/bounty/board/", HTTP_HOST=HOST).data
        o = next(x for x in b["offers"] if x["id"] == self.off.id)
        self.assertEqual(len(o["subtasks"]), 2)
        self.assertIn({"key": "hr", "label": "Найм", "n_active": 1, "n_total": 1}, b["departments"])
        U = get_user_model()
        client = U.objects.create_user("v2-client", "cl@example.test", "x")
        client.account_kind = U.AccountKind.CLIENT
        client.save()
        cid = self.post(self.e1, f"/api/bounty/offers/{self.off.id}/take/").data["claim"]["id"]
        self.assertEqual(self.post(client, f"/api/bounty/claims/{cid}/subtasks/", {"done": [0]}).status_code, 403)
