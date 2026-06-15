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
    filterset_fields = ["channel", "status", "assigned_to"]
    search_fields = ["title", "contact__first_name", "contact__phone"]

    def get_queryset(self):
        qs = super().get_queryset()
        allowed = self.request.user.allowed_channel_ids()
        if allowed is not None:
            qs = qs.filter(channel_id__in=allowed)
        return qs

    @action(detail=True, methods=["get"])
    def messages(self, request, pk=None):
        conv = self.get_object()
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
