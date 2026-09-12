"""API відгуків для магазину wallcov.com.ua (сервер → сервер, та сама підпис HMAC, що й замовлення).

Контракт: wallcov-growth-2026-09/reviews/api-contract.md. Усі маршрути — POST з JSON:
  /api/integrations/shop/reviews/ping/       перевірка підпису
  /api/integrations/shop/reviews/invite/     приглашення за кодом (імʼя, товари — без телефону/суми)
  /api/integrations/shop/reviews/submit/     прийом відгуку (оцінка, текст, до 5 фото — CRM знімає EXIF/гео)
  /api/integrations/shop/reviews/published/  стрічка опублікованих (і знятих) відгуків
"""
import json

from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.integrations.views import ShopOrderWebhookView
from .models import ReviewSettings
from .services import ReviewError, invite_payload, published_feed, submit_review


class _SignedView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        if ShopOrderWebhookView._verify_signature(request) is not None:
            error = ReviewError("bad_signature", "Підпис недійсний", 403)
            return Response(error.body(), status=error.status)
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = None
        if not isinstance(body, dict):
            error = ReviewError("bad_json", "Некоректний JSON")
            return Response(error.body(), status=error.status)
        try:
            return self.handle(body)
        except ReviewError as error:
            return Response(error.body(), status=error.status)

    def handle(self, body):  # pragma: no cover — перевизначається
        raise NotImplementedError


class ShopReviewPingView(_SignedView):
    def handle(self, body):
        return Response({"ok": True, "api_version": 1, "server_time": timezone.localtime().isoformat()})


class ShopReviewInviteView(_SignedView):
    def handle(self, body):
        invite = invite_payload(str(body.get("code") or ""), mark_opened=body.get("mark_opened") is True)
        return Response({"ok": True, "api_version": 1, "invite": invite})


class ShopReviewSubmitView(_SignedView):
    def handle(self, body):
        review, duplicate = submit_review(body)
        return Response({
            "ok": True, "api_version": 1, "review_id": review.id, "status": review.status, "duplicate": duplicate,
            "rating": review.rating, "thank_you": "positive" if review.rating >= 4 else "negative",
            "google_review_url": ReviewSettings.get().google_review_url,
        }, status=200 if duplicate else 201)


class ShopReviewPublishedView(_SignedView):
    def handle(self, body):
        return Response(published_feed(body))
