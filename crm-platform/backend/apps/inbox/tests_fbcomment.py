"""fbcomment 15.09.2026: відповіді в коментарях Meta. Усі виклики Graph підмінені — жодної реальної мережі."""
import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.crm.models import Contact
from .meta_comments import CommentReplyError, GraphError
from .models import Channel, Conversation, Message
from .services import send_message

User = get_user_model()
PAGE = "PAGE1"


class _Graph:
    """Підміна meta_comments._call: відповіді по (метод, шлях) + журнал викликів."""

    def __init__(self, routes=None):
        self.routes = routes or {}
        self.calls = []

    def __call__(self, method, path, params=None, timeout=20):
        self.calls.append((method, path, dict(params or {})))
        r = self.routes.get((method, path))
        if isinstance(r, BaseException):
            raise r
        if callable(r):
            return r(params or {})
        if r is None:
            raise AssertionError("неочікуваний виклик Graph: %s %s" % (method, path))
        return r

    def posts(self):
        return [c for c in self.calls if c[0] == "POST"]


class _Base(TestCase):
    def setUp(self):
        # страховка: будь-яка спроба реальної мережі — падіння тесту
        self._net = patch("urllib.request.urlopen", side_effect=AssertionError("реальна мережа заборонена в тестах"))
        self._net.start()
        self._ids = patch("apps.inbox.meta._OUR_IDS", {PAGE, "IGBIZ"})
        self._ids.start()
        self._pid = patch("apps.inbox.meta.PAGE_ID", PAGE)
        self._pid.start()
        self.user = User.objects.create_superuser("fbc-owner", password="x", first_name="Олександр")
        self.fb = Channel.objects.create(kind="facebook", name="Meta · facebook",
                                         config={"meta": True, "platform": "page", "page_id": PAGE})
        self.ig = Channel.objects.create(kind="instagram", name="Meta · instagram",
                                         config={"meta": True, "platform": "instagram"})
        self.contact = Contact.objects.create(first_name="Івана", last_name="Тест")

    def tearDown(self):
        self._net.stop()
        self._ids.stop()
        self._pid.stop()

    def fb_comment_chat(self):
        conv = Conversation.objects.create(channel=self.fb, contact=self.contact,
                                           external_chat_id="comment:facebook:POST_1:client1")
        Message.objects.create(conversation=conv, direction="in", text="Галатея", external_id="POST_C1")
        Message.objects.create(conversation=conv, direction="out", text="Вітаю! Тест-набір чи обʼєм?",
                               external_id="POST_R1", sender=self.user,
                               attachments=[{"type": "comment_reply", "mode": "public", "comment_id": "POST_C1"}])
        Message.objects.create(conversation=conv, direction="in", text="Кімната 22,5 м², ціна?", external_id="POST_C2")
        return conv


class PublicCommentReplyTests(_Base):
    def test_public_reply_goes_to_latest_client_comment(self):
        conv = self.fb_comment_chat()
        g = _Graph({("POST", "POST_C2/comments"): {"id": "POST_R2"}})
        with patch("apps.inbox.meta_comments._call", g):
            msg = send_message(conv, "Порахую точно", user=self.user)
        self.assertEqual(g.posts(), [("POST", "POST_C2/comments", {"message": "Порахую точно"})])
        msg.refresh_from_db()
        self.assertEqual((msg.status, msg.external_id), ("sent", "POST_R2"))
        self.assertEqual(msg.attachments[0]["type"], "comment_reply")
        self.assertEqual((msg.attachments[0]["mode"], msg.attachments[0]["comment_id"]), ("public", "POST_C2"))

    def test_old_comment_is_not_window_risk(self):
        """Публічна відповідь у гілці не залежить від 24-годинного вікна Messenger."""
        conv = self.fb_comment_chat()
        Message.objects.filter(conversation=conv, direction="in").update(created_at=timezone.now() - timedelta(days=3))
        g = _Graph({("POST", "POST_C2/comments"): {"id": "POST_R2"}})
        with patch("apps.inbox.meta_comments._call", g):
            msg = send_message(conv, "Відповідь", user=self.user)
        self.assertEqual(msg.status, "sent")

    def test_meta_error_but_published_is_marked_sent(self):
        """Випадок Івани Забурко: Meta опублікувала, але CRM отримала помилку → звіряємо гілку, це «надіслано»."""
        conv = self.fb_comment_chat()
        now = timezone.now().strftime("%Y-%m-%dT%H:%M:%S+0000")
        g = _Graph({
            ("POST", "POST_C2/comments"): TimeoutError("The read operation timed out"),
            ("GET", "POST_C2/comments"): {"data": [
                {"id": "POST_OTHER", "message": "Порахую точно", "created_time": now, "from": {"id": "someone"}},
                {"id": "POST_R2", "message": "Порахую точно", "created_time": now, "from": {"id": PAGE}},
            ]},
        })
        with patch("apps.inbox.meta_comments._call", g):
            msg = send_message(conv, "Порахую точно", user=self.user)
        msg.refresh_from_db()
        self.assertEqual((msg.status, msg.external_id), ("sent", "POST_R2"))
        self.assertEqual(len(g.posts()), 1)  # жодної повторної публікації

    def test_real_failure_is_saved_with_reason(self):
        conv = self.fb_comment_chat()
        g = _Graph({
            ("POST", "POST_C2/comments"): GraphError(400, 368, None, "It looks like you were misusing this feature"),
            ("GET", "POST_C2/comments"): {"data": []},
        })
        with patch("apps.inbox.meta_comments._call", g):
            with self.assertRaises(CommentReplyError) as cm:
                send_message(conv, "Порахую точно", user=self.user)
        self.assertIn("антиспам", str(cm.exception))
        msg = conv.messages.filter(direction="out").order_by("-id").first()
        self.assertEqual(msg.status, "failed")
        self.assertEqual(msg.attachments[-1]["type"], "send_error")
        self.assertIn("антиспам", msg.attachments[-1]["text"])

    def test_deleted_comment_gives_clear_text(self):
        conv = self.fb_comment_chat()
        g = _Graph({("POST", "POST_C2/comments"): GraphError(
            400, 100, 33, "Unsupported post request. Object with ID 'POST_C2' does not exist")})
        with patch("apps.inbox.meta_comments._call", g):
            with self.assertRaises(CommentReplyError) as cm:
                send_message(conv, "Текст", user=self.user)
        self.assertEqual(cm.exception.code, "comment_gone")
        self.assertIn("видалено", str(cm.exception))

    def test_no_client_comment_is_error_not_silent_success(self):
        """Було: без коментаря клієнта адаптер повертав "" і CRM показувала «надіслано» — нічого не відправивши."""
        conv = Conversation.objects.create(channel=self.fb, contact=self.contact,
                                           external_chat_id="comment:facebook:POST_9:nobody")
        g = _Graph()
        with patch("apps.inbox.meta_comments._call", g):
            with self.assertRaises(CommentReplyError) as cm:
                send_message(conv, "Текст", user=self.user)
        self.assertEqual((cm.exception.code, cm.exception.blocked), ("no_target", True))
        self.assertEqual(conv.messages.count(), 0)
        self.assertEqual(g.calls, [])


class InstagramCommentReplyTests(_Base):
    def ig_chat(self, cid):
        conv = Conversation.objects.create(channel=self.ig, contact=self.contact,
                                           external_chat_id="comment:instagram:MEDIA_1:client_ig")
        Message.objects.create(conversation=conv, direction="in", text="Луна", external_id=cid)
        return conv

    def test_instagram_uses_replies_edge(self):
        conv = self.ig_chat("IGC_TOP")
        g = _Graph({("GET", "IGC_TOP"): {"id": "IGC_TOP"}, ("POST", "IGC_TOP/replies"): {"id": "IGR_1"}})
        with patch("apps.inbox.meta_comments._call", g):
            msg = send_message(conv, "Відповідь", user=self.user)
        self.assertEqual(g.posts(), [("POST", "IGC_TOP/replies", {"message": "Відповідь"})])
        self.assertEqual(msg.external_id, "IGR_1")

    def test_instagram_nested_comment_replies_to_top_level(self):
        conv = self.ig_chat("IGC_CHILD")
        g = _Graph({("GET", "IGC_CHILD"): {"id": "IGC_CHILD", "parent_id": "IGC_TOP"},
                    ("POST", "IGC_TOP/replies"): {"id": "IGR_2"}})
        with patch("apps.inbox.meta_comments._call", g):
            msg = send_message(conv, "Відповідь", user=self.user)
        self.assertEqual(g.posts()[0][1], "IGC_TOP/replies")
        self.assertEqual(msg.attachments[0]["comment_id"], "IGC_CHILD")
        self.assertEqual(msg.attachments[0]["reply_to"], "IGC_TOP")

    def test_instagram_deleted_comment_blocked_before_send(self):
        conv = self.ig_chat("IGC_GONE")
        g = _Graph({("GET", "IGC_GONE"): GraphError(400, 100, 33, "Object with ID 'IGC_GONE' does not exist")})
        with patch("apps.inbox.meta_comments._call", g):
            with self.assertRaises(CommentReplyError) as cm:
                send_message(conv, "Відповідь", user=self.user)
        self.assertEqual((cm.exception.code, cm.exception.blocked), ("comment_gone", True))
        self.assertEqual(conv.messages.filter(direction="out").count(), 0)
        self.assertEqual(g.posts(), [])

    def test_instagram_private_not_supported(self):
        conv = self.ig_chat("IGC_TOP")
        g = _Graph({("GET", "IGC_TOP"): {"id": "IGC_TOP"}})
        with patch("apps.inbox.meta_comments._call", g):
            with self.assertRaises(CommentReplyError) as cm:
                send_message(conv, "Відповідь", user=self.user, comment_mode="private")
        self.assertEqual(cm.exception.code, "private_unsupported")
        self.assertEqual(g.posts(), [])


class PrivateCommentReplyTests(_Base):
    def test_private_reply_to_latest_comment(self):
        conv = self.fb_comment_chat()
        g = _Graph({("GET", "POST_C2"): {"can_reply_privately": True},
                    ("POST", "%s/messages" % PAGE): {"recipient_id": "PSID", "message_id": "m_1"}})
        with patch("apps.inbox.meta_comments._call", g):
            msg = send_message(conv, "Пишу вам у Messenger", user=self.user, comment_mode="private")
        (method, path, params), = g.posts()
        self.assertEqual(path, "%s/messages" % PAGE)
        self.assertEqual(params["recipient"], '{"comment_id": "POST_C2"}')
        self.assertEqual(json.loads(params["message"]), {"text": "Пишу вам у Messenger"})  # Meta приймає \\u-екранування
        self.assertEqual((msg.external_id, msg.attachments[0]["mode"]), ("m_1", "private"))

    def test_second_private_reply_to_same_comment_blocked(self):
        conv = self.fb_comment_chat()
        Message.objects.create(conversation=conv, direction="out", text="перша приватна", external_id="m_0",
                               sender=self.user,
                               attachments=[{"type": "comment_reply", "mode": "private", "comment_id": "POST_C2"}])
        before = conv.messages.count()
        g = _Graph({("GET", "POST_C2"): {"can_reply_privately": True}})
        with patch("apps.inbox.meta_comments._call", g):
            with self.assertRaises(CommentReplyError) as cm:
                send_message(conv, "друга приватна", user=self.user, comment_mode="private")
        e = cm.exception
        self.assertEqual((e.code, e.blocked, e.can_public), ("private_used", True, True))
        self.assertIn("лише ОДНУ", str(e))
        self.assertEqual(conv.messages.count(), before)  # нічого не записано
        self.assertEqual(g.posts(), [])                   # нічого не відправлено

    def test_private_blocked_when_meta_says_no(self):
        conv = self.fb_comment_chat()
        g = _Graph({("GET", "POST_C2"): {"can_reply_privately": False}})
        with patch("apps.inbox.meta_comments._call", g):
            with self.assertRaises(CommentReplyError) as cm:
                send_message(conv, "приватна", user=self.user, comment_mode="private")
        self.assertEqual(cm.exception.code, "private_not_allowed")
        self.assertEqual(g.posts(), [])

    def test_private_allowed_again_on_new_client_comment(self):
        conv = self.fb_comment_chat()
        Message.objects.create(conversation=conv, direction="out", text="перша приватна", external_id="m_0",
                               sender=self.user,
                               attachments=[{"type": "comment_reply", "mode": "private", "comment_id": "POST_C2"}])
        Message.objects.create(conversation=conv, direction="in", text="А доставка?", external_id="POST_C3")
        g = _Graph({("GET", "POST_C3"): {"can_reply_privately": True},
                    ("POST", "%s/messages" % PAGE): {"message_id": "m_2"}})
        with patch("apps.inbox.meta_comments._call", g):
            send_message(conv, "Доставка НП", user=self.user, comment_mode="private")
        self.assertEqual(g.posts()[0][2]["recipient"], '{"comment_id": "POST_C3"}')

    def test_private_expired_after_7_days(self):
        conv = self.fb_comment_chat()
        Message.objects.filter(external_id="POST_C2").update(created_at=timezone.now() - timedelta(days=8))
        g = _Graph()
        with patch("apps.inbox.meta_comments._call", g):
            with self.assertRaises(CommentReplyError) as cm:
                send_message(conv, "приватна", user=self.user, comment_mode="private")
        self.assertEqual(cm.exception.code, "private_expired")
        self.assertEqual(g.calls, [])

    def test_meta_rejects_private_already_replied(self):
        """Якщо Meta все ж відмовила (10900 — уже відповідали), менеджер бачить причину і кнопку «публічно»."""
        conv = self.fb_comment_chat()
        g = _Graph({("GET", "POST_C2"): {"can_reply_privately": True},
                    ("POST", "%s/messages" % PAGE): GraphError(400, 10900, None, "Activity already replied to")})
        with patch("apps.inbox.meta_comments._call", g):
            with self.assertRaises(CommentReplyError) as cm:
                send_message(conv, "приватна", user=self.user, comment_mode="private")
        self.assertEqual((cm.exception.code, cm.exception.can_public), ("private_used", True))
        msg = conv.messages.filter(direction="out").order_by("-id").first()
        self.assertEqual(msg.status, "failed")


class CommentApiTests(_Base):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_blocked_private_returns_409_with_public_button(self):
        conv = self.fb_comment_chat()
        Message.objects.create(conversation=conv, direction="out", text="перша приватна", external_id="m_0",
                               sender=self.user,
                               attachments=[{"type": "comment_reply", "mode": "private", "comment_id": "POST_C2"}])
        g = _Graph({("GET", "POST_C2"): {"can_reply_privately": True}})
        with patch("apps.inbox.meta_comments._call", g):
            r = self.client.post(f"/api/conversations/{conv.id}/send/",
                                 {"text": "ще раз", "comment_mode": "private"}, format="json")
        self.assertEqual(r.status_code, 409)
        body = r.json()
        self.assertEqual((body["code"], body["can_public"]), ("private_used", True))
        self.assertIn("лише ОДНУ", body["detail"])

    def test_public_path_via_api(self):
        conv = self.fb_comment_chat()
        g = _Graph({("POST", "POST_C2/comments"): {"id": "POST_R2"}})
        with patch("apps.inbox.meta_comments._call", g):
            r = self.client.post(f"/api/conversations/{conv.id}/send/",
                                 {"text": "публічно", "comment_mode": "public"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["attachments"][0]["mode"], "public")

    def test_comment_target_describes_where_reply_goes(self):
        conv = self.fb_comment_chat()
        g = _Graph({("GET", "POST_C2"): {"can_reply_privately": True}})
        with patch("apps.inbox.meta_comments._call", g):
            r = self.client.get(f"/api/conversations/{conv.id}/comment_target/")
        d = r.json()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(d["is_comment"])
        self.assertEqual((d["default_mode"], d["platform"]), ("public", "facebook"))
        self.assertEqual(d["target"]["comment_id"], "POST_C2")
        self.assertTrue(d["can_private"])
        self.assertEqual(g.posts(), [])

    def test_comment_target_for_normal_chat(self):
        conv = Conversation.objects.create(channel=self.fb, contact=self.contact, external_chat_id="PSID_1")
        g = _Graph()
        with patch("apps.inbox.meta_comments._call", g):
            r = self.client.get(f"/api/conversations/{conv.id}/comment_target/")
        self.assertEqual(r.json(), {"is_comment": False})
        self.assertEqual(g.calls, [])


class MessengerUnchangedTests(_Base):
    """Звичайний чат Messenger (не коментар) — поведінка як і раніше."""

    def dm(self):
        conv = Conversation.objects.create(channel=self.fb, contact=self.contact, external_chat_id="PSID_1")
        Message.objects.create(conversation=conv, direction="in", text="Привіт", external_id="mid.in.1")
        return conv

    @patch("apps.inbox.meta.send_message", return_value={"recipient_id": "PSID_1", "message_id": "mid.out.1"})
    def test_messenger_send_unchanged(self, meta_send):
        conv = self.dm()
        g = _Graph()
        with patch("apps.inbox.meta_comments._call", g):
            msg = send_message(conv, "Відповідь у Messenger", user=self.user, comment_mode="private")
        meta_send.assert_called_once_with("PSID_1", "Відповідь у Messenger", platform="facebook")
        self.assertEqual(g.calls, [])
        self.assertEqual((msg.status, msg.external_id, msg.attachments), ("sent", "mid.out.1", []))

    @patch("apps.inbox.meta.send_message", return_value={"message_id": "mid.out.2"})
    def test_messenger_window_risk_unchanged(self, meta_send):
        conv = self.dm()
        Message.objects.filter(conversation=conv, direction="in").update(created_at=timezone.now() - timedelta(hours=30))
        msg = send_message(conv, "Пізно", user=self.user)
        self.assertEqual(msg.status, "window_risk")

    @patch("apps.inbox.meta.send_message", side_effect=RuntimeError("Meta IG 400: window"))
    def test_messenger_failure_unchanged(self, meta_send):
        conv = self.dm()
        with self.assertRaises(RuntimeError):
            send_message(conv, "Текст", user=self.user)
        msg = conv.messages.filter(direction="out").first()
        self.assertEqual((msg.status, msg.attachments), ("failed", []))
