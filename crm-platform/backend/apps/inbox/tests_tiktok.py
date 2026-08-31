"""Тести прямого TikTok-каналу (tiktok.py). Без мережі: HTTP до TikTok замокано."""
import hashlib
import hmac
import json
import time
import urllib.parse
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.crm.models import Lead
from .models import Channel, Conversation, Message
from . import tiktok

User = get_user_model()
BIZ = "biz-open-id-1"


def _event(kind="im_receive_msg", *, conv="conv-1", mid="m-1", text="Привіт", mtype="text",
           frm="client_nick", frm_id="client-1", to="dekor_dlia_stin", to_id=BIZ, extra=None):
    content = {"conversation_id": conv, "message_id": mid, "type": mtype,
               "from": frm, "from_user": {"id": frm_id}, "to": to, "to_user": {"id": to_id},
               "timestamp": int(time.time() * 1000)}
    if mtype == "text":
        content["text"] = {"body": text}
    if extra:
        content.update(extra)
    return {"event": kind, "user_openid": BIZ, "content": json.dumps(content)}


class TiktokWebhookTests(TestCase):
    def setUp(self):
        self.ch = Channel.objects.create(kind="tiktok", name="TikTok · Direct", config={
            "tiktok_direct": True, "business_id": BIZ, "access_token": "tok",
            "expires_at": (timezone.now() + timedelta(hours=12)).isoformat(),
            "refresh_token": "ref", "refresh_expires_at": (timezone.now() + timedelta(days=20)).isoformat(),
        })
        # ChatPlace-канал TikTok поруч — не повинен отримувати прямі події
        self.cp = Channel.objects.create(kind="tiktok", name="ChatPlace · TikTok", config={"chatplace": True})

    def test_incoming_creates_conversation_contact_lead(self):
        self.assertEqual(tiktok.handle_event(_event()), 1)
        conv = Conversation.objects.get(channel=self.ch, external_chat_id="conv-1")
        self.assertEqual(conv.unread, 1)
        self.assertEqual(conv.title, "client_nick")
        self.assertIsNotNone(conv.contact)
        self.assertEqual(conv.contact.nickname, "@client_nick")
        self.assertIn("tiktok.com/@client_nick", conv.contact.social_link)
        self.assertEqual(Lead.objects.filter(contact=conv.contact, source="tiktok").count(), 1)
        m = conv.messages.get()
        self.assertEqual((m.direction, m.text, m.external_id), ("in", "Привіт", "m-1"))
        self.assertFalse(Conversation.objects.filter(channel=self.cp).exists())

    def test_duplicate_webhook_is_ignored(self):
        tiktok.handle_event(_event())
        self.assertEqual(tiktok.handle_event(_event()), 0)
        self.assertEqual(Message.objects.filter(conversation__channel=self.ch).count(), 1)

    def test_echo_sent_outside_crm_is_outgoing_ai(self):
        tiktok.handle_event(_event())
        ev = _event("im_send_msg", mid="m-2", text="Відповідь Юлі", frm="dekor_dlia_stin", frm_id=BIZ,
                    to="client_nick", to_id="client-1")
        self.assertEqual(tiktok.handle_event(ev), 1)
        conv = Conversation.objects.get(external_chat_id="conv-1")
        self.assertEqual(conv.unread, 1)  # echo не додає непрочитаних
        out = conv.messages.get(external_id="m-2")
        self.assertEqual((out.direction, out.sender_name), ("out", "ai_assistant"))

    def test_echo_of_crm_message_is_not_duplicated(self):
        tiktok.handle_event(_event())
        conv = Conversation.objects.get(external_chat_id="conv-1")
        Message.objects.create(conversation=conv, direction="out", text="Від менеджера", external_id="m-crm")
        ev = _event("im_send_msg", mid="m-crm", text="Від менеджера", frm="dekor_dlia_stin", frm_id=BIZ,
                    to="client_nick", to_id="client-1")
        self.assertEqual(tiktok.handle_event(ev), 0)
        self.assertEqual(conv.messages.count(), 2)

    def test_read_event_and_unknown_are_ignored(self):
        self.assertEqual(tiktok.handle_event(_event("im_mark_read_msg")), 0)
        self.assertEqual(tiktok.handle_event({"event": "something_else"}), 0)

    def test_share_post_becomes_text_with_link(self):
        ev = _event(mid="m-3", mtype="share_post", extra={"share_post": {"embed_url": "https://www.tiktok.com/embed/123"}})
        tiktok.handle_event(ev)
        m = Message.objects.get(external_id="m-3")
        self.assertIn("https://www.tiktok.com/embed/123", m.text)

    @patch("apps.inbox.tiktok._download_image", return_value="https://crm.wallcovdec.com.ua/api/f/abc/tiktok_m4.jpg")
    def test_incoming_image_is_attached(self, dl):
        ev = _event(mid="m-4", mtype="image", extra={"image": {"media_id": "media-9"}})
        tiktok.handle_event(ev)
        m = Message.objects.get(external_id="m-4")
        self.assertEqual(m.attachments[0]["type"], "photo")
        self.assertIn("/api/f/abc/", m.attachments[0]["url"])
        dl.assert_called_once()

    def test_inactive_channel_ignores_events(self):
        self.ch.is_active = False
        self.ch.save()
        self.assertEqual(tiktok.handle_event(_event()), 0)


class TiktokSignatureTests(TestCase):
    def test_signature_ok_and_bad(self):
        body = b'{"event":"im_receive_msg"}'
        with patch.object(tiktok, "APP_SECRET", "s3cret"):
            t = str(int(time.time()))
            sig = hmac.new(b"s3cret", (t + ".").encode() + body, hashlib.sha256).hexdigest()
            self.assertTrue(tiktok.verify_signature(body, "t=%s,s=%s" % (t, sig)))
            self.assertFalse(tiktok.verify_signature(body, "t=%s,s=deadbeef" % t))
            self.assertFalse(tiktok.verify_signature(body, ""))
            old = str(int(time.time()) - 3600)
            sig_old = hmac.new(b"s3cret", (old + ".").encode() + body, hashlib.sha256).hexdigest()
            self.assertFalse(tiktok.verify_signature(body, "t=%s,s=%s" % (old, sig_old)))

    def test_webhook_view_rejects_bad_signature_and_accepts_good(self):
        Channel.objects.create(kind="tiktok", name="TikTok · Direct",
                               config={"tiktok_direct": True, "business_id": BIZ})
        client = APIClient()
        body = json.dumps(_event(mid="m-v1")).encode()
        with patch.object(tiktok, "APP_SECRET", "s3cret"):
            r = client.post("/api/inbox/tiktok/webhook/", data=body, content_type="application/json",
                            HTTP_TIKTOK_SIGNATURE="t=1,s=bad")
            self.assertEqual(r.status_code, 401)
            t = str(int(time.time()))
            sig = hmac.new(b"s3cret", (t + ".").encode() + body, hashlib.sha256).hexdigest()
            r = client.post("/api/inbox/tiktok/webhook/", data=body, content_type="application/json",
                            HTTP_TIKTOK_SIGNATURE="t=%s,s=%s" % (t, sig))
            self.assertEqual(r.status_code, 200)
        self.assertTrue(Message.objects.filter(external_id="m-v1").exists())
        self.assertEqual(client.get("/api/inbox/tiktok/webhook/").status_code, 200)


class TiktokSendAndWindowTests(TestCase):
    def setUp(self):
        self.ch = Channel.objects.create(kind="tiktok", name="TikTok · Direct", config={
            "tiktok_direct": True, "business_id": BIZ, "access_token": "tok",
            "expires_at": (timezone.now() + timedelta(hours=12)).isoformat(),
            "refresh_token": "ref", "refresh_expires_at": (timezone.now() + timedelta(days=20)).isoformat(),
        })
        self.conv = Conversation.objects.create(channel=self.ch, external_chat_id="conv-w", title="x")

    def test_adapter_is_direct_for_direct_channel_and_chatplace_for_chatplace(self):
        from .adapters import get_adapter, ChatPlaceAdapter
        self.assertIsInstance(get_adapter(self.ch), tiktok.TiktokDirectAdapter)
        cp = Channel.objects.create(kind="tiktok", name="ChatPlace · TikTok", config={"chatplace": True})
        self.assertIsInstance(get_adapter(cp), ChatPlaceAdapter)

    def test_window_closed_without_incoming(self):
        st = tiktok.window_state(self.conv)
        self.assertFalse(st["open"])
        with self.assertRaises(RuntimeError):
            tiktok.TiktokDirectAdapter(self.ch).send("conv-w", "Привіт")

    def test_window_open_then_limit(self):
        Message.objects.create(conversation=self.conv, direction="in", text="q", external_id="in1")
        self.assertTrue(tiktok.window_state(self.conv)["open"])
        for i in range(10):
            Message.objects.create(conversation=self.conv, direction="out", text="a%d" % i, external_id="o%d" % i)
        st = tiktok.window_state(self.conv)
        self.assertFalse(st["open"])
        self.assertIn("10", st["reason"])

    def test_window_expired_after_48h(self):
        m = Message.objects.create(conversation=self.conv, direction="in", text="q", external_id="in2")
        Message.objects.filter(pk=m.pk).update(created_at=timezone.now() - timedelta(hours=49))
        self.assertFalse(tiktok.window_state(self.conv)["open"])

    @patch("apps.inbox.tiktok._request")
    def test_send_text_calls_api_and_returns_message_id(self, req):
        req.return_value = {"code": 0, "data": {"message": {"message_id": "sent-1"}}}
        Message.objects.create(conversation=self.conv, direction="in", text="q", external_id="in3")
        mid = tiktok.TiktokDirectAdapter(self.ch).send("conv-w", "Добрий день")
        self.assertEqual(mid, "sent-1")
        args, kwargs = req.call_args
        self.assertEqual(args[1], "/business/message/send/")
        self.assertEqual(kwargs["body"]["recipient"], "conv-w")
        self.assertEqual(kwargs["body"]["text"]["body"], "Добрий день")
        self.assertEqual(kwargs["token"], "tok")

    @patch("apps.inbox.tiktok._request")
    def test_token_refresh_when_expiring(self, req):
        self.ch.config["expires_at"] = (timezone.now() + timedelta(minutes=1)).isoformat()
        self.ch.save()
        req.return_value = {"code": 0, "data": {"access_token": "new-tok", "refresh_token": "new-ref",
                                                "expires_in": 86400, "refresh_token_expires_in": 2592000}}
        self.assertEqual(tiktok.valid_token(self.ch), "new-tok")
        self.ch.refresh_from_db()
        self.assertEqual(self.ch.config["access_token"], "new-tok")
        self.assertEqual(req.call_args[0][1], "/tt_user/oauth2/refresh_token/")

    def test_send_media_not_supported(self):
        with self.assertRaises(RuntimeError):
            tiktok.TiktokDirectAdapter(self.ch).send_media("conv-w", b"x", "a.jpg", "photo")


class TiktokViewsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser("owner", "o@x.ua", "pass")
        self.client_api = APIClient()
        self.client_api.force_authenticate(self.owner)

    def test_status_not_configured(self):
        with patch.object(tiktok, "APP_ID", ""), patch.object(tiktok, "APP_SECRET", ""):
            r = self.client_api.get("/api/inbox/tiktok/status/")
            self.assertEqual(r.status_code, 200)
            self.assertFalse(r.data["configured"])
            self.assertFalse(r.data["connected"])
            r = self.client_api.post("/api/inbox/tiktok/connect/", {})
            self.assertEqual(r.status_code, 400)

    def test_connect_returns_authorize_url(self):
        with patch.object(tiktok, "APP_ID", "app123"), patch.object(tiktok, "APP_SECRET", "sec"):
            r = self.client_api.post("/api/inbox/tiktok/connect/", {})
            self.assertEqual(r.status_code, 200)
            self.assertIn("https://www.tiktok.com/v2/auth/authorize?", r.data["url"])
            self.assertIn("client_key=app123", r.data["url"])
            self.assertIn(urllib.parse.quote(",".join(tiktok.SCOPES), safe=""), r.data["url"].replace("%2C", "%2C"))

    def test_connect_requires_manage_permission(self):
        from apps.accounts.models import Role
        role = Role.objects.create(name="Менеджер-тест", permissions=[])
        u = User.objects.create_user("mgr", "m@x.ua", "pass")
        u.role = role
        u.save()
        c = APIClient()
        c.force_authenticate(u)
        self.assertEqual(c.post("/api/inbox/tiktok/connect/", {}).status_code, 403)

    @patch("apps.inbox.tiktok.register_webhook", return_value={"code": 0})
    @patch("apps.inbox.tiktok.business_profile", return_value={"username": "dekor_dlia_stin", "display_name": "Wallcov", "profile_image": ""})
    @patch("apps.inbox.tiktok.exchange_code")
    def test_callback_creates_channel_and_redirects(self, ex, prof, wh):
        ex.return_value = {"business_id": BIZ, "access_token": "a", "refresh_token": "r",
                           "expires_at": (timezone.now() + timedelta(hours=24)).isoformat(),
                           "refresh_expires_at": (timezone.now() + timedelta(days=30)).isoformat(), "scope": "x"}
        state = tiktok.make_state(self.owner.id)
        r = APIClient().get("/api/inbox/tiktok/callback/", {"code": "abc", "state": state})
        self.assertEqual(r.status_code, 302)
        self.assertIn("tiktok=connected", r["Location"])
        ch = tiktok.get_channel()
        self.assertIsNotNone(ch)
        self.assertEqual(ch.config["username"], "dekor_dlia_stin")
        self.assertEqual(ch.config["business_id"], BIZ)
        self.assertTrue(ch.config["webhook_registered"])
        # повторний callback оновлює той самий канал, а не створює другий
        APIClient().get("/api/inbox/tiktok/callback/", {"code": "abc2", "state": tiktok.make_state(self.owner.id)})
        self.assertEqual(Channel.objects.filter(kind="tiktok", config__tiktok_direct=True).count(), 1)

    def test_callback_rejects_bad_state(self):
        r = APIClient().get("/api/inbox/tiktok/callback/", {"code": "abc", "state": "forged"})
        self.assertEqual(r.status_code, 403)


class TiktokCommentsTests(TestCase):
    """Коментарі під відео → Чати: базова лінія, нові коментарі, echo, відповідь з CRM."""

    def setUp(self):
        self.ch = Channel.objects.create(kind="tiktok", name="TikTok · Direct", config={
            "tiktok_direct": True, "business_id": BIZ, "access_token": "tok",
            "expires_at": (timezone.now() + timedelta(hours=12)).isoformat(),
            "refresh_token": "ref", "refresh_expires_at": (timezone.now() + timedelta(days=20)).isoformat(),
        })
        self.video_page = {"code": 0, "data": {"videos": [
            {"item_id": "v1", "caption": "Мокрий шовк", "thumbnail_url": "https://t/1.jpg",
             "share_url": "https://www.tiktok.com/@dekor_dlia_stin/video/v1", "comments": 2}]}}

    @patch("apps.inbox.tiktok._request")
    def test_first_run_only_baselines(self, req):
        comments = {"code": 0, "data": {"has_more": False, "comments": [
            {"comment_id": "c9", "create_time": 500, "text": "стара історія", "owner": False,
             "username": "old_user", "display_name": "Old", "user_id": "u9", "video_id": "v1"}]}}
        req.side_effect = [self.video_page, comments]
        out = tiktok.poll_comments()
        self.assertEqual((out["new_comments"], out["baselined"]), (0, 1))
        self.ch.refresh_from_db()
        self.assertEqual(self.ch.config["tt_comment_state"]["v1"], 500)
        self.assertFalse(Conversation.objects.filter(external_chat_id__startswith="comment:tiktok:").exists())

    @patch("apps.inbox.tiktok._request")
    def test_new_comments_ingested_with_lead_and_echo(self, req):
        self.ch.config["tt_comment_state"] = {"v1": 100}
        self.ch.save()
        comments = {"code": 0, "data": {"has_more": False, "comments": [
            {"comment_id": "c2", "create_time": 200, "text": "Скільки коштує?", "owner": False,
             "username": "olena_x", "display_name": "Olena", "user_id": "u1", "video_id": "v1"},
            {"comment_id": "c1", "create_time": 150, "text": "Дякуємо за інтерес!", "owner": True,
             "username": "dekor_dlia_stin", "display_name": "Wallcov", "user_id": "biz", "video_id": "v1"},
        ]}}
        req.side_effect = [self.video_page, comments]
        out = tiktok.poll_comments()
        self.assertEqual(out["new_comments"], 2)
        conv = Conversation.objects.get(external_chat_id="comment:tiktok:v1:olena_x")
        self.assertEqual(conv.unread, 1)
        self.assertEqual(conv.config["source_card"]["platform"], "tiktok")
        self.assertEqual(conv.config["source_card"]["media_id"], "v1")
        m_in = conv.messages.get(external_id="c2")
        self.assertEqual((m_in.direction, m_in.sender_name), ("in", "olena_x"))
        self.assertEqual(Lead.objects.filter(contact=conv.contact, source="tiktok").count(), 1)
        conv_own = Conversation.objects.get(external_chat_id="comment:tiktok:v1:dekor_dlia_stin")
        out_msg = conv_own.messages.get()
        self.assertEqual((out_msg.direction, out_msg.sender_name), ("out", "ai_assistant"))
        self.ch.refresh_from_db()
        req.side_effect = [self.video_page, comments]
        self.assertEqual(tiktok.poll_comments()["new_comments"], 0)

    @patch("apps.inbox.tiktok._request")
    def test_adapter_replies_to_last_client_comment(self, req):
        conv = Conversation.objects.create(channel=self.ch, external_chat_id="comment:tiktok:v1:olena_x",
                                           title="Olena")
        Message.objects.create(conversation=conv, direction="in", text="Скільки коштує?", external_id="c2")
        req.return_value = {"code": 0, "data": {"comment_id": "r1"}}
        rid = tiktok.TiktokDirectAdapter(self.ch).send("comment:tiktok:v1:olena_x", "Відповідь")
        self.assertEqual(rid, "r1")
        args, kwargs = req.call_args
        self.assertEqual(args[1], "/business/comment/reply/create/")
        self.assertEqual(kwargs["body"]["video_id"], "v1")
        self.assertEqual(kwargs["body"]["comment_id"], "c2")

    def test_adapter_comment_reply_without_incoming_raises(self):
        with self.assertRaises(RuntimeError):
            tiktok.TiktokDirectAdapter(self.ch).send("comment:tiktok:v1:nobody", "Hi")
