"""Біржа задач (14.09.2026): «Беру» → доказ → «Прийнято» / «На доробку», права, ліміти, фонд, мʼяке правило стандарту,
рядок «Задачі з біржі» в ЗП місяця і ЗП без застосунку. Жодних зовнішніх запитів."""
import sys
from datetime import date
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from apps.bounty import services as S
from apps.bounty.models import TaskCategory, TaskClaim, TaskOffer
from apps.finance.models import FinModelArticle
from apps.payroll import engine
from apps.payroll.models import PayComponent, PayPolicy, PayrollRun, PayScheme

HOST = "crm.wallcovdec.com.ua"


class BountyTests(TestCase):
    def setUp(self):
        cache.clear()
        U = get_user_model()
        self.owner = U.objects.create_superuser("bn-owner", "bno@example.test", "x")
        self.mgr = U.objects.create_user("bn-mgr", "bnm@example.test", "x", first_name="Кер", last_name="Івник")
        self.mgr.extra_permissions = ["bounty.manage"]
        self.mgr.save()
        self.emp1 = U.objects.create_user("bn-e1", "e1@example.test", "x", first_name="Олена", last_name="Перша")
        self.emp2 = U.objects.create_user("bn-e2", "e2@example.test", "x", first_name="Іван", last_name="Другий")
        self.chk = U.objects.create_user("bn-chk", "chk@example.test", "x", first_name="Пере", last_name="Віряючий")
        PayPolicy.objects.update_or_create(pk=1, defaults={"params": {"replaced_articles": []}})
        self.cat = TaskCategory.objects.create(department="marketing", name="Монтаж")
        self.single = TaskOffer.objects.create(category=self.cat, title="Монтаж YouTube", price=Decimal("250"), unit="task",
                                               max_takers=1, active=True, proof_type="link", due_days=3)
        self.piece = TaskOffer.objects.create(category=self.cat, title="Субтитри", price=Decimal("20"), unit="piece",
                                              unit_label="відео", monthly_limit_qty=5, max_per_person=3, max_takers=0,
                                              active=True, proof_type="any")
        self.P = S.month_of()

    # ── помічники ──
    def c(self, user):
        cl = APIClient()
        cl.force_authenticate(user)
        return cl

    def post(self, user, url, data=None):
        return self.c(user).post(url, data or {}, format="json", HTTP_HOST=HOST)

    def get(self, user, url):
        return self.c(user).get(url, HTTP_HOST=HOST)

    def take(self, user, offer, qty=None):
        return self.post(user, f"/api/bounty/offers/{offer.id}/take/", {"qty": qty} if qty is not None else {})

    def submit(self, user, claim_id, **kw):
        return self.post(user, f"/api/bounty/claims/{claim_id}/submit/", kw or {"proof_url": "https://example.test/x", "proof_text": "зроблено все"})

    def act(self, user, claim_id, act, **kw):
        return self.post(user, f"/api/bounty/claims/{claim_id}/{act}/", kw)

    def scheme(self, user, **params):
        y, m = int(self.P[:4]), int(self.P[5:7])
        s = PayScheme.objects.create(user=user, position="Менеджер", valid_from=date(y - 1, m, 1), employment="none")
        PayComponent.objects.create(scheme=s, kind="fixed_monthly", params={"amount": 1000})
        if params.get("scores") is not None:
            PayComponent.objects.create(scheme=s, kind="standard", params={"max": 0, "scores": params["scores"]})
        return s

    # ── основний сценарій ──
    def test_take_submit_accept_flow_and_payroll_line(self):
        self.scheme(self.emp1)
        r = self.take(self.emp1, self.single)
        self.assertEqual(r.status_code, 201, r.content)
        cid = r.data["claim"]["id"]
        self.assertEqual(r.data["claim"]["status"], "taken")
        self.assertIsNotNone(r.data["claim"]["due_at"])
        # без доказу — не здати (тип доказу «посилання»)
        self.assertEqual(self.submit(self.emp1, cid, proof_text="готово, дивіться").status_code, 400)
        r = self.submit(self.emp1, cid, proof_url="https://drive.example.test/f")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["status"], "submitted")
        r = self.act(self.mgr, cid, "accept", quality=5, comment="супер")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["status"], "accepted")
        self.assertEqual(r.data["amount"], 250.0)
        self.assertEqual(r.data["payroll_period"], self.P)
        calc = engine.calc(self.emp1, self.P)
        line = [l for l in calc["lines"] if l["kind"] == "bounty"]
        self.assertEqual(len(line), 1)
        self.assertEqual(line[0]["title"], "Задачі з біржі")
        self.assertEqual(line[0]["amount"], 250)
        self.assertEqual(calc["total"], 1250)
        acts = [e["act"] for e in TaskClaim.objects.get(pk=cid).history]
        self.assertEqual(acts, ["take", "submit", "accept"])

    def test_single_slot_shows_busy_for_others(self):
        self.assertEqual(self.take(self.emp1, self.single).status_code, 201)
        r = self.take(self.emp2, self.single)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "busy")
        b = self.get(self.emp2, "/api/bounty/board/").data
        o = next(x for x in b["offers"] if x["id"] == self.single.id)
        self.assertEqual(o["state"], "busy")
        self.assertEqual(o["busy_by"][0]["name"], "Олена Перша")
        mine = next(x for x in self.get(self.emp1, "/api/bounty/board/").data["offers"] if x["id"] == self.single.id)
        self.assertEqual(mine["state"], "mine")
        # штучну задачу беруть кілька людей одночасно
        self.assertEqual(self.take(self.emp1, self.piece, 1).status_code, 201)
        self.assertEqual(self.take(self.emp2, self.piece, 1).status_code, 201)

    # ── права ──
    def test_employee_cannot_accept_own_or_others_manage_can(self):
        cid = self.take(self.emp1, self.single).data["claim"]["id"]
        self.submit(self.emp1, cid, proof_url="https://example.test/a")
        self.assertEqual(self.act(self.emp1, cid, "accept").status_code, 403)  # свою — ні
        self.assertEqual(self.act(self.emp2, cid, "accept").status_code, 403)  # без права — ні
        self.assertEqual(self.act(self.chk, cid, "rework", comment="переробити").status_code, 403)
        self.assertEqual(self.get(self.emp2, "/api/bounty/claims/?scope=all").status_code, 403)
        self.assertEqual(self.get(self.emp1, "/api/bounty/claims/?scope=review").data["results"], [])
        self.assertEqual(len(self.get(self.mgr, "/api/bounty/claims/?scope=review").data["results"]), 1)
        self.assertEqual(self.act(self.mgr, cid, "accept").status_code, 200)

    def test_manager_cannot_accept_own_claim(self):
        cid = self.take(self.mgr, self.single).data["claim"]["id"]
        self.submit(self.mgr, cid, proof_url="https://example.test/a")
        self.assertEqual(self.act(self.mgr, cid, "accept").status_code, 403)
        self.assertEqual(self.act(self.owner, cid, "accept").status_code, 200)

    def test_checker_accepts_only_his_offers(self):
        self.single.checker = self.chk
        self.single.save()
        c1 = self.take(self.emp1, self.single).data["claim"]["id"]
        self.submit(self.emp1, c1, proof_url="https://example.test/a")
        c2 = self.take(self.emp1, self.piece, 1).data["claim"]["id"]
        self.submit(self.emp1, c2, proof_text="субтитри до 1 відео")
        self.assertTrue(self.get(self.chk, "/api/bounty/board/").data["me"]["can_review"])
        review = self.get(self.chk, "/api/bounty/claims/?scope=review").data["results"]
        self.assertEqual([r["id"] for r in review], [c1])
        self.assertEqual(self.act(self.chk, c2, "accept").status_code, 403)
        r = self.act(self.chk, c1, "accept", amount="999")  # суму вручну — лише власник
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.act(self.chk, c1, "accept").status_code, 200)

    def test_client_account_has_no_access(self):
        U = get_user_model()
        cl = U.objects.create_user("bn-client", "cl@example.test", "x")
        cl.account_kind = U.AccountKind.CLIENT
        cl.save()
        self.assertEqual(self.get(cl, "/api/bounty/board/").status_code, 403)
        self.assertEqual(self.take(cl, self.single).status_code, 403)
        self.emp2.denied_permissions = ["bounty.view"]
        self.emp2.save()
        self.assertEqual(self.get(self.emp2, "/api/bounty/board/").status_code, 403)

    # ── ліміти ──
    def test_monthly_and_per_person_limits(self):
        self.assertEqual(self.take(self.emp1, self.piece, 3).status_code, 201)
        r = self.take(self.emp1, self.piece, 1)
        self.assertEqual((r.status_code, r.data["code"]), (409, "already"))
        r = self.take(self.emp2, self.piece, 3)
        self.assertEqual((r.status_code, r.data["code"]), (409, "limit"))  # 3 + 3 > 5
        self.assertEqual(self.take(self.emp2, self.piece, 2).status_code, 201)
        r = self.take(self.chk, self.piece, 1)
        self.assertEqual((r.status_code, r.data["code"]), (409, "limit"))
        b = self.get(self.chk, "/api/bounty/board/").data
        self.assertEqual(next(x for x in b["offers"] if x["id"] == self.piece.id)["state"], "limit")
        # ліміт на людину
        per = TaskOffer.objects.create(category=self.cat, title="Обкладинки", price=Decimal("10"), unit="piece",
                                       max_per_person=2, max_takers=0, active=True)
        cid = self.take(self.emp1, per, 2).data["claim"]["id"]
        self.submit(self.emp1, cid, proof_text="2 обкладинки готові")
        self.assertEqual(self.act(self.mgr, cid, "accept").status_code, 200)
        r = self.take(self.emp1, per, 1)
        self.assertEqual((r.status_code, r.data["code"]), (409, "person_limit"))
        self.assertEqual(self.take(self.emp2, per, 1).status_code, 201)

    def test_accept_over_monthly_limit_needs_force(self):
        cid = self.take(self.emp1, self.piece, 3).data["claim"]["id"]
        self.submit(self.emp1, cid, proof_text="зробив більше, ніж брав", qty=6)
        r = self.act(self.mgr, cid, "accept")
        self.assertEqual((r.status_code, r.data["code"], r.data["can_force"]), (409, "limit", True))
        r = self.act(self.mgr, cid, "accept", force=True)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["amount"], 120.0)

    def test_rework_flow(self):
        cid = self.take(self.emp1, self.single).data["claim"]["id"]
        self.submit(self.emp1, cid, proof_url="https://example.test/v1")
        self.assertEqual(self.act(self.mgr, cid, "rework").status_code, 400)  # без коментаря
        r = self.act(self.mgr, cid, "rework", comment="Додайте субтитри")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "rework")
        self.assertEqual(r.data["comment"], "Додайте субтитри")
        self.assertTrue(r.data["can_submit"] is False)  # переглядає керівник — не він здає
        self.assertEqual(self.act(self.mgr, cid, "accept").status_code, 409)  # спершу доробка
        mine = self.get(self.emp1, "/api/bounty/claims/?scope=mine").data["results"][0]
        self.assertTrue(mine["can_submit"])
        self.assertEqual(self.submit(self.emp1, cid, proof_url="https://example.test/v2").status_code, 200)
        r = self.act(self.mgr, cid, "accept")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([e["act"] for e in r.data["history"]], ["take", "submit", "rework", "submit", "accept"])

    def test_cancel_rules(self):
        cid = self.take(self.emp1, self.single).data["claim"]["id"]
        self.assertEqual(self.act(self.emp2, cid, "cancel").status_code, 403)
        self.assertEqual(self.act(self.emp1, cid, "cancel").status_code, 200)
        c2 = self.take(self.emp2, self.single).data["claim"]["id"]  # звільнилось
        self.submit(self.emp2, c2, proof_url="https://example.test/a")
        self.assertEqual(self.act(self.emp2, c2, "cancel").status_code, 403)  # здане — лише керівник
        self.assertEqual(self.act(self.mgr, c2, "cancel", comment="дубль").status_code, 200)

    # ── прайс і видимість ──
    def test_inactive_offer_hidden_and_cannot_be_taken(self):
        off = TaskOffer.objects.create(category=self.cat, title="Чернетка", price=Decimal("100"), active=False)
        ids = [o["id"] for o in self.get(self.emp1, "/api/bounty/board/").data["offers"]]
        self.assertNotIn(off.id, ids)
        self.assertIn(off.id, [o["id"] for o in self.get(self.mgr, "/api/bounty/board/").data["offers"]])
        r = self.take(self.emp1, off)
        self.assertEqual((r.status_code, r.data["code"]), (409, "inactive"))

    def test_catalog_edit_permissions_activation_and_order(self):
        body = {"category_id": self.cat.id, "title": "Нова задача", "price": "150", "unit": "task"}
        self.assertEqual(self.post(self.emp1, "/api/bounty/offers/", body).status_code, 403)
        self.assertEqual(self.post(self.emp1, "/api/bounty/categories/", {"department": "sales", "name": "Чати"}).status_code, 403)
        r = self.post(self.mgr, "/api/bounty/categories/", {"department": "sales", "name": "Чати"})
        self.assertEqual(r.status_code, 201)
        cat2 = r.data["id"]
        r = self.post(self.mgr, "/api/bounty/offers/", {**body, "category_id": cat2})
        self.assertEqual(r.status_code, 201, r.content)
        oid = r.data["id"]
        self.assertFalse(r.data["active"])  # нова задача — вимкнена, доки власник не ввімкне
        r2 = self.post(self.mgr, "/api/bounty/offers/", {**body, "category_id": cat2, "title": "Друга"})
        self.assertEqual(self.post(self.mgr, "/api/bounty/offers/", {**body, "unit": "pct", "price": "150"}).status_code, 400)
        self.assertNotIn(oid, [o["id"] for o in self.get(self.emp1, "/api/bounty/board/").data["offers"]])
        r = self.post(self.mgr, "/api/bounty/offers/activate/", {"department": "sales", "active": True})
        self.assertEqual(r.data["changed"], 2)
        self.assertIn(oid, [o["id"] for o in self.get(self.emp1, "/api/bounty/board/").data["offers"]])
        # порядок: «Друга» вгору
        self.post(self.mgr, f"/api/bounty/offers/{r2.data['id']}/move/", {"dir": "up"})
        titles = [o.title for o in TaskOffer.objects.filter(category_id=cat2).order_by("order", "id")]
        self.assertEqual(titles, ["Друга", "Нова задача"])
        # редагування і мʼяке видалення
        r = self.c(self.mgr).patch(f"/api/bounty/offers/{oid}/", {"price": "175", "checker_id": self.chk.id}, format="json", HTTP_HOST=HOST)
        self.assertEqual((r.status_code, r.data["price"], r.data["checker_id"]), (200, 175.0, self.chk.id))
        self.assertEqual(self.c(self.emp1).delete(f"/api/bounty/offers/{oid}/", HTTP_HOST=HOST).status_code, 403)
        self.assertEqual(self.c(self.mgr).delete(f"/api/bounty/offers/{oid}/", HTTP_HOST=HOST).status_code, 200)
        self.assertTrue(TaskOffer.objects.get(pk=oid).archived)
        self.assertNotIn(oid, [o["id"] for o in self.get(self.emp1, "/api/bounty/board/").data["offers"]])
        self.assertIn(oid, [o["id"] for o in self.get(self.mgr, "/api/bounty/board/").data["archived_offers"]])
        r = self.post(self.mgr, f"/api/bounty/offers/{oid}/restore/")
        self.assertEqual((r.status_code, r.data["archived"], r.data["active"]), (200, False, False))
        # видалення напряму — усі його задачі в архів
        r = self.c(self.mgr).delete(f"/api/bounty/categories/{cat2}/", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(TaskOffer.objects.filter(category_id=cat2, archived=False).count(), 0)

    # ── стандарт і фонд ──
    def test_standard_below_75_is_soft_warning(self):
        self.scheme(self.emp1, scores={S.prev_month(self.P): 0.6})
        b = self.get(self.emp1, "/api/bounty/board/").data
        self.assertFalse(b["me"]["standard"]["ok"])
        r = self.take(self.emp1, self.single)
        self.assertEqual(r.status_code, 201)  # не блокує
        self.assertIn("60%", r.data["warning"])
        self.assertIn("60%", TaskClaim.objects.get(pk=r.data["claim"]["id"]).std_warning)
        self.scheme(self.emp2, scores={S.prev_month(self.P): 0.8})
        r = self.take(self.emp2, self.piece, 1)
        self.assertEqual((r.status_code, r.data["warning"]), (201, ""))

    def test_fund_limit_blocks_take_and_accept_needs_force(self):
        art = FinModelArticle.objects.create(category="fixed", name="Біржа задач", value=Decimal("300"),
                                             value_type="fixed_sum_per_month")
        c1 = self.take(self.emp1, self.single).data["claim"]["id"]  # 250 у резерві
        r = self.take(self.emp2, self.piece, 3)  # 60 > 50
        self.assertEqual((r.status_code, r.data["code"]), (409, "fund"))
        c2 = self.take(self.emp2, self.piece, 2).data["claim"]["id"]  # 40 ≤ 50
        f = self.get(self.mgr, "/api/bounty/board/").data["fund"]
        self.assertEqual((f["limit"], f["reserved"], f["left"]), (300.0, 290.0, 10.0))
        self.submit(self.emp1, c1, proof_url="https://example.test/a")
        self.assertEqual(self.act(self.mgr, c1, "accept").status_code, 200)
        art.value = Decimal("260")
        art.save()
        self.submit(self.emp2, c2, proof_text="2 відео з субтитрами")
        r = self.act(self.mgr, c2, "accept")
        self.assertEqual((r.status_code, r.data["code"]), (409, "fund"))
        self.assertEqual(self.act(self.mgr, c2, "accept", force=True).status_code, 200)
        self.assertIsNone(self.get(self.emp1, "/api/bounty/board/").data["fund"])  # фонд бачить лише керівник

    def test_no_fund_article_means_no_limit(self):
        self.assertFalse(S.fund_info()["enforced"])
        self.assertEqual(FinModelArticle.objects.filter(name="Біржа задач").count(), 0)  # CRM статтю НЕ створює

    # ── ЗП ──
    def test_payroll_line_only_accepted_of_that_month(self):
        self.scheme(self.emp1)
        nxt, prv = S.next_month(self.P), S.prev_month(self.P)
        TaskClaim.objects.create(offer=self.single, user=self.emp1, status="accepted", amount=Decimal("250"), price=250, payroll_period=self.P)
        TaskClaim.objects.create(offer=self.piece, user=self.emp1, status="accepted", amount=Decimal("100"), price=20, qty=5, unit="piece", payroll_period=nxt)
        TaskClaim.objects.create(offer=self.piece, user=self.emp1, status="submitted", price=20, qty=5, unit="piece")
        TaskClaim.objects.create(offer=self.piece, user=self.emp1, status="cancelled", amount=Decimal("999"), price=20, payroll_period=self.P)
        TaskClaim.objects.create(offer=self.single, user=self.emp2, status="accepted", amount=Decimal("777"), price=250, payroll_period=self.P)
        cur = engine.calc(self.emp1, self.P)
        bl = [l for l in cur["lines"] if l["kind"] == "bounty"]
        self.assertEqual([l["amount"] for l in bl], [250])
        self.assertEqual(cur["total"], 1250)
        self.assertEqual([l["amount"] for l in engine.calc(self.emp1, nxt)["lines"] if l["kind"] == "bounty"], [100])
        self.assertEqual([l for l in engine.calc(self.emp1, prv)["lines"] if l["kind"] == "bounty"], [])

    def test_payroll_without_bounty_app_still_works(self):
        self.scheme(self.emp1)
        TaskClaim.objects.create(offer=self.single, user=self.emp1, status="accepted", amount=Decimal("250"), price=250, payroll_period=self.P)
        with mock.patch.dict(sys.modules, {"apps.bounty.payroll": None}):  # модуля немає → ImportError
            r = engine.calc(self.emp1, self.P)
        self.assertEqual(r["total"], 1000)
        self.assertFalse([l for l in r["lines"] if l["kind"] == "bounty"])
        with mock.patch("apps.bounty.payroll.django_apps.is_installed", return_value=False):  # не в INSTALLED_APPS
            r = engine.calc(self.emp1, self.P)
        self.assertEqual(r["total"], 1000)
        self.assertEqual(engine.calc(self.emp1, self.P)["total"], 1250)

    def test_approved_payroll_month_moves_accept_to_next_month(self):
        PayrollRun.objects.create(period=self.P, user=self.emp1, status="approved", total=0, company_cost=0)
        cid = self.take(self.emp1, self.single).data["claim"]["id"]
        self.submit(self.emp1, cid, proof_url="https://example.test/a")
        r = self.act(self.mgr, cid, "accept", payroll_period=self.P)
        self.assertEqual((r.status_code, r.data["code"]), (409, "run_approved"))
        r = self.act(self.mgr, cid, "accept")
        self.assertEqual(r.data["payroll_period"], S.next_month(self.P))
        # прийняте в незатвердженому місяці можна скасувати
        self.assertEqual(self.act(self.mgr, cid, "cancel", comment="помилка").status_code, 200)

    def test_pct_unit_needs_payments_base(self):
        pct = TaskOffer.objects.create(category=self.cat, title="% з оплат", price=Decimal("3"), unit="pct", max_takers=0, active=True)
        cid = self.take(self.emp1, pct).data["claim"]["id"]
        self.submit(self.emp1, cid, proof_text="угоди 101, 102 після реактивації")
        self.assertEqual(self.act(self.mgr, cid, "accept").status_code, 400)
        r = self.act(self.mgr, cid, "accept", base_amount="10000")
        self.assertEqual((r.status_code, r.data["amount"]), (200, 300.0))

    # ── доказ-файл ──
    def test_proof_file_access(self):
        cid = self.take(self.emp1, self.single).data["claim"]["id"]
        f = SimpleUploadedFile("proof.jpg", b"\xff\xd8\xffdata", content_type="image/jpeg")
        r = self.c(self.emp2).post(f"/api/bounty/claims/{cid}/files/", {"file": f}, format="multipart", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 403)
        f = SimpleUploadedFile("proof.jpg", b"\xff\xd8\xffdata", content_type="image/jpeg")
        r = self.c(self.emp1).post(f"/api/bounty/claims/{cid}/files/", {"file": f}, format="multipart", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 201, r.content)
        fid = r.data["id"]
        self.assertEqual(self.get(self.emp2, f"/api/bounty/files/{fid}/").status_code, 403)
        r = self.get(self.mgr, f"/api/bounty/files/{fid}/")
        self.assertEqual((r.status_code, r.content), (200, b"\xff\xd8\xffdata"))
        self.assertEqual(self.get(self.emp1, f"/api/bounty/files/{fid}/").status_code, 200)
        self.submit(self.emp1, cid, proof_url="https://example.test/a")
        f = SimpleUploadedFile("late.jpg", b"x", content_type="image/jpeg")
        r = self.c(self.emp1).post(f"/api/bounty/claims/{cid}/files/", {"file": f}, format="multipart", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 409)

    def test_photo_proof_requires_file_or_link(self):
        ph = TaskOffer.objects.create(category=self.cat, title="Фото", price=Decimal("50"), active=True, proof_type="photo")
        cid = self.take(self.emp1, ph).data["claim"]["id"]
        self.assertEqual(self.submit(self.emp1, cid, proof_text="фото зроблено, повірте").status_code, 400)
        f = SimpleUploadedFile("p.png", b"png", content_type="image/png")
        self.c(self.emp1).post(f"/api/bounty/claims/{cid}/files/", {"file": f}, format="multipart", HTTP_HOST=HOST)
        self.assertEqual(self.submit(self.emp1, cid, proof_text="").status_code, 200)

    # ── підсумки ──
    def test_summary_scope_and_strengths(self):
        for u, amt, q in ((self.emp1, 250, 5), (self.emp1, 100, 4), (self.emp2, 60, 3)):
            TaskClaim.objects.create(offer=self.single, user=u, status="accepted", amount=Decimal(amt), price=amt,
                                     payroll_period=self.P, quality=q)
        s = self.get(self.mgr, f"/api/bounty/summary/?month={self.P}").data
        self.assertEqual([p["name"] for p in s["people"]], ["Олена Перша", "Іван Другий"])
        self.assertEqual(s["people"][0]["amount"], 350.0)
        self.assertEqual(s["people"][0]["avg_quality"], 4.5)
        self.assertTrue(s["people"][0]["strengths"][0].startswith("Монтаж — 2"))
        self.assertEqual(s["people"][1]["strengths"], [])  # якість 3 — не «сильна сторона»
        self.assertEqual(s["total"], 410.0)
        own = self.get(self.emp2, f"/api/bounty/summary/?month={self.P}").data
        self.assertEqual([p["name"] for p in own["people"]], ["Іван Другий"])
        self.assertIsNone(own["fund"])

    # ── каталог Wallcov ──
    def test_seed_dry_then_idempotent_and_respects_deleted(self):
        TaskOffer.objects.all().delete()
        TaskCategory.objects.all().delete()
        out = StringIO()
        call_command("bounty_seed", "--dry", stdout=out)
        self.assertEqual(TaskOffer.objects.count(), 0)
        self.assertEqual(TaskCategory.objects.count(), 0)
        self.assertIn("нічого не записано", out.getvalue())
        call_command("bounty_seed", stdout=StringIO())
        n = TaskOffer.objects.count()
        self.assertGreaterEqual(n, 110)
        self.assertEqual(TaskOffer.objects.filter(active=True).count(), 0)
        self.assertEqual(TaskOffer.objects.exclude(note__startswith="ціна для обговорення").count(), 0)
        self.assertEqual(set(TaskCategory.objects.values_list("department", flat=True)),
                         {"marketing", "sales", "warehouse", "salon", "objects", "content", "ai_crm", "hr", "office"})
        gone = TaskOffer.objects.order_by("id").first()
        gone.archived = True
        gone.save()
        out = StringIO()
        call_command("bounty_seed", stdout=out)
        self.assertEqual(TaskOffer.objects.count(), n)
        self.assertTrue(TaskOffer.objects.get(pk=gone.pk).archived)
        self.assertIn("нових задач 0", out.getvalue())
