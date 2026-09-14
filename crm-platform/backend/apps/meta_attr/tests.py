"""Тести міток реклами Meta (14.09.2026, meta-attr). Лише Postgres (distinct on)."""
import time
from datetime import datetime, timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.crm.meta_conversions import has_verified_meta_attribution
from apps.crm.models import Contact, Deal, Funnel, Lead, Stage
from apps.crm.views import convert_lead_to_deal
from apps.inbox.models import Channel, Conversation, Message
from apps.integrations.models import IntegrationSettings

from . import services as ma
from .models import MetaWebhookLog

IG = "17841400000000000"
AD = "120256301632720011"
REF = {"ad_id": AD, "source": "ADS", "type": "OPEN_THREAD",
       "ads_context_data": {"ad_title": "Галатея 06.08.26", "photo_url": "https://example.com/a.jpg"}}


def _identity(sender_id, kind, name="", username=""):
    return (name or "Тест Клієнт", username or "")


def _at(y, m, d, h=12):
    return timezone.make_aware(datetime(y, m, d, h, 0))


class PhraseTests(TestCase):
    def setUp(self):
        ma.clear_phrase_cache()

    def test_classes_a_and_c_match(self):
        for text in ("Galatea🔥", "Сирена💎", "Патера💎", "Galatea🖌️", "Pattera🌿", "Luna🎨",
                     "Прорахунок на об`єм та консультація Galatea🌼", "Консультація та прорахунок об'ємуLuna🎨",
                     "Розрахунок на обʼєм", "розрахунок на об'єм"):
            with self.subTest(text=text):
                self.assertTrue(ma.match_ad_phrase(text))
        self.assertEqual(ma.match_ad_phrase_group("Galatea🔥")[1], "A")
        self.assertEqual(ma.match_ad_phrase_group("Розрахунок на обʼєм")[1], "C")

    def test_plain_words_start_and_chat_do_not_match(self):
        for text in ("Галатея", "Сирена", "/start", "Galatea🔥 яка ціна?", "Дякую🙏", "🔥", "", None, "Тестовий набір"):
            with self.subTest(text=text):
                self.assertEqual(ma.match_ad_phrase(text), "")

    def test_list_is_configurable(self):
        IntegrationSettings.objects.create(provider=ma.PHRASES_PROVIDER, config={"emoji_words": ["Мармур"]})
        ma.clear_phrase_cache()
        self.assertTrue(ma.match_ad_phrase("Мармур✨"))
        self.assertEqual(ma.match_ad_phrase("Galatea🔥"), "")
        self.assertTrue(ma.match_ad_phrase("Розрахунок на обʼєм"))   # phrases з замовчувань


class Base(TestCase):
    def setUp(self):
        ma.clear_phrase_cache()
        for target, kw in (("apps.inbox.meta.PAGE_TOKEN", {"new": ""}),
                           ("apps.inbox.meta.IG_TOKEN", {"new": ""}),
                           ("apps.inbox.meta._resolve_meta_identity", {"side_effect": _identity}),
                           ("apps.inbox.meta._enrich_contact", {"return_value": []})):
            p = patch(target, **kw)
            p.start()
            self.addCleanup(p.stop)
        self.lf = Funnel.objects.create(name="Лиды", is_lead_funnel=True)
        self.l1 = Stage.objects.create(funnel=self.lf, name="Лід отриманий", order=0)
        self.l_lost = Stage.objects.create(funnel=self.lf, name="Не вдалося зв.", order=9, is_lost=True)
        self.df = Funnel.objects.create(name="21 Основний продукт", order=1)
        self.d1 = Stage.objects.create(funnel=self.df, name="Новий", order=0)
        self.d_won = Stage.objects.create(funnel=self.df, name="Успішна угода", order=5, is_won=True)
        self.d_lost = Stage.objects.create(funnel=self.df, name="Не реалізовано", order=6, is_lost=True)
        self.ch = Channel.objects.create(kind="instagram", name="Meta · instagram",
                                         config={"meta": True, "platform": "instagram"})

    def hook(self, sender, text=None, referral=None, top_referral=None):
        from apps.inbox.meta import handle_webhook
        ev = {"sender": {"id": sender}, "recipient": {"id": IG}, "timestamp": int(time.time() * 1000)}
        if text is not None:
            msg = {"mid": "mid-%s-%s" % (sender, time.time_ns()), "text": text}
            if referral:
                msg["referral"] = referral
            ev["message"] = msg
        if top_referral:
            ev["referral"] = top_referral
        return handle_webhook({"object": "instagram", "entry": [{"id": IG, "time": 1, "messaging": [ev]}]})

    def client_with_chat(self, ext="igsid-1", nickname=""):
        contact = Contact.objects.create(first_name="Анна", nickname=nickname)
        conv = Conversation.objects.create(channel=self.ch, external_chat_id=ext, contact=contact)
        return contact, conv

    def lead(self, contact, attr=None, stage=None, days_ago=0):
        obj = Lead.objects.create(title="Лід", contact=contact, funnel=self.lf, stage=stage or self.l1,
                                  source="instagram", meta_attribution=attr or {})
        if days_ago:
            Lead.objects.filter(pk=obj.pk).update(created_at=timezone.now() - timedelta(days=days_ago))
            obj.refresh_from_db()
        return obj

    def deal(self, contact, attr=None, stage=None, days_ago=0, created=None, amount=0):
        obj = Deal.objects.create(title="Угода", contact=contact, funnel=self.df, stage=stage or self.d1,
                                  source="instagram", amount=amount, meta_attribution=attr or {})
        when = created or (timezone.now() - timedelta(days=days_ago) if days_ago else None)
        if when:
            Deal.objects.filter(pk=obj.pk).update(created_at=when)
            obj.refresh_from_db()
        return obj


class WebhookTests(Base):
    def test_new_chat_first_text_is_likely_and_never_sent_to_capi(self):
        self.hook("igsid-2", text="Galatea🔥")
        lead = Lead.objects.get(contact__conversations__external_chat_id="igsid-2")
        a = lead.meta_attribution
        self.assertEqual(a["class"], ma.CLASS_LIKELY)
        self.assertEqual(a["source_kind"], "likely_ad")
        self.assertEqual(a["phrase"], "Galatea🔥")
        self.assertTrue(a["attributed_at"])
        self.assertFalse(has_verified_meta_attribution(lead))
        self.assertTrue(MetaWebhookLog.objects.filter(reason="phrase_no_referral", sender_id="igsid-2").exists())

    def test_plain_word_stays_organic(self):
        self.hook("igsid-3", text="Галатея")
        lead = Lead.objects.get(contact__conversations__external_chat_id="igsid-3")
        self.assertEqual(lead.meta_attribution.get("source_kind"), "organic")

    def test_referral_on_new_chat_is_exact_with_date_and_raw_log(self):
        self.hook("igsid-5", text="Привіт", referral=REF)
        leads = Lead.objects.filter(contact__conversations__external_chat_id="igsid-5")
        self.assertEqual(leads.count(), 1)
        a = leads[0].meta_attribution
        self.assertEqual((a["source_kind"], a["class"], a["method"], a["ad_id"]), ("paid_ad", "meta_ad", "referral", AD))
        self.assertTrue(a["attributed_at"])
        self.assertTrue(has_verified_meta_attribution(leads[0]))
        self.assertTrue(MetaWebhookLog.objects.filter(reason="ads_data", ad_id=AD).exists())

    def test_likely_is_upgraded_by_later_referral(self):
        self.hook("igsid-9", text="Сирена💎")
        self.hook("igsid-9", top_referral=REF)
        leads = Lead.objects.filter(contact__conversations__external_chat_id="igsid-9")
        self.assertEqual(leads.count(), 1)
        a = leads[0].meta_attribution
        self.assertEqual(a["class"], ma.CLASS_EXACT)
        self.assertEqual(a["upgraded_from_likely"], "Сирена💎")

    def test_open_deal_is_marked_instead_of_new_lead(self):
        contact, _conv = self.client_with_chat()
        deal = self.deal(contact)
        self.hook("igsid-1", top_referral=REF)
        deal.refresh_from_db()
        self.assertEqual(deal.meta_attribution["ad_id"], AD)
        self.assertFalse(Lead.objects.filter(contact=contact).exists())

    def test_closed_old_deal_untouched_new_lead_created(self):
        contact, _conv = self.client_with_chat()
        old = self.deal(contact, stage=self.d_won, days_ago=60, amount=900)
        self.hook("igsid-1", top_referral=REF)
        old.refresh_from_db()
        self.assertEqual(old.meta_attribution, {})
        lead = Lead.objects.get(contact=contact)
        self.assertEqual(lead.meta_attribution["ad_id"], AD)

    def test_old_open_lead_not_marked_and_no_duplicate(self):
        contact, conv = self.client_with_chat()
        old = self.lead(contact, days_ago=10)
        self.hook("igsid-1", top_referral=REF)
        old.refresh_from_db()
        conv.refresh_from_db()
        self.assertEqual(old.meta_attribution, {})
        self.assertEqual(Lead.objects.filter(contact=contact).count(), 1)
        self.assertEqual(conv.config["ad_referral"]["ad_id"], AD)

    def test_exact_mark_is_never_overwritten(self):
        contact, _conv = self.client_with_chat()
        lead = self.lead(contact, attr={"source_kind": "paid_ad", "platform": "instagram", "ad_id": "old-ad"})
        self.hook("igsid-1", top_referral=REF)
        lead.refresh_from_db()
        self.assertEqual(lead.meta_attribution["ad_id"], "old-ad")


class InheritTests(Base):
    def exact(self, days_ago, ad="ad-1"):
        return {"source_kind": "paid_ad", "platform": "instagram", "ad_id": ad, "class": "meta_ad",
                "attributed_at": (timezone.now() - timedelta(days=days_ago)).isoformat()}

    def test_takes_lead_click_within_30_days(self):
        contact, _conv = self.client_with_chat()
        lead = self.lead(contact, attr=self.exact(5))
        deal = self.deal(contact)
        self.assertTrue(ma.inherit_meta_attribution(deal))
        deal.refresh_from_db()
        self.assertEqual(deal.meta_attribution["ad_id"], "ad-1")
        self.assertEqual(deal.meta_attribution["inherited_from"], "lead:%s" % lead.id)

    def test_skips_click_older_than_30_days(self):
        contact, _conv = self.client_with_chat()
        self.lead(contact, attr=self.exact(40))
        deal = self.deal(contact)
        self.assertFalse(ma.inherit_meta_attribution(deal))
        deal.refresh_from_db()
        self.assertEqual(deal.meta_attribution, {})

    def test_chat_click_upgrades_likely_deal(self):
        contact, conv = self.client_with_chat()
        conv.config = {"ad_referral": self.exact(2, ad="ad-chat")}
        conv.save(update_fields=["config"])
        deal = self.deal(contact, attr=ma.likely_attr("Galatea🔥"))
        self.assertTrue(ma.inherit_meta_attribution(deal))
        deal.refresh_from_db()
        self.assertEqual(deal.meta_attribution["ad_id"], "ad-chat")
        self.assertEqual(deal.meta_attribution["upgraded_from_likely"], "Galatea🔥")

    def test_inbox_create_deal_button_inherits(self):
        owner = get_user_model().objects.create_superuser(username="t_owner", password="x", email="o@example.com")
        contact, conv = self.client_with_chat()
        self.lead(contact, attr=self.exact(3))
        api = APIClient()
        api.force_authenticate(owner)
        r = api.post("/api/conversations/%s/create_deal/" % conv.id, {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        deal = Deal.objects.get(pk=r.json()["deal_id"])
        self.assertEqual(deal.meta_attribution["ad_id"], "ad-1")

    def test_convert_lead_to_deal_takes_chat_click(self):
        owner = get_user_model().objects.create_superuser(username="t_owner2", password="x", email="o2@example.com")
        contact, conv = self.client_with_chat()
        conv.config = {"ad_referral": self.exact(1, ad="ad-conv")}
        conv.save(update_fields=["config"])
        lead = self.lead(contact, attr={"source_kind": "organic", "platform": "instagram"})
        deal = convert_lead_to_deal(lead, self.df, owner, "тест")
        deal.refresh_from_db()
        self.assertEqual(deal.meta_attribution["ad_id"], "ad-conv")


class SweepTests(Base):
    def test_nightly_sweep_skips_closed_and_older_deals(self):
        contact, _conv = self.client_with_chat(nickname="anna.w")
        self.lead(contact, attr={"source_kind": "paid_ad", "platform": "instagram", "ad_id": "ad-s"}, days_ago=2)
        old_won = self.deal(contact, stage=self.d_won, days_ago=60)
        fresh = self.deal(contact, days_ago=1)
        call_command("sweep_ad_attribution", "--apply", stdout=StringIO())
        old_won.refresh_from_db()
        fresh.refresh_from_db()
        self.assertEqual(old_won.meta_attribution, {})
        self.assertEqual(fresh.meta_attribution["ad_id"], "ad-s")


class BackfillTests(Base):
    def chat(self, contact, text, when, ext, channel=None):
        conv = Conversation.objects.create(channel=channel or self.cp, external_chat_id=ext, contact=contact)
        msg = Message.objects.create(conversation=conv, direction="in", text=text)
        Message.objects.filter(pk=msg.pk).update(created_at=when)
        Conversation.objects.filter(pk=conv.pk).update(created_at=when)
        return conv

    def set_created(self, obj, when):
        type(obj).objects.filter(pk=obj.pk).update(created_at=when)
        obj.refresh_from_db()
        return obj

    def setUp(self):
        super().setUp()
        self.cp = Channel.objects.create(kind="instagram", name="Instagram (архів ChatPlace)", config={"chatplace": True})
        # A: «Galatea🔥» 10.07 — лід, відкрита й програна угоди після контакту, стара виграна до контакту
        self.a = Contact.objects.create(first_name="А")
        self.chat(self.a, "Galatea🔥", _at(2026, 7, 10), "cp-a")
        self.a_lead = self.set_created(self.lead(self.a), _at(2026, 7, 10, 13))
        self.a_open = self.deal(self.a, created=_at(2026, 7, 12))
        self.a_lost = self.deal(self.a, stage=self.d_lost, created=_at(2026, 7, 12))
        self.a_old = self.deal(self.a, stage=self.d_won, created=_at(2026, 5, 1))
        # B: просто «Галатея» — не мітимо
        self.b = Contact.objects.create(first_name="Б")
        self.chat(self.b, "Галатея", _at(2026, 7, 11), "cp-b")
        self.b_lead = self.set_created(self.lead(self.b), _at(2026, 7, 11, 13))
        # C: «Розрахунок на обʼєм», але вже є точна мітка — не чіпаємо
        self.c = Contact.objects.create(first_name="В")
        self.chat(self.c, "Розрахунок на обʼєм", _at(2026, 8, 25), "ig-c", channel=self.ch)
        self.c_lead = self.lead(self.c, attr={"source_kind": "paid_ad", "platform": "instagram", "ad_id": "ad-c"})
        # D: «Сирена💎» 15.07 — лише лід
        self.d = Contact.objects.create(first_name="Г")
        self.chat(self.d, "Сирена💎", _at(2026, 7, 15), "cp-d")
        self.d_lead = self.set_created(self.lead(self.d), _at(2026, 7, 15, 13))

    def attrs(self):
        return {name: type(o).objects.get(pk=o.pk).meta_attribution for name, o in (
            ("a_lead", self.a_lead), ("a_open", self.a_open), ("a_lost", self.a_lost), ("a_old", self.a_old),
            ("b_lead", self.b_lead), ("c_lead", self.c_lead), ("d_lead", self.d_lead))}

    def test_dry_run_writes_nothing(self):
        before = self.attrs()
        out = StringIO()
        call_command("backfill_meta_likely_ad", stdout=out)
        self.assertEqual(self.attrs(), before)
        self.assertIn("DRY-RUN", out.getvalue())
        self.assertIn("Лідів позначити", out.getvalue())

    def test_live_marks_only_allowed_targets(self):
        call_command("backfill_meta_likely_ad", "--live", stdout=StringIO())
        a = self.attrs()
        self.assertEqual(a["a_lead"]["class"], ma.CLASS_LIKELY)
        self.assertEqual(a["a_lead"]["phrase"], "Galatea🔥")
        self.assertEqual(a["a_lead"]["method"], "first_text_backfill")
        self.assertEqual(a["a_open"]["class"], ma.CLASS_LIKELY)
        self.assertEqual(a["a_lost"], {})
        self.assertEqual(a["a_old"], {})
        self.assertEqual(a["b_lead"], {})
        self.assertEqual(a["c_lead"]["ad_id"], "ad-c")
        self.assertEqual(a["d_lead"]["phrase"], "Сирена💎")
        # повторний запуск нічого не міняє
        snapshot = self.attrs()
        call_command("backfill_meta_likely_ad", "--live", stdout=StringIO())
        self.assertEqual(self.attrs(), snapshot)

    def test_limit_processes_only_first_client(self):
        call_command("backfill_meta_likely_ad", "--live", "--limit", "1", stdout=StringIO())
        a = self.attrs()
        self.assertEqual(a["a_lead"]["class"], ma.CLASS_LIKELY)
        self.assertEqual(a["d_lead"], {})

    def test_exact_carry_deals_and_comment_chats(self):
        e = Contact.objects.create(first_name="Д")
        self.set_created(self.lead(e, attr={"source_kind": "paid_ad", "platform": "instagram", "ad_id": "ad-e"}),
                         _at(2026, 8, 25))
        e_open = self.deal(e, created=_at(2026, 8, 26))
        e_lost = self.deal(e, stage=self.d_lost, created=_at(2026, 8, 26))
        f = Contact.objects.create(first_name="Є")
        conv = Conversation.objects.create(channel=self.ch, external_chat_id="comment:instagram:p1:userf", contact=f,
                                           config={"source_card": {"is_ad": True, "ad_id": "ad-9", "media_id": "m-1"}})
        Conversation.objects.filter(pk=conv.pk).update(created_at=_at(2026, 8, 20))
        f_lead = self.set_created(self.lead(f), _at(2026, 8, 20, 13))
        out = StringIO()
        call_command("backfill_meta_likely_ad", "--exact-carry", stdout=out)
        self.assertEqual(Deal.objects.get(pk=e_open.pk).meta_attribution, {})       # DRY
        call_command("backfill_meta_likely_ad", "--exact-carry", "--live", stdout=StringIO())
        self.assertEqual(Deal.objects.get(pk=e_open.pk).meta_attribution["ad_id"], "ad-e")
        self.assertEqual(Deal.objects.get(pk=e_lost.pk).meta_attribution, {})
        fa = Lead.objects.get(pk=f_lead.pk).meta_attribution
        self.assertEqual((fa["ad_id"], fa["method"], fa["class"]), ("ad-9", "comment_ad_backfill", "meta_ad"))
        self.assertTrue(has_verified_meta_attribution(Lead.objects.get(pk=f_lead.pk)))


class ApiTests(Base):
    def setUp(self):
        super().setUp()
        self.owner = get_user_model().objects.create_superuser(username="t_api", password="x", email="a@example.com")
        self.api = APIClient()
        self.api.force_authenticate(self.owner)

    def test_contact_badge_reads_deals(self):
        contact, _conv = self.client_with_chat()
        self.deal(contact, attr=ma.likely_attr("Galatea🔥"))
        r = self.api.get("/api/meta-attr/contact/%s/" % contact.id)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["class"], ma.CLASS_LIKELY)

    def test_conversation_badge_exact_from_chat_and_unknown(self):
        contact, conv = self.client_with_chat()
        self.assertEqual(self.api.get("/api/meta-attr/conversation/%s/" % conv.id).json()["class"], "unknown")
        conv.config = {"ad_referral": ma.stamp_exact({"source_kind": "paid_ad", "platform": "instagram", "ad_id": AD})}
        conv.save(update_fields=["config"])
        body = self.api.get("/api/meta-attr/conversation/%s/" % conv.id).json()
        self.assertEqual(body["class"], ma.CLASS_EXACT)
        self.assertEqual(body["ad"]["ad_id"], AD)

    def test_phrases_get_and_put(self):
        r = self.api.get("/api/meta-attr/phrases/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Galatea", r.json()["emoji_words"])
        r = self.api.put("/api/meta-attr/phrases/", {"emoji_words": ["Мармур"]}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(ma.match_ad_phrase("Мармур🔥"))

    def test_ad_context_banner_reads_deals(self):
        contact, conv = self.client_with_chat()
        self.deal(contact, attr={"source_kind": "paid_ad", "platform": "instagram", "ad_id": AD, "ad_title": "Галатея"})
        r = self.api.get("/api/conversations/%s/ad_context/" % conv.id)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json().get("ad_title"), "Галатея")
