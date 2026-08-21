from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from .meta_marketing import _action_map, _date_chunks, _nbu_rate, _pick
from .models import (
    Contact, Deal, Funnel, Lead, MetaAccountDailyStat, MetaAdDailyStat,
    MetaContentStat, Payment, Stage,
)


class MetaMarketingAnalyticsTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="meta-analytics-admin", password="test-pass-123", email="analytics@example.com",
        )
        self.client.force_login(self.admin)

    def test_paid_ads_and_organic_content_are_returned_separately(self):
        common = {
            "date": date(2026, 8, 20), "account_id": "act_1", "account_name": "Wallcov",
            "currency": "USD", "spend": "12.5000", "impressions": 1000, "reach": 800,
            "clicks": 50, "messages_started": 10, "meta_leads": 2,
        }
        MetaAdDailyStat.objects.create(level="account", object_id="1", **common)
        MetaAdDailyStat.objects.create(
            level="ad", object_id="ad-1", campaign_id="campaign-1", campaign_name="Test campaign",
            adset_id="adset-1", adset_name="Test adset", ad_id="ad-1", ad_name="Test creative",
            thumbnail_url="https://example.com/ad.jpg", **common,
        )
        MetaContentStat.objects.create(
            ig_account_id="ig-1", media_id="media-1", caption="Organic post",
            media_type="IMAGE", media_product_type="FEED",
            published_at=timezone.now(), like_count=25, comments_count=3,
            reach=500, views=550, saved=7, shares=4, total_interactions=39,
            follows=6, profile_visits=11,
        )

        response = self.client.get("/api/meta-marketing/?from=2026-08-01&to=2026-08-31")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["paid"]["summary"]["spend"], 12.5)
        self.assertEqual(body["paid"]["ads"][0]["ad_id"], "ad-1")
        self.assertEqual(body["organic"]["content"][0]["media_id"], "media-1")
        self.assertEqual(body["organic"]["content"][0]["follows"], 6)
        self.assertNotIn("caption", body["paid"]["summary"])

    def test_followers_daily_meta_funnel_and_profitability_are_exposed(self):
        lead_funnel = Funnel.objects.create(name="Лиды", is_lead_funnel=True)
        lead_stage = Stage.objects.create(funnel=lead_funnel, name="Новый")
        core = Funnel.objects.create(name="21 Основний продукт")
        core_stage = Stage.objects.create(funnel=core, name="Оплачено", is_won=True)
        other = Funnel.objects.create(name="Другая воронка")
        other_stage = Stage.objects.create(funnel=other, name="Оплачено", is_won=True)
        first_customer = Contact.objects.create(first_name="Первый")
        ad_customer = Contact.objects.create(first_name="Реклама")

        Lead.objects.create(
            title="Instagram без ID", contact=first_customer, funnel=lead_funnel,
            stage=lead_stage, source="instagram",
        )
        Lead.objects.create(
            title="Instagram с ID", contact=ad_customer, funnel=lead_funnel,
            stage=lead_stage, source="instagram",
            meta_attribution={"platform": "instagram", "source_kind": "paid_ad", "ad_id": "ad-1"},
        )
        first = Deal.objects.create(
            title="Первая", contact=first_customer, funnel=core, stage=core_stage,
            source="instagram", amount=1000,
        )
        repeat = Deal.objects.create(
            title="Повторная", contact=first_customer, funnel=core, stage=core_stage,
            source="instagram", amount=2000,
        )
        excluded = Deal.objects.create(
            title="Исключена", contact=ad_customer, funnel=other, stage=other_stage,
            source="other", amount=3000,
        )
        attributed = Deal.objects.create(
            title="Реклама", contact=ad_customer, funnel=other, stage=other_stage,
            source="facebook", amount=4000,
            meta_attribution={"platform": "facebook", "source_kind": "paid_ad", "ad_id": "ad-1"},
        )
        moments = [
            (first, "2026-08-10T08:00:00+00:00"),
            (repeat, "2026-08-11T08:00:00+00:00"),
            (excluded, "2026-08-12T08:00:00+00:00"),
            (attributed, "2026-08-13T08:00:00+00:00"),
        ]
        for deal, moment in moments:
            payment = Payment.objects.create(deal=deal, provider="cash", amount=deal.amount, is_paid=True)
            Payment.objects.filter(pk=payment.pk).update(created_at=datetime.fromisoformat(moment))

        MetaAccountDailyStat.objects.create(
            date=date(2026, 8, 13), ig_account_id="ig-1", username="wallcov",
            followers_total=63057, followers_gained=25,
        )
        MetaAdDailyStat.objects.create(
            date=date(2026, 8, 13), level="account", account_id="act_1", object_id="1",
            currency="USD", spend="10", fx_rate_to_uah="40", spend_uah="400",
            messages_started=7,
        )

        body = self.client.get("/api/meta-marketing/?from=2026-08-01&to=2026-08-31").json()
        self.assertEqual(body["followers"]["current_total"], 63057)
        self.assertEqual(body["followers"]["period_gained"], 25)
        self.assertEqual(body["summary"]["meta_origin_leads"], 2)
        self.assertEqual(body["summary"]["meta_unassigned_leads"], 1)
        self.assertEqual(body["profitability"]["sales"], 3)
        self.assertEqual(body["profitability"]["repeat_sales"], 1)
        self.assertEqual(body["profitability"]["revenue"], 7000.0)
        self.assertEqual(body["profitability"]["repeat_revenue"], 2000.0)
        self.assertEqual(body["profitability"]["average_ltv"], 3500.0)
        self.assertEqual(body["profitability"]["ad_spend_uah"], 400.0)
        self.assertTrue(any(row["crm_meta_leads"] == 2 for row in body["daily"]))
        self.assertTrue(any(row["followers_total"] == 63057 for row in body["daily"]))

    def test_uah_rate_does_not_call_network(self):
        self.assertEqual(_nbu_rate("UAH", date(2026, 8, 21)), 1)

    def test_unsupported_follower_metric_stays_null_not_zero(self):
        MetaContentStat.objects.create(
            ig_account_id="ig-1", media_id="reel-1", caption="Reel",
            media_type="VIDEO", media_product_type="REELS", published_at=timezone.now(),
            follows=None, profile_visits=None,
        )
        body = self.client.get("/api/meta-marketing/?from=2026-08-01&to=2026-08-31").json()
        row = body["organic"]["content"][0]
        self.assertIsNone(row["follows"])
        self.assertIsNone(row["profile_visits"])

    def test_daily_stat_identity_is_unique(self):
        values = {"date": date(2026, 8, 20), "level": "account", "account_id": "act_1", "object_id": "1"}
        MetaAdDailyStat.objects.create(**values)
        with self.assertRaises(IntegrityError), transaction.atomic():
            MetaAdDailyStat.objects.create(**values)

    def test_action_parser_uses_meta_action_names(self):
        actions = _action_map([
            {"action_type": "onsite_conversion.messaging_conversation_started_7d", "value": "17"},
            {"action_type": "lead", "value": "3"},
        ])
        self.assertEqual(_pick(actions, ("onsite_conversion.messaging_conversation_started_7d",)), 17)
        self.assertEqual(_pick(actions, ("lead", "leadgen_grouped")), 3)

    def test_long_backfill_is_split_into_small_meta_requests(self):
        chunks = list(_date_chunks(date(2026, 6, 16), date(2026, 7, 2), days=7))
        self.assertEqual(chunks, [
            (date(2026, 6, 16), date(2026, 6, 22)),
            (date(2026, 6, 23), date(2026, 6, 29)),
            (date(2026, 6, 30), date(2026, 7, 2)),
        ])
