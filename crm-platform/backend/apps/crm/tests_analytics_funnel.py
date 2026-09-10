from datetime import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from .models import Deal, Funnel, Ga4DailyStat, Stage


class SalesFunnelPercentTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="funnel-admin", password="test-pass-123", email="funnel@example.com",
        )
        self.client.force_login(self.user)

    def test_zero_stage_does_not_turn_following_zero_into_one_hundred_percent(self):
        funnel = Funnel.objects.create(name="Тест процентів")
        stages = [
            Stage.objects.create(funnel=funnel, name=f"Етап {idx}", order=idx)
            for idx in range(4)
        ]
        first = Deal.objects.create(title="Перший", funnel=funnel, stage=stages[0])
        second = Deal.objects.create(title="Другий", funnel=funnel, stage=stages[1])
        Deal.objects.filter(pk__in=[first.pk, second.pk]).update(
            created_at=timezone.make_aware(datetime(2026, 9, 5, 12, 0)),
        )

        response = self.client.get(
            f"/api/analytics/sales-funnel/?from=2026-09-01&to=2026-09-10&funnel={funnel.pk}",
        )

        self.assertEqual(response.status_code, 200)
        steps = response.json()["stages"]
        self.assertEqual([step["through"] for step in steps], [2, 1, 0, 0])
        self.assertEqual([step["pct_prev"] for step in steps], [100, 50, 0, None])


class MarketingWebsiteAnalyticsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="website-admin", password="test-pass-123", email="website@example.com",
        )
        self.client.force_login(self.user)

    @patch("apps.warehouse.shop_site.fetch_shop_analytics")
    def test_ga4_response_includes_shop_data_for_the_same_exact_period(self, fetch_shop):
        fetch_shop.return_value = {
            "from": "2026-09-01", "to": "2026-09-10",
            "summary": {"views": 12, "visitors": 7, "orders": 1},
            "top_products": [], "top_pages": [],
            "measurement": {"status": "partial", "traffic_sources": "ga4_only"},
        }
        Ga4DailyStat.objects.create(
            date="2026-09-05", site="wallcov.com.ua", property_id="1",
            sessions=5, active_users=4, new_users=4, key_events=0,
        )

        response = self.client.get("/api/marketing/ga4/?from=2026-09-01&to=2026-09-10")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["shop_analytics"]["status"], "ok")
        self.assertEqual(body["shop_analytics"]["data"]["summary"]["visitors"], 7)
        self.assertEqual(body["search_console"]["status"], "not_connected")
        fetch_shop.assert_called_once_with({"from": "2026-09-01", "to": "2026-09-10"})

    @patch("apps.warehouse.shop_site.fetch_shop_analytics", side_effect=TimeoutError)
    def test_shop_failure_is_not_reported_as_zero(self, _fetch_shop):
        response = self.client.get("/api/marketing/ga4/?from=2026-09-01&to=2026-09-10")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["shop_analytics"], {"status": "unavailable", "data": None})
