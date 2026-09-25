"""Контент-завод: етап 0 (посилання, доступ) і етап 1 (питання клієнтів). ШІ підмінено — жодних зовнішніх запитів."""
from datetime import timedelta
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.crm.models import AiUsage, Contact
from apps.inbox.models import Channel, Conversation, Message
from apps.inbox.models import MediaLibraryItem, SharedLink
from . import questions as qsvc
from . import telegram as tgsvc
from . import analyst as ansvc
from .models import ReelStyle as ReelStyleModel
from .models import (AnalystReport, AnalystSettings, ChannelLinkError, ContentChannel, DriveFolder, FeedItem,
                     QuestionMention, QuestionSettings, QuestionTopic, SourceAsset, SourceChat, TgPost, TgSettings,
                     parse_channel_link)


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
        with patch.dict("os.environ", {"TG_CONTENT_BOT_TOKEN": ""}):
            r = c.get("/api/content-factory/telegram/").json()
        self.assertFalse(r["settings"]["publish_enabled"])  # без токена бота публікація недоступна
        self.assertEqual(r["next_topic"]["id"], self.cold.id)


# ── Публікація і план (Telegram підмінено — жодних реальних повідомлень) ─────────────────────────

class PublishTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="pb-owner", password="x", is_superuser=True, is_staff=True)
        self.trusted = User.objects.create_user(username="pb-trusted", password="x",
                                                extra_permissions=["content_factory.access"])
        self.photos = []
        for i in range(3):
            f = SharedLink.objects.create(token=f"tok{i}xxxxxxxxxxxx", filename=f"p{i}.jpg", content_type="image/jpeg", data=b"img")
            self.photos.append(MediaLibraryItem.objects.create(title=f"p{i}", material="Галатея", kind="image",
                                                               tags="реальне фото", file=f).id)
        self.calls = []
        self.env = patch.dict("os.environ", {"TG_CONTENT_BOT_TOKEN": "t", "TG_CONTENT_CHANNEL_ID": "@chan",
                                             "TG_CONTENT_OWNER_CHAT_ID": "42"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def _fake_tg(self, method, fields, files=None):
        self.calls.append((method, fields.get("chat_id"), fields.get("caption"), sorted((files or {}).keys())))
        if method == "sendMediaGroup":
            return [{"message_id": 10 + n} for n in range(len(files))]
        return {"message_id": 99}

    def _post(self, text="Короткий текст", status=TgPost.Status.APPROVED):
        return TgPost.objects.create(title="t", text=text, photo_ids=self.photos, status=status)

    def test_short_text_is_caption_of_album(self):
        p = self._post()
        with patch.object(tgsvc, "_tg", side_effect=self._fake_tg):
            tgsvc.publish(p.id)
        self.assertEqual([c[0] for c in self.calls], ["sendMediaGroup"])
        self.assertEqual(self.calls[0][1], "@chan")
        p.refresh_from_db()
        self.assertEqual((p.status, p.tg_message_id), (TgPost.Status.PUBLISHED, "10,11,12"))

    def test_long_text_separate_message_and_once_only(self):
        p = self._post(text="а" * 1500)
        with patch.object(tgsvc, "_tg", side_effect=self._fake_tg):
            tgsvc.publish(p.id)
            tgsvc.publish(p.id)  # повторно нічого не шле
        self.assertEqual([c[0] for c in self.calls], ["sendMediaGroup", "sendMessage"])

    def test_only_approved_and_error_saved(self):
        p = self._post(status=TgPost.Status.DRAFT)
        with self.assertRaises(tgsvc.PublishError):
            tgsvc.publish(p.id)
        p.status = TgPost.Status.APPROVED
        p.save()
        with patch.object(tgsvc, "_tg", side_effect=tgsvc.PublishError("Telegram: chat not found")):
            with self.assertRaises(tgsvc.PublishError):
                tgsvc.publish(p.id)
        p.refresh_from_db()
        self.assertEqual(p.status, TgPost.Status.APPROVED)
        self.assertIn("chat not found", p.publish_error)

    def test_schedule_publishes_only_due(self):
        due = self._post()
        due.scheduled_at = timezone.now() - timedelta(minutes=1)
        due.save()
        later = self._post()
        later.scheduled_at = timezone.now() + timedelta(days=1)
        later.save()
        draft = self._post(status=TgPost.Status.DRAFT)
        draft.scheduled_at = timezone.now() - timedelta(minutes=1)
        draft.save()
        with patch.object(tgsvc, "_tg", side_effect=self._fake_tg):
            done, failed = tgsvc.publish_due()
        self.assertEqual((done, failed), ([due.id], []))

    def test_api_rights_and_test_goes_to_owner_chat(self):
        p = self._post()
        c = APIClient()
        c.force_authenticate(self.trusted)
        self.assertEqual(c.post(f"/api/content-factory/telegram/posts/{p.id}/publish/").status_code, 403)
        self.assertEqual(c.patch(f"/api/content-factory/telegram/posts/{p.id}/", {"scheduled_at": "2026-10-01T10:00"},
                                 format="json").status_code, 403)
        self.assertEqual(c.post(f"/api/content-factory/telegram/posts/{p.id}/delete/").status_code, 404)
        c.force_authenticate(self.owner)
        with patch.object(tgsvc, "_tg", side_effect=self._fake_tg):
            self.assertEqual(c.post(f"/api/content-factory/telegram/posts/{p.id}/test/").status_code, 200)
        self.assertEqual(self.calls[0][1], "42")
        p.refresh_from_db()
        self.assertEqual(p.status, TgPost.Status.APPROVED)  # перевірка не публікує
        r = c.patch(f"/api/content-factory/telegram/posts/{p.id}/", {"scheduled_at": "2026-10-01T10:00"}, format="json")
        self.assertTrue(r.json()["scheduled_at"].startswith("2026-10-01T10:00"))
        with patch.object(tgsvc, "_tg", side_effect=self._fake_tg):
            self.assertEqual(c.post(f"/api/content-factory/telegram/posts/{p.id}/publish/").json()["status"], "published")
        self.assertEqual(c.patch(f"/api/content-factory/telegram/posts/{p.id}/", {"text": "x"}, format="json").status_code, 400)

    def test_manual_post_free(self):
        c = APIClient()
        c.force_authenticate(self.trusted)
        r = c.post("/api/content-factory/telegram/posts/", {"text": "Анонс майстер-класу\nу суботу"}, format="json")
        self.assertEqual((r.status_code, r.json()["title"]), (201, "Анонс майстер-класу"))


# ── Джерела: TG-групи за file_id ───────────────────────────────────────────────────────────────
class SourceTests(TestCase):
    SECRET = "test-ingest-secret"

    def setUp(self):
        self.owner = User.objects.create_user(username="src-owner", password="x", is_superuser=True, is_staff=True)
        self.env = patch.dict("os.environ", {"CF_INGEST_SECRET": self.SECRET, "TG_CONTENT_BOT_TOKEN": "t",
                                             "TG_CONTENT_CHANNEL_ID": "@wallcovpro", "TG_CONTENT_OWNER_CHAT_ID": "42"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.c = APIClient()

    def _msg(self, mid, uid, caption="", group="", chat_id=-1001234567890, title="Обʼєкти"):
        m = {"message_id": mid, "date": 1758700000, "chat": {"id": chat_id, "type": "supergroup", "title": title},
             "photo": [{"file_id": f"small{uid}", "file_unique_id": f"s{uid}", "width": 90, "height": 90},
                       {"file_id": f"big{uid}", "file_unique_id": uid, "width": 1280, "height": 960, "file_size": 200000}]}
        if caption:
            m["caption"] = caption
        if group:
            m["media_group_id"] = group
        return {"message": m}

    def _post(self, update, secret=SECRET):
        return self.c.post("/api/content-factory/sources/ingest/", update, format="json", HTTP_X_CF_INGEST=secret)

    def test_secret_and_disabled_chat(self):
        self.assertEqual(self._post(self._msg(1, "u1"), secret="wrong").status_code, 403)
        self.assertEqual(self._post(self._msg(1, "u1")).json()["status"], "chat-disabled")
        self.assertFalse(SourceAsset.objects.exists())
        chat = SourceChat.objects.get()
        self.assertFalse(chat.enabled)
        chat.enabled = True
        chat.save()
        self.assertEqual(self._post(self._msg(1, "u1", caption="Галатея, спальня #готово")).json()["status"], "created")
        a = SourceAsset.objects.get()
        self.assertEqual((a.file_id, a.thumb_file_id, a.material), ("big" + "u1", "smallu1", "Галатея"))
        self.assertIn("спальня", a.tags)
        self.assertEqual(a.link, "https://t.me/c/1234567890/1")

    def test_our_channel_auto_enabled_and_album_caption(self):
        ch = {"id": -100555, "type": "channel", "title": "Wallcov", "username": "wallcovpro"}
        for n, (uid, cap) in enumerate((("a1", ""), ("a2", "Мокрий шовк у коридорі"), ("a3", ""))):
            upd = self._msg(10 + n, uid, caption=cap, group="G1")
            upd = {"channel_post": dict(upd["message"], chat=ch)}
            self._post(upd)
        self.assertTrue(SourceChat.objects.get(chat_id=-100555).enabled)
        self.assertEqual(set(SourceAsset.objects.values_list("material", flat=True)), {"Мокрий шовк"})
        self.assertEqual(SourceAsset.objects.first().link.split("/")[3], "wallcovpro")

    def test_list_thumb_signature_and_publish_by_file_id(self):
        SourceChat.objects.create(chat_id=-1001, title="Група", enabled=True)
        self._post(self._msg(5, "p5", caption="Патера", chat_id=-1001))
        a = SourceAsset.objects.get()
        self.c.force_authenticate(self.owner)
        r = self.c.get("/api/content-factory/sources/?material=Патера").json()
        self.assertEqual(r["total"], 1)
        self.assertTrue(r["items"][0]["thumb_url"].startswith("/api/content-factory/sources/thumb/"))
        self.assertEqual(APIClient().get("/api/content-factory/sources/thumb/forged/").status_code, 404)
        post = TgPost.objects.create(title="t", text="Текст", status=TgPost.Status.APPROVED, source_ids=[a.id])
        calls = []
        with patch.object(tgsvc, "_tg", side_effect=lambda m, f, files=None: calls.append((m, f, files)) or {"message_id": 1}):
            tgsvc.publish(post.id)
        method, fields, files = calls[0]
        self.assertEqual((method, fields["photo"], files), ("sendPhoto", "bigp5", None))  # без завантаження файлу


# ── Google Drive і аналітика опублікованих (мережа підмінена) ─────────────────────────────────────
class DriveAndStatsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="dr-owner", password="x", is_superuser=True, is_staff=True)

    def test_drive_sync_indexes_links_only(self):
        from . import drive
        tree = {
            "ROOT": [{"id": "F1", "name": "ВЕЛЬВЕТ Луна", "mimeType": drive.FOLDER_MIME},
                     {"id": "doc", "name": "кошторис.pdf", "mimeType": "application/pdf"}],
            "F1": [{"id": "IMG1", "name": "спальня.jpg", "mimeType": "image/jpeg", "size": "1000",
                    "webViewLink": "https://drive.google.com/file/d/IMG1/view"},
                   {"id": "VID1", "name": "нанесення.mp4", "mimeType": "video/mp4", "size": "5000",
                    "videoMediaMetadata": {"durationMillis": 12000}}],
        }
        folder = DriveFolder.objects.create(folder_id="ROOT", title="А 2025")
        with patch.object(drive, "children", side_effect=lambda fid: iter(tree.get(fid, []))):
            self.assertEqual(drive.sync_folder(folder), 2)
            self.assertEqual(drive.sync_folder(folder), 2)  # повторно — без дублів
        self.assertEqual(SourceAsset.objects.count(), 2)
        img = SourceAsset.objects.get(file_id="IMG1")
        self.assertEqual((img.origin, img.material, img.caption), ("drive", "Вельвет Луна", "А 2025 / ВЕЛЬВЕТ Луна"))
        self.assertIn("спальня", img.tags)
        self.assertEqual(SourceAsset.objects.get(file_id="VID1").duration, 12)
        self.assertEqual(drive.parse_folder_link("https://drive.google.com/drive/folders/1abcDEF?usp=sharing"), "1abcDEF")

    def test_stats_snapshot_and_published_tab(self):
        from .models import TgPostStat
        p = TgPost.objects.create(title="Шовк", text="т", status=TgPost.Status.PUBLISHED, tg_message_id="1022,1023",
                                  published_at=timezone.now() - timedelta(hours=2))
        TgPost.objects.create(title="Чернетка", text="т")
        with patch.dict("os.environ", {"TG_CONTENT_CHANNEL_ID": "@wallcovpro"}), \
                patch.object(tgsvc, "public_stats", return_value=(1300, 5, {"🔥": 4, "❤": 1})) as ps:
            self.assertEqual(tgsvc.collect_stats(), 1)
            ps.assert_called_with("wallcovpro", "1022")
        p.refresh_from_db()
        self.assertEqual((p.views, p.reactions), (1300, 5))
        self.assertEqual(TgPostStat.objects.count(), 1)
        c = APIClient()
        c.force_authenticate(self.owner)
        with patch.dict("os.environ", {"TG_CONTENT_CHANNEL_ID": "@wallcovpro"}):
            r = c.get("/api/content-factory/telegram/published/").json()
            drafts = c.get("/api/content-factory/telegram/").json()["posts"]
        self.assertEqual((r["summary"]["count"], r["summary"]["avg_views"]), (1, 1300))
        self.assertEqual(r["posts"][0]["tg_link"], "https://t.me/wallcovpro/1022")
        self.assertEqual([x["title"] for x in drafts], ["Чернетка"])  # опубліковані — лише у своїй вкладці


# ── Етап 3: стрічка й аналітик (ChatPlace і ШІ підмінено) ─────────────────────────────────────────
class FeedAnalystTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="an-owner", password="x", is_superuser=True, is_staff=True)
        self.trusted = User.objects.create_user(username="an-trusted", password="x",
                                                extra_permissions=["content_factory.access"])

    def _fake_mcp(self, name, args=None):
        if name == "virale_accounts_list":
            return [{"id": "A1", "username": "mazanka_kyiv"}, {"id": "A2", "username": "dekor_dlia_stin"},
                    {"id": "A3", "username": "private", "isRestricted": True}]
        if name == "virale_videos_list":
            u = "mazanka_kyiv" if args["accountId"] == "A1" else "dekor_dlia_stin"
            now = timezone.now().strftime("%Y-%m-%d %H:%M:%S")
            return {"data": [{"id": f"{u}-{n}", "username": u, "url": f"https://x/{n}", "viewsCount": v,
                              "publishedAt": now, "caption": f"хук {n}"} for n, v in enumerate([1000, 1000, 5000])]}
        if name == "virale_dashboard":
            return {"accountHero": {"username": "dekor_dlia_stin", "followers": 65257, "medianViews": 9181}}
        raise AssertionError(name)

    def test_feed_sync_outlier_and_own_hidden(self):
        with patch.object(ansvc, "_mcp", side_effect=self._fake_mcp), patch.object(ansvc, "PAUSE_SEC", 0):
            r = ansvc.sync_feed()
        self.assertEqual(r, {"accounts": 3, "items": 6})  # закритий акаунт пропущено
        rows = ansvc.feed(days=7)
        self.assertEqual({i.username for i, _ in rows}, {"mazanka_kyiv"})  # свої — окремо
        top, x = rows[0]
        self.assertEqual((top.views, x), (5000, 5.0))  # 5000 проти медіани 1000
        c = APIClient()
        c.force_authenticate(self.trusted)
        self.assertEqual(c.post("/api/content-factory/feed/").status_code, 403)
        self.assertEqual(c.patch(f"/api/content-factory/feed/{top.id}/", {"status": "saved"}, format="json").json()["status"], "saved")
        self.assertEqual(c.get("/api/content-factory/feed/?status=saved").json()["items"][0]["x"], 5.0)

    def test_report_budget_and_generation(self):
        s = AnalystSettings.get()
        s.monthly_budget_usd = 0
        s.save()
        with self.assertRaises(ansvc.BudgetError):
            ansvc.generate_report(call=lambda p: {})
        s.monthly_budget_usd = 1
        s.save()
        seen = []
        fake = lambda p: seen.append(p) or {"summary": "Шовк зайшов.\n\nРобимо ще.", "ideas": [
            {"title": "Шви", "hook": "Чи видно шви?", "why": "питали 9 разів", "format": "рилс", "material": "Галатея"}]}
        with patch.object(ansvc, "_mcp", side_effect=self._fake_mcp):
            r = ansvc.generate_report(call=fake)
        self.assertEqual(r.ideas[0]["hook"], "Чи видно шви?")
        self.assertIn("65257", seen[0])  # у ШІ пішли реальні цифри акаунта
        c = APIClient()
        c.force_authenticate(self.owner)
        data = c.get("/api/content-factory/analyst/").json()
        self.assertEqual((len(data["reports"]), data["settings"]["weekly_enabled"]), (1, False))


class StyleTests(TestCase):
    def test_presets_drawtext_and_reference(self):
        from . import styles
        styles.ensure_presets()
        styles.ensure_presets()  # без дублів
        self.assertEqual(ReelStyleModel.objects.filter(origin="preset").count(), len(styles.PRESETS))
        big = ReelStyleModel.objects.get(name__startswith="Великий")
        vf = styles.drawtext(big, "/tmp/t.txt")
        self.assertIn("borderw=7", vf)
        self.assertNotIn("box=1", vf)
        item = FeedItem.objects.create(external_id="x1", username="sk_tanos", url="https://x", preview_url="https://img/x.jpg")

        class R:
            headers = {"Content-Type": "image/jpeg"}
            def read(self): return b"img"
            def __enter__(self): return self
            def __exit__(self, *a): return False
        fake = {"font_kind": "geometric", "weight": "Black", "color": "#FFE600", "stroke": 4, "box": False,
                "position": 0.3, "upper": True, "size_rel": "huge", "notes": "жовтий капс зверху"}
        with patch("urllib.request.urlopen", return_value=R()), patch.object(styles, "_gemini", return_value=fake):
            st = styles.from_feed_item(item)
        self.assertEqual((st.font, st.weight, st.size, st.upper, st.origin), ("Montserrat", "Black", 92, True, "reference"))
        with patch("urllib.request.urlopen", return_value=R()), patch.object(styles, "_gemini", return_value={"no_text": True}):
            self.assertIsNone(styles.from_feed_item(item))


class BlogCarouselAssistTests(TestCase):
    """25.09: блоги, каруселі, вичитка й поради. ШІ підмінено."""
    def setUp(self):
        from . import blogs as blogsvc
        self.owner = User.objects.create_user(username="owner-blog", password="x", is_superuser=True, is_staff=True)
        self.c = APIClient()
        self.c.force_authenticate(self.owner)
        blogsvc.ensure_blogs()
        self.blogsvc = blogsvc

    def test_seed_and_accounts(self):
        from .models import Blog
        self.assertEqual(Blog.objects.filter(is_default=True).count(), 1)
        w = Blog.objects.get(slug="wallcov")
        self.assertTrue(w.use_crm_kb and w.label_ai and self.blogsvc.is_ready(w))
        self.assertTrue(ContentChannel.objects.filter(handle="dekor_dlia_stin", blog=w, role="own").exists())
        oleg = Blog.objects.get(slug="oleg")
        self.assertFalse(self.blogsvc.is_ready(oleg))  # шаблон з «[заповніть]» не генерує
        with self.assertRaises(ValueError):
            self.blogsvc.require_ready(oleg)
        r = self.c.get("/api/content-factory/blogs/")
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(len(r.json()["blogs"]), 9)

    def test_facts_rules_always_included(self):
        from .models import Blog, BlogFact
        b = Blog.objects.get(slug="stiny-v-shotsi")
        BlogFact.objects.create(blog=b, kind="rule", title="Барсик завжди рудий", text="")
        BlogFact.objects.create(blog=b, kind="fact", title="Олена живе на 5 поверсі", text="квартира")
        text, titles = self.blogsvc.facts_block(b, "щось зовсім інше")
        self.assertIn("Барсик завжди рудий", text)
        self.assertIn("Мета блогу", self.blogsvc.system_for(b, "завдання"))

    def test_carousel_generate_and_render(self):
        from . import carousels as carsvc
        from .models import Blog
        b = Blog.objects.get(slug="stiny-v-shotsi")
        fake = lambda p: {"title": "Хто рахує банки ✨", "caption": "Підпис", "checks": ["ціна"],
                          "slides": [{"headline": f"Слайд {i}", "body": "Текст слайда про ремонт", "image_hint": "кіт"} for i in range(5)]}
        c = carsvc.generate(b, "Скільки банок брати", n=5, template="plaster", images="none", call=fake)
        self.assertEqual(len(c.slides), 5)
        self.assertEqual(c.title, "Хто рахує банки")  # емодзі прибрано
        self.assertTrue(all(s.get("rendered_id") for s in c.slides))
        png = SharedLink.objects.get(pk=c.slides[0]["rendered_id"])
        self.assertEqual(bytes(png.data)[:2], b"\xff\xd8")  # JPEG
        r = self.c.patch(f"/api/content-factory/carousels/{c.id}/",
                         {"slides": [{"headline": "Новий", "body": "б"}] * 5}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["slides"][0]["headline"], "Новий")

    def test_proofread_keeps_text_when_empty_reply(self):
        from . import assist
        r = assist.proofread("Привіт світ", call=lambda p: {})
        self.assertEqual(r["text"], "Привіт світ")
        r = assist.proofread("Првіт", call=lambda p: {"text": "Привіт", "changes": [{"was": "Првіт", "now": "Привіт", "why": "орфографія"}]})
        self.assertEqual((r["text"], len(r["changes"])), ("Привіт", 1))

    def test_advice_filters_actions(self):
        from . import assist
        from .models import Blog, ReelDraft
        w = Blog.objects.get(slug="wallcov")
        reel = ReelDraft.objects.create(title="t", blog=w, beats=[{"text": "a", "scene_id": 1, "seconds": 2},
                                                                    {"text": "b", "image_id": 5, "seconds": 2}])
        fake = lambda p: {"advice": [
            {"title": "Перехід", "why": "досмотр", "action": {"type": "transition", "beat": 1, "value": "fade"}},
            {"title": "Погано", "why": "x", "action": {"type": "transition", "beat": 1, "value": "spin"}},
            {"title": "Перемалювати фактуру", "why": "x", "action": {"type": "regenerate", "beat": 0, "value": "нова стіна"}},
            {"title": "ШІ-кадр", "why": "x", "action": {"type": "edit_frame", "beat": 1, "value": "додати стрілку"}},
            {"title": "Поза межами", "why": "x", "action": {"type": "text", "beat": 9, "value": "т"}}]}
        out = assist.reel_advice(reel, call=fake)
        self.assertEqual([a["title"] for a in out], ["Перехід", "ШІ-кадр"])
