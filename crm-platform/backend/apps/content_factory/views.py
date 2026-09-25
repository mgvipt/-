"""Контент-завод — API (етап 0, 24.09.2026).

Доступ: власник (суперюзер) або право content_factory.access. Решта отримує 403.
GET  /api/content-factory/overview/        — лічильники сторінок
GET  /api/content-factory/channels/        — список сторінок
POST /api/content-factory/channels/        — {link, platform?, role, title?, note?}
PATCH/DELETE /api/content-factory/channels/<id>/
Етап 1: GET /questions/, PATCH /questions/settings/, POST /questions/run/, PATCH /questions/<id>/
Етап 2: GET /telegram/, PATCH /telegram/settings/, POST /telegram/draft/, PATCH /telegram/posts/<id>/, POST /telegram/posts/<id>/photos/
Публікація (24.09): POST /telegram/posts/ (вручну), POST /telegram/posts/<id>/test|publish/, GET /telegram/media/
Джерела (24.09): POST /sources/ingest/ (бот, секрет), GET /sources/, PATCH /sources/chats/<id>/, PATCH /sources/<id>/,
  GET /sources/thumb/<підпис>/ (без логіна, підпис діє 1 год)
Етап 3: GET/POST /feed/ (стрічка Virale, оновити), PATCH /feed/<id>/, GET/PATCH/POST /analyst/ (звіти, налаштування)
Етап 4–5: GET/POST /reels/ (список, зробити у фоні), PATCH /reels/<id>/, POST /reels/<id>/test/ (надіслати Олегу)
"""
import hmac
import json
import os
import re
from datetime import timedelta

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.http import Http404, HttpResponse
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import questions as qsvc
from . import analyst as ansvc
from . import reels as reelsvc
from . import styles as stylesvc
from . import drive as drivesvc
from . import sources as srcsvc
from . import telegram as tgsvc
from . import aiimage as aisvc
from . import blogs as blogsvc
from . import carousels as carsvc
from . import studio as studiosvc
from . import assist as assistsvc
from . import learn as learnsvc
from . import visual as visualsvc
from . import marketing as mktsvc
from .models import (AnalystReport, AnalystSettings, Blog, BlogFact, Carousel, ContentMemory, ChannelLinkError, ContentChannel, DriveFolder, FeedItem,
                     QuestionMention, QuestionSettings, QuestionTopic, ReelDraft, ReelStyle, SourceAsset, SourceChat,
                     TgPost, TgSettings, VideoScene, parse_channel_link)

PERM = "content_factory.access"


def can_access(user):
    return bool(user and user.is_authenticated and (user.is_superuser or user.has_perm_code(PERM)))


def _row(ch):
    return {
        "id": ch.id, "platform": ch.platform, "platform_display": ch.get_platform_display(),
        "handle": ch.handle, "url": ch.url, "title": ch.title, "role": ch.role,
        "role_display": ch.get_role_display(), "note": ch.note, "is_active": ch.is_active,
        "blog_id": ch.blog_id, "in_virale": ch.in_virale,
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
            "today": _today(),
        })


def _today():
    """Панель «Сьогодні» (редизайн 24.09): що робити зараз, що заплановано, скільки витрачено. Без ШІ."""
    from apps.assistant.services import month_spent as assist_spent
    from apps.assistant.models import AssistantSettings
    now = timezone.now()
    week = now - timedelta(days=7)
    topics = (QuestionTopic.objects.exclude(status=QuestionTopic.Status.IGNORED)
              .annotate(n7=Count("mentions", filter=Q(mentions__asked_at__gte=week)))
              .filter(n7__gt=0).order_by("-n7")[:4])
    posts = TgPost.objects
    pub7 = posts.filter(status=TgPost.Status.PUBLISHED, published_at__gte=week)
    sched = posts.filter(status=TgPost.Status.APPROVED, scheduled_at__gte=now).order_by("scheduled_at")[:4]
    try:
        hot = [(i, x) for i, x in ansvc.feed(days=7, limit=3) if x]
    except Exception:
        hot = []
    spend = [
        {"key": "questions", "label": "Питання клієнтів", "spent": qsvc.month_spent(),
         "budget": float(QuestionSettings.get().monthly_budget_usd)},
        {"key": "telegram", "label": "Telegram-пости", "spent": tgsvc.month_spent(),
         "budget": float(TgSettings.get().monthly_budget_usd)},
        {"key": "analyst", "label": "Аналітик", "spent": qsvc.month_spent(ansvc.SOURCE),
         "budget": float(AnalystSettings.get().monthly_budget_usd)},
        {"key": "reels", "label": "Рилси", "spent": reelsvc.spent_month(), "budget": None},
        {"key": "assistant", "label": "Асистент", "spent": assist_spent(),
         "budget": float(AssistantSettings.get().monthly_budget_usd)},
    ]
    return {
        "topics": [{"id": t.id, "title": t.title, "material": t.material, "n7": t.n7, "has_kb": bool(t.kb_item_id)}
                   for t in topics],
        "drafts": posts.filter(status=TgPost.Status.DRAFT).count(),
        "scheduled": [{"id": p.id, "title": p.title, "at": p.scheduled_at} for p in sched],
        "published_7d": pub7.count(),
        "views_7d": sum(v or 0 for v in pub7.values_list("views", flat=True)),
        "reels_draft": ReelDraft.objects.filter(status=ReelDraft.Status.DRAFT).count(),
        "reels_ready": ReelDraft.objects.filter(status=ReelDraft.Status.APPROVED).count(),
        "sources_24h": SourceAsset.objects.filter(created_at__gte=now - timedelta(days=1)).count(),
        "sources_total": SourceAsset.objects.filter(hidden=False).count(),
        "hot": [{"id": i.id, "username": i.username, "x": x, "url": i.url, "preview_url": i.preview_url,
                 "caption": (i.caption or "")[:140]} for i, x in hot],
        "spend": [{**r, "spent": round(r["spent"], 3)} for r in spend],
    }


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
            blog=Blog.objects.filter(pk=data.get("blog_id") or 0).first(), created_by=request.user)
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
        if "blog_id" in data:
            ch.blog = Blog.objects.filter(pk=data["blog_id"] or 0).first()
        ch.save()
        return Response(_row(ch))

    def post(self, request, pk):
        """POST /channels/<id>/virale/ — додати сторінку у Virale, щоб її ролики йшли в стрічку (витрачає ліміт дій Virale)."""
        if not request.user.is_superuser:
            return Response({"error": "Лише власник."}, status=403)
        ch = get_object_or_404(ContentChannel, pk=pk)
        if ch.platform not in ("instagram", "tiktok", "youtube"):
            return Response({"error": "Virale відстежує лише Instagram, TikTok і YouTube."}, status=400)
        try:
            ansvc._mcp("virale_accounts_add", {"url": ch.url})
        except RuntimeError as e:
            return Response({"error": f"Virale: {str(e)[:200]}"}, status=400)
        ch.in_virale = True
        ch.save(update_fields=["in_virale"])
        return Response(dict(_row(ch), note="Додано у Virale — ролики зʼявляться після найближчого оновлення стрічки."))

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


def _iso(v):
    return timezone.localtime(v).isoformat() if v else None


def _post(request, p):
    return {
        "id": p.id, "title": p.title, "text": p.text, "material": p.material, "status": p.status,
        "status_display": p.get_status_display(), "photos": _photos(request, p.photo_ids or []),
        "videos": _photos(request, p.video_ids or []), "photo_ids": p.photo_ids or [], "video_ids": p.video_ids or [],
        "sources": _source_rows(SourceAsset.objects.filter(id__in=p.source_ids or [])),
        "source_ids": p.source_ids or [],
        "facts": p.facts or [], "checks": p.checks or [], "model": p.model,
        "topic": {"id": p.topic_id, "title": p.topic.title} if p.topic_id else None,
        "created_at": _iso(p.created_at), "scheduled_at": _iso(p.scheduled_at), "published_at": _iso(p.published_at),
        "publish_error": p.publish_error, "views": p.views, "reactions": p.reactions,
        "reactions_detail": p.reactions_detail or {}, "stats_at": _iso(p.stats_at),
        "tg_link": (f"https://t.me/{tgsvc.channel_username()}/{p.tg_message_id.split(',')[0]}"
                    if p.tg_message_id else ""),
    }


def _tg_settings(s):
    return {"daily_drafts": s.daily_drafts, "model": s.model, "models": QuestionSettings.MODELS,
            "monthly_budget_usd": float(s.monthly_budget_usd), "spent_month_usd": round(tgsvc.month_spent(), 4),
            "estimate_usd": tgsvc.estimate_usd(s.model), "channel": s.channel, "publish_enabled": tgsvc.publish_ready()}


class TelegramView(_Base):
    def get(self, request):
        nt = tgsvc.next_topic()
        posts = TgPost.objects.select_related("topic").exclude(
            status__in=[TgPost.Status.REJECTED, TgPost.Status.PUBLISHED]).order_by("status", "scheduled_at", "-created_at")[:40]
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


class TelegramManualPostView(_Base):
    """POST {title, text} — пост вручну, без ШІ (безкоштовно)."""
    def post(self, request):
        data = request.data or {}
        text = str(data.get("text") or "").strip()
        if not text:
            return Response({"error": "Напишіть текст поста."}, status=400)
        p = TgPost.objects.create(title=str(data.get("title") or text.split("\n")[0])[:200], text=text[:4000])
        return Response(_post(request, p), status=201)


class TelegramMediaView(_Base):
    """GET ?kind=image|video&material= — фото/відео з бібліотеки для поста (реальні фото й усі відео)."""
    def get(self, request):
        from apps.inbox.models import MediaLibraryItem
        kind = "video" if request.GET.get("kind") == "video" else "image"
        qs = MediaLibraryItem.objects.filter(is_active=True, kind=kind)
        if kind == "image":
            qs = qs.filter(tags__icontains=tgsvc.REAL_TAG)
        if request.GET.get("material"):
            qs = qs.filter(material__iexact=request.GET["material"])
        ids = list(qs.order_by("material", "sort", "id").values_list("id", flat=True)[:120])
        materials = sorted(set(MediaLibraryItem.objects.filter(is_active=True, kind=kind).filter(
            **({"tags__icontains": tgsvc.REAL_TAG} if kind == "image" else {})).values_list("material", flat=True)))
        return Response({"items": _photos(request, ids), "materials": materials})


class TelegramSendView(_Base):
    """POST /test/ — у особистий чат Олега; POST /publish/ — у канал зараз. Лише власник."""
    def post(self, request, pk, action):
        if not request.user.is_superuser:
            return Response({"error": "Публікувати може лише власник."}, status=403)
        p = get_object_or_404(TgPost, pk=pk)
        try:
            if action == "test":
                tgsvc.send_test(p)
                return Response({"ok": True, "note": "Надіслано вам у Telegram (@wallcov_smm_bot)."})
            p = tgsvc.publish(p.id)
        except tgsvc.PublishError as e:
            return Response({"error": str(e)}, status=400)
        return Response(_post(request, p))


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
    """PATCH {title?, text?, status?, scheduled_at?, photo_ids?, video_ids?} — правка, схвалення, план.
    «Опубліковано» через API не ставиться; опублікований пост не змінюється."""
    def patch(self, request, pk):
        p = get_object_or_404(TgPost, pk=pk)
        data = request.data or {}
        if p.status == TgPost.Status.PUBLISHED:
            return Response({"error": "Пост уже в каналі — змінити його тут не можна."}, status=400)
        if "scheduled_at" in data:
            if not request.user.is_superuser:
                return Response({"error": "Планувати публікацію може лише власник."}, status=403)
            if data["scheduled_at"]:
                when = parse_datetime(str(data["scheduled_at"]))
                if when is None:
                    return Response({"error": "Невірна дата."}, status=400)
                if timezone.is_naive(when):
                    when = timezone.make_aware(when)
                p.scheduled_at = when
            else:
                p.scheduled_at = None
        for field in ("photo_ids", "video_ids", "source_ids"):
            if field in data:
                ids = [int(i) for i in (data[field] or []) if str(i).isdigit()]
                setattr(p, field, ids[:tgsvc.MAX_MEDIA])
        if len(p.photo_ids or []) + len(p.video_ids or []) + len(p.source_ids or []) > tgsvc.MAX_MEDIA:
            return Response({"error": f"У пості максимум {tgsvc.MAX_MEDIA} фото й відео разом."}, status=400)
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


# ── Джерела контенту (24.09.2026): TG-групи й канал за посиланням, без завантаження файлів ─────────

def _source_rows(qs):
    return [{
        "id": a.id, "kind": a.kind, "kind_display": a.get_kind_display(), "caption": a.caption, "material": a.material,
        "tags": a.tags or [], "link": a.link, "hidden": a.hidden,
        "chat": a.chat.title if a.chat_id else ("Google Drive" if a.origin == SourceAsset.Origin.DRIVE else ""),
        "origin": a.origin, "file_name": a.file_name,
        "thumb_url": f"/api/content-factory/sources/thumb/{srcsvc.thumb_token(a.id)}/"
        if (a.thumb_file_id or a.kind == "photo" or a.origin == SourceAsset.Origin.DRIVE) else "",
        "duration": a.duration, "posted_at": _iso(a.posted_at),
    } for a in qs.select_related("chat")]


class SourceIngestView(APIView):
    """Приймає апдейти від бота @wallcov_smm_bot (Hetzner). Без логіна — лише із секретом CF_INGEST_SECRET."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        secret = os.environ.get("CF_INGEST_SECRET", "")
        if not secret or not hmac.compare_digest(request.headers.get("X-CF-Ingest", ""), secret):
            return Response({"error": "forbidden"}, status=403)
        try:
            update = request.data if isinstance(request.data, dict) else json.loads(request.body or b"{}")
        except ValueError:
            return Response({"error": "bad json"}, status=400)
        return Response({"status": srcsvc.ingest(update)})


class SourceThumbView(APIView):
    """Мініатюра за підписаним посиланням (для <img>, де немає заголовка авторизації). Підпис діє 1 годину."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, token):
        got = srcsvc.thumb_bytes(token)
        if not got:
            raise Http404
        resp = HttpResponse(got[0], content_type=got[1])
        resp["Cache-Control"] = "private, max-age=3600"
        return resp


class SourcesView(_Base):
    """GET ?chat=&material=&kind=&q=&hidden= — файли з джерел; плюс список чатів і матеріалів."""
    def get(self, request):
        qs = SourceAsset.objects.all()
        blog = Blog.objects.filter(pk=request.GET.get("blog") or 0).first()
        if blog:
            qs = qs.filter(blog=blog)
        if request.GET.get("hidden") != "1":
            qs = qs.filter(hidden=False)
        for key, field in (("chat", "chat_id"), ("material", "material"), ("kind", "kind"), ("origin", "origin")):
            if request.GET.get(key):
                qs = qs.filter(**{field: request.GET[key]})
        if request.GET.get("q"):
            qs = qs.filter(caption__icontains=request.GET["q"])
        total = qs.count()
        chats = [{"id": c.id, "title": c.title or str(c.chat_id), "username": c.username, "kind": c.kind,
                  "enabled": c.enabled, "count": c.n, "blog_id": c.blog_id}
                 for c in SourceChat.objects.annotate(n=Count("assets")) if not blog or c.blog_id in (blog.id, None)]
        mats = list((SourceAsset.objects.filter(blog=blog) if blog else SourceAsset.objects).exclude(material="")
                    .values_list("material").annotate(n=Count("id")).order_by("-n"))
        folders = [{"id": f.id, "folder_id": f.folder_id, "title": f.title or f.folder_id, "enabled": f.enabled,
                    "files_count": f.files_count, "last_error": f.last_error, "last_sync_at": _iso(f.last_sync_at),
                    "link": f"https://drive.google.com/drive/folders/{f.folder_id}", "blog_id": f.blog_id}
                   for f in DriveFolder.objects.all() if not blog or f.blog_id in (blog.id, None)]
        return Response({"total": total, "items": _source_rows(qs[:120]), "chats": chats, "drive_folders": folders,
                         "drive_email": drivesvc.service_email(),
                         "materials": [{"name": m, "count": n} for m, n in mats],
                         "ingest_ready": bool(os.environ.get("CF_INGEST_SECRET"))})


class SourceChatView(_Base):
    def patch(self, request, pk):
        if not request.user.is_superuser:
            return Response({"error": "Вмикати джерела може лише власник."}, status=403)
        c = get_object_or_404(SourceChat, pk=pk)
        data = request.data or {}
        if "enabled" in data:
            c.enabled = bool(data["enabled"])
        if "blog_id" in data:  # чат переходить у інший блог разом з уже прийнятими файлами
            c.blog = Blog.objects.filter(pk=data["blog_id"] or 0).first()
            SourceAsset.objects.filter(chat=c).update(blog=c.blog)
        c.save()
        return Response({"id": c.id, "enabled": c.enabled, "blog_id": c.blog_id})


class SourceAssetView(_Base):
    """PATCH {material?, tags?, hidden?} — поправити теги вручну або сховати файл."""
    def patch(self, request, pk):
        a = get_object_or_404(SourceAsset, pk=pk)
        data = request.data or {}
        if "material" in data:
            a.material = str(data["material"] or "")[:80]
        if "tags" in data:
            a.tags = [str(x)[:40] for x in (data["tags"] or [])][:20]
        if "hidden" in data:
            a.hidden = bool(data["hidden"])
        a.save()
        return Response(_source_rows(SourceAsset.objects.filter(pk=a.pk))[0])


class DriveFoldersView(_Base):
    """POST {link} — додати папку Google Drive; PATCH /<id>/ {enabled}; POST /sync/ — обійти зараз (у фоні)."""
    def post(self, request):
        if not request.user.is_superuser:
            return Response({"error": "Додавати папки може лише власник."}, status=403)
        fid = drivesvc.parse_folder_link((request.data or {}).get("link", ""))
        if len(fid) < 10:
            return Response({"error": "Вставте посилання на папку Google Drive."}, status=400)
        try:
            title = drivesvc.folder_meta(fid).get("name", "")
        except drivesvc.DriveError:
            return Response({"error": f"CRM не бачить цю папку. Відкрийте її для {drivesvc.service_email()} (Читач)."},
                            status=400)
        f, _ = DriveFolder.objects.update_or_create(folder_id=fid, defaults={
            "title": title[:200], "enabled": True, "blog": Blog.objects.filter(pk=(request.data or {}).get("blog_id") or 0).first()})
        return Response({"id": f.id, "title": f.title}, status=201)


class DriveFolderView(_Base):
    def patch(self, request, pk):
        if not request.user.is_superuser:
            return Response({"error": "Лише власник."}, status=403)
        f = get_object_or_404(DriveFolder, pk=pk)
        data = request.data or {}
        if "enabled" in data:
            f.enabled = bool(data["enabled"])
        if "blog_id" in data:
            f.blog = Blog.objects.filter(pk=data["blog_id"] or 0).first()  # файли папки перейдуть при найближчому обході
        f.save()
        return Response({"id": f.id, "enabled": f.enabled, "blog_id": f.blog_id})


class DriveSyncView(_Base):
    def post(self, request):
        if not request.user.is_superuser:
            return Response({"error": "Лише власник."}, status=403)
        import threading
        from django.db import connection

        def work():
            try:
                drivesvc.sync_all()
            finally:
                connection.close()
        threading.Thread(target=work, daemon=True).start()
        return Response({"ok": True, "note": "Оновлення запущено — великі папки обходяться кілька хвилин."})


class TelegramPublishedView(_Base):
    """GET — опубліковані з CRM пости: перегляди, реакції, історія знімків, підсумок. POST /refresh/ — оновити цифри."""
    def get(self, request):
        from .models import TgPostStat
        posts = list(TgPost.objects.select_related("topic").filter(status=TgPost.Status.PUBLISHED)
                     .order_by("-published_at")[:100])
        hist = {}
        for s in TgPostStat.objects.filter(post__in=posts).order_by("taken_at"):
            hist.setdefault(s.post_id, []).append({"at": _iso(s.taken_at), "views": s.views, "reactions": s.reactions})
        rows = []
        for p in posts:
            r = _post(request, p)
            h = hist.get(p.id, [])
            day = [x for x in h if x["at"] and p.published_at and
                   parse_datetime(x["at"]) - p.published_at <= timedelta(hours=25)]
            r["history"] = h
            r["views_24h"] = day[-1]["views"] if day else None
            rows.append(r)
        seen = [p.views for p in posts if p.views is not None]
        best = max(posts, key=lambda p: p.views or -1) if seen else None
        return Response({
            "posts": rows,
            "summary": {"count": len(posts), "avg_views": round(sum(seen) / len(seen)) if seen else None,
                        "total_reactions": sum(p.reactions or 0 for p in posts),
                        "best": {"id": best.id, "title": best.title, "views": best.views} if best else None},
        })

    def post(self, request):
        return Response({"updated": tgsvc.collect_stats(force=True)})


# ── Етап 3: стрічка рекомендацій і аналітик ───────────────────────────────────────────────────────

def _bg(fn):
    """Запустити довгу роботу у фоні (оновлення з ChatPlace йде з паузами між запитами)."""
    import threading
    from django.db import connection

    def work():
        try:
            fn()
        except Exception:
            pass
        finally:
            connection.close()
    threading.Thread(target=work, daemon=True).start()


class FeedView(_Base):
    """GET ?days=7&sort=outlier|views|er|date&status=&own=1 — ролики ніші. POST — оновити з Virale (у фоні, власник)."""
    def get(self, request):
        try:
            days = max(1, min(int(request.GET.get("days", 7)), 90))
        except ValueError:
            days = 7
        blog = Blog.objects.filter(pk=request.GET.get("blog") or 0).first()
        rows = ansvc.feed(days=days, sort=request.GET.get("sort", "outlier"), status=request.GET.get("status", ""),
                          include_own=request.GET.get("own") == "1", only_tracked=request.GET.get("all") != "1", blog=blog,
                          q=request.GET.get("q", "")[:120], author=request.GET.get("author", "")[:100])
        s = AnalystSettings.get()
        return Response({
            "items": [{"id": i.id, "username": i.username, "platform": i.platform, "url": i.url,
                       "preview_url": i.preview_url, "caption": i.caption, "media_type": i.media_type,
                       "duration": i.duration, "views": i.views, "likes": i.likes, "comments": i.comments,
                       "engagement": i.engagement, "x": x, "status": i.status, "is_own": i.is_own,
                       "published_at": _iso(i.published_at)} for i, x in rows],
            "total": FeedItem.objects.count(), "last_sync_at": _iso(s.last_feed_sync_at), "last_note": s.last_feed_note,
            "tracked": len(ansvc.tracked_handles(blog)),
            "authors": sorted(ansvc.tracked_handles(blog)) if request.GET.get("all") != "1"
                       else list(FeedItem.objects.values_list("username", flat=True).distinct().order_by("username")[:200]),
            "blog_pages": [{"id": c.id, "handle": c.handle, "platform": c.platform, "role": c.role, "in_virale": c.in_virale}
                           for c in ContentChannel.objects.filter(blog=blog).exclude(role=ContentChannel.Role.OWN)] if blog else [],
        })

    def post(self, request):
        if not request.user.is_superuser:
            return Response({"error": "Оновлювати стрічку може лише власник."}, status=403)
        _bg(ansvc.sync_feed)
        return Response({"ok": True, "note": "Оновлюю — 22 сторінки з паузами, це 1–2 хвилини."})


class FeedItemView(_Base):
    def patch(self, request, pk):
        i = get_object_or_404(FeedItem, pk=pk)
        st = (request.data or {}).get("status")
        if st not in FeedItem.Status.values:
            return Response({"error": "Невідомий статус."}, status=400)
        i.status = st
        i.save(update_fields=["status"])
        return Response({"id": i.id, "status": i.status})


def _reports_for(blog_id):
    """Звіти блогу; старі звіти без блогу (до 25.09) — це Wallcov."""
    qs = AnalystReport.objects.all()
    if not blog_id:
        return qs
    cond = Q(blog_id=blog_id)
    if Blog.objects.filter(pk=blog_id, slug="wallcov").exists():
        cond |= Q(blog__isnull=True)
    return qs.filter(cond)


class AnalystView(_Base):
    """GET — останні звіти й налаштування. PATCH — налаштування (власник). POST — звіт зараз (платно, власник)."""
    def get(self, request):
        s = AnalystSettings.get()
        return Response({
            "settings": {"weekly_enabled": s.weekly_enabled, "model": s.model, "models": QuestionSettings.MODELS,
                         "monthly_budget_usd": float(s.monthly_budget_usd),
                         "spent_month_usd": round(qsvc.month_spent(ansvc.SOURCE), 4),
                         "estimate_usd": ansvc.estimate_usd(s.model)},
            "reports": [{"id": r.id, "created_at": _iso(r.created_at), "period_days": r.period_days, "summary": r.summary,
                         "ideas": r.ideas, "inputs": r.inputs, "model": r.model}
                        for r in _reports_for(request.GET.get("blog"))[:10]],
        })

    def patch(self, request):
        if not request.user.is_superuser:
            return Response({"error": "Лише власник."}, status=403)
        s, data = AnalystSettings.get(), request.data or {}
        if "weekly_enabled" in data:
            s.weekly_enabled = bool(data["weekly_enabled"])
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
        return self.get(request)

    def post(self, request):
        if not request.user.is_superuser:
            return Response({"error": "Робити платний звіт може лише власник."}, status=403)
        try:
            ansvc.generate_report(days=int((request.data or {}).get("days") or 7),
                                  blog=Blog.objects.filter(pk=(request.data or {}).get("blog_id") or 0).first())
        except ansvc.BudgetError as e:
            return Response({"error": str(e)}, status=402)
        except ValueError as e:
            return Response({"error": str(e)}, status=400)
        return self.get(request)


# ── Етапи 4–5: рилси з нарізок ────────────────────────────────────────────────────────────────────

def _scene_thumb(request, s):
    if not s or not s.thumb_id:
        return ""
    return request.build_absolute_uri(f"/api/f/{s.thumb.token}/").replace("http://", "https://", 1)


def _link_url(request, link_id):
    from apps.inbox.models import SharedLink
    tok = SharedLink.objects.filter(pk=link_id).values_list("token", flat=True).first()
    if not tok:
        return ""
    return request.build_absolute_uri(f"/api/f/{tok}/").replace("http://", "https://", 1) if request else f"/api/f/{tok}/"


def _reel(request, r):
    scenes = {s.id: s for s in VideoScene.objects.filter(id__in=[b.get("scene_id") for b in r.beats]).select_related("asset", "thumb")}
    return {
        "id": r.id, "title": r.title, "topic": r.topic, "material": r.material, "caption": r.caption,
        "status": r.status, "status_display": r.get_status_display(), "duration": r.duration, "error": r.error,
        "facts": r.facts, "created_at": _iso(r.created_at), "style_id": r.style_id, "blog_id": r.blog_id, "busy": r.busy,
        "style_name": r.style.name if r.style_id else "Класичний",
        "stage": r.stage, "brief": {k: v for k, v in (r.brief or {}).items() if k not in ("prev_texts", "prev_caption")},
        "can_undo_texts": bool((r.brief or {}).get("prev_texts")), "review": r.review or {},
        "notes": studiosvc.editor_notes(r) if r.stage in ("script", "material", "style") else [],
        "variants": {k: _link_url(request, v) for k, v in (r.variants or {}).items()},
        "video_url": request.build_absolute_uri(f"/api/f/{r.file.token}/").replace("http://", "https://", 1) if r.file_id else "",
        "beats": [dict(b, what=scenes[b["scene_id"]].what if b.get("scene_id") in scenes else (b.get("prompt") or ""),
                       source=scenes[b["scene_id"]].asset.link if b.get("scene_id") in scenes else "",
                       thumb_url=(_link_url(request, b["image_id"]) if b.get("image_id")
                                  else _scene_thumb(request, scenes.get(b.get("scene_id"))))) for b in r.beats],
    }


class ReelsView(_Base):
    """GET — рилси й стан розмітки. POST {topic, material} — зробити рилс (у фоні, лише власник)."""
    def get(self, request):
        marked = (SourceAsset.objects.filter(kind="video").exclude(markup_at=None).values_list("material")
                  .annotate(n=Count("id")).order_by("-n"))
        mats = (SourceAsset.objects.filter(kind="video", hidden=False).exclude(material="").values_list("material")
                .annotate(n=Count("id")).order_by("-n"))
        return Response({
            "reels": [_reel(request, r) for r in ReelDraft.objects.select_related("file")
                      .filter(**({"blog_id": request.GET["blog"]} if request.GET.get("blog") else {}))[:20]],
            "images_spent_month_usd": round(aisvc.spent_month(), 3), "images_cap_usd": aisvc.MONTH_CAP,
            "materials": [{"name": m, "videos": n} for m, n in mats],
            "marked": {m: n for m, n in marked}, "scenes": VideoScene.objects.count(),
            "spent_month_usd": reelsvc.spent_month(),
            "ideas": [{"title": i["title"], "material": i.get("material", "")} for r in AnalystReport.objects.all()[:1]
                      for i in r.ideas if "рилс" in (i.get("format") or "")],
        })

    def post(self, request):
        if not request.user.is_superuser:
            return Response({"error": "Робити рилси (платно) може лише власник."}, status=403)
        topic = str((request.data or {}).get("topic") or "").strip()[:300]
        material = str((request.data or {}).get("material") or "").strip()
        blog = blogsvc.get_blog((request.data or {}).get("blog_id"))
        asset_ids = [int(x) for x in ((request.data or {}).get("asset_ids") or []) if str(x).isdigit()][:6]
        if not topic or (blog.real_footage and not material and not asset_ids):
            return Response({"error": "Вкажіть тему" + (" й матеріал (або виберіть відео)." if blog.real_footage else ".")}, status=400)
        if not blogsvc.is_ready(blog):
            return Response({"error": f"Блог «{blog.name}» ще не налаштований — допишіть майстер-промт у «Блогах»."}, status=400)
        style = ReelStyle.objects.filter(pk=(request.data or {}).get("style_id") or 0).first()

        def work():
            try:
                reelsvc.make_reel(topic, material, style=style, blog=blog, asset_ids=asset_ids or None)
            except Exception as e:
                ReelDraft.objects.create(title=topic[:200], topic=topic, material=material, blog=blog,
                                         status=ReelDraft.Status.REJECTED, error=str(e)[:300])
        _bg(work)
        return Response({"ok": True, "note": "Роблю рилс: розмітка нових відео, сценарій, монтаж — 3–8 хвилин."})


class StudioView(_Base):
    """Майстер рилса: POST /studio/ideas/ — 5 ідей; GET /studio/search/?q= — пошук Shorts на YouTube;
    POST /studio/ {brief, blog_id, material, asset_ids, style_id} — створити рилс і скласти сценарій (у фоні)."""
    def get(self, request, action=None):
        if action != "search":
            return Response(status=405)
        try:
            return Response(studiosvc.search_all(request.GET.get("q", ""), request.GET.get("where", "web")))
        except ValueError as e:
            return Response({"error": str(e)}, status=400)
        except Exception as e:
            return Response({"error": f"YouTube не відповів: {str(e)[:120]}"}, status=502)

    def post(self, request, action=None):
        if not request.user.is_superuser:
            return Response({"error": "Лише власник (ШІ платний)."}, status=403)
        data = request.data or {}
        blog = blogsvc.get_blog(data.get("blog_id"))
        if action == "ideas":
            try:
                feed_ids = [int(x) for x in (data.get("feed_ids") or []) if str(x).isdigit()][:3]
                return Response(studiosvc.ideas(blog, str(data.get("source") or "ai"), str(data.get("text") or "")[:1500],
                                                str(data.get("url") or "")[:500], feed_ids))
            except (ValueError, reelsvc.ReelError) as e:
                return Response({"error": str(e)}, status=400)
        brief = data.get("brief") if isinstance(data.get("brief"), dict) else {}
        brief = {k: reelsvc.clean_text(str(brief.get(k) or ""))[:400] for k in ("title", "hook", "goal", "why", "shots", "fit", "source")} | (
            {"structure": brief["structure"]} if isinstance(brief.get("structure"), (dict, list)) else {})
        if not brief.get("title"):
            return Response({"error": "Виберіть або впишіть ідею."}, status=400)
        material = str(data.get("material") or "").strip()[:80]
        asset_ids = [int(x) for x in (data.get("asset_ids") or []) if str(x).isdigit()][:6]
        if blog.real_footage and not material and not asset_ids:
            return Response({"error": "Виберіть матеріал або відео, з яких монтувати."}, status=400)
        if not blogsvc.is_ready(blog):
            return Response({"error": f"Блог «{blog.name}» ще не налаштований — допишіть майстер-промт у «Блогах»."}, status=400)
        r = ReelDraft.objects.create(title=brief["title"][:200], topic=brief["title"][:300], material=material, blog=blog,
                                     brief=brief, stage="idea", busy=True,
                                     style=ReelStyle.objects.filter(pk=data.get("style_id") or 0).first())

        def work():
            try:
                studiosvc.build_script(ReelDraft.objects.get(pk=r.pk), material=material, asset_ids=asset_ids or None)
            except Exception as e:
                ReelDraft.objects.filter(pk=r.pk).update(error=f"Сценарій не вдався: {str(e)[:200]}", busy=False)
        _bg(work)
        return Response({"ok": True, "id": r.id, "note": "Сценарист пише сценарій і підбирає кадри — 1–5 хвилин."})


class ReelScenesView(_Base):
    """GET ?material=&q= — сцени для заміни кадру (з превʼю). POST {material} — добудувати превʼю (безкоштовно, у фоні)."""
    def get(self, request):
        qs = VideoScene.objects.filter(asset__hidden=False).select_related("asset", "thumb").order_by("-quality", "id")
        if request.GET.get("material"):
            qs = qs.filter(asset__material=request.GET["material"])
        if request.GET.get("q"):
            qs = qs.filter(Q(what__icontains=request.GET["q"]) | Q(shot__icontains=request.GET["q"]))
        return Response({"scenes": [{"id": s.id, "what": s.what, "shot": s.shot, "quality": s.quality,
                                     "seconds": round(s.end - s.start, 1), "thumb_url": _scene_thumb(request, s),
                                     "source": s.asset.link} for s in qs[:150]],
                         "without_thumb": qs.filter(thumb=None).count()})

    def post(self, request):
        if not request.user.is_superuser:
            return Response({"error": "Лише власник."}, status=403)
        material = str((request.data or {}).get("material") or "")
        _bg(lambda: reelsvc.backfill_thumbs(material))
        return Response({"ok": True, "note": "Готую превʼю кадрів — хвилина-дві."})


class ReelView(_Base):
    def patch(self, request, pk):
        r = get_object_or_404(ReelDraft, pk=pk)
        data = request.data or {}
        if "beats" in data:
            beats = []
            old = {i: dict(x) for i, x in enumerate(r.beats)}
            for n, b in enumerate(data["beats"] or []):
                keep = {k: b[k] for k in ("image_id", "ai", "prompt", "orig_scene_id") if b.get(k)}
                if keep.get("image_id"):  # ШІ-кадр: лише ті картинки, що вже були в цьому ролику
                    known = {x.get("image_id") for x in old.values()}
                    if keep["image_id"] not in known:
                        return Response({"error": "Невідомий ШІ-кадр."}, status=400)
                    limit, sid = 8.0, None
                elif not b.get("scene_id") and keep.get("prompt") and r.stage != "done":
                    limit, sid = 8.0, None  # майстер: кадр ще не намальований — лише опис для ШІ
                    keep = {"prompt": keep["prompt"]}
                else:
                    sc = VideoScene.objects.filter(pk=b.get("scene_id")).first()
                    if not sc:
                        return Response({"error": "Такої сцени немає."}, status=400)
                    limit, sid = sc.end - sc.start, sc.id
                    keep = {k: v for k, v in keep.items() if k == "orig_scene_id"}
                try:
                    secs = max(0.8, min(float(b.get("seconds") or 2.5), limit))
                except (TypeError, ValueError):
                    return Response({"error": "Тривалість має бути числом."}, status=400)
                row = {"text": reelsvc.clean_text(str(b.get("text") or ""))[:80], "seconds": round(secs, 2), **keep}
                fx = b.get("fx") or {}
                fx = {k: v for k, v in (("transition", fx.get("transition")), ("motion", fx.get("motion")))
                      if (k == "transition" and v in reelsvc.XFADE) or (k == "motion" and v in reelsvc.MOTIONS)}
                if fx:
                    row["fx"] = fx
                if sid:
                    row["scene_id"] = sid
                beats.append(row)
            if not 2 <= len(beats) <= 8:
                return Response({"error": "У ролику має бути від 2 до 8 кадрів."}, status=400)
            r.beats = beats
        if "status" in data:
            if data["status"] not in ReelDraft.Status.values:
                return Response({"error": "Невідомий статус."}, status=400)
            r.status = data["status"]
        if "caption" in data:
            r.caption = str(data["caption"] or "")[:2200]
        if "style_id" in data:
            r.style = ReelStyle.objects.filter(pk=data["style_id"] or 0).first()
        if "stage" in data:
            if data["stage"] not in studiosvc.STAGES:
                return Response({"error": "Невідомий крок."}, status=400)
            r.stage = data["stage"]
            if r.stage == "done" and r.status == ReelDraft.Status.DRAFT and r.file_id:
                r.status = ReelDraft.Status.APPROVED
        r.save()
        return Response(_reel(request, r))

    def _studio(self, request, pk):
        """POST /reels/<id>/studio/ {op}: script — скласти сценарій заново; texts / undo_texts — переписати тексти / повернути;
        fill — намалювати відсутні кадри; autofx — ефекти монтажера; review — перевірка командою."""
        if not request.user.is_superuser:
            return Response({"error": "Лише власник."}, status=403)
        r = get_object_or_404(ReelDraft, pk=pk)
        op = (request.data or {}).get("op")
        if r.busy:
            return Response({"error": "Ролик ще обробляється — зачекайте."}, status=409)
        try:
            if op == "texts":
                studiosvc.rewrite_texts(r)
            elif op == "undo_texts":
                studiosvc.undo_texts(r)
            elif op == "autofx":
                r.beats = studiosvc.auto_fx(r.beats)
                r.save(update_fields=["beats"])
            elif op == "review":
                studiosvc.team_review(r)
            elif op in ("script", "fill"):
                if op == "fill" and aisvc.spent_month() >= aisvc.MONTH_CAP:
                    return Response({"error": f"Досягнуто місячної стелі ШІ-картинок ${aisvc.MONTH_CAP:.0f}."}, status=402)
                ReelDraft.objects.filter(pk=r.pk).update(busy=True, error="")

                def work():
                    try:
                        x = ReelDraft.objects.get(pk=r.pk)
                        if op == "script":
                            studiosvc.build_script(x, material=x.material)
                        else:
                            studiosvc.fill_missing(x)
                    except Exception as e:
                        ReelDraft.objects.filter(pk=r.pk).update(error=str(e)[:300])
                    finally:
                        ReelDraft.objects.filter(pk=r.pk).update(busy=False)
                _bg(work)
                return Response({"ok": True, "note": "Сценарист переписує сценарій — 1–3 хвилини." if op == "script"
                                 else f"Художник малює кадри ({len(studiosvc.missing(r))}) — до хвилини на кадр."})
            else:
                return Response({"error": "Невідома дія."}, status=400)
        except (ValueError, reelsvc.ReelError) as e:
            return Response({"error": str(e)}, status=400)
        r.refresh_from_db()
        return Response(_reel(request, r))

    def post(self, request, pk, action=None):
        """POST /reels/<id>/test/ — надіслати Олегу в Telegram; /render/ — перемонтувати за зміненими кадрами (у фоні)."""
        if action == "render":
            r = get_object_or_404(ReelDraft, pk=pk)

            if studiosvc.missing(r):
                return Response({"error": "Не всі кадри мають картинку — завершіть крок «Матеріал»."}, status=400)
            ReelDraft.objects.filter(pk=r.pk).update(busy=True, error="")

            def work():
                try:
                    reelsvc.rerender(r)
                    if r.stage in ("idea", "script", "material", "style"):
                        ReelDraft.objects.filter(pk=r.pk).update(stage="draft")
                except Exception as e:
                    ReelDraft.objects.filter(pk=r.pk).update(error=f"Перемонтаж не вдався: {str(e)[:200]}")
                finally:
                    ReelDraft.objects.filter(pk=r.pk).update(busy=False)
            _bg(work)
            return Response({"ok": True, "note": "Монтую — до хвилини."})
        if action == "studio":
            return self._studio(request, pk)
        if action == "frame":
            if not request.user.is_superuser:
                return Response({"error": "ШІ-кадри (платно) — лише власник."}, status=403)
            r = get_object_or_404(ReelDraft, pk=pk)
            data = request.data or {}
            try:
                idx = int(data.get("index"))
                assert 0 <= idx < len(r.beats)
            except (TypeError, ValueError, AssertionError):
                return Response({"error": "Невідомий кадр."}, status=400)
            op = data.get("op")
            if op not in ("improve", "regenerate", "revert", "edit"):
                return Response({"error": "Невідома дія."}, status=400)
            if op != "revert" and aisvc.spent_month() >= aisvc.MONTH_CAP:
                return Response({"error": f"Досягнуто місячної стелі ШІ-картинок ${aisvc.MONTH_CAP:.0f}."}, status=402)
            if r.busy:
                return Response({"error": "Цей ролик ще обробляється — зачекайте."}, status=409)
            ReelDraft.objects.filter(pk=r.pk).update(busy=True, error="")
            prompt = str(data.get("prompt") or "")[:800]

            def work():
                try:
                    if op == "improve":
                        reelsvc.improve_frame(r, idx)
                    elif op == "regenerate":
                        reelsvc.regenerate_frame(r, idx, prompt)
                    elif op == "edit":
                        reelsvc.edit_frame(r, idx, prompt)
                    else:
                        reelsvc.revert_frame(r, idx)
                except Exception as e:
                    ReelDraft.objects.filter(pk=r.pk).update(error=f"Кадр {idx + 1}: {str(e)[:200]}")
                finally:
                    ReelDraft.objects.filter(pk=r.pk).update(busy=False)
            _bg(work)
            return Response({"ok": True, "note": {"improve": "Покращую кадр і перемонтовую — до хвилини.",
                                                  "regenerate": "Малюю новий кадр і перемонтовую — до хвилини.",
                                                  "edit": "Домальовую в кадр і перемонтовую — до хвилини.",
                                                  "revert": "Повертаю справжній кадр."}[op]})
        if action in ("versions", "adapt"):
            if not request.user.is_superuser:
                return Response({"error": "Лише власник."}, status=403)
            r = get_object_or_404(ReelDraft, pk=pk)
            target = Blog.objects.filter(pk=(request.data or {}).get("blog_id") or 0).first() if action == "adapt" else None
            if action == "adapt" and not target:
                return Response({"error": "Виберіть блог."}, status=400)

            def work():
                try:
                    if action == "versions":
                        reelsvc.platform_versions(r)
                    else:
                        reelsvc.adapt_to_blog(r, target)
                except Exception as e:
                    ReelDraft.objects.filter(pk=r.pk).update(error=str(e)[:300])
            _bg(work)
            return Response({"ok": True, "note": "Монтую версії для TikTok і YouTube — хвилина-дві." if action == "versions"
                             else f"Адаптую для блогу «{target.name}» — зʼявиться в його рилсах за хвилину-дві."})
        if action == "advice":
            if not request.user.is_superuser:
                return Response({"error": "Лише власник."}, status=403)
            r = get_object_or_404(ReelDraft, pk=pk)
            try:
                return Response({"advice": assistsvc.reel_advice(r)})
            except ValueError as e:
                return Response({"error": str(e)}, status=400)
        if action != "test":
            return Response(status=405)
        if not request.user.is_superuser:
            return Response({"error": "Лише власник."}, status=403)
        r = get_object_or_404(ReelDraft.objects.select_related("file"), pk=pk)
        owner = tgsvc.tg_config()[2]
        if not r.file_id or not owner:
            return Response({"error": "Немає файлу або особистого чату."}, status=400)
        try:
            tgsvc._tg("sendVideo", {"chat_id": owner, "caption": (r.caption or r.title)[:1024], "supports_streaming": "true"},
                      {"video": (r.file.filename, bytes(r.file.data), "video/mp4")})
        except tgsvc.PublishError as e:
            return Response({"error": str(e)}, status=400)
        return Response({"ok": True, "note": "Надіслано вам у Telegram (@wallcov_smm_bot)."})


class ReelStylesView(_Base):
    """GET — стилі тексту (пресети, з референсів, «наш блог») і з чого можна зняти стиль.
    POST {source: "feed"|"asset"|"blog", id?} — зняти стиль з референсу (Gemini, ≈$0.001–0.01, лише власник)."""
    def get(self, request):
        stylesvc.ensure_presets()
        return Response({
            "styles": [{"id": s.id, "name": s.name, "origin": s.origin, "origin_display": s.get_origin_display(),
                        "font": s.font, "weight": s.weight, "size": s.size, "color": s.color, "stroke": s.stroke,
                        "stroke_color": s.stroke_color, "box": s.box, "box_color": s.box_color, "box_opacity": s.box_opacity,
                        "position": s.position, "upper": s.upper, "notes": s.notes, "source_url": s.source_url,
                        "has_structure": bool(s.structure), "structure": s.structure} for s in ReelStyle.objects.all()],
            "feed_refs": [{"id": i.id, "title": f"@{i.username}: {(i.caption or '').splitlines()[0][:60] if i.caption else ''}",
                           "preview_url": i.preview_url} for i in FeedItem.objects.filter(status=FeedItem.Status.SAVED)[:30]],
            "video_refs": [{"id": a.id, "title": (a.caption or a.file_name or f"відео {a.id}")[:80], "chat": a.chat.title if a.chat_id else "Drive"}
                           for a in SourceAsset.objects.filter(kind="video", origin="telegram", hidden=False).select_related("chat")[:30]],
        })

    def post(self, request):
        if not request.user.is_superuser:
            return Response({"error": "Лише власник."}, status=403)
        src, pk = (request.data or {}).get("source"), (request.data or {}).get("id")
        try:
            if src == "feed":
                st = stylesvc.from_feed_item(get_object_or_404(FeedItem, pk=pk))
            elif src == "asset":
                st = stylesvc.from_video_asset(get_object_or_404(SourceAsset, pk=pk, kind="video"))
            elif src == "blog":
                st = stylesvc.our_blog()
            else:
                return Response({"error": "Невідоме джерело."}, status=400)
        except (ValueError, reelsvc.ReelError) as e:
            return Response({"error": str(e)}, status=400)
        if not st:
            return Response({"error": "На цьому кадрі немає тексту — візьміть інший референс."}, status=400)
        return Response({"id": st.id, "name": st.name}, status=201)



# ── 25.09: блоги, їхня база знань і майстер-промт ────────────────────────────────────────────────

def _blog(b, full=False):
    chans = [{"id": c.id, "platform": c.platform, "handle": c.handle, "url": c.url}
             for c in b.channels.filter(role=ContentChannel.Role.OWN).order_by("platform", "handle")]
    out = {"id": b.id, "slug": b.slug, "name": b.name, "kind": b.kind, "kind_display": b.get_kind_display(),
           "about": b.about, "goal": b.goal, "color": b.color, "is_default": b.is_default, "use_crm_kb": b.use_crm_kb,
           "label_ai": b.label_ai, "real_footage": b.real_footage, "ready": blogsvc.is_ready(b),
           "accounts": chans, "facts_count": b.facts.filter(active=True).count(),
           "reels": b.reels.count(), "carousels": b.carousels.count(),
           "open_promises": b.memory.filter(promise_done=False).exclude(promise="").count()}
    if full:
        out.update({"visual": b.visual, "ref_images": [dict(r, url=_link_url(None, r.get("id"))) for r in (b.ref_images or [])],
                    "master_prompt": b.master_prompt, "goal": b.goal, "cta": b.cta, "template": blogsvc.TEMPLATE,
                    "facts": [{"id": f.id, "kind": f.kind, "kind_display": f.get_kind_display(), "title": f.title,
                               "text": f.text, "active": f.active} for f in b.facts.all()],
                    "kinds": BlogFact.Kind.choices})
    return out


class BlogsView(_Base):
    """GET — усі блоги. POST {name, about?, kind?} — новий блог (лише власник)."""
    def get(self, request):
        blogsvc.ensure_blogs()
        return Response({"blogs": [_blog(b) for b in Blog.objects.all()], "kinds": Blog.Kind.choices})

    def post(self, request):
        if not request.user.is_superuser:
            return Response({"error": "Лише власник."}, status=403)
        from django.utils.text import slugify
        from uuid import uuid4
        name = str((request.data or {}).get("name") or "").strip()[:120]
        if not name:
            return Response({"error": "Вкажіть назву блогу."}, status=400)
        kind = (request.data or {}).get("kind") if (request.data or {}).get("kind") in Blog.Kind.values else Blog.Kind.OTHER
        b = Blog.objects.create(name=name, slug=(slugify(name, allow_unicode=False) or "blog")[:40] + "-" + uuid4().hex[:6],
                                kind=kind, about=str((request.data or {}).get("about") or "")[:300],
                                master_prompt=blogsvc.TEMPLATE, sort=Blog.objects.count() * 10 + 10)
        return Response(_blog(b, full=True), status=201)


class BlogView(_Base):
    def get(self, request, pk):
        return Response(_blog(get_object_or_404(Blog, pk=pk), full=True))

    def patch(self, request, pk):
        if not request.user.is_superuser:
            return Response({"error": "Лише власник."}, status=403)
        b = get_object_or_404(Blog, pk=pk)
        data = request.data or {}
        for f, n in (("name", 120), ("about", 300), ("master_prompt", 8000), ("goal", 1000), ("cta", 1000)):
            if f in data:
                setattr(b, f, str(data[f] or "")[:n])
        if not b.name.strip():
            return Response({"error": "Назва не може бути порожньою."}, status=400)
        for f in ("use_crm_kb", "label_ai", "real_footage"):
            if f in data:
                setattr(b, f, bool(data[f]))
        if data.get("kind") in Blog.Kind.values:
            b.kind = data["kind"]
        if "color" in data and re.fullmatch(r"#[0-9a-fA-F]{6}", str(data["color"] or "")):
            b.color = data["color"]
        b.save()
        return Response(_blog(b, full=True))

    def delete(self, request, pk):
        if not request.user.is_superuser:
            return Response({"error": "Лише власник."}, status=403)
        b = get_object_or_404(Blog, pk=pk)
        if b.is_default:
            return Response({"error": "Основний блог видалити не можна."}, status=400)
        b.delete()  # акаунти, рилси й каруселі лишаються (привʼязка стає порожньою)
        return Response(status=204)


class BlogAccountsView(_Base):
    """POST {link} — привʼязати наш акаунт до блогу. DELETE ?channel= — відвʼязати (сторінка лишається)."""
    def post(self, request, pk):
        if not request.user.is_superuser:
            return Response({"error": "Лише власник."}, status=403)
        b = get_object_or_404(Blog, pk=pk)
        try:
            platform, handle, url = parse_channel_link((request.data or {}).get("link", ""), (request.data or {}).get("platform", ""))
        except ChannelLinkError as e:
            return Response({"error": str(e)}, status=400)
        ch, created = ContentChannel.objects.get_or_create(platform=platform, handle=handle,
                                                          defaults={"url": url, "role": ContentChannel.Role.OWN, "blog": b})
        if not created:
            if ch.role != ContentChannel.Role.OWN:
                return Response({"error": f"Ця сторінка вже є в списку як «{ch.get_role_display()}»."}, status=409)
            ch.blog = b
            ch.save(update_fields=["blog"])
        return Response(_blog(b, full=True))

    def delete(self, request, pk):
        if not request.user.is_superuser:
            return Response({"error": "Лише власник."}, status=403)
        b = get_object_or_404(Blog, pk=pk)
        ContentChannel.objects.filter(pk=request.GET.get("channel") or 0, blog=b).update(blog=None)
        return Response(_blog(b, full=True))


class BlogFactsView(_Base):
    """POST {kind, title, text} — запис бази знань блогу."""
    def post(self, request, pk):
        if not request.user.is_superuser:
            return Response({"error": "Лише власник."}, status=403)
        b = get_object_or_404(Blog, pk=pk)
        data = request.data or {}
        title = str(data.get("title") or "").strip()[:200]
        if not title:
            return Response({"error": "Вкажіть заголовок запису."}, status=400)
        BlogFact.objects.create(blog=b, title=title, text=str(data.get("text") or "")[:4000],
                                kind=data.get("kind") if data.get("kind") in BlogFact.Kind.values else BlogFact.Kind.FACT)
        return Response(_blog(b, full=True), status=201)


class BlogFactView(_Base):
    def patch(self, request, pk, fid):
        if not request.user.is_superuser:
            return Response({"error": "Лише власник."}, status=403)
        f = get_object_or_404(BlogFact, pk=fid, blog_id=pk)
        data = request.data or {}
        if "title" in data:
            f.title = str(data["title"] or "").strip()[:200] or f.title
        if "text" in data:
            f.text = str(data["text"] or "")[:4000]
        if data.get("kind") in BlogFact.Kind.values:
            f.kind = data["kind"]
        if "active" in data:
            f.active = bool(data["active"])
        f.save()
        return Response(_blog(f.blog, full=True))

    def delete(self, request, pk, fid):
        if not request.user.is_superuser:
            return Response({"error": "Лише власник."}, status=403)
        f = get_object_or_404(BlogFact, pk=fid, blog_id=pk)
        b = f.blog
        f.delete()
        return Response(_blog(b, full=True))


class BlogBriefView(_Base):
    """POST {brief} — чернетка майстер-промту з опису Олега (Haiku ≈$0.003). Не зберігає."""
    def post(self, request, pk):
        if not request.user.is_superuser:
            return Response({"error": "Лише власник."}, status=403)
        b = get_object_or_404(Blog, pk=pk)
        brief = str((request.data or {}).get("brief") or "").strip()[:3000]
        if len(brief) < 20:
            return Response({"error": "Опишіть блог хоча б двома-трьома реченнями."}, status=400)
        return Response(blogsvc.master_from_brief(b, brief))


# ── 25.09: каруселі ───────────────────────────────────────────────────────────────────────────────

def _carousel(request, c):
    return {
        "id": c.id, "blog_id": c.blog_id, "topic": c.topic, "title": c.title, "caption": c.caption, "template": c.template,
        "kind": c.kind, "funnel": c.funnel,
        "status": c.status, "status_display": c.get_status_display(), "busy": c.busy, "error": c.error,
        "facts": c.facts, "created_at": _iso(c.created_at),
        "slides": [{"headline": s.get("headline", ""), "body": s.get("body", ""), "hint": s.get("hint", ""),
                    "image_kind": (s.get("image") or {}).get("kind", "none"),
                    "image_prompt": (s.get("image") or {}).get("prompt", ""), "pos": s.get("pos") or "auto", "has_prev": bool(s.get("prev")),
                    "has_image_prev": bool(s.get("image_prev")),
                    "png_url": _link_url(request, s["rendered_id"]) if s.get("rendered_id") else ""} for s in c.slides],
    }


class CarouselsView(_Base):
    """GET ?blog= — каруселі блогу. POST {blog_id, topic, slides, template, images, material} — зробити (у фоні)."""
    def get(self, request):
        qs = Carousel.objects.all()
        if request.GET.get("blog"):
            qs = qs.filter(blog_id=request.GET["blog"])
        from .telegram import real_materials
        return Response({"carousels": [_carousel(request, c) for c in qs[:20]], "templates": list(carsvc.TEMPLATES.items()),
                         "kinds": list(carsvc.KINDS.items()), "funnels": list(carsvc.FUNNELS.items()),
                         "promises": [{"id": m.id, "promise": m.promise, "title": m.title} for m in
                                      ContentMemory.objects.filter(blog_id=request.GET.get("blog") or 0, promise_done=False).exclude(promise="").order_by("created_at")[:5]],
                         "materials": sorted(set(real_materials())), "spent_month_usd": round(carsvc.spent_month(), 3),
                         "images_spent_month_usd": round(aisvc.spent_month(), 3), "images_cap_usd": aisvc.MONTH_CAP})

    def post(self, request):
        if not request.user.is_superuser:
            return Response({"error": "Робити каруселі (платно) може лише власник."}, status=403)
        data = request.data or {}
        blog = blogsvc.get_blog(data.get("blog_id"))
        topic = str(data.get("topic") or "").strip()[:300]
        if not topic:
            return Response({"error": "Вкажіть тему."}, status=400)
        if not blogsvc.is_ready(blog):
            return Response({"error": f"Блог «{blog.name}» ще не налаштований — допишіть майстер-промт у «Блогах»."}, status=400)
        images = data.get("images") if data.get("images") in ("auto", "library", "ai", "none") else "auto"
        if images == "ai" and aisvc.spent_month() >= aisvc.MONTH_CAP:
            return Response({"error": f"Досягнуто місячної стелі ШІ-картинок ${aisvc.MONTH_CAP:.0f}."}, status=402)
        tpl = data.get("template") if data.get("template") in carsvc.TEMPLATES else "photo"
        c = Carousel.objects.create(blog=blog, topic=topic, title=topic[:200], template=tpl, busy=True)
        n, material = data.get("slides") or 6, str(data.get("material") or "")[:80]
        kind, funnel = data.get("kind") or "single", data.get("funnel") or "save"

        def work():
            try:
                carsvc.generate(blog, topic, n=n, template=tpl, images=images, material=material, into=c, kind=kind, funnel=funnel)
            except Exception as e:
                Carousel.objects.filter(pk=c.pk).update(error=str(e)[:300], status=Carousel.Status.REJECTED)
            finally:
                Carousel.objects.filter(pk=c.pk).update(busy=False)
        _bg(work)
        return Response({"ok": True, "id": c.id, "note": "Пишу слайди й малюю — 1–2 хвилини (з ШІ-картинками довше)."})


class CarouselView(_Base):
    def patch(self, request, pk):
        c = get_object_or_404(Carousel, pk=pk)
        if c.busy:
            return Response({"error": "Карусель ще готується — зачекайте."}, status=409)
        data = request.data or {}
        redraw = False
        if isinstance(data.get("slides"), list):
            if len(data["slides"]) != len(c.slides):
                return Response({"error": "Кількість слайдів змінювати тут не можна."}, status=400)
            for s, new in zip(c.slides, data["slides"]):
                s["headline"] = carsvc._lines(new.get("headline"), 90)  # переноси рядків зберігаються
                s["body"] = carsvc._lines(new.get("body"), 400)
                if new.get("pos") in ("auto", "top", "center", "bottom"):
                    s["pos"] = new["pos"]
            redraw = True
        if data.get("template") in carsvc.TEMPLATES:
            c.template, redraw = data["template"], True
        if "caption" in data:
            c.caption = str(data["caption"] or "")[:2200]
        if data.get("status") in Carousel.Status.values:
            c.status = data["status"]
        c.save()
        if redraw:
            carsvc.render(c)
        return Response(_carousel(request, c))

    def delete(self, request, pk):
        if not request.user.is_superuser:
            return Response({"error": "Лише власник."}, status=403)
        from apps.inbox.models import SharedLink
        c = get_object_or_404(Carousel, pk=pk)
        SharedLink.objects.filter(id__in=[s.get("rendered_id") for s in c.slides if s.get("rendered_id")]).delete()
        c.delete()
        return Response(status=204)

    def post(self, request, pk, action=None):
        if not request.user.is_superuser:
            return Response({"error": "Лише власник."}, status=403)
        c = get_object_or_404(Carousel, pk=pk)
        if action == "test":
            try:
                carsvc.send_test(c)
            except tgsvc.PublishError as e:
                return Response({"error": str(e)}, status=400)
            return Response({"ok": True, "note": "Надіслано вам у Telegram альбомом."})
        if action == "text":  # лише текст: один слайд або всі; картинки лишаються
            data = request.data or {}
            if c.busy:
                return Response({"error": "Карусель ще обробляється — зачекайте."}, status=409)
            try:
                if data.get("op") == "all":
                    carsvc.rewrite_all(c, wish=str(data.get("wish") or "")[:300])
                elif data.get("op") == "undo":
                    carsvc.undo_slide(c, int(data.get("index")))
                else:
                    idx = int(data.get("index"))
                    if not 0 <= idx < len(c.slides):
                        raise ValueError("Невідомий слайд.")
                    carsvc.rewrite_slide(c, idx, wish=str(data.get("wish") or "")[:300])
            except (TypeError, ValueError) as e:
                return Response({"error": str(e) or "Невідомий слайд."}, status=400)
            return Response(_carousel(request, c))
        if action == "adapt":
            target = Blog.objects.filter(pk=(request.data or {}).get("blog_id") or 0).first()
            if not target:
                return Response({"error": "Виберіть блог."}, status=400)
            try:
                new = carsvc.adapt_to_blog(c, target)
            except ValueError as e:
                return Response({"error": str(e)}, status=400)
            return Response({"ok": True, "id": new.id, "note": f"Готово: копія в блозі «{target.name}»."})
        if action == "advice":
            try:
                return Response({"advice": carsvc.advice(c)})
            except ValueError as e:
                return Response({"error": str(e)}, status=400)
        if action != "image":
            return Response(status=405)
        data = request.data or {}
        try:
            idx = int(data.get("index"))
            assert 0 <= idx < len(c.slides)
        except (TypeError, ValueError, AssertionError):
            return Response({"error": "Невідомий слайд."}, status=400)
        op = data.get("op")
        if op == "none":
            carsvc._remember_image(c.slides[idx])
            c.slides[idx]["image"] = {"kind": "none"}
            carsvc.render(c)
            return Response(_carousel(request, c))
        if op == "undo":
            try:
                carsvc.undo_image(c, idx)
            except ValueError as e:
                return Response({"error": str(e)}, status=400)
            return Response(_carousel(request, c))
        if op == "library":
            from apps.inbox.models import MediaLibraryItem
            if not MediaLibraryItem.objects.filter(pk=data.get("lib_id") or 0, kind="image").exists():
                return Response({"error": "Такого фото в бібліотеці немає."}, status=400)
            carsvc.set_library_image(c, idx, data["lib_id"])
            return Response(_carousel(request, c))
        if op not in ("ai", "improve", "interior", "improve_all"):
            return Response({"error": "Невідома дія."}, status=400)
        if aisvc.spent_month() >= aisvc.MONTH_CAP:
            return Response({"error": f"Досягнуто місячної стелі ШІ-картинок ${aisvc.MONTH_CAP:.0f}."}, status=402)
        if c.busy:
            return Response({"error": "Карусель ще обробляється — зачекайте."}, status=409)
        Carousel.objects.filter(pk=c.pk).update(busy=True, error="")
        prompt = str(data.get("prompt") or "").strip()[:800] or c.slides[idx].get("hint") or c.slides[idx].get("headline") or c.title

        def work():
            try:
                cc = Carousel.objects.get(pk=c.pk)
                if op == "ai":
                    carsvc.set_ai_image(cc, idx, prompt)
                elif op == "interior":
                    carsvc.interior_image(cc, idx)
                elif op == "improve_all":
                    carsvc.improve_all(cc)
                else:
                    carsvc.improve_image(cc, idx)
            except Exception as e:
                Carousel.objects.filter(pk=c.pk).update(error=f"Слайд {idx + 1}: {str(e)[:200]}")
            finally:
                Carousel.objects.filter(pk=c.pk).update(busy=False)
        _bg(work)
        return Response({"ok": True, "note": "Малюю картинку й перемальовую слайд — до хвилини."})



# ── 25.09: вичитка тексту ШІ й ШІ-обробка фото в постах ──────────────────────────────────────────

class ProofreadView(_Base):
    """POST {text, blog_id?} — орфографія й формулювання (Haiku ≈$0.001–0.003). Повертає виправлений текст і зміни."""
    def post(self, request):
        if not request.user.is_superuser:
            return Response({"error": "Лише власник."}, status=403)
        text = str((request.data or {}).get("text") or "")
        if not text.strip():
            return Response({"error": "Немає тексту для перевірки."}, status=400)
        blog = Blog.objects.filter(pk=(request.data or {}).get("blog_id") or 0).first()
        return Response(assistsvc.proofread(text, blog))


class TelegramPhotoAIView(_Base):
    """POST {photo_id, op: improve|edit, prompt?} — ШІ-копія фото поста (оригінал у бібліотеці не змінюється).
    Копія — неактивний запис бібліотеки з міткою «ШІ-обробка» (агенти продажу її не бачать); у пості міняється id."""
    def post(self, request, pk):
        if not request.user.is_superuser:
            return Response({"error": "Лише власник."}, status=403)
        from apps.inbox.models import MediaLibraryItem
        post = get_object_or_404(TgPost, pk=pk)
        data = request.data or {}
        try:
            pid = int(data.get("photo_id"))
        except (TypeError, ValueError):
            return Response({"error": "Невідоме фото."}, status=400)
        if pid not in (post.photo_ids or []):
            return Response({"error": "Цього фото немає в пості."}, status=400)
        m = MediaLibraryItem.objects.filter(pk=pid).select_related("file").first()
        if not m or not m.file_id or not m.file.data:
            return Response({"error": "Файл фото недоступний."}, status=400)
        op, prompt = data.get("op"), str(data.get("prompt") or "").strip()[:800]
        blog = blogsvc.default_blog()
        try:
            if op == "improve":
                out, mime = aisvc.improve(bytes(m.file.data), m.file.content_type, blog, aspect="4:5")
            elif op == "edit" and prompt:
                keep = " Фактуру, колір і малюнок декоративного покриття НЕ змінюй." if blog.label_ai else ""
                out, mime = aisvc.generate(f"Відредагуй це фото: {prompt}. Усе інше залиш як є.{keep} Без тексту.",
                                           aspect="4:5", ref=(bytes(m.file.data), m.file.content_type))
            else:
                return Response({"error": "Невідома дія або порожнє завдання."}, status=400)
        except aisvc.ImageError as e:
            return Response({"error": str(e)}, status=402)
        link = aisvc.save(out, mime, f"tg-{post.id}-{pid}-ai")
        copy = MediaLibraryItem.objects.create(title=f"{m.title} · ШІ-обробка"[:160], kind="image", section=m.section,
                                               material=m.material, tags="ШІ-обробка", file=link, is_active=False)
        post.photo_ids = [copy.id if i == pid else i for i in post.photo_ids]
        post.save(update_fields=["photo_ids"])
        return Response(_post(request, post))



class BlogMemoryView(_Base):
    """GET — памʼять блогу: останній контент і відкриті обіцянки. PATCH ?id= {promise_done} — закрити/відкрити обіцянку."""
    def get(self, request, pk):
        b = get_object_or_404(Blog, pk=pk)
        row = lambda m: {"id": m.id, "kind": m.kind, "kind_display": m.get_kind_display(), "ref_id": m.ref_id, "title": m.title,
                         "summary": m.summary, "promise": m.promise, "promise_done": m.promise_done,
                         "answers": m.answers_id, "created_at": _iso(m.created_at)}
        return Response({"recent": [row(m) for m in ContentMemory.objects.filter(blog=b)[:30]],
                         "open": [row(m) for m in ContentMemory.objects.filter(blog=b, promise_done=False).exclude(promise="").order_by("created_at")]})

    def patch(self, request, pk):
        if not request.user.is_superuser:
            return Response({"error": "Лише власник."}, status=403)
        m = get_object_or_404(ContentMemory, pk=request.GET.get("id") or 0, blog_id=pk)
        m.promise_done = bool((request.data or {}).get("promise_done"))
        m.save(update_fields=["promise_done"])
        return self.get(request, pk)



class BlogLearnView(_Base):
    """Навчити блог знаннями ззовні.
    POST (файл у multipart «file», або JSON {text} / {url}) — розібрати на пропозиції записів (не зберігає, ≈$0.02–0.08).
    POST /accept/ {items:[{kind,title,text}], master_add?} — додати вибрані записи й (за бажанням) дописати майстер-промт."""
    def post(self, request, pk, action=None):
        if not request.user.is_superuser:
            return Response({"error": "Лише власник."}, status=403)
        b = get_object_or_404(Blog, pk=pk)
        if action == "accept":
            data = request.data or {}
            made = 0
            for it in (data.get("items") or [])[:200]:
                title = str((it or {}).get("title") or "").strip()[:200]
                if not title:
                    continue
                kind = it.get("kind") if it.get("kind") in BlogFact.Kind.values else BlogFact.Kind.FACT
                BlogFact.objects.create(blog=b, kind=kind, title=title, text=str(it.get("text") or "")[:4000])
                made += 1
            add = str(data.get("master_add") or "").strip()
            if add:
                b.master_prompt = (b.master_prompt.rstrip() + "\n" + add[:3000]).strip()
                b.save(update_fields=["master_prompt", "updated_at"])
            return Response({"added": made, "master_updated": bool(add), "blog": _blog(b, full=True)})
        try:
            if action == "drive-list":
                return Response({"docs": learnsvc.drive_list(str((request.data or {}).get("link") or ""))})
            if action == "drive":  # вибрані документи Google Drive → один спільний розбір (назва документа — заголовок розділу)
                ids = [str(x) for x in ((request.data or {}).get("ids") or [])][:12]
                if not ids:
                    return Response({"error": "Виберіть документи."}, status=400)
                return Response(learnsvc.extract_docs(b, ids))
            f = request.FILES.get("file")
            if f:
                if f.size > 15 * 1024 * 1024:
                    return Response({"error": "Файл більший за 15 МБ."}, status=400)
                text = learnsvc.text_from_file(f.name, f.read())
            elif (request.data or {}).get("url"):
                text = learnsvc.text_from_url(str(request.data["url"]).strip())
            else:
                text = str((request.data or {}).get("text") or "")
            return Response(learnsvc.extract(b, text))
        except learnsvc.LearnError as e:
            return Response({"error": str(e)}, status=400)



class ChannelContentView(_Base):
    """GET — що зараз є на сторінці: останні ролики/пости з Virale (перегляди, ER, «×N від звичного»), зведення."""
    def get(self, request, pk):
        import statistics
        ch = get_object_or_404(ContentChannel, pk=pk)
        qs = list(FeedItem.objects.filter(username__iexact=ch.handle).order_by("-published_at")[:40])
        med = ansvc.medians()
        views = [i.views for i in qs if i.views]
        items = [{"id": i.id, "url": i.url, "preview_url": i.preview_url, "caption": (i.caption or "")[:300],
                  "media_type": i.media_type, "duration": i.duration, "views": i.views, "likes": i.likes,
                  "comments": i.comments, "engagement": i.engagement, "x": ansvc.outlier(i, med), "status": i.status,
                  "published_at": _iso(i.published_at)} for i in qs]
        best = max(items, key=lambda x: x["x"] or 0) if items else None
        return Response({"channel": _row(ch), "items": items, "summary": {
            "count": len(items), "median_views": int(statistics.median(views)) if views else None,
            "best": {"caption": best["caption"][:120], "x": best["x"], "url": best["url"]} if best and best["x"] else None,
            "last": items[0]["published_at"] if items else None,
            "reels_share": round(sum(1 for i in qs if (i.media_type or "").lower() in ("video", "reel", "clips")) / len(qs) * 100) if qs else None,
        }})



class BlogVisualView(_Base):
    """POST (multipart «file» — відео/картинка до 20 МБ, або JSON {asset_id} — відео з «Джерел») — зняти візуальну біблію
    з прикладу (Gemini ≈$0.01–0.03). PATCH {visual} — правка опису вручну. DELETE ?ref= — прибрати кадр-референс."""
    def post(self, request, pk):
        if not request.user.is_superuser:
            return Response({"error": "Лише власник."}, status=403)
        b = get_object_or_404(Blog, pk=pk)
        f = request.FILES.get("file")
        try:
            if f:
                if f.size > 20 * 1024 * 1024:
                    return Response({"error": "Файл більший за 20 МБ — обріжте приклад до 20–60 секунд."}, status=400)
                data, mime = f.read(), (f.content_type or "application/octet-stream")
            else:
                a = get_object_or_404(SourceAsset, pk=(request.data or {}).get("asset_id") or 0)
                import tempfile, shutil
                folder = tempfile.mkdtemp()
                try:
                    with open(reelsvc.fetch_original(a, folder), "rb") as fh:
                        data = fh.read()
                finally:
                    shutil.rmtree(folder, ignore_errors=True)
                mime = a.mime or ("video/mp4" if a.kind == "video" else "image/jpeg")
            if not (mime.startswith("video/") or mime.startswith("image/")):
                return Response({"error": "Потрібне відео або картинка."}, status=400)
            r, refs = visualsvc.analyze(b, data, mime)
            if not r.get("style"):
                return Response({"error": "ШІ не зміг описати приклад — спробуйте інший фрагмент."}, status=400)
            visualsvc.apply(b, r, refs)
        except reelsvc.ReelError as e:
            return Response({"error": str(e)}, status=400)
        return Response(_blog(b, full=True))

    def patch(self, request, pk):
        if not request.user.is_superuser:
            return Response({"error": "Лише власник."}, status=403)
        b = get_object_or_404(Blog, pk=pk)
        v = (request.data or {}).get("visual")
        if isinstance(v, dict):
            b.visual = {k: v[k] for k in ("style", "palette", "characters", "environment", "motion", "pacing", "text_style") if k in v}
            b.save(update_fields=["visual", "updated_at"])
        return Response(_blog(b, full=True))

    def delete(self, request, pk):
        if not request.user.is_superuser:
            return Response({"error": "Лише власник."}, status=403)
        b = get_object_or_404(Blog, pk=pk)
        rid = int(request.GET.get("ref") or 0)
        b.ref_images = [r for r in (b.ref_images or []) if r.get("id") != rid]
        b.save(update_fields=["ref_images", "updated_at"])
        return Response(_blog(b, full=True))



class WriteView(_Base):
    """POST {blog_id, idea, format: caption|reel|telegram|tiktok|youtube, current?} — текст від ШІ-SMM-стратега (≈$0.01)."""
    def post(self, request):
        if not request.user.is_superuser:
            return Response({"error": "Лише власник."}, status=403)
        data = request.data or {}
        blog = blogsvc.get_blog(data.get("blog_id"))
        try:
            return Response(mktsvc.write(blog, str(data.get("idea") or "")[:1500], fmt=str(data.get("format") or "caption"),
                                         current=str(data.get("current") or "")[:4000]))
        except ValueError as e:
            return Response({"error": str(e)}, status=400)
