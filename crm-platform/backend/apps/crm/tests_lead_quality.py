"""Якість звернення (11.09): одна відмітка на останньому ліді, ставиться в чаті й картках."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.crm.lead_quality import from_close_reason, mark_on_close, set_quality
from apps.crm.models import Contact, Funnel, Lead, Stage


class LeadQualityTests(TestCase):
    def setUp(self):
        self.funnel = Funnel.objects.create(name="Ліди (тест)", is_lead_funnel=True)
        self.stage = Stage.objects.create(funnel=self.funnel, name="Лід отриманий", order=0)
        self.contact = Contact.objects.create(first_name="Тест", phone="+380670003344")
        self.lead = Lead.objects.create(title="l", contact=self.contact, funnel=self.funnel, stage=self.stage)
        self.admin = get_user_model().objects.create_superuser("lq-admin", "lq@example.test", "x")

    def test_close_reason_mapping(self):
        self.assertEqual(from_close_reason("Нецільовий: спам / бот"), ("nontarget", "spam"))
        self.assertEqual(from_close_reason("Нецільовий: не наш товар"), ("nontarget", "not_our"))
        self.assertEqual(from_close_reason("Нецільовий: постачальник / вакансія"), ("nontarget", "supplier_job"))
        self.assertEqual(from_close_reason("Не звернення (коментар, спілкування)"), ("comment", ""))
        self.assertEqual(from_close_reason("Дорого / бюджет"), ("target", ""))
        self.assertEqual(from_close_reason("Не відповів після дожимів"), ("noreply", ""))
        self.assertIsNone(from_close_reason(""))

    def test_close_marks_target_only_if_empty(self):
        mark_on_close(self.contact.id, "Дорого / бюджет")
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.quality, "target")
        set_quality(self.lead, "noreply", user=self.admin)
        mark_on_close(self.contact.id, "Не відповідає (ігнор)")
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.quality, "noreply")  # ручну відмітку не перетерли

    def test_close_nontarget_overrides(self):
        set_quality(self.lead, "target", user=self.admin)
        mark_on_close(self.contact.id, "Нецільовий: помилився адресою")
        self.lead.refresh_from_db()
        self.assertEqual((self.lead.quality, self.lead.quality_reason), ("nontarget", "wrong"))

    def test_api_get_and_set(self):
        c = APIClient()
        c.force_authenticate(self.admin)
        url = "/api/contacts/%s/lead-quality/" % self.contact.id
        r = c.get(url, HTTP_HOST="crm.wallcovdec.com.ua")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["lead_id"], self.lead.id)
        r = c.post(url, {"quality": "nontarget", "reason": "spam"}, format="json", HTTP_HOST="crm.wallcovdec.com.ua")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["quality"], "nontarget")
        self.assertEqual(r.json()["reason_label"], "Спам / бот")
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.quality_by_id, self.admin.id)
        r = c.post(url, {"quality": "bogus"}, format="json", HTTP_HOST="crm.wallcovdec.com.ua")
        self.assertEqual(r.status_code, 400)
