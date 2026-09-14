"""Регресія 11.09: AI-агент не повинен повертати в роботу лід, який менеджер закрив,
поки агент думав.

run_agent_sweep (крон */10) завантажує ліда, кілька секунд чекає Claude, і _move_stage
зберігав стадію зі СТАРОГО знімка поверх «Не вдалося зв.» — лід повертався в роботу через
2–48 с після «Завершити чат» (15 лідів з 01.08: 341, 5252, 5461, 5577…). А _fill_needs тим
самим старим знімком стирав close_reason/_reached_stage_id (лід 5577).
"""
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.crm import agent
from apps.crm.models import AgentConfig, Contact, Funnel, Lead, Stage
from apps.inbox.models import Channel, Conversation
from apps.inbox.views import _close_contact_leads

SWEEP_RUN_AGENT = "apps.crm.management.commands.run_agent_sweep.run_agent"
REASON = "Не відповідає (ігнор)"


class AgentDoesNotReopenClosedLeadTests(TestCase):
    def setUp(self):
        # стадії як у живій воронці «Лиды»
        self.funnel = Funnel.objects.create(name="Лиды", is_lead_funnel=True)
        names = ["Лід отриманий", "Взято в роботу", "Контакт встановлений", "Кваліфікований", "Підбір рішення"]
        self.st = {n: Stage.objects.create(funnel=self.funnel, name=n, order=i) for i, n in enumerate(names)}
        self.lost = Stage.objects.create(funnel=self.funnel, name="Не вдалося зв.", order=5, is_lost=True)
        self.later = Stage.objects.create(funnel=self.funnel, name="Хочу пізніше", order=6)
        self.ch = Channel.objects.create(kind="instagram", name="ChatPlace · Instagram", config={})
        self.contact, self.conv, self.lead = self._lead("race-1")
        AgentConfig.objects.update_or_create(id=1, defaults={"enabled": True, "autonomous": True, "auto_on_reply": True})

    def _lead(self, chat_id):
        contact = Contact.objects.create(first_name=chat_id)
        conv = Conversation.objects.create(channel=self.ch, contact=contact, external_chat_id=chat_id)
        Conversation.objects.filter(pk=conv.pk).update(last_message_at=timezone.now())
        lead = Lead.objects.create(title=chat_id, funnel=self.funnel, stage=self.st["Взято в роботу"], contact=contact)
        return contact, conv, lead

    def _snapshot(self):
        # знімок ліда, як його тримає агент під час виклику Claude
        return Lead.objects.select_related("stage", "funnel", "contact").get(pk=self.lead.pk)

    def _close_chat(self, reason=REASON):
        # те саме, що робить кнопка «Завершити чат» (InboxViewSet.close)
        Conversation.objects.filter(pk=self.conv.pk).update(status="closed")
        _close_contact_leads(self.contact.id, reason)

    def test_stale_move_stage_does_not_reopen_closed_lead(self):
        stale = self._snapshot()
        self._close_chat()
        r = agent._move_stage(stale, "lead", "Контакт встановлений", "клієнт відповів", None, True)
        self.assertFalse(r["ok"])
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.stage_id, self.lost.id)

    def test_stale_move_stage_keeps_deferred_lead(self):
        stale = self._snapshot()
        self._close_chat("Хочу пізніше")
        agent._move_stage(stale, "lead", "Контакт встановлений", "клієнт відповів", None, True)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.stage_id, self.later.id)

    def test_manager_closes_chat_while_claude_is_thinking(self):
        def fake_call(system, user_text, model, max_tokens=1200):
            self._close_chat()  # менеджер тисне «Завершити чат», поки Claude думає
            return {"content": [
                {"type": "tool_use", "name": "fill_needs", "input": {"material": "Galateya"}},
                {"type": "tool_use", "name": "move_stage",
                 "input": {"to_stage": "Контакт встановлений", "reason": "клієнт відповів"}}]}

        with patch.object(agent, "_call", side_effect=fake_call):
            agent.run_agent(self._snapshot(), "lead", trigger="sweep")
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.stage_id, self.lost.id)
        q = self.lead.qualification
        self.assertEqual(q.get("close_reason"), REASON)
        self.assertEqual(q.get("_reached_stage_id"), self.st["Взято в роботу"].id)
        self.assertEqual(q.get("material"), "Galateya")

    def test_open_lead_still_moves_forward(self):
        r = agent._move_stage(self._snapshot(), "lead", "Контакт встановлений", "клієнт відповів", None, True)
        self.assertTrue(r["ok"])
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.stage_id, self.st["Контакт встановлений"].id)

    def test_sweep_skips_lead_whose_chat_is_closed(self):
        Conversation.objects.filter(pk=self.conv.pk).update(status="closed")
        with patch(SWEEP_RUN_AGENT) as run:
            call_command("run_agent_sweep", stdout=StringIO())
        run.assert_not_called()

    def test_sweep_runs_lead_with_open_chat(self):
        with patch(SWEEP_RUN_AGENT) as run:
            call_command("run_agent_sweep", stdout=StringIO())
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0].pk, self.lead.pk)

    def test_sweep_rechecks_stage_right_before_run(self):
        # список лідів уже завантажено; поки агент працює з першим, другого закривають
        _, _, lead2 = self._lead("race-2")
        seen = []

        def fake_run(entity, kind, **kw):
            seen.append(entity.pk)
            other = lead2 if entity.pk == self.lead.pk else self.lead
            Lead.objects.filter(pk=other.pk).update(stage=self.lost)

        with patch(SWEEP_RUN_AGENT, side_effect=fake_run):
            call_command("run_agent_sweep", stdout=StringIO())
        self.assertEqual(len(seen), 1)


    def test_sweep_skips_deal_whose_chat_is_closed(self):
        # 14.09: угоду з завершеним чатом агент теж не рухає, поки клієнт не напише
        from apps.crm.models import Deal
        Lead.objects.filter(pk=self.lead.pk).update(stage=self.lost)
        df = Funnel.objects.create(name="21 Основний продукт")
        ds = Stage.objects.create(funnel=df, name="Розрахунок", order=0)
        Deal.objects.create(title="d", funnel=df, stage=ds, contact=self.contact, amount=100)
        Conversation.objects.filter(pk=self.conv.pk).update(status="closed")
        with patch(SWEEP_RUN_AGENT) as run:
            call_command("run_agent_sweep", stdout=StringIO())
        run.assert_not_called()
