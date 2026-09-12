"""Підписаний прийом заявок з інтернет-магазину wallcov.com.ua (сервер → сервер).

Форми «Отримати розрахунок» у статтях «Поради та ідеї» і квіз магазину (12.09.2026).
Магазин приймає форму у себе (CSRF, ханіпот, ліміт запитів) і пересилає її сюди з тим самим
підписом, що й замовлення: `X-Wallcov-Timestamp` + `X-Wallcov-Signature` =
HMAC-SHA256(SHOP_WEBHOOK_SECRET, "{ts}." + тіло). Угода — у воронці «23 Інтернет-магазин
wallcov.com.ua», `qualification.article` = slug статті / джерело. Клієнту нічого не надсилається.
Контракт: wallcov-growth-2026-09/crm-intake-contract.md.
"""
import hashlib
import json
import re

from django.db import connection, transaction
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.integrations.views import ShopOrderWebhookView
from .landing_intake import SubmissionConflict, receive
from .models import Channel, Conversation, LandingSubmission

SHOP_LANDING = "wallcov.com.ua"
FIELDS = ("name", "phone", "consent", "preferred", "intent", "product", "product_label", "area",
          "room", "installer", "message", "article", "form", "page_url", "quiz", "first_touch", "last_touch")


def _error(code, detail, status, field=None):
    body = {"ok": False, "code": code, "detail": detail}
    if field:
        body["field"] = field
    return Response(body, status=status)


def _web_channel():
    channel, _ = Channel.objects.get_or_create(
        kind="web", name="Web Chat · Wallcov",
        defaults={"config": {"web_chat": True, "ai": "juliya"}, "is_active": True},
    )
    return channel


class ShopLeadWebhookView(APIView):
    """POST /api/integrations/shop/leads/ — заявка з форми магазину → угода + задача менеджеру."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        if ShopOrderWebhookView._verify_signature(request) is not None:
            return _error("bad_signature", "Підпис недійсний", 403)
        try:
            body = json.loads(request.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _error("bad_json", "Некоректний JSON", 400)
        if not isinstance(body, dict):
            return _error("bad_json", "Очікується JSON-обʼєкт", 400)
        submission = str(body.get("submission_id") or "").strip()
        if not re.fullmatch(r"[a-zA-Z0-9_-]{8,64}", submission):
            return _error("validation", "submission_id: 8–64 символи a-z, A-Z, 0-9, _ або -", 400, "submission_id")
        request_id = "shop-" + submission
        data = {key: body.get(key) for key in FIELDS if key in body}
        data["submission_id"] = request_id
        try:
            with transaction.atomic():
                # Повтори одного звернення йдуть по черзі: один чат, одна угода.
                if connection.vendor == "postgresql":
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_advisory_xact_lock(%s)",
                                       [int(hashlib.sha256(request_id.encode()).hexdigest()[:15], 16)])
                receipt = (LandingSubmission.objects.filter(request_id=request_id)
                           .select_related("conversation").first())
                conv = receipt.conversation if receipt else Conversation.objects.create(
                    channel=_web_channel(),
                    external_chat_id="%s:form:%s" % (SHOP_LANDING, submission),
                    title="[%s] Заявка з сайту" % SHOP_LANDING,
                    config={"site_form": SHOP_LANDING},
                )
                result = receive(conv, data, landing_id=SHOP_LANDING, notify_client=False)
        except SubmissionConflict as exc:
            return _error("conflict", str(exc), 409, "submission_id")
        except ValueError as exc:
            return _error("validation", str(exc), 400)
        return Response({"ok": True, "api_version": 1, "deal_id": result["deal_id"],
                         "duplicate": result["duplicate"]}, status=200 if result["duplicate"] else 201)
