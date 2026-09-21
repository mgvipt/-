from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from apps.crm.models import Contact, Deal, DealItem, Funnel, GlobalRule, Payment, Stage
from apps.inbox.models import Channel, Conversation, Message, QuickReply
from apps.warehouse.models import Product
from . import pattera_masterclass as tutorial


class TutorialTests(TestCase):
    def setUp(self):
        self.contact = Contact.objects.create(first_name="Synthetic tutorial QA")
        self.funnel = Funnel.objects.create(name="Synthetic")
        self.paid = Stage.objects.create(funnel=self.funnel, name="Оплату отримано", order=3)
        self.waiting = Stage.objects.create(funnel=self.funnel, name="Домовились про оплату", order=2)
        self.deal = Deal.objects.create(title="Synthetic", contact=self.contact, funnel=self.funnel, stage=self.paid,
                                        amount=100, np_data={"preserve": "delivery"})
        self.product = Product.objects.create(pk=1654, name="Травертин — тестовий набір Pattera Fine", price=100)
        DealItem.objects.create(deal=self.deal, product=self.product, quantity=1, price=100)
        self.payment = Payment.objects.create(deal=self.deal, amount=100, is_paid=True)
        GlobalRule.objects.create(block="automation", title=tutorial.RULE_TITLE, enabled=True)
        QuickReply.objects.create(title=tutorial.REPLY_TITLE, category="Майстер-класи", text="Tutorial " + tutorial.URL)
        channel = Channel.objects.create(name="Synthetic", kind="telegram")
        self.conv = Conversation.objects.create(channel=channel, contact=self.contact, external_chat_id="synthetic")
        Message.objects.create(conversation=self.conv, direction="in", text="Synthetic request")
        self.transport = patch("apps.inbox.services.send_message", side_effect=lambda conv,text,user=None: Message.objects.create(conversation=conv,direction="out",text=text,status="sent"))
        self.send = self.transport.start()
        self.addCleanup(self.transport.stop)

    def test_paid_sends_once_and_preserves_shipping(self):
        self.assertEqual(tutorial.attempt(self.deal.id), "sent")
        self.assertEqual(tutorial.attempt(self.deal.id), "already_claimed")
        self.send.assert_called_once()
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.np_data["preserve"], "delivery")

    def test_stage_without_payment_is_blocked(self):
        Payment.objects.filter(pk=self.payment.pk).update(is_paid=False)
        self.assertEqual(tutorial.attempt(self.deal.id), "ineligible")
        self.send.assert_not_called()

    def test_payment_without_paid_stage_is_blocked(self):
        Deal.objects.filter(pk=self.deal.pk).update(stage=self.waiting)
        self.assertEqual(tutorial.attempt(self.deal.id), "ineligible")

    def test_refunded_or_zero_payment_is_blocked(self):
        for fields in ({"checkbox_return_id":"return"}, {"checkbox_return_id":"", "amount":0}):
            Payment.objects.filter(pk=self.payment.pk).update(**fields)
            self.assertEqual(tutorial.attempt(self.deal.id), "ineligible")

    def test_other_effect_or_material_is_blocked(self):
        other = Product.objects.create(pk=1694, name="Арт бетон Pattera Fine", price=100)
        self.deal.items.update(product=other)
        self.assertEqual(tutorial.attempt(self.deal.id), "ineligible")
        self.deal.items.update(product=None,custom_name="Травертин Pattera Fine")
        self.assertEqual(tutorial.attempt(self.deal.id), "ineligible")

    def test_full_material_needs_explicit_effect(self):
        fine = Product.objects.create(pk=1639, name="Pattera Fine", price=100)
        self.deal.items.update(product=fine)
        self.assertEqual(tutorial.attempt(self.deal.id), "ineligible")
        Deal.objects.filter(pk=self.deal.pk).update(qualification={"material":"Pattera Fine", "effect":"Травертин"})
        self.assertEqual(tutorial.attempt(self.deal.id), "sent")

    def test_disabling_rule_blocks_sends(self):
        GlobalRule.objects.update(enabled=False)
        self.assertEqual(tutorial.attempt(self.deal.id), "disabled")

    def test_missing_or_comment_chat_is_blocked(self):
        self.conv.external_chat_id = "comment:synthetic"
        self.conv.save()
        self.assertEqual(tutorial.attempt(self.deal.id), "no_safe_chat")
        self.send.assert_not_called()

    def test_meta_closed_window_is_blocked(self):
        channel = self.conv.channel
        channel.kind = "instagram"
        channel.save()
        self.conv.messages.update(created_at=timezone.now()-timedelta(hours=25))
        self.assertEqual(tutorial.attempt(self.deal.id), "no_safe_chat")

    def test_failure_is_not_retried(self):
        self.send.side_effect = RuntimeError("synthetic timeout")
        self.assertEqual(tutorial.attempt(self.deal.id), "review_required")
        self.assertEqual(tutorial.attempt(self.deal.id), "already_claimed")
        self.send.assert_called_once()

    def test_existing_shared_link_is_not_repeated(self):
        Message.objects.create(conversation=self.conv,direction="out",text=tutorial.URL,status="sent")
        self.assertEqual(tutorial.attempt(self.deal.id), "already_shared")
        self.send.assert_not_called()

    def test_real_stage_signal_after_commit(self):
        Deal.objects.filter(pk=self.deal.pk).update(stage=self.waiting)
        self.deal.refresh_from_db()
        with self.captureOnCommitCallbacks(execute=True):
            self.deal.stage = self.paid
            self.deal.save(update_fields=["stage"])
        self.send.assert_called_once()

    def test_real_payment_signal_after_commit(self):
        Payment.objects.filter(pk=self.payment.pk).update(is_paid=False)
        self.payment.refresh_from_db()
        with self.captureOnCommitCallbacks(execute=True):
            self.payment.is_paid = True
            self.payment.save(update_fields=["is_paid"])
        self.send.assert_called_once()

    def test_same_stage_save_does_not_trigger(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.deal.save(update_fields=["amount"])
        self.send.assert_not_called()

    def test_claim_on_other_deal_blocks_duplicate(self):
        Deal.objects.create(title="Other", contact=self.contact, funnel=self.funnel, stage=self.paid,
                            np_data={tutorial.MARKER:{"status":"claimed"}})
        self.assertEqual(tutorial.attempt(self.deal.id), "already_claimed_contact")
        self.send.assert_not_called()
