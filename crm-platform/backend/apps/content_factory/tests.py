"""Контент-завод: етап 0 (посилання, доступ) і етап 1 (питання клієнтів). ШІ підмінено — жодних зовнішніх запитів."""
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.crm.models import AiUsage, Contact
from apps.inbox.models import Channel, Conversation, Message
from apps.inbox.models import MediaLibraryItem
from . import questions as qsvc
from . import telegram as tgsvc
from .models import (ChannelLinkError, ContentChannel, QuestionMention, QuestionSettings, QuestionTopic, TgPost,
                     TgSettings, parse_channel_link)


class ParseLinkTests(SimpleTestCase):
    def test_profiles(self):
        cases = {
            "https://www.instagram.com/dekor_dlia_stin/": ("instagram", "dekor_dlia_stin"),
            "instagram.com/Textuuri?igsh=abc": ("instagram", "textuuri"),
            "https://www.tiktok.com/@Dekor_dlia_stin?lang=uk": ("tiktok", "dekor_dlia_stin"),
            "https://www.youtube.com/@Wallcov/shorts": ("youtube", "wallcov"),
            "https://youtube.com/channel/UC123abc": ("youtube", "channel/UC123abc"),
            "https://t.me/wallcovpro": ("telegram", "wallcovpro"),
            "t.me/s/wallcovpro": ("telegram", "wallcovpro"),
        }
        for link, (platform, handle) in cases.items():
            with self.subTest(link=link):
                p, h, _url = parse_channel_link(link)
                self.assertEqual((p, h), (platform, handle))

    def test_at_name_needs_platform(self):
        self.assertEqual(parse_channel_link("@wallcovpro", "telegram")[:2], ("telegram", "wallcovpro"))
        with self.assertRaises(ChannelLinkError):
            parse_channel_link("@wallcovpro")

    def test_posts_and_invites_rejected(self):
        for link in ("https://www.instagram.com/reel/DWLrZmljCcq/", "https://vm.tiktok.com/ZMabc/",
                     "https://youtu.be/abc", "https://www.youtube.com/watch?v=abc", "https://t.me/+AbCd",
                     "https://facebook.com/wallcov", ""):
            with self.subTest(link=link), self.assertRaises(ChannelLinkError):
                parse_channel_link(link)


class AccessTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="cf-owner", password="x", is_superuser=True, is_staff=True)
        self.manager = User.objects.create_user(username="cf-manager", password="x")
        self.trusted = User.objects.create_user(username="cf-trusted", password="x",
                                                extra_permissions=["content_factory.access"])

    def _client(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def test_manager_forbidden(self):
        c = self._client(self.manager)
        self.assertEqual(c.get("/api/content-factory/channels/").status_code, 403)
        self.assertEqual(c.post("/api/content-factory/channels/", {"link": "t.me/x1"}, format="json").status_code, 403)
        self.assertFalse(ContentChannel.objects.exists())

    def test_trusted_with_permission_allowed(self):
        self.assertEqual(self._client(self.trusted).get("/api/content-factory/overview/").status_code, 200)

    def test_owner_add_duplicate_edit_delete(self):
        c = self._client(self.owner)
        r = c.post("/api/content-factory/channels/",
                   {"link": "https://www.instagram.com/dekor_dlia_stin/", "role": "own"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        pk = r.json()["id"]
        dup = c.post("/api/content-factory/channels/", {"link": "instagram.com/DEKOR_DLIA_STIN"}, format="json")
        self.assertEqual(dup.status_code, 409)
        bad = c.post("/api/content-factory/channels/", {"link": "https://www.instagram.com/p/xyz/"}, format="json")
        self.assertEqual(bad.status_code, 400)
        self.assertIn("пост", bad.json()["error"])
        r = c.patch(f"/api/content-factory/channels/{pk}/", {"note": "основний", "is_active": False}, format="json")
        self.assertEqual((r.json()["note"], r.json()["is_active"]), ("основний", False))
        ov = c.get("/api/content-factory/overview/").json()
        self.assertEqual(ov["channels_total"], 0)  # вимкнена не рахується
        self.assertEqual(c.delete(f"/api/content-factory/channels/{pk}/").status_code, 204)


# ── Етап 1: питання клієнтів ─────────────────────────────────────────────────────────────────


class QuestionFilterTests(SimpleTestCase):
    def test_filter_without_ai(self):
        for t in ("Скільки коштує галатея на 12 квадратів", "Чи можна мити стіну з шовком?", "А есть фото этого набора?"):
            self.assertTrue(qsvc.is_question(t), t)
        for t in ("Дякую!", "ок", "+", "Добрий день", "Надсилаю фото стіни", "?" * 3):
            self.assertFalse(qsvc.is_question(t), t)

    def test_clean_hides_contacts(self):
        c = qsvc.clean("Скільки коштує? мій номер +380 99 123 45 67, пошта a.b@gmail.com https://x.y/z")
        self.assertNotIn("123", c)
        self.assertNotIn("gmail", c)
        self.assertNotIn("https", c)


class QuestionRunTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="q-owner", password="x", is_superuser=True, is_staff=True)
        self.manager = User.objects.create_user(username="q-manager", password="x")
        ch = Channel.objects.create(kind="instagram", name="IG test", config={})
        conv = Conversation.objects.create(channel=ch, contact=Contact.objects.create(first_name="Тест"), external_chat_id="t1")
        self.msgs = [Message.objects.create(conversation=conv, direction="in", text=t) for t in (
            "Скільки коштує Галатея на кімнату?", "скільки коштує галатея на кімнату", "Чи можна мити шовк?",
            "Дякую!", "А доставка Новою поштою є?", "Як наносити без майстра?", "Чи буде видно шви?")]
        Message.objects.create(conversation=conv, direction="out", text="Скільки у вас метрів?")

    def _fake(self, calls):
        def call(prompt):
            calls.append(prompt)
            AiUsage.objects.create(source=qsvc.SOURCE, model="claude-haiku-4-5", cost_usd=0.01)
            return {"a": [[1, "n1"], [2, "n2"], [3, "n3"], [4, "n4"], [5, "n5"]],
                    "new": [{"key": f"n{i}", "title": f"Тема {i}", "material": ""} for i in range(1, 6)]}
        return call

    def test_disabled_no_ai(self):
        calls = []
        r = qsvc.run(call=self._fake(calls))
        self.assertEqual(calls, [])
        self.assertIn("Вимкнено", r["note"])
        self.assertEqual(QuestionSettings.get().last_message_id, 0)  # питання дочекаються вмикання

    def test_dry_run_counts_and_dedups(self):
        r = qsvc.run(dry_run=True)
        self.assertEqual(r["questions"], 5)  # дубль склеєно, «Дякую» і вихідне — відсіяно
        self.assertGreater(r["estimate_usd"], 0)

    def test_run_once_then_nothing_to_pay(self):
        s = QuestionSettings.get(); s.enabled = True; s.save()
        calls = []
        r = qsvc.run(call=self._fake(calls))
        self.assertEqual(len(calls), 1)
        self.assertEqual(r["assigned"], 6)  # 5 тем, дубль — друга згадка тієї ж теми
        self.assertEqual(QuestionTopic.objects.count(), 5)
        self.assertEqual(QuestionSettings.get().last_message_id, Message.objects.filter(direction="in").latest("id").id)
        r2 = qsvc.run(call=self._fake(calls))
        self.assertEqual(len(calls), 1)  # другий прохід — жодного платного виклику
        self.assertIn("менше", r2["note"])

    def test_budget_cap_stops_before_call(self):
        s = QuestionSettings.get(); s.enabled = True; s.monthly_budget_usd = 1; s.save()
        AiUsage.objects.create(source=qsvc.SOURCE, model="claude-haiku-4-5", cost_usd=1.0)
        calls = []
        r = qsvc.run(call=self._fake(calls))
        self.assertEqual(calls, [])
        self.assertIn("ліміту", r["note"])
        self.assertFalse(QuestionMention.objects.exists())

    def test_ai_error_keeps_pointer(self):
        s = QuestionSettings.get(); s.enabled = True; s.save()
        def boom(prompt):
            raise RuntimeError("мережа")
        r = qsvc.run(call=boom)
        self.assertIn("Помилка ШІ", r["note"])
        self.assertEqual(QuestionSettings.get().last_message_id, self.msgs[0].id - 1)

    def test_api_access(self):
        c = APIClient(); c.force_authenticate(self.manager)
        self.assertEqual(c.get("/api/content-factory/questions/").status_code, 403)
        c.force_authenticate(self.owner)
        r = c.get("/api/content-factory/questions/")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["settings"]["enabled"])
        self.assertEqual(r.json()["settings"]["pending"]["questions"], 5)
        self.assertEqual(c.patch("/api/content-factory/questions/settings/", {"monthly_budget_usd": 999},
                                 format="json").status_code, 400)
        r = c.patch("/api/content-factory/questions/settings/", {"model": "claude-haiku-4-5"}, format="json")
        self.assertEqual(r.json()["model"], "claude-haiku-4-5")


# ── Етап 2: Telegram-автопілот ────────────────────────────────────────────────────────────────
class TelegramTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="tg-owner", password="x", is_superuser=True, is_staff=True)
        self.trusted = User.objects.create_user(username="tg-trusted", password="x",
                                                extra_permissions=["content_factory.access"])
        now = timezone.now()
        self.hot = QuestionTopic.objects.create(title="Чи можна мити шовк", material="Мокрий шовк", last_seen=now)
        self.cold = QuestionTopic.objects.create(title="Де магазин", last_seen=now)
        for i in range(5):
            QuestionMention.objects.create(topic=self.hot, message_id=1000 + i, asked_at=now)
        QuestionMention.objects.create(topic=self.cold, message_id=2000, asked_at=now)
        for i in range(5):
            MediaLibraryItem.objects.create(title=f"Шовк реальний {i}", material="Мокрий шовк",
                                            tags="інтер'єр реальне фото", kind="image")
        MediaLibraryItem.objects.create(title="AI інтерʼєр", material="Мокрий шовк", tags="інтер'єр", kind="image")
        self.calls = []

    def _fake(self, prompt):
        self.calls.append(prompt)
        AiUsage.objects.create(source=tgsvc.SOURCE, model="claude-sonnet-4-6", cost_usd=0.01)
        return {"title": "Миття шовку", "text": "Шовк можна мити?\n\nТак — мʼякою губкою.", "material": "Мокрий шовк",
                "checks": ["можна мити — перевірити"]}

    def test_hot_topic_real_photos_cta(self):
        p = tgsvc.generate(call=self._fake)
        self.assertEqual(p.topic, self.hot)
        self.assertIn("ig.me/m/dekor_dlia_stin", p.text)
        self.assertEqual(len(p.photo_ids), 3)
        ai_ids = set(MediaLibraryItem.objects.filter(title="AI інтерʼєр").values_list("id", flat=True))
        self.assertFalse(ai_ids & set(p.photo_ids))  # лише реальні фото
        self.assertIn("Чи можна мити шовк", self.calls[0])

    def test_topic_not_repeated_and_rejected_frees_it(self):
        p = tgsvc.generate(call=self._fake)
        self.assertEqual(tgsvc.next_topic(), self.cold)
        p.status = TgPost.Status.REJECTED
        p.save()
        self.assertEqual(tgsvc.next_topic(), self.hot)

    def test_budget_blocks_before_call(self):
        s = TgSettings.get()
        s.monthly_budget_usd = 0.01
        s.save()
        AiUsage.objects.create(source=tgsvc.SOURCE, model="claude-sonnet-4-6", cost_usd=0.01)
        with self.assertRaises(tgsvc.BudgetError):
            tgsvc.generate(call=self._fake)
        self.assertEqual(self.calls, [])

    def test_api_owner_and_trusted(self):
        c = APIClient()
        c.force_authenticate(self.trusted)
        self.assertEqual(c.get("/api/content-factory/telegram/").status_code, 200)
        self.assertEqual(c.post("/api/content-factory/telegram/draft/").status_code, 403)  # платне — лише власник
        p = tgsvc.generate(call=self._fake)
        old = list(p.photo_ids)
        r = c.post(f"/api/content-factory/telegram/posts/{p.id}/photos/")
        self.assertEqual(r.status_code, 200)
        self.assertNotEqual(sorted(x["id"] for x in r.json()["photos"]), sorted(old))
        r = c.patch(f"/api/content-factory/telegram/posts/{p.id}/", {"status": "approved", "text": "Новий текст"},
                    format="json")
        self.assertEqual((r.json()["status"], r.json()["text"]), ("approved", "Новий текст"))
        self.assertEqual(c.patch(f"/api/content-factory/telegram/posts/{p.id}/", {"status": "published"},
                                 format="json").status_code, 400)
        c.force_authenticate(self.owner)
        r = c.get("/api/content-factory/telegram/").json()
        self.assertFalse(r["settings"]["publish_enabled"])
        self.assertEqual(r["next_topic"]["id"], self.cold.id)
