"""Контент-завод — API (етап 0, 24.09.2026).

Доступ: власник (суперюзер) або право content_factory.access. Решта отримує 403.
GET  /api/content-factory/overview/        — лічильники сторінок
GET  /api/content-factory/channels/        — список сторінок
POST /api/content-factory/channels/        — {link, platform?, role, title?, note?}
PATCH/DELETE /api/content-factory/channels/<id>/
"""
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ChannelLinkError, ContentChannel, parse_channel_link

PERM = "content_factory.access"


def can_access(user):
    return bool(user and user.is_authenticated and (user.is_superuser or user.has_perm_code(PERM)))


def _row(ch):
    return {
        "id": ch.id, "platform": ch.platform, "platform_display": ch.get_platform_display(),
        "handle": ch.handle, "url": ch.url, "title": ch.title, "role": ch.role,
        "role_display": ch.get_role_display(), "note": ch.note, "is_active": ch.is_active,
        "created_at": timezone.localtime(ch.created_at).isoformat(),
    }


class _Base(APIView):
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not can_access(request.user):
            self.permission_denied(request, message="Розділ «Контент-завод» доступний лише власнику.")


class OverviewView(_Base):
    def get(self, request):
        qs = ContentChannel.objects.filter(is_active=True)
        by_role = dict(qs.values_list("role").annotate(n=Count("id")))
        by_platform = dict(qs.values_list("platform").annotate(n=Count("id")))
        return Response({
            "channels_total": qs.count(),
            "by_role": {r: by_role.get(r, 0) for r in ContentChannel.Role.values},
            "by_platform": {p: by_platform.get(p, 0) for p in ContentChannel.Platform.values},
        })


class ChannelListView(_Base):
    def get(self, request):
        return Response({"results": [_row(c) for c in ContentChannel.objects.all()],
                         "roles": ContentChannel.Role.choices, "platforms": ContentChannel.Platform.choices})

    def post(self, request):
        data = request.data or {}
        try:
            platform, handle, url = parse_channel_link(data.get("link", ""), data.get("platform", ""))
        except ChannelLinkError as e:
            return Response({"error": str(e)}, status=400)
        role = data.get("role") or ContentChannel.Role.COMPETITOR
        if role not in ContentChannel.Role.values:
            return Response({"error": "Невідомий тип сторінки."}, status=400)
        existing = ContentChannel.objects.filter(platform=platform, handle=handle).first()
        if existing:
            return Response({"error": f"Ця сторінка вже є в списку ({existing.get_role_display().lower()}).",
                             "id": existing.id}, status=409)
        ch = ContentChannel.objects.create(
            platform=platform, handle=handle, url=url, role=role,
            title=(data.get("title") or "").strip()[:200], note=(data.get("note") or "").strip(),
            created_by=request.user)
        return Response(_row(ch), status=201)


class ChannelDetailView(_Base):
    def patch(self, request, pk):
        ch = get_object_or_404(ContentChannel, pk=pk)
        data = request.data or {}
        if "role" in data:
            if data["role"] not in ContentChannel.Role.values:
                return Response({"error": "Невідомий тип сторінки."}, status=400)
            ch.role = data["role"]
        if "title" in data:
            ch.title = (data.get("title") or "").strip()[:200]
        if "note" in data:
            ch.note = (data.get("note") or "").strip()
        if "is_active" in data:
            ch.is_active = bool(data["is_active"])
        ch.save()
        return Response(_row(ch))

    def delete(self, request, pk):
        get_object_or_404(ContentChannel, pk=pk).delete()
        return Response(status=204)
