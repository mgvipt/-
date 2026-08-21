from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings

from .meta_conversions import event_name_for_stage, process_event, queue_stage_event
from .models import Contact, Deal, Funnel, Lead, MetaConversionEvent, Payment, Stage
from .views import convert_lead_to_deal


class MetaConversionMappingTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.lead_funnel = Funnel.objects.create(name="Лиды", is_lead_funnel=True)
        self.sales_funnel = Funnel.objects.create(name="21 Основний продукт")
        self.contact = Contact.objects.create(
            first_name="Олег",
            last_name="Тестовий",
            phone="+380 (97) 000-00-01",
            email="TEST@EXAMPLE.COM",
        )

    def stage(self, funnel, name, **kwargs):
        return Stage.objects.create(funnel=funnel, name=name, order=funnel.stages.count(), **kwargs)

    def paid_attr(self, **extra):
        return {"source_kind": "paid_ad", "platform": "instagram", "ad_id": "ad-test-101", **extra}

    def test_live_stage_names_map_to_expected_events(self):
        cases = {
            "Лід отриманий": "Lead",
            "Контакт встановлений": "Contact",
            "Кваліфікований": "QualifiedLead",
            "Розрахунок здійснено (КП)": "QuoteSent",
            "Домовились про оплату": "InitiateCheckout",
            "Успішна угода": "OrderCompleted",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(event_name_for_stage(self.stage(self.sales_funnel, name)), expected)

    def test_lost_archive_and_payment_stage_are_not_stage_conversions(self):
        lost = self.stage(self.sales_funnel, "Не реализовано", is_lost=True)
        paid = self.stage(self.sales_funnel, "Оплату отримано")
        archive = Funnel.objects.create(name="Архів", is_archive=True)
        archived = self.stage(archive, "Новая заявка")
        self.assertIsNone(event_name_for_stage(lost))
        self.assertIsNone(event_name_for_stage(paid))
        self.assertIsNone(event_name_for_stage(archived))

        hiring = Funnel.objects.create(name="11. Найм сотрудников")
        technical = Funnel.objects.create(name="Техническая(Тесты)")
        self.assertIsNone(event_name_for_stage(self.stage(hiring, "Контакт встановлений")))
        self.assertIsNone(event_name_for_stage(self.stage(technical, "Новая")))

    def test_lead_create_and_stage_change_queue_hashed_idempotent_events(self):
        first = self.stage(self.lead_funnel, "Лід отриманий")
        qualified = self.stage(self.lead_funnel, "Кваліфікований")
        lead = Lead.objects.create(
            title="Тестовий лід", contact=self.contact, funnel=self.lead_funnel,
            stage=first, source="instagram", amount=100, meta_attribution=self.paid_attr(),
        )
        event = MetaConversionEvent.objects.get(event_name="Lead")
        payload_text = str(event.payload)
        self.assertNotIn("380970000001", payload_text)
        self.assertNotIn("test@example.com", payload_text.lower())
        self.assertEqual(len(event.payload["user_data"]["ph"][0]), 64)
        self.assertEqual(event.payload["action_source"], "system_generated")

        lead.title = "Без зміни стадії"
        lead.save(update_fields=["title", "updated_at"])
        self.assertEqual(MetaConversionEvent.objects.count(), 1)

        lead.stage = qualified
        lead.save(update_fields=["stage", "updated_at"])
        self.assertEqual(MetaConversionEvent.objects.filter(event_name="QualifiedLead").count(), 1)
        queue_stage_event(lead)
        self.assertEqual(MetaConversionEvent.objects.filter(event_name="QualifiedLead").count(), 1)

    def test_purchase_only_comes_from_real_paid_payment(self):
        paid_stage = self.stage(self.sales_funnel, "Оплату отримано")
        deal = Deal.objects.create(
            title="Тестова сделка", contact=self.contact, funnel=self.sales_funnel,
            stage=paid_stage, source="instagram", amount=1500, meta_attribution=self.paid_attr(),
        )
        self.assertFalse(MetaConversionEvent.objects.filter(event_name="Purchase").exists())

        payment = Payment.objects.create(
            deal=deal, provider="bank", amount=500, is_paid=False, external_id="test-payment-1",
        )
        self.assertFalse(MetaConversionEvent.objects.filter(event_name="Purchase").exists())
        payment.is_paid = True
        payment.save(update_fields=["is_paid"])
        purchase = MetaConversionEvent.objects.get(event_name="Purchase")
        self.assertEqual(purchase.payload["custom_data"]["value"], 500.0)
        self.assertEqual(purchase.payload["custom_data"]["currency"], "UAH")

        payment.save(update_fields=["is_paid"])
        self.assertEqual(MetaConversionEvent.objects.filter(event_name="Purchase").count(), 1)

    def test_command_defaults_to_dry_run(self):
        first = self.stage(self.lead_funnel, "Лід отриманий")
        Lead.objects.create(title="Dry run", funnel=self.lead_funnel, stage=first, contact=self.contact,
                            meta_attribution=self.paid_attr())
        output = StringIO()
        with patch("apps.crm.meta_conversions.send_event") as send:
            call_command("meta_capi_sync", stdout=output)
        send.assert_not_called()
        self.assertIn("DRY_RUN", output.getvalue())

    @override_settings()
    def test_sender_is_blocked_while_disabled(self):
        first = self.stage(self.lead_funnel, "Лід отриманий")
        Lead.objects.create(title="Disabled", funnel=self.lead_funnel, stage=first, contact=self.contact,
                            meta_attribution=self.paid_attr())
        event = MetaConversionEvent.objects.get(event_name="Lead")
        with patch.dict("os.environ", {"META_CAPI_ENABLED": "0"}, clear=False):
            updated, ok = process_event(event.pk)
        self.assertFalse(ok)
        self.assertEqual(updated.status, "failed")
        self.assertIn("META_CAPI_ENABLED", updated.last_error)

    def test_explicit_send_marks_event_sent_when_meta_confirms(self):
        first = self.stage(self.lead_funnel, "Лід отриманий")
        Lead.objects.create(title="Confirmed", funnel=self.lead_funnel, stage=first, contact=self.contact,
                            meta_attribution=self.paid_attr())
        event = MetaConversionEvent.objects.get(event_name="Lead")
        with patch("apps.crm.meta_conversions.send_event", return_value={"events_received": 1}):
            updated, ok = process_event(event.pk, test_event_code="TEST123")
        self.assertTrue(ok)
        self.assertEqual(updated.status, "sent")
        self.assertIsNotNone(updated.sent_at)

    def test_manual_and_organic_leads_never_queue_meta_events(self):
        first = self.stage(self.lead_funnel, "Лід отриманий")
        Lead.objects.create(title="Ручний", funnel=self.lead_funnel, stage=first,
                            contact=self.contact, source="other")
        Lead.objects.create(
            title="Органічний Instagram", funnel=self.lead_funnel, stage=first,
            contact=self.contact, source="instagram",
            meta_attribution={"source_kind": "organic", "platform": "instagram"},
        )
        Lead.objects.create(
            title="Instagram без рекламного ID", funnel=self.lead_funnel, stage=first,
            contact=self.contact, source="instagram",
            meta_attribution={"source_kind": "paid_ad", "platform": "instagram"},
        )
        self.assertEqual(MetaConversionEvent.objects.count(), 0)

    def test_lead_form_and_paid_ad_queue_with_attribution_ids(self):
        first = self.stage(self.lead_funnel, "Лід отриманий")
        paid = Lead.objects.create(
            title="Реклама", funnel=self.lead_funnel, stage=first, contact=self.contact,
            source="instagram", meta_attribution=self.paid_attr(campaign_id="camp-1"),
        )
        lead_form = Lead.objects.create(
            title="Lead form", funnel=self.lead_funnel, stage=first, contact=self.contact,
            source="facebook", meta_attribution={
                "source_kind": "lead_form", "platform": "facebook",
                "lead_id": "lead-22", "form_id": "form-7",
            },
        )
        p1 = MetaConversionEvent.objects.get(lead=paid)
        p2 = MetaConversionEvent.objects.get(lead=lead_form)
        self.assertEqual(p1.payload["custom_data"]["meta_ad_id"], "ad-test-101")
        self.assertEqual(p1.payload["custom_data"]["meta_campaign_id"], "camp-1")
        self.assertEqual(p2.payload["custom_data"]["meta_lead_id"], "lead-22")
        self.assertEqual(p2.payload["custom_data"]["meta_form_id"], "form-7")

    def test_lead_to_deal_keeps_verified_attribution(self):
        first = self.stage(self.lead_funnel, "Лід отриманий")
        sales_first = self.stage(self.sales_funnel, "Лід отриманий")
        lead = Lead.objects.create(
            title="Конвертація", funnel=self.lead_funnel, stage=first, contact=self.contact,
            source="instagram", meta_attribution=self.paid_attr(campaign_id="camp-copy"),
        )
        lead_event_id = MetaConversionEvent.objects.get(lead=lead).pk
        deal = convert_lead_to_deal(lead, self.sales_funnel, None, "test")
        self.assertEqual(deal.stage_id, sales_first.id)
        self.assertEqual(deal.meta_attribution["campaign_id"], "camp-copy")
        orphaned_snapshot = MetaConversionEvent.objects.get(pk=lead_event_id)
        self.assertIsNone(orphaned_snapshot.lead_id)
        with patch("apps.crm.meta_conversions.send_event", return_value={"events_received": 1}):
            _, ok = process_event(orphaned_snapshot.pk)
        self.assertTrue(ok)

    def test_unattributed_payment_is_not_queued(self):
        paid_stage = self.stage(self.sales_funnel, "Оплату отримано")
        deal = Deal.objects.create(
            title="Органічна угода", contact=self.contact, funnel=self.sales_funnel,
            stage=paid_stage, source="instagram", amount=900,
        )
        Payment.objects.create(deal=deal, provider="bank", amount=900, is_paid=True,
                               external_id="organic-payment")
        self.assertFalse(MetaConversionEvent.objects.filter(event_name="Purchase").exists())

    def test_meta_marketing_dashboard_separates_ads_from_manual_cards(self):
        first = self.stage(self.lead_funnel, "Лід отриманий")
        Lead.objects.create(
            title="Ad lead", funnel=self.lead_funnel, stage=first, contact=self.contact,
            source="instagram", meta_attribution=self.paid_attr(campaign_id="camp-dashboard"),
        )
        Lead.objects.create(
            title="Manual lead", funnel=self.lead_funnel, stage=first,
            contact=self.contact, source="instagram",
        )
        admin = get_user_model().objects.create_superuser(
            username="meta-dashboard-admin", password="test-pass-123", email="admin@example.com",
        )
        self.client.force_login(admin)
        response = self.client.get("/api/meta-marketing/?from=2020-01-01&to=2030-01-01")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["summary"]["attributed_leads"], 1)
        self.assertEqual(body["summary"]["manual_or_organic_leads"], 1)
        self.assertEqual(body["campaigns"][0]["campaign_id"], "camp-dashboard")
        self.assertFalse(body["integration"]["insights_sync_configured"])
