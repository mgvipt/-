"""Тести «продажі по креативах» (14.09.2026, meta-creatives). Лише Postgres (DISTINCT ON)."""
from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.crm.models import Contact, Deal, Funnel, Lead, MetaAdDailyStat, Stage
from apps.finance.models import Account, Category, Transaction

URL = "/api/meta-attr/creative-sales/?from=2026-08-01&to=2026-08-31"
AD_A = "120256485274790011"
AD_B = "120253710209050011"


def _at(y, m, d, h=12):
    return timezone.make_aware(datetime(y, m, d, h, 0))


def exact(ad_id, title="Галатея 02.09.26"):
    return {"source_kind": "paid_ad", "platform": "instagram", "ad_id": ad_id, "ad_title": title,
            "campaign_id": "c1", "adset_id": "s1", "source_context": "ad_referral"}


def likely(phrase="Galatea🔥"):
    return {"source_kind": "likely_ad", "class": "meta_ad_likely", "method": "first_text",
            "phrase": phrase, "platform": "instagram", "source_context": "first_text_keyword"}


class CreativeSalesTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user("owner_mc", password="x", is_superuser=True, is_staff=True)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.lf = Funnel.objects.create(name="Лиды", is_lead_funnel=True)
        self.l1 = Stage.objects.create(funnel=self.lf, name="Лід отриманий", order=0)
        self.df = Funnel.objects.create(name="21 Основний продукт", order=1)
        self.d1 = Stage.objects.create(funnel=self.df, name="Новий", order=0)
        self.won = Stage.objects.create(funnel=self.df, name="Успішна угода", order=5, is_won=True)
        self.acc = Account.objects.create(name="Каса тест")
        self.cat_in = Category.objects.create(name="Онлайн", direction="in")
        self.cat_out = Category.objects.create(name="Повернення", direction="out")

    # ── помічники ──
    def deal(self, attr, won=False, created=None, contact=None, owner=None, amount=0):
        d = Deal.objects.create(title="Угода", funnel=self.df, stage=self.won if won else self.d1,
                                contact=contact, owner=owner, amount=amount, meta_attribution=attr)
        Deal.objects.filter(pk=d.pk).update(created_at=created or _at(2026, 8, 10))
        return d

    def lead(self, attr, created=None, contact=None):
        x = Lead.objects.create(title="Лід", funnel=self.lf, stage=self.l1, contact=contact,
                                source="instagram", meta_attribution=attr)
        Lead.objects.filter(pk=x.pk).update(created_at=created or _at(2026, 8, 10))
        return x

    def tx(self, deal, amount, direction="in", day=date(2026, 8, 12)):
        cat = self.cat_in if direction == "in" else self.cat_out
        return Transaction.objects.create(direction=direction, amount=Decimal(str(amount)), account=self.acc,
                                          category=cat if direction != "transfer" else None, deal=deal, date=day)

    def get(self, url=URL, client=None):
        resp = (client or self.client).get(url)
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        return resp.json()

    # ── 1. точна і «ймовірно» не змішуються ──
    def test_exact_and_likely_are_separate(self):
        d_exact = self.deal(exact(AD_A), won=True)
        self.tx(d_exact, 1000)
        d_likely = self.deal(likely("Galatea🔥"))
        self.tx(d_likely, 500)
        self.deal({"source_kind": "organic", "platform": "instagram"})          # органіка — ніде
        body = self.get()
        self.assertEqual(set(body["by_ad"]), {AD_A})
        a = body["by_ad"][AD_A]
        self.assertEqual((a["deals"], a["paid"], a["revenue"]), (1, 1, 1000.0))
        self.assertEqual([d["id"] for d in a["deals_list"]], [d_exact.id])
        self.assertEqual(len(body["likely_by_phrase"]), 1)
        ph = body["likely_by_phrase"][0]
        self.assertEqual((ph["phrase"], ph["deals"], ph["paid"], ph["revenue"]), ("Galatea🔥", 1, 1, 500.0))
        self.assertNotIn("ad_id", ph)
        self.assertEqual(body["totals"]["exact"]["revenue"], 1000.0)
        self.assertEqual(body["totals"]["likely"]["revenue"], 500.0)

    def test_likely_with_ad_id_is_still_not_counted_for_the_ad(self):
        attr = likely("Сирена💎")
        attr["ad_id"] = AD_A                     # навіть якщо хтось допише ad_id — клас «ймовірно»
        self.tx(self.deal(attr, won=True), 300)
        body = self.get()
        self.assertEqual(body["by_ad"], {})
        self.assertEqual(body["likely_by_phrase"][0]["revenue"], 300.0)

    # ── 2. гроші — лише надходження з журналу ──
    def test_revenue_only_from_income_transactions(self):
        d1 = self.deal(exact(AD_A), won=True, amount=99999)   # сума угоди НЕ є виручкою
        self.tx(d1, 700)
        self.tx(d1, 200, direction="out")
        self.tx(d1, 300, direction="transfer")
        self.deal(exact(AD_A), won=True, amount=5000)          # успішна без грошей → оплачена, 0 ₴
        d3 = self.deal(exact(AD_A))                            # відкрита з передоплатою → оплачена
        self.tx(d3, 100)
        self.deal(exact(AD_A))                                 # відкрита без грошей → не оплачена
        a = self.get()["by_ad"][AD_A]
        self.assertEqual((a["deals"], a["paid"], a["revenue"]), (4, 3, 800.0))

    # ── 3. фільтр періоду ──
    def test_period_filter_by_creation_date(self):
        inside = self.deal(exact(AD_A), won=True, created=_at(2026, 8, 31, 20))
        self.tx(inside, 400, day=date(2026, 9, 20))            # оплата ПІСЛЯ періоду — рахується
        outside = self.deal(exact(AD_A), won=True, created=_at(2026, 7, 31, 10))
        self.tx(outside, 9000, day=date(2026, 8, 5))           # угода до періоду — не рахується
        self.deal(exact(AD_B), created=_at(2026, 9, 1, 10))    # після періоду
        self.lead(exact(AD_B), created=_at(2026, 7, 15))
        body = self.get()
        self.assertEqual(set(body["by_ad"]), {AD_A})
        a = body["by_ad"][AD_A]
        self.assertEqual((a["deals"], a["paid"], a["revenue"]), (1, 1, 400.0))
        self.assertEqual(body["period"], {"from": "2026-08-01", "to": "2026-08-31"})
        self.assertEqual(self.get("/api/meta-attr/creative-sales/?from=2026-07-01&to=2026-07-31")
                         ["by_ad"][AD_A]["revenue"], 9000.0)

    def test_leads_count_people_once(self):
        anna = Contact.objects.create(first_name="Анна")
        self.lead(exact(AD_A), contact=anna)
        self.deal(exact(AD_A), contact=anna)
        self.lead(exact(AD_A))                                 # без контакту — окрема людина
        self.lead(likely(), contact=anna)                      # «ймовірно» — у свій блок
        body = self.get()
        self.assertEqual(body["by_ad"][AD_A]["leads"], 2)
        self.assertEqual(body["likely_by_phrase"][0]["leads"], 1)

    # ── 4. витрати і «виручка на 1 ₴» ──
    def test_revenue_per_uah_uses_same_period_spend(self):
        self.tx(self.deal(exact(AD_A), won=True), 1000)
        for day, spend_uah in ((date(2026, 8, 3), "300"), (date(2026, 8, 4), "200"), (date(2026, 7, 30), "999")):
            MetaAdDailyStat.objects.create(level="ad", object_id=AD_A, ad_id=AD_A, ad_name="Галатея 02.09",
                                           account_id="act", date=day, spend="10", spend_uah=spend_uah)
        a = self.get()["by_ad"][AD_A]
        self.assertEqual((a["title"], a["spend_uah"], a["revenue_per_uah"]), ("Галатея 02.09", 500.0, 2.0))
        MetaAdDailyStat.objects.create(level="ad", object_id=AD_A, ad_id=AD_A, account_id="act",
                                       date=date(2026, 8, 5), spend="5", spend_uah=None)
        a = self.get()["by_ad"][AD_A]
        self.assertIsNone(a["spend_uah"])                      # день без курсу НБУ → не вгадуємо
        self.assertIsNone(a["revenue_per_uah"])

    # ── 5. права ──
    def _user(self, name, perms):
        u = get_user_model().objects.create_user(name, password="x")
        u.extra_permissions = perms
        u.save()
        c = APIClient()
        c.force_authenticate(u)
        return u, c

    def test_permissions_money_and_deal_list(self):
        d1 = self.deal(exact(AD_A), won=True)
        self.tx(d1, 1000)
        _, no_access = self._user("no_mm", ["deal.view.all", "deal.view"])
        self.assertEqual(no_access.get(URL).status_code, 403)

        _, marketer = self._user("mm_only", ["marketing.view"])
        body = self.get(client=marketer)
        a = body["by_ad"][AD_A]
        self.assertEqual((a["deals"], a["paid"]), (1, 1))
        self.assertIsNone(a["revenue"])
        self.assertIsNone(body["totals"]["exact"]["revenue"])
        self.assertFalse(body["can_open_deals"])
        self.assertEqual(a["deals_list"], [])

        mgr, mgr_client = self._user("mm_mgr", ["marketing.view", "marketing.money", "deal.view"])
        own = self.deal(exact(AD_A), owner=mgr)
        body = self.get(client=mgr_client)
        a = body["by_ad"][AD_A]
        self.assertTrue(body["deals_limited_to_own"])
        self.assertEqual([d["id"] for d in a["deals_list"]], [own.id])  # чужа угода не видна
        self.assertEqual(a["deals_hidden"], 1)
        self.assertEqual(a["revenue"], 1000.0)                  # цифри — повні, як у всієї вкладки

    # ── 6. без запитів «на кожен креатив» ──
    def test_query_count_does_not_grow_with_creatives(self):
        def run():
            with CaptureQueriesContext(connection) as ctx:
                self.get()
            return len(ctx.captured_queries)
        for i in range(2):
            self.tx(self.deal(exact("ad-%d" % i), won=True), 100)
            self.lead(exact("ad-%d" % i))
        small = run()
        for i in range(2, 12):
            self.tx(self.deal(exact("ad-%d" % i), won=True), 100)
            self.lead(exact("ad-%d" % i))
            self.deal(likely("Сирена%d💎" % i))
        self.assertEqual(run(), small)
        self.assertEqual(len(self.get()["by_ad"]), 12)
