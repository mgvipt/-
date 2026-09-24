"""Особистий асистент: приймання (секрет, групи вимкнені), власник, витяг у пропозиції, схвалення → чернетка бази."""
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.crm.models import AiUsage
from apps.knowledge.models import KnowledgeItem
from . import services as svc
from .models import AssistantChat, AssistantMessage, AssistantProposal, AssistantSettings

SECRET = "test-secret"


def biz(mid, text, uid=500, chat=777, name="Таргетолог"):
    return {"business_message": {"message_id": mid, "date": 1758700000 + mid, "text": text,
                                 "chat": {"id": chat, "type": "private", "first_name": name},
                                 "from": {"id": uid, "first_name": "Олег" if uid == 42 else name}}}


class AssistantTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="as-owner", password="x", is_superuser=True, is_staff=True)
        self.manager = User.objects.create_user(username="as-manager", password="x",
                                                extra_permissions=["content_factory.access"])
        self.env = patch.dict("os.environ", {"CF_INGEST_SECRET": SECRET})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.c = APIClient()

    def post(self, upd, secret=SECRET):
        return self.c.post("/api/assistant/ingest/", upd, format="json", HTTP_X_CF_INGEST=secret)

    def test_ingest_business_owner_and_groups_off(self):
        self.assertEqual(self.post(biz(1, "x"), secret="no").status_code, 403)
        self.assertEqual(self.post(biz(1, "Олег, бюджет на жовтень 800$")).json()["status"], "saved")
        self.post(biz(2, "Добре, тоді запускаємо в понеділок", uid=42))
        self.assertEqual(self.post({"business_connection": {"id": "bc", "user": {"id": 42}}}).json()["status"], "owner-set")
        self.assertTrue(AssistantMessage.objects.get(message_id=2).from_owner)
        grp = {"message": {"message_id": 5, "date": 1758700000, "text": "у групі",
                           "chat": {"id": -100, "type": "supergroup", "title": "Робоча"}, "from": {"id": 9}}}
        self.assertEqual(self.post(grp).json()["status"], "chat-disabled")
        self.assertFalse(AssistantChat.objects.get(chat_id=-100).enabled)

    def test_extract_accept_to_draft_and_budget(self):
        self.post(biz(1, "Ціна Галатеї від постачальника з жовтня 1250 грн/кг"))
        self.post(biz(2, "Домовились: креативи до 30.09", uid=42))
        mids = list(AssistantMessage.objects.values_list("id", flat=True))
        calls = []

        def fake(prompt):
            calls.append(prompt)
            AiUsage.objects.create(source=svc.EXTRACT_SOURCE, model="x", cost_usd=0.01)
            return {"items": [{"kind": "price", "title": "Галатея 1250 грн/кг з жовтня", "text": "Нова ціна.",
                               "who": "постачальник", "quote_ids": [mids[0]]},
                              {"kind": "agreement", "title": "Креативи до 30.09", "text": "Таргетолог.",
                               "who": "таргетолог", "due": "2026-09-30", "quote_ids": [mids[1]]}]}
        self.assertEqual(svc.extract(call=fake), 2)
        self.assertEqual(svc.extract(call=fake), 0)  # уже розібрано — не платимо вдруге
        self.assertEqual(len(calls), 1)
        price = AssistantProposal.objects.get(kind="price")
        svc.accept(price)
        item = KnowledgeItem.objects.get(pk=price.knowledge_item_id)
        self.assertEqual((item.status, item.topic), ("draft", "pricing"))  # агенти не бачать до затвердження
        agr = AssistantProposal.objects.get(kind="agreement")
        svc.accept(agr)
        self.assertIsNone(agr.knowledge_item_id)  # домовленість — лише в журналі
        s = AssistantSettings.get()
        s.monthly_budget_usd = 0
        s.save()
        self.post(biz(3, "ще щось важливе про доставку новою поштою"))
        with self.assertRaises(svc.BudgetError):
            svc.extract(call=fake)

    def test_owner_only(self):
        self.c.force_authenticate(self.manager)
        self.assertEqual(self.c.get("/api/assistant/").status_code, 403)
        self.c.force_authenticate(self.owner)
        self.assertEqual(self.c.get("/api/assistant/").status_code, 200)
