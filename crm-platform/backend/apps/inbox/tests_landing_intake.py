import base64
import io
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase, TransactionTestCase, override_settings
from django.db import connections
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.core.cache import cache
from rest_framework.test import APIRequestFactory, force_authenticate
from types import SimpleNamespace
from django.utils import timezone
from PIL import Image
from apps.accounts.models import User
from apps.crm.models import Contact, Deal, Funnel, Stage, Task, Payment
from apps.crm.landing_metrics import landing_report, source_kind
from .models import Channel, Conversation, Message, LandingSubmission, Notification
from .landing_intake import receive, attach_photos
from .webchat import WebChatView, _token, _rate_ok


class LandingIntakeTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="test-intake-owner", is_superuser=True)
        self.funnel = Funnel.objects.create(name="Лендинг · wallcovdliastin.com.ua")
        self.stage = Stage.objects.create(funnel=self.funnel, name="Нова")
        self.channel = Channel.objects.create(kind="web", name="test", config={"web_chat": True})
        self.conv = Conversation.objects.create(channel=self.channel, external_chat_id="test-only", status="closed")
        self.data = dict(submission_id="test-request-a", phone="0970000012", name="Тест", consent=True,
                         room="Спальня", area=30, product="sirena", preferred="viber", analytics={"fbclid": "test123"})

    def test_receipt_task_owner_notification_and_reopen_are_atomic(self):
        result = receive(self.conv, self.data)
        deal = Deal.objects.get(pk=result["deal_id"])
        self.assertEqual(deal.owner, self.owner)
        self.assertEqual(deal.amount, Decimal("5692.50"))
        self.assertEqual(deal.qualification["volume_kg"], "4.500")
        self.assertEqual(deal.qualification["utm"]["fbclid"], "test123")
        self.assertEqual(Task.objects.filter(deal=deal).count(), 1)
        self.assertEqual(Notification.objects.filter(user=self.owner).count(), 1)
        self.conv.refresh_from_db()
        self.assertEqual(self.conv.status, "open")
        self.assertEqual(self.conv.unread, 1)

    def test_retry_after_move_keeps_deal_and_task(self):
        first = receive(self.conv, self.data)
        new = Funnel.objects.create(name="Sample")
        Deal.objects.filter(pk=first["deal_id"]).update(funnel=new)
        second = receive(self.conv, self.data)
        self.assertEqual(first["deal_id"], second["deal_id"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(Task.objects.count(), 1)
        other = receive(self.conv, {**self.data, "submission_id": "test-request-b"})
        self.assertNotEqual(other["deal_id"], first["deal_id"])
        self.assertEqual(Contact.objects.count(), 1)

    def test_same_request_different_parameters_is_not_a_new_deal(self):
        receive(self.conv, self.data)
        with self.assertRaises(ValueError):
            receive(self.conv, {**self.data, "area": 45})
        self.assertEqual(Deal.objects.count(), 1)

    def test_task_failure_rolls_back_lead_and_contact(self):
        with patch("apps.inbox.landing_intake.Task.objects.create", side_effect=RuntimeError("test-only")):
            with self.assertRaises(RuntimeError):
                receive(self.conv, self.data)
        self.assertEqual(Deal.objects.count(), 0)
        self.assertEqual(Contact.objects.count(), 0)
        self.assertEqual(LandingSubmission.objects.count(), 0)

    def test_unknown_area_product_and_sample_keep_intent(self):
        result = receive(self.conv, {**self.data, "area": None, "product": ""})
        self.assertEqual(result["estimate_from"], 0)
        sample = receive(self.conv, {**self.data, "submission_id": "sample-test", "intent": "sample", "area": None})
        self.assertEqual(Deal.objects.get(pk=sample["deal_id"]).qualification["intent"], "sample")
        self.assertEqual(sample["estimate_from"], 220)

    def test_velvet_matches_frontend_minimum(self):
        result = receive(self.conv, {**self.data, "product": "luna", "area": 20})
        self.assertEqual(result["estimate_from"], 3900)
        self.assertEqual(result["estimate_to"], 3900)

    def test_invalid_phone_nan_and_photos_do_not_create_deals(self):
        for change in ({"phone": "123"}, {"area": "NaN"}, {"photos": [{"data": "aGVsbG8="}]}):
            with self.assertRaises(ValueError):
                receive(self.conv, {**self.data, **change})
        self.assertEqual(Deal.objects.count(), 0)

    def test_photos_idempotent_and_bound_to_receipt(self):
        image = Image.new("RGB", (20, 20), "white")
        f = io.BytesIO(); image.save(f, format="JPEG")
        photos = [{"data": base64.b64encode(f.getvalue()).decode()}]
        first = receive(self.conv, {**self.data, "photos": photos})
        self.assertEqual(first["photo_count"], 1)
        result = attach_photos(self.conv, {"submission_id": self.data["submission_id"], "photos": photos})
        self.assertEqual(result["photo_count"], 1)
        stranger = Conversation.objects.create(channel=self.channel, external_chat_id="stranger")
        with self.assertRaises(ValueError):
            attach_photos(stranger, {"submission_id": self.data["submission_id"], "photos": photos})

    def test_report_includes_moves_and_does_not_cap_totals(self):
        first = receive(self.conv, self.data)
        moved = Funnel.objects.create(name="Sample")
        Deal.objects.filter(pk=first["deal_id"]).update(funnel=moved)
        for n in range(101):
            Deal.objects.create(title="isolated test", funnel=self.funnel, stage=self.stage)
        rows, summary = landing_report(timezone.now().date(), timezone.now().date())
        self.assertEqual(summary["total"], 102)
        self.assertEqual(len(rows), 100)
        self.assertEqual(summary["from_ads"], 0)
        self.assertEqual(summary["sources"]["meta_click_unconfirmed"], 1)
        self.assertEqual(source_kind({"utm_medium": "paid_social"}), "paid")

    def test_existing_client_owner_wins_over_chat_queue(self):
        owner = User.objects.create_user(username="existing-client-owner")
        Contact.objects.create(first_name="Test only", phone="+380970000012", owner=owner)
        self.conv.assigned_to = self.owner
        self.conv.save()
        result = receive(self.conv, self.data)
        self.assertEqual(Deal.objects.get(pk=result["deal_id"]).owner_id, owner.pk)

    def test_only_real_outgoing_human_message_records_response(self):
        receive(self.conv, self.data)
        self.conv.refresh_from_db()
        Message.objects.create(conversation=self.conv, direction="out", text="Automated")
        Message.objects.create(conversation=self.conv, direction="out", text="Internal", internal=True, sender=self.owner)
        self.assertIsNone(LandingSubmission.objects.get().responded_at)
        Message.objects.create(conversation=self.conv, direction="out", text="Human response in isolated database", sender=self.owner)
        self.assertIsNotNone(LandingSubmission.objects.get().responded_at)

    def test_accept_task_records_acceptance_but_not_response(self):
        from apps.crm.views import TaskViewSet
        receive(self.conv, self.data)
        receipt = LandingSubmission.objects.get()
        request = APIRequestFactory().post("/test-only/accept/", {}, format="json")
        force_authenticate(request, user=self.owner)
        response = TaskViewSet.as_view({"post": "accept"})(request, pk=receipt.task_id)
        self.assertEqual(response.status_code, 200)
        receipt.refresh_from_db()
        self.assertIsNotNone(receipt.accepted_at)
        self.assertIsNone(receipt.responded_at)
        Task.objects.filter(pk=receipt.task_id).update(status="done")
        repeat = APIRequestFactory().post("/test-only/accept/", {}, format="json")
        force_authenticate(repeat, user=self.owner)
        response = TaskViewSet.as_view({"post": "accept"})(repeat, pk=receipt.task_id)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Task.objects.get(pk=receipt.task_id).status, "done")

    @override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
    def test_endpoint_receipt_and_retry_are_confirmed(self):
        cache.clear()
        factory = APIRequestFactory()
        view = WebChatView.as_view()
        request = factory.post("/test-only/", {**self.data, "action": "lead", "token": _token(self.conv)}, format="json")
        first = view(request)
        self.assertEqual(first.status_code, 200)
        request = factory.post("/test-only/", {**self.data, "action": "lead", "token": _token(self.conv)}, format="json")
        second = view(request)
        self.assertEqual(first.data["deal_id"], second.data["deal_id"])
        self.assertTrue(second.data["duplicate"])

    @override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
    def test_rate_limit_isolated_by_verified_session(self):
        cache.clear()
        another = Conversation.objects.create(channel=self.channel, external_chat_id="other-rate-test")
        request = SimpleNamespace(META={"REMOTE_ADDR": "127.0.0.1"}, data={"token": _token(self.conv)})
        second = SimpleNamespace(META=request.META, data={"token": _token(another)})
        for _ in range(30):
            self.assertTrue(_rate_ok(request, "poll"))
        self.assertFalse(_rate_ok(request, "poll"))
        self.assertTrue(_rate_ok(second, "poll"))


class LandingConcurrencyTests(TransactionTestCase):
    def test_two_simultaneous_posts_have_one_receipt_deal_and_contact(self):
        User.objects.create_user(username="isolated-concurrency-owner", is_superuser=True)
        funnel = Funnel.objects.create(name="Лендинг · wallcovdliastin.com.ua")
        Stage.objects.create(funnel=funnel, name="Нова")
        channel = Channel.objects.create(kind="web", name="concurrency-only", config={"web_chat": True})
        conv = Conversation.objects.create(channel=channel, external_chat_id="concurrent-test")
        barrier = Barrier(2)
        data = dict(submission_id="concurrent-test-only", phone="0970000012", consent=True, product="sirena", area=30)
        def submit():
            connections.close_all()
            try:
                own = Conversation.objects.get(pk=conv.pk)
                barrier.wait(timeout=5)
                return receive(own, data)
            finally:
                connections.close_all()
        # Isolated DB only. Never enqueue production CAPI/events from a test commit.
        with patch("django.db.transaction.on_commit"), patch("urllib.request.urlopen", side_effect=AssertionError("External request in test")):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(submit) for _ in range(2)]
                results = [f.result(timeout=15) for f in futures]
        self.assertEqual(results[0]["deal_id"], results[1]["deal_id"])
        self.assertEqual(Deal.objects.count(), 1)
        self.assertEqual(Contact.objects.count(), 1)
        self.assertEqual(Task.objects.count(), 1)
        self.assertEqual(LandingSubmission.objects.count(), 1)
