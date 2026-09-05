"""Public web-chat bridge: landing -> CRM Contact Center -> Wallcov «Юля»."""
from __future__ import annotations

import json
import re
import secrets
import urllib.request
from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.core import signing
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.crm.models import Contact, Deal, Funnel
from .models import Channel, Conversation, Message
from .services import _phone_variants


LANDING_ID = "wallcovdliastin.com.ua"
ALLOWED_ORIGINS = {
    "https://wallcov-dlia-stin.olegwallcov.chatgpt.site",
    "https://wallcovdliastin.com.ua",
    "https://www.wallcovdliastin.com.ua",
}
PRODUCTS = {
    "sirena": {"label": "Шовк · Сирена", "price_from": Decimal("189.75"), "price_to": Decimal("189.75")},
    "mermi": {"label": "Шовк · Мерми", "price_from": Decimal("161.70"), "price_to": Decimal("161.70")},
    "luna": {"label": "Вельвет · Луна (звичайна)", "price_from": Decimal("195.00"), "price_to": Decimal("312.00")},
}
TEST_KIT_MINIMUM = Decimal("220.00")
TOKEN_SALT = "wallcov-web-chat-v1"


def _origin_allowed(request) -> bool:
    origin = (request.headers.get("Origin") or "").rstrip("/")
    return not origin or origin in ALLOWED_ORIGINS


def _messages(conv: Conversation):
    return [
        {
            "id": row.id,
            "direction": row.direction,
            "text": row.text,
            "author": "manager" if row.sender_id else ("juliya" if row.direction == "out" else "client"),
            "created_at": row.created_at.isoformat(),
        }
        for row in conv.messages.filter(internal=False).order_by("id")
    ]


def _token(conv: Conversation) -> str:
    return signing.dumps({"conversation_id": conv.id, "landing_id": LANDING_ID}, salt=TOKEN_SALT, compress=True)


def _conversation(raw_token: str) -> Conversation:
    payload = signing.loads(raw_token, salt=TOKEN_SALT, max_age=60 * 60 * 24 * 14)
    if payload.get("landing_id") != LANDING_ID:
        raise signing.BadSignature("wrong landing")
    return Conversation.objects.select_related("contact", "assigned_to", "channel").get(
        pk=payload["conversation_id"], channel__config__web_chat=True
    )


def _rate_ok(request, suffix: str, limit: int = 12) -> bool:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
    ip = forwarded or request.META.get("REMOTE_ADDR", "unknown")
    identity = "ip:" + ip
    # Sites proxies many visitors through the same IP. A verified, signed
    # session gets its own fixed window; arbitrary client headers cannot pick it.
    raw = request.data.get("token")
    if raw:
        try:
            payload = signing.loads(raw, salt=TOKEN_SALT, max_age=60 * 60 * 24 * 14)
            if payload.get("landing_id") == LANDING_ID:
                identity = "conversation:" + str(payload["conversation_id"])
        except (signing.BadSignature, KeyError, TypeError):
            pass
    if suffix == "poll":
        limit = 30
    elif suffix == "start":
        limit = 60
    key = "webchat:v2:%s:%s:%s" % (LANDING_ID, identity, suffix)
    if cache.add(key, 1, timeout=60):
        return True
    try:
        return cache.incr(key) <= limit
    except ValueError:  # Window expired between add and incr.
        return cache.add(key, 1, timeout=60)


def _ai_reply(conv: Conversation, incoming: Message, client_name: str = ""):
    manager_active = bool(conv.assigned_to_id) or conv.messages.filter(
        direction="out", sender__isnull=False, created_at__gte=timezone.now() - timedelta(hours=12)
    ).exists()
    if manager_active:
        return None
    history = []
    for row in conv.messages.filter(internal=False).exclude(pk=incoming.pk).order_by("id").reverse()[:12][::-1]:
        history.append({"role": "user" if row.direction == "in" else "assistant", "text": row.text})
    body = json.dumps({
        "client_text": incoming.text,
        "client_name": client_name,
        "channel": "web_chat",
        "history": history,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        "http://172.17.0.1:8001/seller",
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "WallcovCRM-WebChat/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as response:  # noqa: S310 - internal service
            data = json.loads(response.read().decode("utf-8"))
        confidence = float(data.get("confidence") or 0)
        answer = (data.get("answer") or "").strip()
    except Exception:
        confidence, answer = 0, ""
    if confidence < 0.65 or not answer:
        answer = "Дякую! Я передала питання менеджеру Wallcov — він підключиться до цього чату. Залиште номер, щоб ми не втратили зв’язок."
    return Message.objects.create(
        conversation=conv,
        direction="out",
        text=answer[:4000],
        external_id="web-ai:%s" % incoming.id,
        sender_name="Юля · Wallcov",
    )


def _decimal_area(value) -> Decimal:
    try:
        area = Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Вкажіть площу числом")
    if not area.is_finite() or area < Decimal("1") or area > Decimal("1000"):
        raise ValueError("Площа має бути від 1 до 1000 м²")
    return area


class WebChatView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def options(self, request, *args, **kwargs):
        return self._cors(request, Response(status=204))

    def _cors(self, request, response):
        origin = (request.headers.get("Origin") or "").rstrip("/")
        if origin in ALLOWED_ORIGINS:
            response["Access-Control-Allow-Origin"] = origin
            response["Access-Control-Allow-Methods"] = "POST, OPTIONS"
            response["Access-Control-Allow-Headers"] = "Content-Type"
            response["Access-Control-Max-Age"] = "86400"
            response["Vary"] = "Origin"
        return response

    def post(self, request):
        if not _origin_allowed(request):
            return self._cors(request, Response({"detail": "origin not allowed"}, status=403))
        action = str(request.data.get("action") or "").strip()
        if action not in {"start", "poll", "message", "lead", "photo"}:
            return self._cors(request, Response({"detail": "unknown action"}, status=400))
        if not _rate_ok(request, action):
            return self._cors(request, Response({"detail": "Забагато запитів. Спробуйте за хвилину."}, status=429))
        try:
            handler = getattr(self, "_action_" + action)
        except AttributeError:
            return self._cors(request, Response({"detail": "unknown action"}, status=400))
        try:
            response = handler(request)
        except (signing.BadSignature, Conversation.DoesNotExist, KeyError):
            response = Response({"detail": "Сесію чату не знайдено. Оновіть сторінку."}, status=401)
        except ValueError as exc:
            response = Response({"detail": str(exc)}, status=400)
        return self._cors(request, response)

    def _action_start(self, request):
        channel, _ = Channel.objects.get_or_create(
            kind="web",
            name="Web Chat · Wallcov",
            defaults={"config": {"web_chat": True, "ai": "juliya"}, "is_active": True},
        )
        visitor = re.sub(r"[^a-zA-Z0-9_-]", "", str(request.data.get("visitor_id") or ""))[:64]
        external_chat_id = "%s:%s" % (LANDING_ID, visitor or secrets.token_urlsafe(16))
        conv = Conversation.objects.create(
            channel=channel,
            external_chat_id=external_chat_id,
            title="[%s] Гість сайту" % LANDING_ID,
        )
        greeting = Message.objects.create(
            conversation=conv,
            direction="out",
            text="Вітаю! Я Юля з Wallcov. Допоможу підібрати шовк або вельвет і порахувати матеріал. Для якої кімнати обираєте покриття?",
            external_id="web-greeting:%s" % conv.id,
            sender_name="Юля · Wallcov",
        )
        conv.last_message_at = greeting.created_at
        conv.save(update_fields=["last_message_at"])
        return Response({"token": _token(conv), "conversation_id": conv.id, "messages": _messages(conv)})

    def _action_poll(self, request):
        conv = _conversation(str(request.data.get("token") or ""))
        return Response({"messages": _messages(conv), "manager_active": bool(conv.assigned_to_id)})

    def _action_message(self, request):
        conv = _conversation(str(request.data.get("token") or ""))
        text = str(request.data.get("text") or "").strip()
        if not text or len(text) > 1200:
            raise ValueError("Повідомлення має містити від 1 до 1200 символів")
        client_message_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(request.data.get("client_message_id") or ""))[:80]
        external_id = "web-in:" + (client_message_id or secrets.token_urlsafe(10))
        existing = Message.objects.filter(conversation=conv, external_id=external_id).first()
        if not existing:
            incoming = Message.objects.create(
                conversation=conv, direction="in", text=text, external_id=external_id,
                sender_name=(str(request.data.get("name") or "")[:160] or "Гість сайту"),
            )
            conv.unread += 1
            conv.last_message_at = incoming.created_at
            conv.save(update_fields=["unread", "last_message_at"])
            _ai_reply(conv, incoming, str(request.data.get("name") or "")[:120])
        return Response({"messages": _messages(conv)})

    def _action_lead(self, request):
        from .landing_intake import receive
        conv = _conversation(str(request.data.get("token") or ""))
        result = receive(conv, request.data)
        saved_conv = Conversation.objects.get(pk=result["conversation_id"])
        result.update(token=_token(saved_conv), messages=_messages(saved_conv))
        return Response(result)

    def _action_photo(self, request):
        from .landing_intake import attach_photos
        conv = _conversation(str(request.data.get("token") or ""))
        return Response(attach_photos(conv, request.data))
