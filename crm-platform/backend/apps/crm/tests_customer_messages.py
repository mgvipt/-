from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from apps.crm.models import Deal, GlobalRule, Funnel, Stage
from apps.inbox.models import Message, QuickReply
from apps.integrations.models import IntegrationSettings
from apps.warehouse.models import Product
from apps.reviews.models import ReviewSettings
from . import customer_messages as cm
from .pattera_masterclass import RULE_TITLE, REPLY_TITLE, URL
from .views import DealViewSet, requisites_text
from apps.inbox.views import MediaLibraryView


class CustomerMessageMirrorTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username="message-mirror-qa", is_superuser=True, is_staff=True)
        self.factory = APIRequestFactory()
        self.funnel = Funnel.objects.create(name="Synthetic")
        self.stage = Stage.objects.create(funnel=self.funnel, name="Synthetic", order=0)

    def card(self, key):
        return next(c for c in cm.reference()["cards"] if c["key"] == key)

    def test_reference_is_read_only_and_does_not_send(self):
        before = (QuickReply.objects.count(), Message.objects.count(), ReviewSettings.objects.count())
        with patch("apps.inbox.services.send_message", side_effect=AssertionError("must not send")) as send:
            request = self.factory.get("/api/inbox/media-library/?view=automations")
            force_authenticate(request, self.user)
            response = MediaLibraryView.as_view()(request)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Cache-Control"], "no-store")
            self.assertGreater(len(response.data["cards"]), 12)
            send.assert_not_called()
        self.assertEqual(before, (QuickReply.objects.count(), Message.objects.count(), ReviewSettings.objects.count()))

    def test_unauthenticated_cannot_read_requisites(self):
        response = MediaLibraryView.as_view()(self.factory.get("/?view=automations"))
        self.assertIn(response.status_code, (401, 403))

    def test_masterclass_changes_show_without_sync_and_rule_status_is_live(self):
        q = QuickReply.objects.create(title=REPLY_TITLE, category="Майстер-класи", text="Current " + URL)
        rule = GlobalRule.objects.create(title=RULE_TITLE, enabled=True)
        self.assertEqual(self.card("tutorial_%s" % q.id)["messages"], [q.text])
        self.assertEqual(self.card("tutorial_%s" % q.id)["mode"], "Автоматично")
        q.text = "Edited " + URL; q.save()
        rule.enabled = False; rule.save()
        self.assertEqual(self.card("tutorial_%s" % q.id)["messages"], [q.text])
        self.assertEqual(self.card("tutorial_%s" % q.id)["mode"], "Лише вручну")
        q.is_active=False; q.save()
        self.assertEqual(self.card("tutorial_%s" % q.id)["mode"], "Вимкнено")

    def test_tools_follow_live_prices_order_and_disable(self):
        a = Product.objects.create(name="Tool A", price=50)
        b = Product.objects.create(name="Tool B", price=75)
        cfg = IntegrationSettings.objects.create(provider="upsell_test_kit", is_active=True, config={"product_ids":[b.id,a.id]})
        first = self.card("tools")["messages"][0]
        self.assertIn("1. Tool B — 75 грн", first)
        a.price=99;a.save()
        self.assertIn("2. Tool A — 99 грн", self.card("tools")["messages"][0])
        cfg.is_active=False;cfg.save()
        self.assertEqual(self.card("tools")["messages"], [])

    def test_reviews_follow_current_text_delay_and_off_switch(self):
        cfg = ReviewSettings.objects.create(pk=1, text_main="Live {матеріал}", send_enabled=False, delay_main_days=12)
        self.assertEqual(self.card("review_main")["messages"], ["Live {матеріал}"])
        self.assertIn("12", self.card("review_main")["when"])
        self.assertEqual(self.card("review_main")["mode"], "Автоматичне надсилання вимкнено")
        cfg.text_main="Changed {посилання}";cfg.save()
        self.assertEqual(self.card("review_main")["messages"], [cfg.text_main])

    def test_bank_preview_reads_sending_function(self):
        d=SimpleNamespace(id="[номер замовлення]",amount="[сума]")
        self.assertEqual(self.card("bank")["messages"][0], requisites_text(d)[1])

    def test_np_preview_is_the_actual_sending_builder(self):
        with patch("apps.crm.management.commands.np_status_sync._msg", return_value="Changed NP text"):
            for key in ("shipped", "arrived", "reminder"):
                self.assertEqual(self.card(key)["messages"], ["Changed NP text"])

    def test_no_messages_for_stage_only_events(self):
        for key in ("failed","confirmed","warehouse","transit","received"):
            self.assertEqual(self.card(key)["messages"], [])

    def test_ttn_creation_does_not_claim_shipment_and_keeps_cod(self):
        self.assertNotIn("відправлено", cm.ttn_created("synthetic"))
        self.assertIn("створено ТТН", cm.ttn_created("synthetic"))
        self.assertNotIn("До сплати", cm.ttn_created("synthetic"))
        self.assertIn("До сплати при отриманні: 123 грн", cm.ttn_created("synthetic",123))

    def test_np_form_preserves_masterclass_claim(self):
        d=Deal.objects.create(title="Synthetic",funnel=self.funnel,stage=self.stage,np_data={"pattera_travertine_masterclass_v1":{"state":"sent"},"msg_arrived":True})
        request=self.factory.post("/",{"np_data":{"city":"Synthetic"}},format="json")
        force_authenticate(request,self.user)
        with patch.object(DealViewSet,"get_object",return_value=d):
            result=DealViewSet.as_view({"post":"np_save"})(request,pk=d.id)
        self.assertEqual(result.status_code,200)
        d.refresh_from_db()
        self.assertEqual(d.np_data["pattera_travertine_masterclass_v1"],{"state":"sent"})
        self.assertTrue(d.np_data["msg_arrived"])

    def test_payment_action_uses_shared_messages_in_order(self):
        from apps.crm.models import Contact
        from apps.inbox.models import Channel, Conversation
        c=Contact.objects.create(first_name="Synthetic mirror")
        d=Deal.objects.create(title="Synthetic",funnel=self.funnel,stage=self.stage,contact=c,amount=100)
        ch=Channel.objects.create(name="Synthetic",kind="telegram")
        Conversation.objects.create(channel=ch,contact=c,external_chat_id="synthetic-only")
        req=self.factory.post("/",{"kind":"requisites","amount":100},format="json")
        force_authenticate(req,self.user)
        with patch.object(DealViewSet,"get_object",return_value=d), patch("apps.crm.views._advance_deal_stage"), patch("apps.inbox.services.send_message") as send:
            result=DealViewSet.as_view({"post":"send_pay_link"})(req,pk=d.id)
        self.assertEqual(result.status_code,200,result.data)
        texts=[call.args[1] for call in send.call_args_list]
        self.assertEqual(len(texts),5)
        self.assertEqual(texts[0],requisites_text(d,100)[1])
        self.assertEqual(texts[-2:],[cm.shipping_details(),cm.shipping_term()])
