"""Розділ «Відгуки» в CRM: модерація (Олег), журнал просьб «кому б відправили», правила, фото.

Права: переглядати — власник або reviews.view / reviews.moderate; модерувати — власник або reviews.moderate;
змінювати правила — лише власник. Увімкнути відправку клієнтам через API неможливо (тексти не затверджені).
"""
from django.core import signing
from django.db.models import Count, F
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.crm.models import Contact, log_activity
from .models import Review, ReviewOptOut, ReviewPhoto, ReviewRequest, ReviewSettings
from .services import PHOTO_SALT, live_allowed, public_name, review_link, run_sweep

ACTIONS = {"publish": "опубліковано", "hide": "приховано", "reply": "відповідь Wallcov", "feature": "закріплено на головній",
           "unfeature": "знято з головної", "edit_text": "приховано особисті дані в тексті",
           "display_name": "змінено підпис", "hide_photo": "приховано фото", "show_photo": "показано фото"}
INT_FIELDS = {"delay_main_days": (1, 90), "delay_test_days": (1, 90), "remind_after_days": (1, 60),
              "repeat_block_days": (1, 365), "expire_days": (7, 365), "window_wait_days": (1, 90),
              "manager_quiet_hours": (0, 240), "per_run_cap": (1, 200)}
TEXT_FIELDS = ("text_main", "text_test", "text_remind")
LOCKED_FIELDS = ("send_enabled", "texts_approved")


def can_view(user):
    return bool(user and user.is_authenticated and (
        user.is_superuser or user.has_perm_code("reviews.view") or user.has_perm_code("reviews.moderate")))


def can_moderate(user):
    return bool(user and user.is_authenticated and (user.is_superuser or user.has_perm_code("reviews.moderate")))


def _iso(value):
    return timezone.localtime(value).isoformat() if value else None


def _page(request):
    try:
        page = max(1, int(request.query_params.get("page") or 1))
    except ValueError:
        page = 1
    try:
        size = min(200, max(1, int(request.query_params.get("page_size") or 50)))
    except ValueError:
        size = 50
    return page, size


def _staff_photo(photo):
    url = "/api/reviews/photo/%s/?sig=%s" % (photo.token, signing.dumps({"t": photo.token}, salt=PHOTO_SALT))
    return {"id": photo.id, "url": url, "thumb_url": url + "&size=thumb", "is_public": photo.is_public,
            "width": photo.width, "height": photo.height}


def staff_review(review):
    req = review.request
    return {
        "id": review.id, "status": review.status, "status_display": review.get_status_display(),
        "rating": review.rating, "text": review.text, "text_original": review.text_original,
        "edited": review.text != review.text_original, "display_name": review.display_name,
        "public_name": public_name(review), "anonymous": review.anonymous, "city": review.city,
        "room": review.room, "applied_by": review.applied_by, "kind": review.kind, "is_test": review.is_test,
        "products": review.products or [], "photos": [_staff_photo(p) for p in review.photos.all()],
        "consent_site": review.consent_site, "consent_social": review.consent_social,
        "consent_version": review.consent_version,
        "reply_text": review.reply_text, "replied_at": _iso(review.replied_at),
        "featured": review.featured, "hidden_reason": review.hidden_reason,
        "deal_id": review.deal_id, "deal_title": review.deal.title if review.deal_id else "",
        "contact_id": review.contact_id, "contact_name": str(review.contact) if review.contact_id else "",
        "conversation_id": req.conversation_id if req else None, "task_id": review.task_id,
        "created_at": _iso(review.created_at), "published_at": _iso(review.published_at),
    }


def request_row(req, user):
    return {
        "id": req.id, "status": req.status, "status_display": req.get_status_display(),
        "kind": req.kind, "kind_display": req.get_kind_display(),
        "deal_id": req.deal_id, "deal_title": req.deal.title if req.deal_id else "",
        "contact_id": req.contact_id, "contact_name": str(req.contact) if req.contact_id else "",
        "received_at": _iso(req.received_at), "due_at": _iso(req.due_at), "channel_label": req.channel_label,
        "reason": req.reason, "journal_at": _iso(req.journal_at), "sent_at": _iso(req.sent_at),
        "submitted_at": _iso(req.submitted_at), "is_test": req.is_test,
        "link": review_link(req.code) if req.is_test and user.is_superuser else "",
    }


def settings_dict(cfg):
    return {
        "send_enabled": cfg.send_enabled, "texts_approved": cfg.texts_approved, "live": live_allowed(cfg),
        "start_date": cfg.start_date.isoformat() if cfg.start_date else None,
        **{name: getattr(cfg, name) for name in INT_FIELDS},
        "send_from": cfg.send_from.strftime("%H:%M"), "send_to": cfg.send_to.strftime("%H:%M"),
        "test_funnel_ids": cfg.test_funnel_ids, "excluded_funnel_ids": cfg.excluded_funnel_ids,
        "allowlist_contact_ids": cfg.allowlist_contact_ids,
        **{name: getattr(cfg, name) for name in TEXT_FIELDS},
        "google_review_url": cfg.google_review_url, "link_example": review_link("Ab3xK9mPq2Rt"),
    }


class ReviewListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not can_view(request.user):
            return Response({"detail": "Немає доступу до відгуків"}, status=403)
        status = request.query_params.get("status") or "pending"
        qs = (Review.objects.select_related("deal", "contact", "request").prefetch_related("photos")
              .order_by("-created_at", "-id"))
        if status != "all":
            qs = qs.filter(status=status)
        page, size = _page(request)
        counts = {key: 0 for key in ("pending", "published", "hidden")}
        counts.update(dict(Review.objects.values_list("status").annotate(n=Count("id"))))
        return Response({"results": [staff_review(r) for r in qs[(page - 1) * size: page * size]],
                         "count": qs.count(), "counts": counts, "can_moderate": can_moderate(request.user)})


class ReviewDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if not can_view(request.user):
            return Response({"detail": "Немає доступу до відгуків"}, status=403)
        review = get_object_or_404(Review.objects.select_related("deal", "contact", "request"), pk=pk)
        return Response(staff_review(review))


class ReviewModerateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not can_moderate(request.user):
            return Response({"detail": "Модерувати відгуки може лише власник або відповідальний"}, status=403)
        review = get_object_or_404(Review.objects.select_related("deal", "contact", "request"), pk=pk)
        action = str(request.data.get("action") or "")
        now, user = timezone.now(), request.user
        if action == "publish":
            if not review.consent_site:
                return Response({"detail": "Клієнт не дав згоди на публікацію — опублікувати не можна"}, status=400)
            if not review.text.strip():
                return Response({"detail": "Відгук без тексту не публікуємо — він лише у статистиці"}, status=400)
            review.status, review.hidden_reason = "published", ""
            review.published_at = review.published_at or now
        elif action == "hide":
            review.status = "hidden"
            review.hidden_reason = str(request.data.get("reason") or "")[:200]
        elif action == "reply":
            text = str(request.data.get("reply_text") or "").strip()[:2000]
            review.reply_text = text
            review.replied_by = user if text else None
            review.replied_at = now if text else None
        elif action in ("feature", "unfeature"):
            review.featured = action == "feature"
        elif action == "edit_text":
            text = str(request.data.get("text") or "").strip()
            if not text or len(text) > 3000:
                return Response({"detail": "Текст — від 1 до 3000 символів"}, status=400)
            review.text = text
        elif action == "display_name":
            review.display_name = str(request.data.get("display_name") or "").strip()[:60]
            review.anonymous = request.data.get("anonymous") is True
        elif action in ("hide_photo", "show_photo"):
            photo = review.photos.filter(pk=request.data.get("photo_id") or 0).first()
            if photo is None:
                return Response({"detail": "Фото не знайдено"}, status=404)
            photo.is_public = action == "show_photo"
            photo.save(update_fields=["is_public"])
        else:
            return Response({"detail": "Невідома дія"}, status=400)
        review.moderated_by, review.moderated_at = user, now
        review.save()
        if review.deal_id:
            log_activity("deal", review.deal_id, "Відгук: %s" % ACTIONS[action], "відгук #%s" % review.id, user)
        return Response(staff_review(review))


class ReviewRequestListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not can_view(request.user):
            return Response({"detail": "Немає доступу до відгуків"}, status=403)
        status = request.query_params.get("status") or "all"
        qs = (ReviewRequest.objects.select_related("deal", "contact")
              .order_by(F("due_at").desc(nulls_last=True), "-id"))
        if status != "all":
            qs = qs.filter(status=status)
        page, size = _page(request)
        cfg = ReviewSettings.get()
        counts = dict(ReviewRequest.objects.values_list("status").annotate(n=Count("id")))
        return Response({"results": [request_row(r, request.user) for r in qs[(page - 1) * size: page * size]],
                         "count": qs.count(), "counts": counts, "send_enabled": cfg.send_enabled,
                         "texts_approved": cfg.texts_approved, "live": live_allowed(cfg),
                         "can_moderate": can_moderate(request.user)})


class ReviewRefreshView(APIView):
    """Оновити журнал зараз (той самий прогін, що й за розкладом; поки відправка вимкнена — лише журнал)."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not can_moderate(request.user):
            return Response({"detail": "Немає прав"}, status=403)
        return Response({"ok": True, "stats": run_sweep()})


class ReviewSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not can_view(request.user):
            return Response({"detail": "Немає доступу до відгуків"}, status=403)
        return Response(settings_dict(ReviewSettings.get()))

    def patch(self, request):
        if not request.user.is_superuser:
            return Response({"detail": "Правила змінює лише власник"}, status=403)
        data = request.data
        if any(key in data for key in LOCKED_FIELDS):
            return Response({"detail": "Відправку клієнтам вмикає розробник після того, як Олег затвердить тексти"},
                            status=400)
        cfg = ReviewSettings.get()
        for name, (low, high) in INT_FIELDS.items():
            if name in data:
                try:
                    value = int(data[name])
                except (TypeError, ValueError):
                    return Response({"detail": "%s — ціле число" % name}, status=400)
                if not low <= value <= high:
                    return Response({"detail": "%s — від %s до %s" % (name, low, high)}, status=400)
                setattr(cfg, name, value)
        if "start_date" in data:
            value = parse_date(str(data["start_date"] or ""))
            if value is None:
                return Response({"detail": "start_date — дата РРРР-ММ-ДД"}, status=400)
            cfg.start_date = value
        for name in TEXT_FIELDS:
            if name in data:
                cfg.__dict__[name] = str(data[name] or "")[:2000]
        if "google_review_url" in data:
            url = str(data["google_review_url"] or "").strip()
            if not url.startswith("https://"):
                return Response({"detail": "Посилання Google має починатися з https://"}, status=400)
            cfg.google_review_url = url[:300]
        if "allowlist_contact_ids" in data:
            ids = data["allowlist_contact_ids"]
            if not isinstance(ids, list) or any(isinstance(i, bool) or not isinstance(i, int) for i in ids):
                return Response({"detail": "allowlist_contact_ids — список id контактів"}, status=400)
            cfg.allowlist_contact_ids = ids
        cfg.save()
        return Response(settings_dict(cfg))


class ReviewOptOutView(APIView):
    """Вручну: «не просити відгуки» у клієнта (або зняти позначку)."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not can_moderate(request.user):
            return Response({"detail": "Немає прав"}, status=403)
        contact = get_object_or_404(Contact, pk=request.data.get("contact_id") or 0)
        if request.data.get("opt_out") is False:
            ReviewOptOut.objects.filter(contact=contact).delete()
        else:
            ReviewOptOut.objects.get_or_create(contact=contact, defaults={"reason": "manual", "created_by": request.user})
        return Response({"ok": True, "opt_out": ReviewOptOut.objects.filter(contact=contact).exists()})


class ReviewPhotoView(View):
    """Фото відгуку: публічно — лише опубліковане й не приховане; модератору — за підписаним посиланням (6 год)."""

    def get(self, request, token):
        photo = ReviewPhoto.objects.select_related("review").filter(token=token).first()
        if photo is None:
            raise Http404
        public = photo.is_public and photo.review.status == "published"
        if not public:
            try:
                payload = signing.loads(request.GET.get("sig") or "", salt=PHOTO_SALT, max_age=6 * 3600)
            except signing.BadSignature:
                payload = None
            if not isinstance(payload, dict) or payload.get("t") != token:
                raise Http404
        data = photo.thumb if request.GET.get("size") == "thumb" else photo.data
        response = HttpResponse(bytes(data), content_type="image/jpeg")
        response["Cache-Control"] = "public, max-age=3600" if public else "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
