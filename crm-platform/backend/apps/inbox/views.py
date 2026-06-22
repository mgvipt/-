from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Channel, Conversation, Message
from .serializers import ChannelSerializer, ConversationSerializer, MessageSerializer
from .adapters import get_adapter
from .services import ingest, send_message


class TelegramWebhookView(APIView):
    """Точка приёма апдейтов от Telegram. Публичная (Telegram дергает её сам).
    URL: /api/inbox/telegram/webhook/<channel_id>/
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, channel_id):
        channel = get_object_or_404(Channel, pk=channel_id, kind="telegram", is_active=True)
        inc = get_adapter(channel).parse_webhook(request.data)
        if inc:
            ingest(channel, inc)
        return Response({"ok": True})


class ChannelViewSet(viewsets.ModelViewSet):
    queryset = Channel.objects.all().order_by("name")
    serializer_class = ChannelSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        allowed = self.request.user.allowed_channel_ids()
        return qs if allowed is None else qs.filter(id__in=allowed)


class ConversationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Conversation.objects.select_related("channel", "contact", "assigned_to")
    serializer_class = ConversationSerializer
    filterset_fields = ["channel", "status", "assigned_to", "contact"]
    search_fields = ["title", "contact__first_name", "contact__phone"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        allowed = user.allowed_channel_ids()
        if allowed is not None:
            qs = qs.filter(channel_id__in=allowed)
        # RBAC: менеджер без права «все чаты» видит только свои —
        # по ответственному чата ИЛИ по ответственному контакта.
        if not user.can_see_all_conversations():
            qs = qs.filter(Q(assigned_to=user) | Q(contact__owner=user))
        # фильтр-чипы (поверх RBAC): Мої / Не призначені
        scope = self.request.query_params.get("scope")
        if scope == "mine":
            qs = qs.filter(assigned_to=user)
        elif scope == "unassigned":
            qs = qs.filter(assigned_to__isnull=True)
        return qs

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        """Переброс чата на ответственного (только руководитель)."""
        u = request.user
        if not (u.can_see_all_conversations() or u.has_perm_code("roles.manage")):
            return Response({"detail": "Нет прав на переброс чата"}, status=status.HTTP_403_FORBIDDEN)
        conv = self.get_object()
        conv.assigned_to_id = request.data.get("user_id") or None
        conv.save(update_fields=["assigned_to"])
        return Response(ConversationSerializer(conv).data)

    @action(detail=True, methods=["get"])
    def messages(self, request, pk=None):
        conv = self.get_object()
        if (conv.channel.config or {}).get("chatplace"):
            try:
                from .chatplace import sync_one_chat, configured
                if configured():
                    sync_one_chat(conv)
            except Exception:
                pass
        conv.unread = 0
        conv.save(update_fields=["unread"])
        return Response(MessageSerializer(conv.messages.all(), many=True).data)

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        conv = self.get_object()
        text = (request.data.get("text") or "").strip()
        if not text:
            return Response({"detail": "Пустое сообщение"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            msg = send_message(conv, text, user=request.user)
        except Exception as e:  # сеть/токен недоступны
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(MessageSerializer(msg).data, status=status.HTTP_201_CREATED)


from django.http import HttpResponse as _HttpResponse
from rest_framework.permissions import AllowAny as _AllowAny


class MetaWebhookView(APIView):
    """Вебхук Meta (Instagram/Facebook) — приймає Direct і коменти напряму в CRM."""
    permission_classes = [_AllowAny]
    authentication_classes = []

    def get(self, request):
        from .meta import VERIFY_TOKEN
        if request.GET.get("hub.verify_token") == VERIFY_TOKEN and request.GET.get("hub.mode") == "subscribe":
            return _HttpResponse(request.GET.get("hub.challenge", ""))
        return _HttpResponse("forbidden", status=403)

    def post(self, request):
        import json as _json
        from .meta import verify_signature, handle_webhook
        raw = request.body
        if not verify_signature(raw, request.headers.get("X-Hub-Signature-256", "")):
            return _HttpResponse("bad signature", status=403)
        try:
            handle_webhook(_json.loads(raw or b"{}"))
        except Exception:
            pass  # завжди 200 — щоб Meta не ретраїла нескінченно
        return _HttpResponse("EVENT_RECEIVED")


class ChatPlaceSyncView(APIView):
    """Ручний запуск синхронізації ChatPlace (також гониться кроном)."""
    def post(self, request):
        from .chatplace import sync_chats, configured
        if not configured():
            return Response({"detail": "CHATPLACE_API_KEY не налаштовано"}, status=400)
        return Response(sync_chats())
