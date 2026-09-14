"""Єдина база знань ІІ (14.09.2026). Лише ізольована тестова БД; Claude, ChatPlace і мережа підмінені —
жодних зовнішніх запитів, жодних повідомлень клієнтам."""
import io
import json
import os
import tempfile
from datetime import datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import PERMISSION_CHOICES, Role, User
from apps.crm.models import KbEntry
from apps.inbox.models import Channel, Conversation, Message
from apps.warehouse.models import Product

from . import catalog
from .fallbacks import compose_style
from .models import KnowledgeItem, KnowledgeReviewLog, KnowledgeSettings, KnowledgeVersion
from .reader import context_for, select


def item(**kw):
    d = dict(kind="qa", topic="other", audience=["rop_hint"], status="approved", title="Питання", text="Відповідь")
    d.update(kw)
    return KnowledgeItem.objects.create(**d)


class ReaderTests(TestCase):
    def setUp(self):
        self.p = Product.objects.create(name="Galateya Silver тест", price=1000, unit="кг", consumption_per_m2="0.15")
        self.ok = item(title="Скільки коштує доставка?", text="МАРКЕР-ДОСТАВКА безкоштовно від 6000", topic="delivery")
        self.rule = item(kind="rule", title="Не вигадувати", text="МАРКЕР-ПРАВИЛО", topic="tone")
        self.draft = item(status="draft", text="МАРКЕР-ЧЕРНЕТКА")
        self.arch = item(status="archived", text="МАРКЕР-АРХІВ")
        self.other = item(audience=["compose_assist"], text="МАРКЕР-ІНШИЙ-АГЕНТ")

    def test_only_approved_for_this_agent(self):
        self.assertEqual({i.id for i in select("rop_hint")}, {self.ok.id, self.rule.id})
        txt = context_for("rop_hint", with_prices=False)
        self.assertIn("МАРКЕР-ДОСТАВКА", txt)
        self.assertIn("МАРКЕР-ПРАВИЛО", txt)
        for bad in ("МАРКЕР-ЧЕРНЕТКА", "МАРКЕР-АРХІВ", "МАРКЕР-ІНШИЙ-АГЕНТ"):
            self.assertNotIn(bad, txt)
        self.assertEqual(select("unknown_agent"), [])

    def test_rules_first_then_matching_the_conversation(self):
        other = item(title="Чи підходить Галатея для кухні?", text="Так", topic="materials")
        got = [i.id for i in select("rop_hint", query="а доставка скільки коштує?", limit=5)]
        self.assertEqual(got[:2], [self.rule.id, self.ok.id])
        self.assertNotIn(other.id, got)

    def test_prices_injected_from_catalog_at_read_time(self):
        item(title="Ціна Галатеї", text="Галатея {price:%d}, на стіну {m2:%d}, інша {price:999999}" % (self.p.id, self.p.id))
        txt = context_for("rop_hint", with_prices=False)
        self.assertIn("1000 грн/кг", txt)
        self.assertIn("150 грн/м²", txt)
        self.assertIn(catalog.UNKNOWN, txt)
        Product.objects.filter(pk=self.p.pk).update(price=1200)
        txt = context_for("rop_hint", with_prices=False)
        self.assertIn("1200 грн/кг", txt)
        self.assertIn("180 грн/м²", txt)

    def test_prices_for_material_mentioned_in_conversation(self):
        txt = context_for("rop_hint", query="скільки коштує галатея?")
        self.assertIn("Ціни з каталогу CRM", txt)
        self.assertIn("Galateya Silver тест — 1000 грн/кг", txt)

    def test_empty_base_returns_empty(self):
        KnowledgeItem.objects.all().delete()
        self.assertEqual(context_for("funnel_agent", with_prices=False), "")
        self.assertEqual(context_for("rop_hint", query="привіт"), "")


class FallbackTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser(username="kb-owner-fb", password="x")
        self.api = APIClient()
        self.api.force_authenticate(self.owner)
        ch = Channel.objects.create(kind="telegram", name="TG kb test", config={})
        self.conv = Conversation.objects.create(channel=ch, external_chat_id="kb-test-1")
        Message.objects.create(conversation=self.conv, direction="in", text="Яка передоплата на накладений платіж?",
                               external_id="kb-in-1")

    def test_compose_style_uses_builtin_text_when_base_empty(self):
        s = compose_style()
        self.assertIn("до 5 000 грн — 20%", s)
        self.assertIn("40×40", s)
        self.assertIn("096 419 18 90", s)
        self.assertNotIn("мін 300 грн", s)
        self.assertNotIn("Мокрий шовк 147", s)

    def test_compose_style_takes_topic_from_base_once_approved(self):
        item(kind="rule", topic="payment", audience=["compose_assist"], title="Оплата", text="МАРКЕР-ОПЛАТА-З-БАЗИ")
        s = compose_style()
        self.assertIn("МАРКЕР-ОПЛАТА-З-БАЗИ", s)
        self.assertNotIn("до 5 000 грн — 20%", s)   # тема «Оплата» тепер з бази
        self.assertIn("40×40", s)                    # «Тест-набори» — ще вбудований текст

    @patch("apps.crm.ai.claude_json", return_value={"text": "ok"})
    def test_ai_compose_endpoint_gets_new_prepayment_rule(self, cj):
        r = self.api.post("/api/conversations/ai_compose/", {"draft": "передоплата 300 грн", "conversation_id": self.conv.id},
                          format="json")
        self.assertEqual(r.status_code, 200, r.content)
        system, prompt = cj.call_args.kwargs["system"], cj.call_args.args[0]
        self.assertIn("до 5 000 грн — 20%", system)
        self.assertNotIn("мін 500 грн передоплата", system)
        self.assertNotIn("ДОВІДКА З БАЗИ ЗНАНЬ", prompt)  # порожня база → запит як раніше

    @patch("apps.crm.ai.claude_json", return_value={"text": "ok"})
    def test_ai_compose_extra_goes_to_prompt_system_stays_stable(self, cj):
        before = compose_style()
        item(topic="objections", audience=["compose_assist"], title="Чи передоплата 300 грн правильна?", text="МАРКЕР-ДОВІДКА")
        self.assertEqual(compose_style(), before)  # системний текст не змінився → кеш працює
        r = self.api.post("/api/conversations/ai_compose/", {"draft": "передоплата 300 грн", "conversation_id": self.conv.id},
                          format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("МАРКЕР-ДОВІДКА", cj.call_args.args[0])
        self.assertNotIn("МАРКЕР-ДОВІДКА", cj.call_args.kwargs["system"])

    @patch("apps.crm.ai.claude_json", return_value={"context": "", "points": [], "suggestion": "ok"})
    def test_ai_reply_prompt_gets_knowledge(self, cj):
        item(topic="objections", audience=["rop_hint"], title="Яка передоплата на накладений платіж?", text="МАРКЕР-РОП")
        r = self.api.post("/api/conversations/%d/ai_reply/" % self.conv.id, {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        prompt, system = cj.call_args.args[0], cj.call_args.kwargs["system"]
        self.assertIn("БАЗА ЗНАНЬ WALLCOV", prompt)
        self.assertIn("до 5 000 грн — 20%", prompt)
        self.assertIn("МАРКЕР-РОП", prompt)
        self.assertIn("Для якої кімнати підбираєте?", system)
        self.assertNotIn("Google Sheet", system)

    def test_funnel_agent_reads_only_approved(self):
        from apps.crm.agent import build_system
        ent = SimpleNamespace(funnel_id=None)
        self.assertNotIn("База знань Wallcov", build_system(ent, "lead"))
        item(status="draft", audience=["funnel_agent"], kind="rule", title="x", text="МАРКЕР-АГЕНТ-ЧЕРНЕТКА")
        self.assertNotIn("МАРКЕР-АГЕНТ-ЧЕРНЕТКА", build_system(ent, "lead"))
        item(audience=["funnel_agent"], kind="rule", title="Правило", text="МАРКЕР-АГЕНТ")
        self.assertIn("МАРКЕР-АГЕНТ", build_system(ent, "lead"))

    def test_coach_prompt_text_fixes(self):
        from apps.crm.coach_prompt import COACH_SYSTEM
        self.assertNotIn("Google Sheet", COACH_SYSTEM)
        self.assertNotIn("+115 грн. Оформлюємо?", COACH_SYSTEM)
        self.assertIn("**Ціни** — тільки з каталогу CRM", COACH_SYSTEM)


class ApprovalTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser(username="kb-owner", password="x")
        self.editor = User.objects.create_user(
            username="kb-editor", role=Role.objects.create(name="kb-editor-role", permissions=["knowledge.edit"]))
        self.approver = User.objects.create_user(
            username="kb-approver", role=Role.objects.create(name="kb-approver-role", permissions=["knowledge.approve"]))
        self.plain = User.objects.create_user(username="kb-plain")

    def c(self, u):
        cl = APIClient()
        cl.force_authenticate(u)
        return cl

    def test_permission_codes_registered(self):
        self.assertTrue({"knowledge.view", "knowledge.edit", "knowledge.approve"} <= {c for c, _ in PERMISSION_CHOICES})

    def test_user_without_rights_has_no_access(self):
        self.assertEqual(self.c(self.plain).get("/api/knowledge/items/").status_code, 403)
        self.assertEqual(self.c(self.plain).get("/api/knowledge/meta/").status_code, 403)

    def test_editor_writes_drafts_only_approver_approves(self):
        ed, ap = self.c(self.editor), self.c(self.approver)
        r = ed.post("/api/knowledge/items/", {"kind": "qa", "topic": "delivery", "audience": ["rop_hint"], "title": "Q",
                                              "text": "A", "status": "approved"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["status"], "draft")
        iid = r.data["id"]
        self.assertEqual(ed.post("/api/knowledge/items/%d/approve/" % iid).status_code, 403)
        self.assertEqual(select("rop_hint"), [])  # чернетку агенти не бачать
        r = ed.patch("/api/knowledge/items/%d/" % iid, {"text": "A2"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["version"], 2)
        r = ap.post("/api/knowledge/items/%d/approve/" % iid, {"note": "ок"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        it = KnowledgeItem.objects.get(pk=iid)
        self.assertEqual((it.status, it.approved_by_id), ("approved", self.approver.id))
        self.assertIsNotNone(it.approved_at)
        self.assertEqual(ed.patch("/api/knowledge/items/%d/" % iid, {"text": "X"}, format="json").status_code, 403)
        self.assertEqual(ed.delete("/api/knowledge/items/%d/" % iid).status_code, 403)
        r = ed.post("/api/knowledge/items/%d/propose/" % iid, {"text": "A3"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        new_id = r.data["id"]
        self.assertEqual((r.data["status"], r.data["replaces"]), ("draft", iid))
        self.assertEqual([i.text for i in select("rop_hint")], ["A2"])  # поки не затверджено — агенти бачать старе
        self.assertEqual(ap.post("/api/knowledge/items/%d/approve/" % new_id).status_code, 200)
        self.assertEqual(KnowledgeItem.objects.get(pk=iid).status, "archived")
        self.assertEqual([i.text for i in select("rop_hint")], ["A3"])
        actions = set(KnowledgeVersion.objects.filter(item_id=iid).values_list("action", flat=True))
        self.assertTrue({"create", "edit", "approve", "archive"} <= actions)

    def test_owner_approves_reviewer_switch_owner_only(self):
        it = item(status="draft")
        self.assertEqual(self.c(self.owner).post("/api/knowledge/items/%d/approve/" % it.id).status_code, 200)
        self.assertEqual(self.c(self.approver).patch("/api/knowledge/settings/", {"reviewer_enabled": True},
                                                     format="json").status_code, 403)
        self.assertFalse(KnowledgeSettings.get().reviewer_enabled)
        r = self.c(self.owner).patch("/api/knowledge/settings/", {"reviewer_enabled": True}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(KnowledgeSettings.get().reviewer_enabled)
        meta = self.c(self.editor).get("/api/knowledge/meta/").data
        self.assertTrue(meta["can_edit"])
        self.assertFalse(meta["can_approve"])

    def test_bulk_approve_only_approver(self):
        a, b = item(status="draft"), item(status="draft")
        self.assertEqual(self.c(self.editor).post("/api/knowledge/items/bulk/", {"ids": [a.id, b.id], "action": "approve"},
                                                  format="json").status_code, 403)
        r = self.c(self.owner).post("/api/knowledge/items/bulk/", {"ids": [a.id, b.id], "action": "approve"}, format="json")
        self.assertEqual(r.data["done"], 2)

    def test_preview_for_every_agent(self):
        item(audience=[c for c, _ in KnowledgeItem.AGENTS], text="МАРКЕР-УСІМ")
        for agent, _ in KnowledgeItem.AGENTS:
            r = self.c(self.owner).get("/api/knowledge/preview/", {"agent": agent, "q": "доставка"})
            self.assertEqual(r.status_code, 200, (agent, r.content))
            self.assertIn("text", r.data)


class ImportTests(TestCase):
    def setUp(self):
        KbEntry.objects.create(id=227, ext_id="33ce145e-test", question="Які умови доставки у вас є?",
                               answer="Доставляємо Новою Поштою на вантажне відділення.", source="chatplace")
        KbEntry.objects.create(id=731, ext_id="b6cefa55-test", question="💬 +380 97 931 21 90",
                               answer="Пишіть: 097 931 21 90, t.me/wallcovpidtrimka", source="chatplace")
        KbEntry.objects.create(id=5, ext_id="x5", question="Чи підходить Galateya для комерційних приміщень?",
                               answer="Так, підходить.", source="chatplace", client_chat_count=7)
        KbEntry.objects.create(id=9, ext_id="x9", question="Порожня", answer="", source="chatplace")

    def run_cmd(self, *args):
        out = io.StringIO()
        call_command("kb_import_ai_center", *args, stdout=out)
        return out.getvalue()

    def test_dry_run_writes_nothing_live_is_idempotent(self):
        out = self.run_cmd()
        self.assertIn("ПРОБНИЙ ЗАПУСК", out)
        self.assertIn("[227]", out)
        self.assertEqual(KnowledgeItem.objects.count(), 0)
        self.run_cmd("--live")
        n = KnowledgeItem.objects.count()
        self.assertEqual(n, 3 + 12)
        d = KnowledgeItem.objects.get(source_ref="kbentry:227")
        self.assertEqual((d.status, d.topic), ("approved", "delivery"))
        self.assertEqual(d.external_ids, {"chatplace_ig": "33ce145e-test"})
        self.assertTrue(KnowledgeVersion.objects.filter(item=d, action="import").exists())
        bad = KnowledgeItem.objects.get(source_ref="kbentry:731")
        self.assertEqual((bad.status, bad.topic), ("draft", "contacts"))
        self.assertIn("⚠️", bad.internal_note)
        g = KnowledgeItem.objects.get(source_ref="kbentry:5")
        self.assertEqual((g.status, g.topic, g.popularity), ("draft", "materials", 7))
        cod = KnowledgeItem.objects.get(source_ref="code:cod_prepay")
        self.assertEqual(cod.status, "draft")
        self.assertIn("до 5 000 грн — 20%", cod.text)
        self.assertIn("funnel_agent", cod.audience)
        self.run_cmd("--live")
        self.assertEqual(KnowledgeItem.objects.count(), n)
        self.assertIn("Буде створено: 0 записів старої бази + 0", self.run_cmd())

    def test_all_draft_flag(self):
        self.run_cmd("--live", "--all-draft", "--no-seeds")
        self.assertEqual(KnowledgeItem.objects.get(source_ref="kbentry:227").status, "draft")
        self.assertFalse(KnowledgeItem.objects.filter(source="code").exists())


class ReviewerTests(TestCase):
    def setUp(self):
        self.day = timezone.localdate() - timedelta(days=1)
        ch = Channel.objects.create(kind="instagram", name="IG kb test", config={})
        self.conv = Conversation.objects.create(channel=ch, external_chat_id="kb-rev-1", status="closed")
        Message.objects.create(conversation=self.conv, direction="in", text="Що входить у тест-набір?", external_id="r1")
        Message.objects.create(conversation=self.conv, direction="out",
                               text="У тест-наборі вже є все потрібне для нанесення. Оформлюємо?", external_id="r2")
        noon = timezone.make_aware(datetime.combine(self.day, time(12, 0)))
        Conversation.objects.filter(pk=self.conv.pk).update(last_message_at=noon)
        self.approved = item(audience=["analyst", "rop_hint"], title="Склад тест-набору", text="Інструмент не входить",
                             topic="test_sets")

    def test_disabled_by_default_no_ai(self):
        with patch("apps.crm.ai.claude_json") as cj:
            out = io.StringIO()
            call_command("kb_review_daily", stdout=out)
        self.assertIn("ВИМКНЕНИЙ", out.getvalue())
        cj.assert_not_called()
        self.assertFalse(KnowledgeItem.objects.filter(source="reviewer").exists())

    def test_dry_run_code_checks_without_ai(self):
        with patch("apps.crm.ai.claude_json") as cj:
            out = io.StringIO()
            call_command("kb_review_daily", "--dry", "--date", self.day.isoformat(), stdout=out)
        cj.assert_not_called()
        txt = out.getvalue()
        self.assertIn("інструмент входить у тест-набір", txt)
        self.assertIn("закрите питання", txt)
        self.assertFalse(KnowledgeItem.objects.filter(source="reviewer").exists())

    def test_enabled_creates_only_drafts_with_dialog_link(self):
        # 14.09 (ai-kb2): ІІ-перевірка — лише ручний запуск Олега (runs.run_controller), команда ІІ не викликає.
        from . import runs
        from .models import KnowledgeRun
        fake = {"findings": [{"type": "contradiction", "who": "ai", "quote": "вже є все потрібне",
                              "problem": "Інструмент не входить", "topic": "test_sets",
                              "suggested_title": "Чи є інструмент у тест-наборі?",
                              "suggested_text": "Ні, інструмент купується окремо."}]}
        with patch("apps.crm.ai.claude_json", return_value=fake) as cj, patch.object(runs, "RUN_INLINE", True):
            runs.spawn(KnowledgeRun.objects.create(kind="controller", params={"conversation_ids": [self.conv.id]}),
                       runs.run_controller)
            self.assertEqual(cj.call_count, 1)
            runs.spawn(KnowledgeRun.objects.create(kind="controller", params={"conversation_ids": [self.conv.id]}),
                       runs.run_controller)
            self.assertEqual(cj.call_count, 1)  # той самий чат удруге не оплачуємо
        drafts = KnowledgeItem.objects.filter(source="reviewer")
        self.assertTrue(drafts.exists())
        self.assertEqual(set(drafts.values_list("status", flat=True)), {"draft"})
        ai_item = drafts.get(title="Чи є інструмент у тест-наборі?")
        self.assertEqual(ai_item.evidence["conversation_id"], self.conv.id)
        self.assertIn("/inbox?c=%d" % self.conv.id, ai_item.internal_note)
        self.assertTrue(drafts.filter(title__startswith="⚠️").exists())  # підсумок перевірки кодом
        self.approved.refresh_from_db()
        self.assertEqual((self.approved.status, self.approved.text), ("approved", "Інструмент не входить"))
        self.assertEqual(KnowledgeReviewLog.objects.filter(conversation_id=self.conv.id).count(), 1)


class FakeMcp:
    def __init__(self, remote):
        self.remote, self.calls = remote, []

    def __call__(self, name, args):
        self.calls.append((name, args))
        if name == "ai_agent_knowledge_base_list":
            return {"items": self.remote if not args.get("offset") else []}
        if name == "ai_agent_knowledge_base_add":
            return {"id": "ds-new"}
        return {"success": True}


class PublisherTests(TestCase):
    def setUp(self):
        self.upd = item(audience=["yulia_ig"], title="Які умови доставки?", text="Нова відповідь",
                        external_ids={"chatplace_ig": "ds-1"})
        self.new = item(audience=["yulia_ig", "yulia_tiktok"], title="Нове питання", text="Нова")
        self.same = item(audience=["yulia_ig"], title="Однакове", text="Так само")
        item(audience=["yulia_ig"], kind="rule", title="Правило", text="не публікується")
        item(audience=["yulia_ig"], status="draft", title="Чернетка", text="не публікується")
        item(audience=["compose_assist"], title="Лише ✨", text="не публікується")
        self.remote = [{"id": "ds-1", "question": "Які умови доставки у вас є?", "answer": "Стара"},
                       {"id": "ds-2", "question": "однакове", "answer": "так  само"}]

    def test_dry_run_only_reads(self):
        fake = FakeMcp(self.remote)
        with patch("apps.knowledge.publisher.default_mcp", return_value=fake):
            out = io.StringIO()
            call_command("kb_publish_chatplace", "--bot", "ig", stdout=out)
        self.assertEqual({c[0] for c in fake.calls}, {"ai_agent_knowledge_base_list"})
        txt = out.getvalue()
        self.assertIn("без змін: 1 · оновити: 1 · додати: 1", txt)
        self.assertIn("--confirm 2", txt)

    def test_live_needs_exact_confirm_then_writes(self):
        fake, tmp = FakeMcp(self.remote), tempfile.mkdtemp()
        with patch("apps.knowledge.publisher.default_mcp", return_value=fake):
            with self.assertRaises(CommandError):
                call_command("kb_publish_chatplace", "--bot", "ig", "--live", "--confirm", "5", "--backup-dir", tmp,
                             stdout=io.StringIO())
            self.assertEqual({c[0] for c in fake.calls}, {"ai_agent_knowledge_base_list"})
            call_command("kb_publish_chatplace", "--bot", "ig", "--live", "--confirm", "2", "--backup-dir", tmp,
                         stdout=io.StringIO())
        names = [c[0] for c in fake.calls]
        self.assertEqual(names.count("ai_agent_knowledge_base_update"), 1)
        self.assertEqual(names.count("ai_agent_knowledge_base_add"), 1)
        upd = next(a for n, a in fake.calls if n == "ai_agent_knowledge_base_update")
        self.assertEqual(upd["datasetId"], "ds-1")
        self.assertNotIn("rule", upd)
        self.new.refresh_from_db()
        self.same.refresh_from_db()
        self.assertEqual(self.new.external_ids.get("chatplace_ig"), "ds-new")
        self.assertEqual(self.same.external_ids.get("chatplace_ig"), "ds-2")
        self.assertTrue(any(f.startswith("kb_publish_backup_ig_") for f in os.listdir(tmp)))

    def test_crm_copy_source_does_not_touch_chatplace(self):
        KbEntry.objects.create(ext_id="ds-1", question="Які умови доставки у вас є?", answer="Стара", source="chatplace")
        with patch("apps.knowledge.publisher.default_mcp") as dm:
            out = io.StringIO()
            call_command("kb_publish_chatplace", "--bot", "ig", "--source", "crm-copy", stdout=out)
        dm.assert_not_called()
        self.assertIn("оновити: 1", out.getvalue())


class WebchatSellerUrlTests(TestCase):
    def setUp(self):
        ch = Channel.objects.create(kind="web", name="Web kb test", config={"web_chat": True})
        self.conv = Conversation.objects.create(channel=ch, external_chat_id="wallcovdliastin.com.ua:kbtest")
        self.msg = Message.objects.create(conversation=self.conv, direction="in", text="Скільки коштує шовк?",
                                          external_id="web-in:kb1")

    @override_settings(WEBCHAT_SELLER_URL="")
    def test_no_url_means_no_network_and_instant_handoff(self):
        from apps.inbox.webchat import _ai_reply
        with patch("apps.inbox.webchat.urllib.request.urlopen") as uo:
            m = _ai_reply(self.conv, self.msg)
        uo.assert_not_called()
        self.assertIn("передала питання менеджеру", m.text)

    @override_settings(WEBCHAT_SELLER_URL="http://10.8.0.1:8001/seller", WEBCHAT_SELLER_TOKEN="t-test")
    def test_url_and_token_from_settings(self):
        from apps.inbox.webchat import _ai_reply
        resp = MagicMock()
        resp.read.return_value = json.dumps({"answer": "Шовк від 162 грн/м²", "confidence": 0.9}).encode()
        cm = MagicMock()
        cm.__enter__.return_value = resp
        with patch("apps.inbox.webchat.urllib.request.urlopen", return_value=cm) as uo:
            m = _ai_reply(self.conv, self.msg)
        req = uo.call_args.args[0]
        self.assertEqual(req.full_url, "http://10.8.0.1:8001/seller")
        self.assertEqual(req.get_header("X-api-token"), "t-test")
        self.assertEqual(m.text, "Шовк від 162 грн/м²")
