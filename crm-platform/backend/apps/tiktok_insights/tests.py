"""Тести аналітики TikTok: парсинг синка (замокані відповіді API) + права на ендпоінти."""
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.inbox.models import Channel
from .models import TtAccountSnapshot, TtDailyStat, TtVideo
from . import service

User = get_user_model()


def _mk_channel():
    return Channel.objects.create(kind="tiktok", name="TikTok · Direct", config={
        "tiktok_direct": True, "business_id": "biz-1", "access_token": "tok",
        "expires_at": (timezone.now() + timedelta(hours=12)).isoformat(),
        "refresh_token": "r", "refresh_expires_at": (timezone.now() + timedelta(days=20)).isoformat(),
    })


class SyncTests(TestCase):
    def setUp(self):
        _mk_channel()

    @patch("apps.inbox.tiktok._request")
    def test_sync_daily_writes_rows_and_snapshot(self, req):
        req.side_effect = [
            {"code": 0, "data": {"metrics": [
                {"date": "2026-08-29", "daily_total_followers": 36000, "daily_new_followers": 25,
                 "daily_lost_followers": 3, "profile_views": 120, "video_views": 5000,
                 "likes": 300, "comments": 12, "shares": 8, "engagement_rate": 0.064,
                 "bio_link_clicks": 7, "phone_number_clicks": 2, "lead_submissions": 1},
                {"date": "2026-08-30", "daily_total_followers": 36023, "daily_new_followers": 23,
                 "daily_lost_followers": 0, "video_views": 6100},
            ]}},
            {"code": 0, "data": {"followers_count": 36023, "total_likes": 480000, "videos_count": 214,
                                 "username": "dekor_dlia_stin", "display_name": "Wallcov",
                                 "audience_genders": [{"gender": "Female", "percentage": 0.78}],
                                 "audience_activity": [{"hour": "19", "count": 12720}],
                                 "average_views": 4200}},
        ]
        out = service.sync_daily(30)
        self.assertEqual(out["daily_rows"], 2)
        self.assertEqual(out["followers"], 36023)
        r = TtDailyStat.objects.get(date="2026-08-29")
        self.assertEqual((r.followers_gained, r.followers_lost, r.video_views, r.phone_clicks), (25, 3, 5000, 2))
        snap = TtAccountSnapshot.objects.get(pk=1)
        self.assertEqual(snap.videos_count, 214)
        self.assertEqual(snap.audience_genders[0]["gender"], "Female")
        self.assertEqual(snap.averages.get("average_views"), 4200)
        # повторний синк оновлює, а не дублює
        req.side_effect = [
            {"code": 0, "data": {"metrics": [{"date": "2026-08-29", "daily_new_followers": 26}]}},
            {"code": 0, "data": {"followers_count": 36030}},
        ]
        service.sync_daily(30)
        self.assertEqual(TtDailyStat.objects.count(), 2)
        self.assertEqual(TtDailyStat.objects.get(date="2026-08-29").followers_gained, 26)

    @patch("apps.inbox.tiktok._request")
    def test_sync_videos_pagination_and_upsert(self, req):
        req.side_effect = [
            {"code": 0, "data": {"has_more": True, "cursor": 111, "videos": [
                {"item_id": "v1", "caption": "A", "create_time": "1786032726", "video_views": 1000,
                 "likes": 50, "comments": 5, "shares": 2, "video_duration": 30.5,
                 "full_video_watched_rate": 0.06, "average_time_watched": 8.4,
                 "impression_sources": [{"impression_source": "For You", "percentage": 0.8}]}]}},
            {"code": 0, "data": {"has_more": False, "videos": [
                {"item_id": "v2", "caption": "B", "video_views": 200}]}},
        ]
        out = service.sync_videos(200)
        self.assertEqual(out["videos"], 2)
        v = TtVideo.objects.get(item_id="v1")
        self.assertEqual((v.views, v.likes, v.duration), (1000, 50, 30.5))
        self.assertEqual(v.impression_sources[0]["impression_source"], "For You")

    def test_sync_without_channel_raises(self):
        Channel.objects.all().delete()
        with self.assertRaises(RuntimeError):
            service.sync_daily(7)


class ApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser("o2", "o2@x.ua", "p")
        self.c = APIClient()
        self.c.force_authenticate(self.owner)
        _mk_channel()
        TtAccountSnapshot.objects.create(pk=1, followers_count=36023, videos_count=214,
                                         audience_activity=[{"hour": "19", "count": 1}])
        for i, d in enumerate(["2026-08-28", "2026-08-29", "2026-08-30"]):
            TtDailyStat.objects.create(date=d, followers_gained=10 + i, video_views=1000 * (i + 1),
                                       engagement_rate=0.05)
        TtVideo.objects.create(item_id="v1", caption="Топ", views=9000, likes=900, comments=10, shares=5)
        TtVideo.objects.create(item_id="v2", caption="Новіше", views=100,
                               create_time=timezone.now())

    def test_summary(self):
        r = self.c.get("/api/tiktok-insights/summary/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["followers_count"], 36023)
        self.assertEqual(r.data["followers_gained_30d"], 33)
        self.assertTrue(r.data["connected"])

    def test_timeseries_sorted_asc(self):
        r = self.c.get("/api/tiktok-insights/timeseries/?days=30")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([x["date"] for x in r.data], ["2026-08-28", "2026-08-29", "2026-08-30"])

    def test_videos_sort_views(self):
        r = self.c.get("/api/tiktok-insights/videos/?sort=views")
        self.assertEqual(r.data[0]["item_id"], "v1")
        self.assertAlmostEqual(r.data[0]["engagement_rate"], round(915 / 9000, 4))

    def test_permission_denied_without_analytics_view(self):
        from apps.accounts.models import Role
        role = Role.objects.create(name="Без аналітики", permissions=[])
        u = User.objects.create_user("plain", "p@x.ua", "p")
        u.role = role
        u.save()
        c = APIClient()
        c.force_authenticate(u)
        for url in ("/api/tiktok-insights/summary/", "/api/tiktok-insights/videos/",
                    "/api/tiktok-insights/timeseries/", "/api/tiktok-insights/trending/"):
            self.assertEqual(c.get(url).status_code, 403, url)
        self.assertEqual(c.post("/api/tiktok-insights/sync/").status_code, 403)

    @patch("apps.tiktok_insights.service.trending", return_value=["декор стіни", "декор стін 2026"])
    def test_trending(self, tr):
        r = self.c.get("/api/tiktok-insights/trending/?q=декор")
        self.assertEqual(r.data["keywords"][1], "декор стін 2026")
