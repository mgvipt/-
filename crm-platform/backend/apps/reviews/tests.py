"""Відгуки (12.09.2026): журнал без відправки, правила, API магазину, модерація.
Лише ізольована тестова БД; send_message підмінено — жодних зовнішніх запитів і повідомлень."""
import base64
import hashlib
import hmac
import io
import json
import time
import uuid
from datetime import time as dtime, timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.crm.models import ActivityLog, Contact, Deal, DealItem, Funnel, Stage, Task
from apps.inbox.models import Channel, Conversation, Message
from apps.warehouse.models import Product
from .models import Review, ReviewOptOut, ReviewPhoto, ReviewRequest, ReviewSettings
from .services import new_code, review_link, run_sweep

SECRET = "test-only-secret"


def _signed(client, path, payload, secret=SECRET, ts=None):
    body = json.dumps(payload, ensure_ascii=False).encode()
    ts = str(ts or int(time.time()))
    sig = hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    return client.post("/api/integrations/shop/reviews/%s/" % path, data=body, content_type="application/json",
                       HTTP_X_WALLCOV_TIMESTAMP=ts, HTTP_X_WALLCOV_SIGNATURE=sig)


def _jpeg_with_exif():
    image = Image.new("RGB", (64, 48), "red")
    exif = Image.Exif()
    exif[0x010F] = "TestCam"
    exif[0x0110] = "Secret Model"
    buf = io.BytesIO()
    image.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


class _Base(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.main = Funnel.objects.create(name="21 Основний продукт")
        Stage.objects.create(funnel=self.main, name="Нова", order=0)
        self.recv = Stage.objects.create(funnel=self.main, name="Отримано", order=13)
        Stage.objects.create(funnel=self.main, name="Успішна угода", order=14, is_won=True)
        self.testf = Funnel.objects.create(name="22 Тестовий набір")
        self.test_recv = Stage.objects.create(funnel=self.testf, name="Отримано", order=13)
        self.tech = Funnel.objects.create(name="Техническая(Тесты)")
        self.tech_stage = Stage.objects.create(funnel=self.tech, name="Новая", order=0)
        self.viber = Channel.objects.create(kind="echat", name="Viber test", config={"echat": True})
        self.wa = Channel.objects.create(kind="echat_whatsapp", name="WA test", config={"echat_whatsapp": True})
        self.ig = Channel.objects.create(kind="instagram", name="IG test", config={})
        cfg = ReviewSettings.get()
        cfg.start_date = (self.now - timedelta(days=40)).date()
        cfg.save()
        self.manager = User.objects.create_user(username="test-manager-reviews")

    def contact(self, phone="+380970000041", **kw):
        return Contact.objects.create(first_name="Олена", last_name="Тестова", phone=phone, **kw)

    def deal(self, contact, funnel=None, stage=None, days=11):
        deal = Deal.objects.create(title="test only", contact=contact, funnel=funnel or self.main,
                                   stage=stage or self.recv, ttn="20450000000001", amount=1000)
        at = self.now - timedelta(days=days)
        log = ActivityLog.objects.create(kind="deal", object_id=deal.id, action="Авто-стадія",
                                         detail="НП_В дорозі → Отримано (НП: test)")
        ActivityLog.objects.filter(pk=log.pk).update(created_at=at)
        Deal.objects.filter(pk=deal.pk).update(stage_changed_at=at)
        return deal

    def conv(self, contact, channel, ext="380970000041"):
        return Conversation.objects.create(channel=channel, contact=contact, external_chat_id=ext)

    def msg(self, conv, direction, hours_ago, sender=None, text="test"):
        message = Message.objects.create(conversation=conv, direction=direction, text=text, sender=sender)
        Message.objects.filter(pk=message.pk).update(created_at=self.now - timedelta(hours=hours_ago))
        return message

    def sweep(self, **kw):
        with patch("apps.inbox.services.send_message", side_effect=AssertionError("no sending in tests")) as mocked:
            stats = run_sweep(now=kw.pop("now", self.now), **kw)
        return stats, mocked


class SweepTests(_Base):
    def test_main_order_after_10_days_goes_to_journal_without_sending(self):
        c = self.contact()
        d = self.deal(c)
        viber = self.conv(c, self.viber)
        self.msg(viber, "in", 24 * 20)
        self.msg(viber, "out", 24 * 19)
        stats, mocked = self.sweep()
        req = ReviewRequest.objects.get(deal=d)
        self.assertEqual((req.kind, req.status), ("main", "would_send"))
        self.assertIn("Viber — діалог уже є", req.reason)
        self.assertIn("відправка вимкнена", req.reason)
        self.assertEqual(req.conversation, viber)
        mocked.assert_not_called()
        self.assertEqual(Message.objects.count(), 2)
        self.assertEqual(Task.objects.count(), 0)
        self.assertEqual(stats["live"], 0)

    def test_main_order_is_not_due_before_10_days(self):
        d = self.deal(self.contact(), days=5)
        self.sweep()
        req = ReviewRequest.objects.get(deal=d)
        self.assertEqual(req.status, "scheduled")
        self.assertGreater(req.due_at, self.now + timedelta(days=4))

    def test_received_before_start_date_is_never_asked(self):
        cfg = ReviewSettings.get()
        cfg.start_date = timezone.localtime(self.now).date()
        cfg.save()
        d = self.deal(self.contact(), days=11)
        self.sweep()
        self.assertFalse(ReviewRequest.objects.filter(deal=d).exists())

    def test_test_kit_after_5_days_waits_while_manager_is_selling(self):
        c = self.contact()
        d = self.deal(c, funnel=self.testf, stage=self.test_recv, days=6)
        viber = self.conv(c, self.viber)
        self.msg(viber, "in", 70)
        last = self.msg(viber, "out", 20, sender=self.manager)
        self.sweep()
        req = ReviewRequest.objects.get(deal=d)
        self.assertEqual((req.kind, req.status), ("test", "waiting"))
        self.assertIn("менеджер", req.reason)
        Message.objects.filter(pk=last.pk).update(created_at=self.now - timedelta(hours=60))
        self.sweep()
        req.refresh_from_db()
        self.assertEqual(req.status, "would_send")

    def test_test_kit_is_skipped_when_main_order_follows(self):
        c = self.contact()
        d = self.deal(c, funnel=self.testf, stage=self.test_recv, days=6)
        Deal.objects.create(title="main after test", contact=c, funnel=self.main,
                            stage=Stage.objects.get(funnel=self.main, name="Нова"))
        self.sweep()
        req = ReviewRequest.objects.get(deal=d)
        self.assertEqual(req.status, "skipped")
        self.assertIn("основне замовлення", req.reason)

    def test_one_request_per_client_in_60_days(self):
        c = self.contact()
        self.deal(c)
        self.deal(c)
        self.sweep()
        self.assertEqual(sorted(ReviewRequest.objects.filter(contact=c).values_list("status", flat=True)),
                         ["skipped", "would_send"])

    def test_opted_out_and_staff_are_never_asked(self):
        c1 = self.contact()
        ReviewOptOut.objects.create(contact=c1, reason="manual")
        d1 = self.deal(c1)
        c2 = self.contact(phone="+380970000042", kinds=["staff"])
        d2 = self.deal(c2)
        self.sweep()
        self.assertEqual(ReviewRequest.objects.get(deal=d1).status, "opted_out")
        self.assertEqual(ReviewRequest.objects.get(deal=d2).status, "skipped")

    def test_instagram_only_inside_24h_window_otherwise_by_phone(self):
        c = self.contact(phone="")
        d = self.deal(c)
        ig = self.conv(c, self.ig, ext="ig-test-1")
        self.msg(ig, "in", 72)
        self.msg(ig, "out", 71)
        self.sweep()
        req = ReviewRequest.objects.get(deal=d)
        self.assertEqual(req.status, "waiting")
        self.assertIn("вікно 24 год закрите", req.reason)
        self.msg(ig, "in", 2)
        self.msg(ig, "out", 1)
        self.sweep()
        req.refresh_from_db()
        self.assertEqual(req.status, "would_send")
        self.assertIn("Instagram — клієнт писав менше 24 год тому", req.reason)
        c2 = self.contact(phone="+380970000043")
        d2 = self.deal(c2)
        ig2 = self.conv(c2, self.ig, ext="ig-test-2")
        self.msg(ig2, "in", 24 * 9)
        self.sweep()
        self.assertIn("WhatsApp — новий діалог за номером", ReviewRequest.objects.get(deal=d2).reason)

    def test_client_waiting_for_answer_is_not_interrupted(self):
        c = self.contact()
        d = self.deal(c)
        viber = self.conv(c, self.viber)
        self.msg(viber, "in", 5, text="А коли буде знижка?")
        self.sweep()
        req = ReviewRequest.objects.get(deal=d)
        self.assertEqual(req.status, "waiting")
        self.assertIn("чекає відповіді", req.reason)

    def test_live_mode_sends_only_to_allowlist_and_stop_opts_out(self):
        cfg = ReviewSettings.get()
        cfg.send_enabled, cfg.texts_approved = True, True
        cfg.text_main = "{імʼя}, як вам {матеріал}? {посилання}"
        cfg.text_test = "Тест {посилання}"
        cfg.text_remind = "Нагадаю {посилання}"
        cfg.send_from, cfg.send_to = dtime(0, 0), dtime(23, 59, 59)
        ok = self.contact()
        d_ok = self.deal(ok)
        viber = self.conv(ok, self.viber)
        self.msg(viber, "in", 48)
        self.msg(viber, "out", 47)
        other = self.contact(phone="+380970000044")
        d_other = self.deal(other)
        cfg.allowlist_contact_ids = [ok.id]
        cfg.save()
        sent = []

        def fake_send(conv, text, user=None):
            sent.append((conv.id, text))
            return Message.objects.create(conversation=conv, direction="out", text=text)

        with patch("apps.inbox.services.send_message", side_effect=fake_send):
            run_sweep(now=self.now)
        req = ReviewRequest.objects.get(deal=d_ok)
        self.assertEqual(req.status, "sent")
        self.assertEqual(len(sent), 1)
        self.assertIn(review_link(req.code), sent[0][1])
        self.assertTrue(sent[0][1].startswith("Олена"))
        self.assertEqual(ReviewRequest.objects.get(deal=d_other).status, "would_send")
        Message.objects.create(conversation=viber, direction="in", text="Стоп, не пишіть мені")
        with patch("apps.inbox.services.send_message", side_effect=fake_send):
            run_sweep(now=self.now + timedelta(minutes=5))
        req.refresh_from_db()
        self.assertEqual(req.status, "opted_out")
        self.assertTrue(ReviewOptOut.objects.filter(contact=ok).exists())
        self.assertEqual(len(sent), 1)

    def test_settings_api_cannot_enable_sending(self):
        owner = User.objects.create_user(username="test-owner-reviews", is_superuser=True)
        client = APIClient()
        client.force_authenticate(owner)
        self.assertEqual(client.patch("/api/reviews/settings/", {"send_enabled": True}, format="json").status_code, 400)
        self.assertFalse(ReviewSettings.get().send_enabled)
        response = client.patch("/api/reviews/settings/", {"delay_main_days": 14}, format="json")
        self.assertEqual((response.status_code, response.json()["delay_main_days"]), (200, 14))
        self.assertEqual(client.get("/api/reviews/requests/").json()["send_enabled"], False)
        manager = APIClient()
        manager.force_authenticate(self.manager)
        self.assertEqual(manager.get("/api/reviews/").status_code, 403)


@override_settings(SHOP_WEBHOOK_SECRET=SECRET)
class ShopApiTests(_Base):
    def setUp(self):
        super().setUp()
        self.product = Product.objects.create(name="Мокрий шовк Сирена (тест)", shop_slug="mokryi-shovk")
        self.other = Product.objects.create(name="Лак (тест)")
        c = self.contact()
        self.test_deal = Deal.objects.create(title="ТЕСТ", contact=c, funnel=self.tech, stage=self.tech_stage, amount=0)
        DealItem.objects.create(deal=self.test_deal, product=self.product, quantity=2, price=500)
        DealItem.objects.create(deal=self.test_deal, product=self.other, quantity=1, price=100)
        self.req = ReviewRequest.objects.create(deal=self.test_deal, contact=c, kind="manual", status="test", is_test=True,
                                                code=new_code(), expires_at=self.now + timedelta(days=60))
        self.owner = User.objects.create_user(username="test-owner-moderator", is_superuser=True)
        self.staff = APIClient()
        self.staff.force_authenticate(self.owner)

    def submit(self, code=None, **kw):
        body = {"event_uuid": str(uuid.uuid4()), "code": code or self.req.code, "rating": 5,
                "text": "Нанесла сама, дуже гарно", "room": "bedroom", "applied_by": "self",
                "consent_site": True, "consent_version": "2026-09-12", "product_ids": [self.product.id]}
        body.update(kw)
        return _signed(self.client, "submit", body), body

    def test_ping_requires_signature(self):
        self.assertEqual(_signed(self.client, "ping", {}).status_code, 200)
        self.assertEqual(self.client.post("/api/integrations/shop/reviews/ping/", data="{}",
                                          content_type="application/json").status_code, 403)
        self.assertEqual(_signed(self.client, "ping", {}, secret="wrong").json()["code"], "bad_signature")
        self.assertEqual(_signed(self.client, "ping", {}, ts=int(time.time()) - 900).status_code, 403)

    def test_invite_gives_first_name_and_products_only(self):
        response = _signed(self.client, "invite", {"code": self.req.code, "mark_opened": True})
        self.assertEqual(response.status_code, 200, response.content)
        invite = response.json()["invite"]
        self.assertEqual((invite["status"], invite["can_submit"], invite["is_test"], invite["first_name"]),
                         ("active", True, True, "Олена"))
        self.assertEqual(invite["suggested_display_name"], "Олена Т.")
        self.assertEqual(invite["products"][0], {"crm_product_id": self.product.id, "name": self.product.name,
                                                 "shop_slug": "mokryi-shovk", "is_primary": True})
        self.assertEqual(invite["google_review_url"], "https://g.page/r/CVZX_3B9PYFbEBM/review")
        self.assertNotIn("0970000041", response.content.decode())
        self.req.refresh_from_db()
        self.assertIsNotNone(self.req.opened_at)
        self.assertEqual(_signed(self.client, "invite", {"code": "AAAAAAAAAAAA"}).status_code, 404)
        journal = ReviewRequest.objects.create(contact=self.req.contact, kind="main", status="would_send", code=new_code())
        self.assertEqual(_signed(self.client, "invite", {"code": journal.code}).status_code, 404)

    def test_submit_strips_exif_and_is_idempotent(self):
        raw = _jpeg_with_exif()
        with Image.open(io.BytesIO(raw)) as original:
            self.assertTrue(len(original.getexif()) > 0)
        response, body = self.submit(photos=[{"data": base64.b64encode(raw).decode(), "content_type": "image/jpeg"}])
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual((data["status"], data["thank_you"], data["duplicate"]), ("pending", "positive", False))
        review = Review.objects.get(pk=data["review_id"])
        with Image.open(io.BytesIO(bytes(review.photos.get().data))) as stored:
            self.assertEqual(len(stored.getexif()), 0)
            self.assertNotIn("exif", stored.info)
        self.assertEqual(review.products[0]["crm_product_id"], self.product.id)
        again = _signed(self.client, "submit", body)
        self.assertEqual((again.status_code, again.json()["duplicate"], again.json()["review_id"]), (200, True, review.id))
        second, _ = self.submit()
        self.assertEqual((second.status_code, second.json()["code"]), (409, "already_submitted"))
        self.assertEqual((Review.objects.count(), Task.objects.count()), (1, 0))
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, "submitted")

    def test_validation_errors_create_nothing(self):
        self.assertEqual(self.submit(rating=6)[0].json()["field"], "rating")
        self.assertEqual(self.submit(product_ids=[999999])[0].json()["field"], "product_ids")
        self.assertEqual(self.submit(photos=[{"data": "bm90LWFuLWltYWdl"}])[0].json()["field"], "photos")
        self.assertEqual(self.submit(event_uuid="x")[0].json()["field"], "event_uuid")
        self.assertEqual(self.submit(consent_site="yes")[0].json()["field"], "consent_site")
        self.assertEqual(Review.objects.count(), 0)

    def test_low_rating_creates_high_priority_task(self):
        response, _ = self.submit(rating=2, text="Колір не той")
        self.assertEqual(response.json()["thank_you"], "negative")
        task = Task.objects.get()
        self.assertEqual(task.priority, "high")
        self.assertIn("2★", task.title)
        self.assertTrue(task.title.startswith("ТЕСТ"))
        self.assertEqual(Review.objects.get().task, task)

    def test_moderation_and_published_feed(self):
        response, _ = self.submit(photos=[{"data": base64.b64encode(_jpeg_with_exif()).decode()}])
        review_id = response.json()["review_id"]

        def feed(**kw):
            return _signed(self.client, "published", {"include_test": True, **kw}).json()

        self.assertEqual(feed()["reviews"], [])
        listing = self.staff.get("/api/reviews/?status=pending").json()
        self.assertEqual(listing["counts"]["pending"], 1)
        token = ReviewPhoto.objects.get().token
        self.assertEqual(self.client.get(listing["results"][0]["photos"][0]["url"]).status_code, 200)
        self.assertEqual(self.client.get("/api/reviews/photo/%s/" % token).status_code, 404)
        moderate = "/api/reviews/%s/moderate/" % review_id
        self.assertEqual(self.staff.post(moderate, {"action": "reply", "reply_text": "Дякуємо!"}, format="json").status_code, 200)
        published = self.staff.post(moderate, {"action": "publish"}, format="json")
        self.assertEqual((published.status_code, published.json()["status"]), (200, "published"))
        data = feed()
        item = data["reviews"][0]
        self.assertEqual((item["status"], item["text"], item["reply"]["text"], item["display_name"]),
                         ("published", "Нанесла сама, дуже гарно", "Дякуємо!", "Олена Т."))
        self.assertTrue(item["verified_purchase"])
        self.assertEqual(len(item["photos"]), 1)
        self.assertEqual(self.client.get("/api/reviews/photo/%s/" % token).status_code, 200)
        self.assertEqual(feed(include_test=False)["reviews"], [])
        self.staff.post(moderate, {"action": "hide", "reason": "тест"}, format="json")
        removed = feed(updated_since=data["server_time"])["reviews"]
        self.assertEqual(len(removed), 1)
        self.assertEqual((removed[0]["review_id"], removed[0]["status"]), (review_id, "removed"))
        self.assertNotIn("text", removed[0])
        self.assertEqual(self.client.get("/api/reviews/photo/%s/" % token).status_code, 404)

    def test_publish_requires_consent_and_text(self):
        response, _ = self.submit(consent_site=False)
        moderate = "/api/reviews/%s/moderate/" % response.json()["review_id"]
        self.assertEqual(self.staff.post(moderate, {"action": "publish"}, format="json").status_code, 400)
        second = ReviewRequest.objects.create(deal=self.test_deal, contact=self.req.contact, kind="manual", status="test",
                                              is_test=True, code=new_code(), expires_at=self.now + timedelta(days=60))
        response, _ = self.submit(code=second.code, text="")
        moderate = "/api/reviews/%s/moderate/" % response.json()["review_id"]
        self.assertEqual(self.staff.post(moderate, {"action": "publish"}, format="json").status_code, 400)
        self.assertEqual(Review.objects.filter(status="published").count(), 0)

    def test_sweep_never_touches_test_links(self):
        self.sweep()
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, "test")
