"""ai-kb2 (14.09.2026): рушій відповіді / тестовий чат, веб-чат, контролер лише за запуском, публікація в Юлю
з підтвердженням, попередня перевірка чернеток. Лише ізольована тестова БД; Claude і ChatPlace ПІДМІНЕНІ —
жодних зовнішніх запитів, жодних повідомлень клієнтам."""
import io
import json
from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.inbox.models import Channel, Conversation, Message
from apps.warehouse.models import Product

from . import runs
from .answer import HANDOFF_TEXT, answer, rop_master_rules
from .fallbacks import compose_style
from .models import KnowledgeCheck, KnowledgeItem, KnowledgeRun, KnowledgeSettings, KnowledgeVersion
from .reader import approved_for

IG_BOT = "647e28e9-73fd-4f06-81cc-5970409a7381"
CC = "apps.knowledge.answer.call_claude"


def kitem(**kw):
    d = dict(kind="qa", topic="other", audience=["yulia_web"], status="approved", title="Питання", text="Відповідь")
    d.update(kw)
    return KnowledgeItem.objects.create(**d)


def resp(text="", content=None, usage=None):
    return {"content": content if content is not None else [{"type": "text", "text": text}],
            "usage": usage or {"input_tokens": 1000, "output_tokens": 100}}


def seller(reply, handoff=False, reason=""):
    return resp(json.dumps({"reply": reply, "handoff": handoff, "reason": reason}, ensure_ascii=False))


def client_of(u):
    c = APIClient()
    c.force_authenticate(u)
    return c


class Users:
    def make_users(self):
        self.owner = User.objects.create_superuser(username="kb2-owner", password="x")
        self.editor = User.objects.create_user(
            username="kb2-editor", role=Role.objects.create(name="kb2-editor-role", permissions=["knowledge.edit"]))
        self.approver = User.objects.create_user(
            username="kb2-approver", role=Role.objects.create(name="kb2-approver-role", permissions=["knowledge.approve"]))
        self.plain = User.objects.create_user(username="kb2-plain")


class FakeMcp:
    def __init__(self, remote=None):
        self.remote, self.calls = list(remote or []), []

    def __call__(self, name, args):
        self.calls.append((name, args))
        if name == "ai_agent_knowledge_base_list":
            return {"items": self.remote if not args.get("offset") else []}
        if name == "ai_agent_knowledge_base_add":
            return {"id": "ds-new"}
        if name == "ai_agent_test_question":
            return {"datasetId": None, "answer": "Доставляємо Новою Поштою", "isQuestionAnswered": True, "buttons": []}
        return {"success": True}


# ───────────────────────── рушій відповіді ─────────────────────────

class AnswerEngineTests(TestCase):
    def setUp(self):
        self.p = Product.objects.create(name="Galateya Silver kb2", price=1000, unit="кг", consumption_per_m2="0.15")
        self.ok = kitem(title="Скільки коштує доставка?", topic="delivery",
                        text="МАРКЕР-ЗАТВ доставка Новою Поштою; Галатея {price:%d}" % self.p.id)
        self.draft = kitem(status="draft", title="Чи є доставка курʼєром?", topic="delivery",
                           text="МАРКЕР-ЧЕРН доставка курʼєром за тарифом")
        self.other = kitem(audience=["compose_assist"], topic="objections", title="Доставка дорога?",
                           text="МАРКЕР-ІНШИЙ доставка — пояснити тариф")
        self.q = [{"role": "client", "text": "Скільки коштує доставка?"}]

    def test_approved_only_by_default_used_items_prices_cost(self):
        with patch(CC, return_value=seller("Доставляємо Новою Поштою 🚚 Для якої кімнати обираєте покриття?")) as cc:
            r = answer("yulia_web", self.q)
        prompt = cc.call_args.args[1]
        self.assertIn("МАРКЕР-ЗАТВ", prompt)
        self.assertNotIn("МАРКЕР-ЧЕРН", prompt)
        self.assertNotIn("МАРКЕР-ІНШИЙ", prompt)
        self.assertEqual([u["id"] for u in r["used_items"]], [self.ok.id])
        self.assertTrue(any("1000 грн/кг" in p for p in r["prices"]), r["prices"])
        self.assertFalse(r["handoff"])
        self.assertIn("Новою Поштою", r["text"])
        self.assertAlmostEqual(r["cost"]["usd"], 0.0015, places=5)  # 1000 × $1/М + 100 × $5/М (Haiku)
        self.assertEqual(cc.call_args.args[2], "claude-haiku-4-5")

    def test_drafts_only_in_test_mode_and_never_leak_to_real_agents(self):
        with patch(CC, return_value=seller("Так, курʼєром теж можна. Для якої кімнати?")) as cc:
            r = answer("yulia_web", [{"role": "client", "text": "А курʼєром доставка є?"}], include_drafts=True)
        self.assertIn("МАРКЕР-ЧЕРН", cc.call_args.args[1])
        self.assertIn(self.draft.id, [u["id"] for u in r["used_items"]])
        self.assertEqual([i.id for i in approved_for("yulia_web")], [self.ok.id])  # справжній агент — лише затверджене

    def test_proposal_replaces_original_in_draft_mode(self):
        kitem(status="draft", replaces=self.ok, title="Скільки коштує доставка?", topic="delivery",
              text="МАРКЕР-ПРАВКА доставка безкоштовно від порогу")
        with patch(CC, return_value=seller("Доставка Новою Поштою. Яку кімнату рахуємо?")) as cc:
            answer("yulia_web", self.q, include_drafts=True)
        self.assertIn("МАРКЕР-ПРАВКА", cc.call_args.args[1])
        self.assertNotIn("МАРКЕР-ЗАТВ", cc.call_args.args[1])

    def test_topic_filter(self):
        kitem(topic="materials", title="Скільки коштує доставка Галатеї?", text="МАРКЕР-МАТЕРІАЛ доставка")
        with patch(CC, return_value=seller("Для якої кімнати?")) as cc:
            answer("yulia_web", self.q, topic="materials")
        self.assertIn("МАРКЕР-МАТЕРІАЛ", cc.call_args.args[1])
        self.assertNotIn("МАРКЕР-ЗАТВ", cc.call_args.args[1])

    def test_audience_filter_compose_sees_its_own(self):
        with patch(CC, return_value=resp(json.dumps({"text": "Доставка за тарифом НП"}))) as cc:
            r = answer("compose_assist", [{"role": "client", "text": "Доставка дорога, чому?"}])
        self.assertIn("МАРКЕР-ІНШИЙ", cc.call_args.args[1])
        self.assertNotIn("МАРКЕР-ЗАТВ", cc.call_args.args[0] + cc.call_args.args[1])
        self.assertEqual(r["text"], "Доставка за тарифом НП")

    def test_compose_with_drafts_uses_the_same_merge_as_real_assistant(self):
        kitem(status="draft", kind="rule", topic="payment", audience=["compose_assist"], title="Оплата",
              text="МАРКЕР-ОПЛАТА-ЧЕРН лише LiqPay")
        with patch(CC, return_value=resp(json.dumps({"text": "ok"}))) as cc:
            answer("compose_assist", self.q, include_drafts=True)
        self.assertIn("МАРКЕР-ОПЛАТА-ЧЕРН", cc.call_args.args[0])       # тема «Оплата» з бази замість вбудованої
        self.assertNotIn("МАРКЕР-ОПЛАТА-ЧЕРН", compose_style())          # справжній ✨ чернетки не бачить
        self.assertIn("до 5 000 грн — 20%", compose_style())

    def test_empty_base_for_seller_hands_off_without_ai(self):
        KnowledgeItem.objects.all().delete()
        with patch(CC) as cc:
            r = answer("yulia_web", self.q)
        cc.assert_not_called()
        self.assertTrue(r["handoff"])
        self.assertEqual(r["text"], HANDOFF_TEXT)

    def test_estimate_only_no_ai(self):
        with patch(CC) as cc:
            r = answer("rop_hint", [], estimate_only=True)
        cc.assert_not_called()
        self.assertGreater(r["estimate"]["usd"], 0)
        self.assertEqual(r["estimate"]["model"], "claude-sonnet-4-6")

    def test_rop_uses_real_coach_prompt_and_master_rules(self):
        self.assertIn("МАЙСТЕР-ПРАВИЛА", rop_master_rules())
        out = {"context": "Питає ціну", "points": ["a", "b"], "suggestion": "Доставка Новою Поштою. Яку кімнату рахуємо?"}
        with patch(CC, return_value=resp(json.dumps(out, ensure_ascii=False))) as cc:
            r = answer("rop_hint", self.q)
        system = cc.call_args.args[0]
        self.assertTrue(system.startswith("# Ти — AI-РОП Wallcov"))
        self.assertIn("МАЙСТЕР-ПРАВИЛА", system)
        self.assertIn("БАЗА ЗНАНЬ WALLCOV", cc.call_args.args[1])
        self.assertEqual(r["text"], out["suggestion"])
        self.assertEqual(r["extra"]["points"], ["a", "b"])

    def test_funnel_agent_shows_actions_and_executes_nothing(self):
        from apps.crm.models import AgentRun
        content = [{"type": "tool_use", "name": "move_stage", "input": {"to_stage": "Оплату отримано", "reason": "погодився"}},
                   {"type": "tool_use", "name": "fill_needs", "input": {"area": "20", "room": "Кухня"}}]
        with patch(CC, return_value=resp(content=content)) as cc:
            r = answer("funnel_agent", [{"role": "client", "text": "Беру, 20 м² на кухню"}])
        self.assertEqual(len(r["actions"]), 2)
        self.assertIn("заблоковано", r["text"])
        self.assertEqual(AgentRun.objects.count(), 0)
        self.assertNotIn("create_task", [t["name"] for t in cc.call_args.kwargs["tools"]])


class SellerGuardTests(TestCase):
    def setUp(self):
        self.p = Product.objects.create(name="Galateya Silver kb2g", price=1000, unit="кг")
        self.it = kitem(title="Скільки коштує Галатея?", topic="pricing", text="Галатея — {price:%d}" % self.p.id)
        self.q = [{"role": "client", "text": "Скільки коштує Галатея?"}]

    def test_invented_price_goes_to_manager(self):
        with patch(CC, return_value=seller("Галатея коштує 999 грн за кілограм. Яку кімнату рахуємо?")):
            r = answer("yulia_web", self.q)
        self.assertTrue(r["handoff"])
        self.assertIn("999 грн", r["handoff_reason"])
        self.assertIn("999", r["draft_reply"])
        self.assertEqual(r["text"], HANDOFF_TEXT)

    def test_catalog_price_is_allowed(self):
        with patch(CC, return_value=seller("Галатея — 1 000 грн/кг. Яку кімнату рахуємо першою?")):
            r = answer("yulia_web", self.q)
        self.assertFalse(r["handoff"], r["handoff_reason"])

    def test_client_wants_to_pay_goes_to_manager(self):
        with patch(CC, return_value=seller("Чудово! Для якої кімнати?")):
            r = answer("yulia_web", [{"role": "client", "text": "Скільки коштує Галатея? Хочу оплатити, скиньте реквізити"}])
        self.assertTrue(r["handoff"])
        self.assertIn("замовити / оплатити", r["handoff_reason"])

    def test_discount_only_with_approved_rule(self):
        with patch(CC, return_value=seller("Зараз діє знижка на Галатею! Для якої кімнати?")):
            r = answer("yulia_web", self.q)
        self.assertTrue(r["handoff"])
        self.assertIn("знижки", r["handoff_reason"])
        kitem(topic="discounts", title="Чи є знижка на Галатею?", text="Знижка 10% на Галатею від 20000 грн")
        with patch(CC, return_value=seller("Так, знижка 10% на Галатею від 20000 грн. Для якої кімнати?")):
            r = answer("yulia_web", [{"role": "client", "text": "Чи є знижка на Галатею?"}])
        self.assertFalse(r["handoff"], r["handoff_reason"])

    def test_model_own_handoff_is_respected(self):
        with patch(CC, return_value=seller("Уточню в менеджера", handoff=True, reason="немає фактів")):
            r = answer("yulia_web", self.q)
        self.assertTrue(r["handoff"])
        self.assertIn("немає фактів", r["handoff_reason"])


# ───────────────────────── API тестового чату ─────────────────────────

class TestChatApiTests(Users, TestCase):
    def setUp(self):
        self.make_users()
        self.it = kitem(audience=["yulia_web", "yulia_ig"], title="Скільки коштує доставка?", topic="delivery",
                        text="Доставка Новою Поштою за тарифом")

    def test_permissions(self):
        self.assertEqual(client_of(self.plain).get("/api/knowledge/test-chat/").status_code, 403)
        self.assertEqual(client_of(self.plain).post("/api/knowledge/test-chat/", {"agent": "yulia_web"}, format="json").status_code, 403)
        r = client_of(self.editor).get("/api/knowledge/test-chat/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([a["value"] for a in r.data["agents"]],
                         ["yulia_ig", "yulia_tiktok", "yulia_web", "compose_assist", "rop_hint", "funnel_agent"])
        self.assertFalse(r.data["stored"])

    def test_reply_is_not_stored_as_chat(self):
        convs, msgs = Conversation.objects.count(), Message.objects.count()
        with patch(CC, return_value=seller("Доставляємо Новою Поштою за тарифом. Для якої кімнати?")):
            r = client_of(self.editor).post("/api/knowledge/test-chat/", {
                "agent": "yulia_web", "include_drafts": True,
                "messages": [{"role": "client", "text": "Скільки коштує доставка?"}]}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["used_items"][0]["id"], self.it.id)
        self.assertEqual((Conversation.objects.count(), Message.objects.count()), (convs, msgs))

    def test_bad_input_and_estimate(self):
        c = client_of(self.editor)
        self.assertEqual(c.post("/api/knowledge/test-chat/", {"agent": "x", "messages": []}, format="json").status_code, 400)
        r = c.post("/api/knowledge/test-chat/", {"agent": "yulia_web", "messages": [{"role": "agent", "text": "Вітаю"}]},
                   format="json")
        self.assertEqual(r.status_code, 400)
        with patch(CC) as cc:
            r = c.post("/api/knowledge/test-chat/", {"agent": "rop_hint", "estimate_only": True, "messages": []}, format="json")
        cc.assert_not_called()
        self.assertEqual(r.status_code, 200)
        self.assertGreater(r.data["estimate"]["usd"], 0)

    def test_chatplace_test_question_is_read_only(self):
        fake = FakeMcp()
        with patch("apps.knowledge.publisher.default_mcp", return_value=fake):
            r = client_of(self.editor).post("/api/knowledge/test-chat/chatplace/",
                                            {"bot": "ig", "question": "Скільки коштує доставка?"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["answer"], "Доставляємо Новою Поштою")
        self.assertEqual(fake.calls, [("ai_agent_test_question", {"botId": IG_BOT, "question": "Скільки коштує доставка?"})])


# ───────────────────────── веб-чат ─────────────────────────

class WebchatAiTests(Users, TestCase):
    def setUp(self):
        self.make_users()
        ch = Channel.objects.create(kind="web", name="Web kb2", config={"web_chat": True})
        self.conv = Conversation.objects.create(channel=ch, external_chat_id="wallcovdliastin.com.ua:kb2")
        Message.objects.create(conversation=self.conv, direction="out", text="Вітаю! Я Юля з Wallcov.", external_id="web-greeting:kb2")
        self.msg = Message.objects.create(conversation=self.conv, direction="in", text="Скільки коштує доставка?",
                                          external_id="web-in:kb2-1")
        self.it = kitem(title="Скільки коштує доставка?", topic="delivery", text="Доставка Новою Поштою за тарифом перевізника")

    def on(self):
        cfg = KnowledgeSettings.get()
        cfg.webchat_ai_enabled = True
        cfg.save()

    def reply(self, msg=None):
        from apps.inbox.webchat import _ai_reply
        return _ai_reply(self.conv, msg or self.msg)

    @override_settings(WEBCHAT_SELLER_URL="")
    def test_switch_off_is_exactly_old_behaviour(self):
        self.assertFalse(KnowledgeSettings.get().webchat_ai_enabled)
        with patch(CC) as cc, patch("apps.inbox.webchat.urllib.request.urlopen") as uo:
            m = self.reply()
        cc.assert_not_called()
        uo.assert_not_called()
        self.assertIn("передала питання менеджеру", m.text)
        self.assertFalse(Message.objects.filter(conversation=self.conv, internal=True).exists())

    def test_switch_on_answers_from_approved_base(self):
        self.on()
        text = "Доставляємо Новою Поштою за тарифом перевізника 🚚 Для якої кімнати обираєте покриття?"
        with patch(CC, return_value=seller(text)) as cc:
            m = self.reply()
        self.assertEqual(m.text, text)
        self.assertEqual(m.external_id, "web-ai:%d" % self.msg.id)
        self.assertIn("Доставка Новою Поштою", cc.call_args.args[1])
        self.assertEqual(cc.call_args.args[2], "claude-haiku-4-5")
        note = Message.objects.get(conversation=self.conv, internal=True)
        self.assertIn("#%d" % self.it.id, note.text)

    def test_switch_on_draft_is_invisible(self):
        self.on()
        KnowledgeItem.objects.filter(pk=self.it.pk).update(status="draft")
        with patch(CC) as cc:
            m = self.reply()
        cc.assert_not_called()
        self.assertEqual(m.text, HANDOFF_TEXT)

    def test_switch_on_guard_price_and_pay_intent(self):
        self.on()
        with patch(CC, return_value=seller("Доставка коштує 150 грн. Для якої кімнати?")):
            m = self.reply()
        self.assertEqual(m.text, HANDOFF_TEXT)
        self.assertIn("не з каталогу", Message.objects.get(conversation=self.conv, internal=True).text)
        m2 = Message.objects.create(conversation=self.conv, direction="in", text="Хочу оплатити, дайте реквізити",
                                    external_id="web-in:kb2-2")
        with patch(CC, return_value=seller("Звісно! Для якої кімнати?")):
            self.assertEqual(self.reply(m2).text, HANDOFF_TEXT)

    def test_switch_on_error_hands_off(self):
        self.on()
        with patch(CC, side_effect=RuntimeError("мережа")):
            m = self.reply()
        self.assertEqual(m.text, HANDOFF_TEXT)
        self.assertIn("помилка", Message.objects.get(conversation=self.conv, internal=True).text)

    def test_switch_owner_only_and_audience_helper(self):
        r = client_of(self.approver).patch("/api/knowledge/settings/", {"webchat_ai_enabled": True}, format="json")
        self.assertEqual(r.status_code, 403)
        r = client_of(self.owner).patch("/api/knowledge/settings/", {"webchat_ai_enabled": True}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["webchat_ai_enabled"])
        self.assertEqual(r.data["webchat_items"], 1)
        ig = kitem(audience=["yulia_ig"], title="IG-запис", text="текст")
        self.assertEqual(client_of(self.approver).post("/api/knowledge/webchat/audience/", {}, format="json").status_code, 403)
        c = client_of(self.owner)
        self.assertEqual(c.post("/api/knowledge/webchat/audience/", {}, format="json").data["count"], 1)
        self.assertEqual(c.post("/api/knowledge/webchat/audience/", {"expected": 5}, format="json").status_code, 409)
        self.assertEqual(c.post("/api/knowledge/webchat/audience/", {"expected": 1}, format="json").data["updated"], 1)
        ig.refresh_from_db()
        self.assertIn("yulia_web", ig.audience)


# ───────────────────────── контролер: лише за запуском ─────────────────────────

class ControllerTests(Users, TestCase):
    def setUp(self):
        self.make_users()
        self.day = timezone.localdate() - timedelta(days=1)
        ch = Channel.objects.create(kind="instagram", name="IG kb2", config={})
        self.conv = Conversation.objects.create(channel=ch, external_chat_id="kb2-rev-1", status="closed")
        Message.objects.create(conversation=self.conv, direction="in", text="Що входить у тест-набір?", external_id="k1")
        Message.objects.create(conversation=self.conv, direction="out", text="У тест-наборі вже є все потрібне. Оформлюємо?",
                               external_id="k2")
        Conversation.objects.filter(pk=self.conv.pk).update(
            last_message_at=timezone.make_aware(datetime.combine(self.day, time(12, 0))))
        self.fake = {"findings": [{"type": "contradiction", "who": "ai", "quote": "вже є все потрібне",
                                   "problem": "Інструмент не входить", "topic": "test_sets",
                                   "suggested_title": "Чи є інструмент у тест-наборі?",
                                   "suggested_text": "Ні, інструмент купується окремо."}]}

    def test_command_never_calls_ai_even_if_old_switch_on(self):
        cfg = KnowledgeSettings.get()
        cfg.reviewer_enabled = True
        cfg.save()
        with patch("apps.crm.ai.claude_json") as cj:
            out = io.StringIO()
            call_command("kb_review_daily", "--date", self.day.isoformat(), stdout=out)
        cj.assert_not_called()
        self.assertIn("лише кнопкою", out.getvalue())
        self.assertFalse(KnowledgeItem.objects.filter(source="reviewer").exists())

    def test_no_schedule_flag(self):
        r = client_of(self.owner).get("/api/knowledge/controller/")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["scheduled"])
        self.assertFalse(client_of(self.owner).get("/api/knowledge/settings/").data["controller_scheduled"])

    def test_estimate_then_manual_run_creates_drafts_with_links(self):
        c = client_of(self.owner)
        with patch("apps.crm.ai.claude_json") as cj:
            est = c.post("/api/knowledge/controller/", {"period": "yesterday", "estimate": True}, format="json")
        cj.assert_not_called()
        self.assertEqual(est.status_code, 200, est.content)
        self.assertEqual(est.data["count"], 1)
        self.assertGreater(est.data["est_usd"], 0)
        with patch("apps.crm.ai.claude_json", return_value=self.fake) as cj, patch.object(runs, "RUN_INLINE", True):
            r = c.post("/api/knowledge/controller/", {"period": "last_n", "n": 5}, format="json")
            self.assertEqual(cj.call_count, 1)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["status"], "done")
        row = r.data["result"]["rows"][0]
        self.assertEqual(row["link"], "/inbox?c=%d" % self.conv.id)
        self.assertTrue(row["items"])
        drafts = KnowledgeItem.objects.filter(source="reviewer")
        self.assertEqual(set(drafts.values_list("status", flat=True)), {"draft"})
        self.assertIn("/inbox?c=%d" % self.conv.id, drafts.get(title="Чи є інструмент у тест-наборі?").internal_note)
        again = c.post("/api/knowledge/controller/", {"period": "yesterday", "estimate": True}, format="json")
        self.assertEqual(again.data["count"], 0)  # той самий чат удруге не оплачуємо

    def test_only_owner_runs(self):
        r = client_of(self.approver).post("/api/knowledge/controller/", {"period": "yesterday"}, format="json")
        self.assertEqual(r.status_code, 403)


# ───────────────────────── публікація в Юлю ─────────────────────────

class PublishTests(Users, TestCase):
    def setUp(self):
        self.make_users()
        self.upd = kitem(audience=["yulia_ig"], title="Які умови доставки?", text="Нова відповідь",
                         external_ids={"chatplace_ig": "ds-1"})
        self.new = kitem(audience=["yulia_ig", "yulia_tiktok"], title="Нове питання", text="Нова")
        self.same = kitem(audience=["yulia_ig"], title="Однакове", text="Так само")
        kitem(audience=["yulia_ig"], status="draft", title="Чернетка", text="не публікується")
        self.remote = [{"id": "ds-1", "question": "Які умови доставки у вас є?", "answer": "Стара"},
                       {"id": "ds-2", "question": "однакове", "answer": "так  само"}]

    def test_preview_then_confirm_with_backup_and_version(self):
        fake, c = FakeMcp(self.remote), client_of(self.owner)
        with patch("apps.knowledge.publisher.default_mcp", return_value=fake), patch.object(runs, "RUN_INLINE", True):
            pv = c.post("/api/knowledge/publish/preview/", {"bot": "ig"}, format="json")
            self.assertEqual(pv.status_code, 200, pv.content)
            self.assertEqual((pv.data["changes"], len(pv.data["add"]), len(pv.data["update"]), pv.data["same"]), (2, 1, 1, 1))
            self.assertEqual(pv.data["update"][0]["old"], "Стара")
            self.assertEqual({n for n, _a in fake.calls}, {"ai_agent_knowledge_base_list"})
            bad = c.post("/api/knowledge/publish/", {"bot": "ig", "fingerprint": "x", "changes": 2}, format="json")
            self.assertEqual(bad.status_code, 409)
            self.assertEqual({n for n, _a in fake.calls}, {"ai_agent_knowledge_base_list"})
            r = c.post("/api/knowledge/publish/", {"bot": "ig", "fingerprint": pv.data["fingerprint"], "changes": 2},
                       format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["status"], "done", r.data)
        names = [n for n, _a in fake.calls]
        self.assertEqual((names.count("ai_agent_knowledge_base_update"), names.count("ai_agent_knowledge_base_add")), (1, 1))
        self.assertNotIn("rule", next(a for n, a in fake.calls if n == "ai_agent_knowledge_base_update"))
        self.assertFalse(any("delete" in n or "global" in n or n == "ai_agent_publish" for n in names))
        run = KnowledgeRun.objects.get(pk=r.data["id"])
        self.assertEqual(run.backup, self.remote)  # бекап бази ChatPlace ДО запису
        self.upd.refresh_from_db()
        self.new.refresh_from_db()
        self.assertEqual(self.upd.external_ids["chatplace_ig_v"], self.upd.version)
        self.assertEqual(self.new.external_ids["chatplace_ig"], "ds-new")
        self.assertTrue(KnowledgeVersion.objects.filter(item=self.new, action="publish").exists())

    def test_plan_changed_between_preview_and_confirm(self):
        fake, c = FakeMcp(self.remote), client_of(self.owner)
        with patch("apps.knowledge.publisher.default_mcp", return_value=fake), patch.object(runs, "RUN_INLINE", True):
            pv = c.post("/api/knowledge/publish/preview/", {"bot": "ig"}, format="json")
            kitem(audience=["yulia_ig"], title="Ще одне", text="Нове затверджене")
            r = c.post("/api/knowledge/publish/", {"bot": "ig", "fingerprint": pv.data["fingerprint"], "changes": 2},
                       format="json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["preview"]["changes"], 3)
        self.assertFalse(any(n != "ai_agent_knowledge_base_list" for n, _a in fake.calls))

    def test_only_owner(self):
        with patch("apps.knowledge.publisher.default_mcp", return_value=FakeMcp(self.remote)):
            self.assertEqual(client_of(self.approver).post("/api/knowledge/publish/preview/", {"bot": "ig"},
                                                           format="json").status_code, 403)
            self.assertEqual(client_of(self.approver).post("/api/knowledge/publish/", {"bot": "ig"},
                                                           format="json").status_code, 403)


# ───────────────────────── попередня перевірка чернеток ─────────────────────────

class PrecheckTests(Users, TestCase):
    def setUp(self):
        self.make_users()
        self.ap = kitem(topic="delivery", title="Які умови доставки у вас є?", text="Новою Поштою")
        self.dup = kitem(status="draft", topic="delivery", title="Які умови доставки у вас є", text="Новою Поштою, так")
        self.flag = kitem(status="draft", topic="delivery", title="Телефон для доставки", text="Пишіть 097 931 21 90")
        self.ok1 = kitem(status="draft", topic="delivery", title="Скільки днів іде посилка до Львова?", text="1–2 дні")
        self.ok2 = kitem(status="draft", topic="delivery", title="Чи можна забрати самовивозом зі складу?", text="Так")
        self.ai = resp(json.dumps({"results": [
            {"id": self.ok1.id, "label": "ready", "reason": "", "ref": None},
            {"id": self.ok2.id, "label": "conflict", "reason": "самовивозу немає", "ref": self.ap.id}]}))

    def run_check(self, user=None):
        with patch(CC, return_value=self.ai) as cc, patch.object(runs, "RUN_INLINE", True):
            r = client_of(user or self.owner).post("/api/knowledge/precheck/", {"topic": "delivery"}, format="json")
        return r, cc

    def test_estimate_is_free_and_code_labels(self):
        with patch(CC) as cc:
            r = client_of(self.editor).post("/api/knowledge/precheck/", {"topic": "delivery", "estimate": True}, format="json")
        cc.assert_not_called()
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.data["drafts"], r.data["code_only"], r.data["ai_items"], r.data["calls"]), (4, 2, 2, 1))
        self.assertGreater(r.data["est_usd"], 0)

    def test_run_labels_nothing_approved_filter_by_label(self):
        r, cc = self.run_check()
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["status"], "done")
        self.assertEqual(cc.call_count, 1)
        labels = dict(KnowledgeCheck.objects.values_list("item_id", "label"))
        self.assertEqual(labels, {self.dup.id: "dup", self.flag.id: "fix", self.ok1.id: "ready", self.ok2.id: "conflict"})
        self.assertEqual(KnowledgeCheck.objects.get(item=self.dup).ref_item_id, self.ap.id)
        self.assertEqual(KnowledgeItem.objects.filter(status="approved").count(), 1)  # нічого не затверджено само
        ids = [x["id"] for x in client_of(self.owner).get("/api/knowledge/items/?status=draft&label=ready").data["results"]]
        self.assertEqual(ids, [self.ok1.id])
        item = client_of(self.owner).get("/api/knowledge/items/%d/" % self.ok2.id).data
        self.assertEqual(item["precheck"]["label"], "conflict")
        # повторний запуск без «перевірити заново» — перевірені не оплачуються вдруге
        with patch(CC) as cc2:
            est = client_of(self.owner).post("/api/knowledge/precheck/", {"topic": "delivery", "estimate": True}, format="json")
        cc2.assert_not_called()
        self.assertEqual(est.data["drafts"], 0)

    def test_permissions(self):
        self.assertEqual(self.run_check(self.editor)[0].status_code, 403)
        self.assertEqual(self.run_check(self.approver)[0].status_code, 201)
        self.assertEqual(client_of(self.approver).post("/api/knowledge/precheck/approve-ready/", {"topic": "delivery"},
                                                       format="json").status_code, 403)

    def test_approve_ready_owner_confirms_count(self):
        self.run_check()
        c = client_of(self.owner)
        self.assertEqual(c.post("/api/knowledge/precheck/approve-ready/", {"topic": "delivery"}, format="json").data["count"], 1)
        self.assertEqual(c.post("/api/knowledge/precheck/approve-ready/", {"topic": "delivery", "expected": 2},
                                format="json").status_code, 409)
        r = c.post("/api/knowledge/precheck/approve-ready/", {"topic": "delivery", "expected": 1}, format="json")
        self.assertEqual(r.data["approved"], 1)
        self.assertEqual(KnowledgeItem.objects.get(pk=self.ok1.pk).status, "approved")
        self.assertEqual(set(KnowledgeItem.objects.filter(pk__in=[self.dup.pk, self.flag.pk, self.ok2.pk])
                             .values_list("status", flat=True)), {"draft"})

    def test_edit_after_check_makes_label_stale(self):
        self.run_check()
        c = client_of(self.owner)
        self.assertEqual(c.patch("/api/knowledge/items/%d/" % self.ok1.id, {"text": "2–3 дні"}, format="json").status_code, 200)
        self.assertEqual(c.post("/api/knowledge/precheck/approve-ready/", {"topic": "delivery"}, format="json").data["count"], 0)
        ids = [x["id"] for x in c.get("/api/knowledge/items/?label=stale").data["results"]]
        self.assertEqual(ids, [self.ok1.id])
        self.assertTrue(c.get("/api/knowledge/items/%d/" % self.ok1.id).data["precheck"]["stale"])
