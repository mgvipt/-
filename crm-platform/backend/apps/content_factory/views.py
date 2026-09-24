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
from .models import (AnalystReport, AnalystSettings, ChannelLinkError, ContentChannel, DriveFolder, FeedItem,
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
        if request.GET.get("hidden") != "1":
            qs = qs.filter(hidden=False)
        for key, field in (("chat", "chat_id"), ("material", "material"), ("kind", "kind"), ("origin", "origin")):
            if request.GET.get(key):
                qs = qs.filter(**{field: request.GET[key]})
        if request.GET.get("q"):
            qs = qs.filter(caption__icontains=request.GET["q"])
        total = qs.count()
        chats = [{"id": c.id, "title": c.title or str(c.chat_id), "username": c.username, "kind": c.kind,
                  "enabled": c.enabled, "count": c.n} for c in SourceChat.objects.annotate(n=Count("assets"))]
        mats = list(SourceAsset.objects.exclude(material="").values_list("material").annotate(n=Count("id")).order_by("-n"))
        folders = [{"id": f.id, "folder_id": f.folder_id, "title": f.title or f.folder_id, "enabled": f.enabled,
                    "files_count": f.files_count, "last_error": f.last_error, "last_sync_at": _iso(f.last_sync_at),
                    "link": f"https://drive.google.com/drive/folders/{f.folder_id}"} for f in DriveFolder.objects.all()]
        return Response({"total": total, "items": _source_rows(qs[:120]), "chats": chats, "drive_folders": folders,
                         "drive_email": drivesvc.service_email(),
                         "materials": [{"name": m, "count": n} for m, n in mats],
                         "ingest_ready": bool(os.environ.get("CF_INGEST_SECRET"))})


class SourceChatView(_Base):
    def patch(self, request, pk):
        if not request.user.is_superuser:
            return Response({"error": "Вмикати джерела може лише власник."}, status=403)
        c = get_object_or_404(SourceChat, pk=pk)
        c.enabled = bool((request.data or {}).get("enabled"))
        c.save(update_fields=["enabled"])
        return Response({"id": c.id, "enabled": c.enabled})


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
        f, _ = DriveFolder.objects.update_or_create(folder_id=fid, defaults={"title": title[:200], "enabled": True})
        return Response({"id": f.id, "title": f.title}, status=201)


class DriveFolderView(_Base):
    def patch(self, request, pk):
        if not request.user.is_superuser:
            return Response({"error": "Лише власник."}, status=403)
        f = get_object_or_404(DriveFolder, pk=pk)
        f.enabled = bool((request.data or {}).get("enabled"))
        f.save(update_fields=["enabled"])
        return Response({"id": f.id, "enabled": f.enabled})


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
        rows = ansvc.feed(days=days, sort=request.GET.get("sort", "outlier"), status=request.GET.get("status", ""),
                          include_own=request.GET.get("own") == "1", only_tracked=request.GET.get("all") != "1")
        s = AnalystSettings.get()
        return Response({
            "items": [{"id": i.id, "username": i.username, "platform": i.platform, "url": i.url,
                       "preview_url": i.preview_url, "caption": i.caption, "media_type": i.media_type,
                       "duration": i.duration, "views": i.views, "likes": i.likes, "comments": i.comments,
                       "engagement": i.engagement, "x": x, "status": i.status, "is_own": i.is_own,
                       "published_at": _iso(i.published_at)} for i, x in rows],
            "total": FeedItem.objects.count(), "last_sync_at": _iso(s.last_feed_sync_at), "last_note": s.last_feed_note,
            "tracked": len(ansvc.tracked_handles()),
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
                        for r in AnalystReport.objects.all()[:10]],
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
            ansvc.generate_report(days=int((request.data or {}).get("days") or 7))
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


def _reel(request, r):
    scenes = {s.id: s for s in VideoScene.objects.filter(id__in=[b.get("scene_id") for b in r.beats]).select_related("asset", "thumb")}
    return {
        "id": r.id, "title": r.title, "topic": r.topic, "material": r.material, "caption": r.caption,
        "status": r.status, "status_display": r.get_status_display(), "duration": r.duration, "error": r.error,
        "facts": r.facts, "created_at": _iso(r.created_at), "style_id": r.style_id,
        "style_name": r.style.name if r.style_id else "Класичний",
        "video_url": request.build_absolute_uri(f"/api/f/{r.file.token}/").replace("http://", "https://", 1) if r.file_id else "",
        "beats": [dict(b, what=scenes[b["scene_id"]].what if b.get("scene_id") in scenes else "",
                       source=scenes[b["scene_id"]].asset.link if b.get("scene_id") in scenes else "",
                       thumb_url=_scene_thumb(request, scenes.get(b.get("scene_id")))) for b in r.beats],
    }


class ReelsView(_Base):
    """GET — рилси й стан розмітки. POST {topic, material} — зробити рилс (у фоні, лише власник)."""
    def get(self, request):
        marked = (SourceAsset.objects.filter(kind="video").exclude(markup_at=None).values_list("material")
                  .annotate(n=Count("id")).order_by("-n"))
        mats = (SourceAsset.objects.filter(kind="video", hidden=False).exclude(material="").values_list("material")
                .annotate(n=Count("id")).order_by("-n"))
        return Response({
            "reels": [_reel(request, r) for r in ReelDraft.objects.select_related("file").all()[:20]],
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
        if not topic or not material:
            return Response({"error": "Вкажіть тему й матеріал."}, status=400)
        style = ReelStyle.objects.filter(pk=(request.data or {}).get("style_id") or 0).first()

        def work():
            try:
                reelsvc.make_reel(topic, material, style=style)
            except Exception as e:
                ReelDraft.objects.create(title=topic[:200], topic=topic, material=material,
                                         status=ReelDraft.Status.REJECTED, error=str(e)[:300])
        _bg(work)
        return Response({"ok": True, "note": "Роблю рилс: розмітка нових відео, сценарій, монтаж — 3–8 хвилин."})


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
            for b in data["beats"] or []:
                sc = VideoScene.objects.filter(pk=b.get("scene_id")).first()
                if not sc:
                    return Response({"error": "Такої сцени немає."}, status=400)
                try:
                    secs = max(0.8, min(float(b.get("seconds") or 2.5), sc.end - sc.start))
                except (TypeError, ValueError):
                    return Response({"error": "Тривалість має бути числом."}, status=400)
                beats.append({"text": reelsvc.clean_text(str(b.get("text") or ""))[:80], "scene_id": sc.id,
                              "seconds": round(secs, 2)})
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
        r.save()
        return Response(_reel(request, r))

    def post(self, request, pk, action=None):
        """POST /reels/<id>/test/ — надіслати Олегу в Telegram; /render/ — перемонтувати за зміненими кадрами (у фоні)."""
        if action == "render":
            r = get_object_or_404(ReelDraft, pk=pk)

            def work():
                try:
                    reelsvc.rerender(r)
                except Exception as e:
                    ReelDraft.objects.filter(pk=r.pk).update(error=f"Перемонтаж не вдався: {str(e)[:200]}")
            _bg(work)
            return Response({"ok": True, "note": "Перемонтовую — до хвилини."})
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
