from datetime import date

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from .meta_marketing import _action_map, _date_chunks, _pick
from .models import MetaAdDailyStat, MetaContentStat


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
