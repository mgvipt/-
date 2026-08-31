"""API аналітики TikTok для сторінки «TikTok» у CRM. Право: analytics.view (як Аналітика)."""
from datetime import date, timedelta

from rest_framework import status as http_status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import TtAccountSnapshot, TtDailyStat, TtVideo


def _can_view(u):
    return bool(u.is_superuser or u.has_perm_code("analytics.view") or u.has_perm_code("roles.manage"))


class TtSummaryView(APIView):
    """GET /api/tiktok-insights/summary/ — шапка сторінки: лічильники, дельти, аудиторія."""

    def get(self, request):
        if not _can_view(request.user):
            return Response({"detail": "Немає прав"}, status=http_status.HTTP_403_FORBIDDEN)
        snap = TtAccountSnapshot.objects.filter(pk=1).first()
        days = list(TtDailyStat.objects.order_by("-date")[:30])
        d7 = [d for d in days if d.date >= date.today() - timedelta(days=7)]
        d30 = days

        def agg(rows, f):
            return sum(getattr(r, f) or 0 for r in rows)

        from apps.inbox import tiktok as tt
        ch = tt.get_channel()
        connected = bool(ch and ch.is_active and (ch.config or {}).get("access_token"))
        return Response({
            "connected": connected,
            "profile": (snap.profile if snap else {}),
            "followers_count": snap.followers_count if snap else 0,
            "total_likes": snap.total_likes if snap else 0,
            "videos_count": snap.videos_count if snap else 0,
            "followers_gained_7d": agg(d7, "followers_gained"),
            "followers_lost_7d": agg(d7, "followers_lost"),
            "followers_gained_30d": agg(d30, "followers_gained"),
            "followers_lost_30d": agg(d30, "followers_lost"),
            "video_views_7d": agg(d7, "video_views"),
            "video_views_30d": agg(d30, "video_views"),
            "profile_views_30d": agg(d30, "profile_views"),
            "likes_30d": agg(d30, "likes"),
            "comments_30d": agg(d30, "comments"),
            "shares_30d": agg(d30, "shares"),
            "link_clicks_30d": agg(d30, "bio_link_clicks"),
            "contact_clicks_30d": agg(d30, "email_clicks") + agg(d30, "phone_clicks") + agg(d30, "address_clicks"),
            "leads_30d": agg(d30, "lead_submissions"),
            "engagement_rate_avg_30d": (round(sum(r.engagement_rate for r in d30) / len(d30), 4)
                                        if d30 and any(r.engagement_rate for r in d30)
                                        else (round((agg(d30, "likes") + agg(d30, "comments") + agg(d30, "shares")) / max(1, agg(d30, "video_views")), 4) if d30 else 0)),
            "audience_ages": snap.audience_ages if snap else [],
            "audience_genders": snap.audience_genders if snap else [],
            "audience_countries": snap.audience_countries if snap else [],
            "audience_cities": snap.audience_cities if snap else [],
            "audience_activity": snap.audience_activity if snap else [],
            "averages": snap.averages if snap else {},
            "last_sync": snap.fetched_at if snap else None,
        })


class TtTimeseriesView(APIView):
    """GET /api/tiktok-insights/timeseries/?days=30 — добові ряди для графіків."""

    def get(self, request):
        if not _can_view(request.user):
            return Response({"detail": "Немає прав"}, status=http_status.HTTP_403_FORBIDDEN)
        try:
            days = max(7, min(60, int(request.GET.get("days", 30))))
        except ValueError:
            days = 30
        rows = list(TtDailyStat.objects.order_by("-date")[:days])[::-1]
        return Response([{
            "date": r.date.isoformat(),
            "followers_total": r.followers_total,
            "followers_gained": r.followers_gained,
            "followers_lost": r.followers_lost,
            "video_views": r.video_views,
            "profile_views": r.profile_views,
            "likes": r.likes, "comments": r.comments, "shares": r.shares,
            "engagement_rate": r.engagement_rate,
            "link_clicks": r.bio_link_clicks,
            "contact_clicks": r.email_clicks + r.phone_clicks + r.address_clicks,
            "leads": r.lead_submissions,
        } for r in rows])


class TtVideosView(APIView):
    """GET /api/tiktok-insights/videos/?sort=views|date|engagement&limit=50 — таблиця відео."""

    def get(self, request):
        if not _can_view(request.user):
            return Response({"detail": "Немає прав"}, status=http_status.HTTP_403_FORBIDDEN)
        sort = request.GET.get("sort", "date")
        try:
            limit = max(5, min(200, int(request.GET.get("limit", 50))))
        except ValueError:
            limit = 50
        qs = TtVideo.objects.all()
        if sort == "views":
            qs = qs.order_by("-views")
        elif sort == "engagement":
            qs = qs.order_by("-likes")
        else:
            qs = qs.order_by("-create_time")
        out = []
        for v in qs[:limit]:
            er = round((v.likes + v.comments + v.shares) / v.views, 4) if v.views else 0
            out.append({
                "item_id": v.item_id, "caption": v.caption[:180], "create_time": v.create_time,
                "thumbnail_url": v.thumbnail_url, "share_url": v.share_url, "duration": v.duration,
                "views": v.views, "reach": v.reach, "likes": v.likes, "comments": v.comments,
                "shares": v.shares, "average_time_watched": v.average_time_watched,
                "full_video_watched_rate": v.full_video_watched_rate,
                "engagement_rate": er, "impression_sources": v.impression_sources,
            })
        return Response(out)


class TtTrendingView(APIView):
    """GET /api/tiktok-insights/trending/?q=декор стін — живі трендові запити TikTok (UA)."""

    def get(self, request):
        if not _can_view(request.user):
            return Response({"detail": "Немає прав"}, status=http_status.HTTP_403_FORBIDDEN)
        q = (request.GET.get("q") or "декор стін").strip()[:60]
        from . import service
        try:
            return Response({"query": q, "keywords": service.trending(q)})
        except Exception as exc:
            return Response({"query": q, "keywords": [], "error": str(exc)[:200]})


class TtSyncView(APIView):
    """POST /api/tiktok-insights/sync/ — ручне оновлення (кнопка на сторінці)."""

    def post(self, request):
        if not _can_view(request.user):
            return Response({"detail": "Немає прав"}, status=http_status.HTTP_403_FORBIDDEN)
        from . import service
        try:
            r1 = service.sync_daily(30)
            r2 = service.sync_videos(200)
            return Response({**r1, **r2})
        except Exception as exc:
            return Response({"detail": str(exc)[:300]}, status=http_status.HTTP_502_BAD_GATEWAY)
