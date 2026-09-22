# -*- coding: utf-8 -*-
"""ІІ-РОП: пряме питання менеджера по діалогу (22.09.2026, Олег: «менеджері смогут спрашивать его
конкретно задав вопрос не только после анализа диалога»)."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.crm.models import Deal, Funnel, Stage, Contact
from apps.crm.sales_analyst import ask_analyst
from apps.inbox.models import Channel, Conversation, Message


class AskAnalystUnitTests(TestCase):
    def test_empty_question_rejected(self):
        r = ask_analyst([], "", context="")
        self.assertIn("error", r)

    @patch("apps.crm.sales_analyst.claude_json")
    def test_returns_answer(self, mock_cj):
        mock_cj.return_value = {"answer": "Клієнт мовчить бо чекає розрахунок площі."}
        msgs = [{"direction": "in", "text": "Скільки коштує?"}, {"direction": "out", "text": "290 грн"}]
        r = ask_analyst(msgs, "Чому клієнт не відповідає?", context="Сума 290 грн")
        self.assertEqual(r["answer"], "Клієнт мовчить бо чекає розрахунок площі.")
        self.assertEqual(r["question"], "Чому клієнт не відповідає?")

    @patch("apps.crm.sales_analyst.claude_json")
    def test_bad_llm_response(self, mock_cj):
        mock_cj.return_value = {}
        r = ask_analyst([{"direction": "in", "text": "привіт"}], "питання?")
        self.assertIn("error", r)


class AskAnalystEndpointTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("owner_ask", "o@x.com", "pass12345")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.f = Funnel.objects.create(name="21 Основний продукт")
        self.st = Stage.objects.create(funnel=self.f, name="Розрахунок", order=1)
        self.contact = Contact.objects.create(first_name="Ваня", nickname="dorchivania")
        self.deal = Deal.objects.create(title="t", funnel=self.f, stage=self.st, amount=300, contact=self.contact)
        ch = Channel.objects.create(name="Meta · instagram", kind="instagram")
        self.conv = Conversation.objects.create(channel=ch, contact=self.contact, external_chat_id="ext1")
        Message.objects.create(conversation=self.conv, direction="in", text="Як замовити пробник?")
        Message.objects.create(conversation=self.conv, direction="out", text="Пробник Galatea — 255 грн")

    def test_missing_question_400(self):
        r = self.client.post("/api/deals/%s/ask_analyst/" % self.deal.id, {}, format="json")
        self.assertEqual(r.status_code, 400)

    @patch("apps.crm.sales_analyst.claude_json")
    def test_deal_ask_ok(self, mock_cj):
        mock_cj.return_value = {"answer": "Так, пробник Galatea вже названо — 255 грн."}
        r = self.client.post("/api/deals/%s/ask_analyst/" % self.deal.id, {"question": "Яка ціна пробника?"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertIn("255", r.json()["answer"])

    @patch("apps.crm.sales_analyst.claude_json")
    def test_lead_ask_ok(self, mock_cj):
        from apps.crm.models import Lead
        lead = Lead.objects.create(title="l", contact=self.contact, funnel=self.f, stage=self.st)
        mock_cj.return_value = {"answer": "Клієнт цікавився Galatea."}
        r = self.client.post("/api/leads/%s/ask_analyst/" % lead.id, {"question": "Про що питав клієнт?"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("answer"))
