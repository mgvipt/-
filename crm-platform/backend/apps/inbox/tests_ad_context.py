# -*- coding: utf-8 -*-
"""22.09.2026: продавець CRM і ШІ-РОП знають, з якої реклами прийшов клієнт."""
from django.test import TestCase

from apps.inbox.ad_context import ad_prompt, ad_topic


class AdTopicTests(TestCase):
    def test_material_from_ad_name(self):
        self.assertEqual(ad_topic("29.04.26 | Галатея | 02.09.26"), "Галатея")
        self.assertEqual(ad_topic("lal 29.04.26 | Галатея | 14.09.26"), "Галатея")
        self.assertEqual(ad_topic("галатея"), "галатея")
        self.assertEqual(ad_topic("20.08.26 | Мокрий шовк | 16.09.26"), "Мокрий шовк")

    def test_general_or_empty_ad_gives_nothing(self):
        self.assertEqual(ad_topic("ret 06.09.26 | Загальний | 14.09.26"), "")
        self.assertEqual(ad_topic(""), "")
        self.assertEqual(ad_topic(None), "")
        self.assertEqual(ad_topic("29.04.26 | 02.09.26"), "")


class AdPromptTests(TestCase):
    def _conv(self, attribution):
        from apps.crm.models import Contact, Funnel, Lead, Stage
        from apps.inbox.models import Channel, Conversation
        c = Contact.objects.create(first_name="Тест реклами")
        if attribution is not None:
            lf = Funnel.objects.create(name="Лиды", is_lead_funnel=True)
            st = Stage.objects.create(funnel=lf, name="Лід отриманий", order=0)
            Lead.objects.create(contact=c, title="лід", funnel=lf, stage=st, meta_attribution=attribution)
        ch = Channel.objects.create(kind="instagram", name="IG тест")
        return Conversation.objects.create(channel=ch, external_chat_id="ad-t-%s" % c.id, contact=c)

    def test_paid_ad_line(self):
        conv = self._conv({"source_kind": "paid_ad", "ad_title": "29.04.26 | Галатея | 02.09.26"})
        line = ad_prompt(conv)
        self.assertIn("«Галатея»", line)
        self.assertIn("НЕ перепитуй", line)

    def test_no_ad_no_line(self):
        self.assertEqual(ad_prompt(self._conv(None)), "")
        self.assertEqual(ad_prompt(self._conv({"source_kind": "organic", "ad_title": "Галатея"})), "")
        self.assertEqual(ad_prompt(self._conv({"source_kind": "paid_ad", "ad_title": "ret | Загальний"})), "")

    def test_seller_prompt_gets_ad_context(self):
        from apps.knowledge.answer import _spec_seller
        spec = _spec_seller("yulia_web", [{"role": "client", "text": "ціна?"}], None,
                            "КЛІЄНТ ПРИЙШОВ З РЕКЛАМИ: «Галатея».", "Галатея")
        self.assertIn("КЛІЄНТ ПРИЙШОВ З РЕКЛАМИ: «Галатея».", spec["user"])
        spec2 = _spec_seller("yulia_web", [{"role": "client", "text": "ціна?"}], None)
        self.assertNotIn("ПРИЙШОВ З РЕКЛАМИ", spec2["user"])
