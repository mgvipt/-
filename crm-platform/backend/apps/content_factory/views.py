"""Контент-завод — API (етап 0, 24.09.2026).

Доступ: власник (суперюзер) або право content_factory.access. Решта отримує 403.
GET  /api/content-factory/overview/        — лічильники сторінок
GET  /api/content-factory/channels/        — список сторінок
POST /api/content-factory/channels/        — {link, platform?, role, title?, note?}
PATCH/DELETE /api/content-factory/channels/<id>/
Етап 1: GET /questions/, PATCH /questions/settings/, POST /questions/run/, PATCH /questions/<id>/
Етап 2: GET /telegram/, PATCH /telegram/settings/, POST /telegram/draft/, PATCH /telegram/posts/<id>/, POST /telegram/posts/<id>/photos/
"""
from datetime import timedelta

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import questions as qsvc
from . import telegram as tgsvc
from .models import (ChannelLinkError, ContentChannel, QuestionMention, QuestionSettings, QuestionTopic, TgPost,
                     TgSettings, parse_channel_link)

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


# ── Етап 1 (24.09.2026): питання клієнтів ─────────────────────────────────────────────────────


def _settings_payload(s, dry=None):
    return {
        "enabled": s.enabled, "model": s.model, "models": QuestionSettings.MODELS,
        "monthly_budget_usd": float(s.monthly_budget_usd), "spent_month_usd": round(qsvc.month_spent(), 4),
        "min_new": s.min_new, "last_run_at": timezone.localtime(s.last_run_at).isoformat() if s.last_run_at else None,
        "last_run_note": s.last_run_note, "pending": dry,
    }


class QuestionsView(_Base):
    """GET ?days=7&status=active — теми, відсортовані за кількістю питань за період."""
    def get(self, request):
        try:
            days = max(1, min(int(request.GET.get("days", 7)), 90))
        except ValueError:
            days = 7
        since = timezone.now() - timedelta(days=days)
        status = request.GET.get("status", "active")
        qs = QuestionTopic.objects.all()
        if status == "active":
            qs = qs.exclude(status=QuestionTopic.Status.IGNORED)
        elif status in QuestionTopic.Status.values:
            qs = qs.filter(status=status)
        qs = qs.annotate(n_period=Count("mentions", filter=Q(mentions__asked_at__gte=since)),
                         n_total=Count("mentions"))
        topics = sorted(qs, key=lambda t: (-t.n_period, -t.n_total, t.id))[:200]
        chans = {}
        for tid, ch, n in (QuestionMention.objects.filter(topic_id__in=[t.id for t in topics], asked_at__gte=since)
                           .values_list("topic_id", "channel").annotate(n=Count("id"))):
            chans.setdefault(tid, {})[ch or "інше"] = n
        s = QuestionSettings.get()
        return Response({
            "days": days,
            "topics": [{
                "id": t.id, "title": t.title, "material": t.material, "status": t.status,
                "status_display": t.get_status_display(), "count_period": t.n_period, "count_total": t.n_total,
                "channels": chans.get(t.id, {}), "examples": t.examples or [],
                "kb": {"id": t.kb_item_id, "title": t.kb_item_title} if t.kb_item_id else None,
                "last_seen": timezone.localtime(t.last_seen).isoformat() if t.last_seen else None,
            } for t in topics if t.n_period or status != "active"],
            "statuses": QuestionTopic.Status.choices,
            "settings": _settings_payload(s, qsvc.run(dry_run=True)),
        })


class QuestionSettingsView(_Base):
    """PATCH {enabled, model, monthly_budget_usd}. Увімкнути платний розбір і змінити ліміт — лише власник."""
    def patch(self, request):
        if not request.user.is_superuser:
            return Response({"error": "Змінювати налаштування розбору може лише власник."}, status=403)
        s, data = QuestionSettings.get(), request.data or {}
        if "enabled" in data:
            s.enabled = bool(data["enabled"])
        if "model" in data:
            if data["model"] not in dict(QuestionSettings.MODELS):
                return Response({"error": "Невідома модель."}, status=400)
            s.model = data["model"]
        if "monthly_budget_usd" in data:
            try:
                b = round(float(data["monthly_budget_usd"]), 2)
            except (TypeError, ValueError):
                return Response({"error": "Ліміт має бути числом."}, status=400)
            if not 0 <= b <= 50:
                return Response({"error": "Ліміт — від $0 до $50 на місяць."}, status=400)
            s.monthly_budget_usd = b
        s.save()
        return Response(_settings_payload(s))


class QuestionRunView(_Base):
    """POST — розібрати нові питання зараз (одна порція до 120 питань; решту — наступним натисканням або вночі)."""
    def post(self, request):
        if not request.user.is_superuser:
            return Response({"error": "Запускати платний розбір може лише власник."}, status=403)
        return Response(qsvc.run(force=True, max_batches=1))


class QuestionTopicView(_Base):
    def patch(self, request, pk):
        t = get_object_or_404(QuestionTopic, pk=pk)
        st = (request.data or {}).get("status")
        if st not in QuestionTopic.Status.values:
            return Response({"error": "Невідомий статус."}, status=400)
        t.status = st
        t.save(update_fields=["status"])
        return Response({"id": t.id, "status": t.status, "status_display": t.get_status_display()})


# ── Етап 2 (24.09.2026): Telegram-автопілот (лише чернетки; публікація з CRM вимкнена) ─────────

def _photos(request, ids):
    from apps.inbox.models import MediaLibraryItem
    from apps.inbox.views import _library_item_data
    by_id = {m.id: m for m in MediaLibraryItem.objects.filter(id__in=ids).select_related("file", "preview_file")
             .defer("file__data", "preview_file__data")}
    out = []
    for i in ids:
        if i in by_id:
            d = _library_item_data(request, by_id[i])
            # preview_url з _library_item_data буває http:// — на https-сторінці браузер його блокує
            https = lambda u: (u or "").replace("http://", "https://", 1)
            out.append({"id": i, "title": d["title"], "url": https(d["url"]), "preview_url": https(d["preview_url"])})
    return out


def _post(request, p):
    return {
        "id": p.id, "title": p.title, "text": p.text, "material": p.material, "status": p.status,
        "status_display": p.get_status_display(), "photos": _photos(request, p.photo_ids or []),
        "facts": p.facts or [], "checks": p.checks or [], "model": p.model,
        "topic": {"id": p.topic_id, "title": p.topic.title} if p.topic_id else None,
        "created_at": timezone.localtime(p.created_at).isoformat(),
    }


def _tg_settings(s):
    return {"daily_drafts": s.daily_drafts, "model": s.model, "models": QuestionSettings.MODELS,
            "monthly_budget_usd": float(s.monthly_budget_usd), "spent_month_usd": round(tgsvc.month_spent(), 4),
            "estimate_usd": tgsvc.estimate_usd(s.model), "channel": s.channel, "publish_enabled": False}


class TelegramView(_Base):
    def get(self, request):
        nt = tgsvc.next_topic()
        posts = TgPost.objects.select_related("topic").exclude(status=TgPost.Status.REJECTED)[:30]
        return Response({
            "settings": _tg_settings(TgSettings.get()),
            "next_topic": {"id": nt.id, "title": nt.title, "count_7d": nt.n} if nt else None,
            "posts": [_post(request, p) for p in posts],
        })


class TelegramSettingsView(_Base):
    def patch(self, request):
        if not request.user.is_superuser:
            return Response({"error": "Змінювати автопілот може лише власник."}, status=403)
        s, data = TgSettings.get(), request.data or {}
        if "daily_drafts" in data:
            s.daily_drafts = bool(data["daily_drafts"])
        if "model" in data:
            if data["model"] not in dict(QuestionSettings.MODELS):
                return Response({"error": "Невідома модель."}, status=400)
            s.model = data["model"]
        if "monthly_budget_usd" in data:
            try:
                b = round(float(data["monthly_budget_usd"]), 2)
            except (TypeError, ValueError):
                return Response({"error": "Ліміт має бути числом."}, status=400)
            if not 0 <= b <= 50:
                return Response({"error": "Ліміт — від $0 до $50 на місяць."}, status=400)
            s.monthly_budget_usd = b
        s.save()
        return Response(_tg_settings(s))


class TelegramDraftView(_Base):
    """POST {topic_id?} — нова чернетка (платно, в межах ліміту). Лише власник."""
    def post(self, request):
        if not request.user.is_superuser:
            return Response({"error": "Створювати платні чернетки може лише власник."}, status=403)
        topic = None
        if (request.data or {}).get("topic_id"):
            topic = get_object_or_404(QuestionTopic, pk=request.data["topic_id"])
        try:
            p = tgsvc.generate(topic)
        except tgsvc.BudgetError as e:
            return Response({"error": str(e)}, status=402)
        except ValueError as e:
            return Response({"error": str(e)}, status=400)
        return Response(_post(request, p), status=201)


class TelegramPostView(_Base):
    """PATCH {title?, text?, status?} — правка тексту й схвалення. «Опубліковано» через API не ставиться."""
    def patch(self, request, pk):
        p = get_object_or_404(TgPost, pk=pk)
        data = request.data or {}
        if "text" in data:
            text = str(data["text"] or "").strip()
            if not text:
                return Response({"error": "Текст поста порожній."}, status=400)
            p.text = text[:4000]
        if "title" in data:
            p.title = str(data["title"] or "").strip()[:200] or p.title
        if "status" in data:
            if data["status"] not in (TgPost.Status.DRAFT, TgPost.Status.APPROVED, TgPost.Status.REJECTED):
                return Response({"error": "Недоступний статус."}, status=400)
            p.status = data["status"]
        p.save()
        return Response(_post(request, p))


class TelegramPhotosView(_Base):
    """POST — інші реальні фото того ж матеріалу (без ШІ, безкоштовно)."""
    def post(self, request, pk):
        p = get_object_or_404(TgPost, pk=pk)
        new = tgsvc.pick_photos(p.material, exclude=p.photo_ids or []) if p.material else []
        if not new:
            return Response({"error": "Інших реальних фото цього матеріалу немає."}, status=400)
        p.photo_ids = new
        p.save(update_fields=["photo_ids", "updated_at"])
        return Response(_post(request, p))
