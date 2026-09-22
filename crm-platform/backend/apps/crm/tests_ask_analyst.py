# -*- coding: utf-8 -*-
"""ШІ-РОП: пряме питання менеджера по діалогу — заземлене в базу знань (22.09.2026).

Олег: «менеджери зможуть спитати конкретно, не лише після аналізу діалогу» + «ШІ-РОП сказав
що інформації про адресу немає, хоча вона є в базі знань — має відповідати спираючись на KB,
а не тільки на сам діалог». Тепер і /api/deals/<id>/ask_analyst/, і /api/leads/<id>/ask_analyst/,
і /api/conversations/<id>/ai_reply/ (з полем question) ведуть до однієї KB-заземленої функції
apps.crm.coach_prompt.ask_rop — та сама персона й база знань, що в кнопці «AI-РОП підказати відповідь»."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.crm.coach_prompt import ask_rop
from apps.crm.models import Deal, Funnel, Stage, Contact, Lead
from apps.inbox.models import Channel, Conversation, Message


class AskRopUnitTests(TestCase):
    def setUp(self):
        ch = Channel.objects.create(name="Meta · instagram", kind="instagram")
        self.contact = Contact.objects.create(first_name="Ваня", nickname="dorchivania")
        self.conv = Conversation.objects.create(channel=ch, contact=self.contact, external_chat_id="ext1")
        Message.objects.create(conversation=self.conv, direction="in", text="Як замовити пробник Galatea?")
        Message.objects.create(conversation=self.conv, direction="out", text="Пробник Galatea — 255 грн")

    def test_empty_question_rejected(self):
        r = ask_rop(self.conv, "")
        self.assertIn("error", r)

    @patch("apps.crm.ai.claude_json")
    def test_returns_answer(self, mock_cj):
        mock_cj.return_value = {"answer": "Так, пробник Galatea вже названо — 255 грн."}
        r = ask_rop(self.conv, "Яка ціна пробника?")
        self.assertIn("255", r["answer"])
        self.assertEqual(r["question"], "Яка ціна пробника?")

    @patch("apps.crm.ai.claude_json")
    def test_bad_llm_response(self, mock_cj):
        mock_cj.return_value = {}
        r = ask_rop(self.conv, "питання?")
        self.assertIn("error", r)

    @patch("apps.crm.ai.claude_json")
    def test_prompt_includes_knowledge_block(self, mock_cj):
        """Ключовий фікс 22.09: питання менеджера мусить іти в KB-пошук (knowledge_block),
        а не лише в діалог — інакше ШІ-РОП каже «інформації немає», хоча вона є в базі."""
        mock_cj.return_value = {"answer": "ок"}
        ask_rop(self.conv, "Де знаходиться наш магазин?")
        prompt = mock_cj.call_args[0][0]
        self.assertIn("Де знаходиться наш магазин", prompt)
        self.assertIn("БАЗА ЗНАНЬ WALLCOV", prompt)


class AskRopEndpointTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("owner_ask2", "o2@x.com", "pass12345")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.f = Funnel.objects.create(name="21 Основний продукт")
        self.st = Stage.objects.create(funnel=self.f, name="Розрахунок", order=1)
        self.contact = Contact.objects.create(first_name="Ваня", nickname="dorchivania")
        self.deal = Deal.objects.create(title="t", funnel=self.f, stage=self.st, amount=300, contact=self.contact)
        ch = Channel.objects.create(name="Meta · instagram", kind="instagram")
        self.conv = Conversation.objects.create(channel=ch, contact=self.contact, external_chat_id="ext1")
        Message.objects.create(conversation=self.conv, direction="in", text="Де знаходиться ваш магазин?")

    def test_missing_question_400(self):
        r = self.client.post("/api/deals/%s/ask_analyst/" % self.deal.id, {}, format="json")
        self.assertEqual(r.status_code, 400)

    @patch("apps.crm.ai.claude_json")
    def test_deal_ask_ok(self, mock_cj):
        mock_cj.return_value = {"answer": "Вірменська 15/1, Могилів-Подільський."}
        r = self.client.post("/api/deals/%s/ask_analyst/" % self.deal.id, {"question": "Де магазин?"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Вірменська", r.json()["answer"])

    @patch("apps.crm.ai.claude_json")
    def test_lead_ask_ok(self, mock_cj):
        lead = Lead.objects.create(title="l", contact=self.contact, funnel=self.f, stage=self.st)
        mock_cj.return_value = {"answer": "Клієнт цікавився Galatea."}
        r = self.client.post("/api/leads/%s/ask_analyst/" % lead.id, {"question": "Про що питав клієнт?"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("answer"))

    @patch("apps.crm.ai.claude_json")
    def test_conversation_ai_reply_question_mode(self, mock_cj):
        """Нове: /api/conversations/<id>/ai_reply/ з полем question — для «Запитати ШІ-РОП» у Відкритих лініях."""
        mock_cj.return_value = {"answer": "Вірменська 15/1, Могилів-Подільський — і ми переважно онлайн."}
        r = self.client.post("/api/conversations/%s/ai_reply/" % self.conv.id, {"question": "Де наш магазин?"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Вірменська", r.json()["answer"])

    @patch("apps.crm.ai.claude_json")
    def test_conversation_ai_reply_no_question_uses_old_coach_mode(self, mock_cj):
        """Без question — стара поведінка (context/points/suggestion) не зламана."""
        mock_cj.return_value = {"context": "c", "points": ["p"], "suggestion": "s"}
        r = self.client.post("/api/conversations/%s/ai_reply/" % self.conv.id, {}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json().get("suggestion"), "s")
