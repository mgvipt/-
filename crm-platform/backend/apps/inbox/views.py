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


class AiSuggestView(APIView):
    """AI-РОП: подсказка ответа клиенту по переписке. Если в «Интеграциях» задан
    ключ AI (Anthropic) — отвечает модель; иначе — разумная заготовка по смыслу."""
    def post(self, request):
        conv = get_object_or_404(Conversation, pk=request.data.get("conversation"))
        last_in = conv.messages.filter(direction="in").last()
        text = (last_in.text if last_in else "").lower()

        # пытаемся через настоящий AI, если задан ключ
        try:
            from apps.integrations.models import IntegrationSettings
            ai = IntegrationSettings.objects.filter(provider="ai", is_active=True).first()
            if ai and ai.config.get("api_key"):
                return Response({"suggestion": _ai_via_anthropic(ai.config, conv)})
        except Exception:
            pass

        # запасной вариант — подсказки по ключевым словам (демо AI-РОП)
        if any(w in text for w in ["цін", "цена", "скільки", "сколько", "вартість", "почем"]):
            s = "Доброго дня! Вартість залежить від обʼєму. Підкажіть, скільки м² потрібно покрити — і я порахую точну ціну та підберу набір 🙂"
        elif any(w in text for w in ["достав", "відправ", "пошт", "ттн"]):
            s = "Відправляємо Новою Поштою по всій Україні, зазвичай 1–2 дні. Підкажіть місто та відділення — оформлю ТТН."
        elif any(w in text for w in ["наявн", "є в", "склад", "остат"]):
            s = "Так, товар у наявності. Можу одразу зарезервувати під вас — на яку кількість оформлюємо?"
        elif any(w in text for w in ["привіт", "добр", "здрав", "вітаю"]):
            s = "Вітаю! Дякую за звернення 🙌 Чим можу допомогти — цікавить конкретний товар чи потрібна консультація?"
        else:
            s = "Дякую за повідомлення! Уточніть, будь ласка, деталі — і я підберу найкращий варіант та розрахую вартість."
        return Response({"suggestion": s, "demo": True})


def _ai_via_anthropic(cfg, conv):
    import json, urllib.request
    msgs = [{"role": "assistant" if m.direction == "out" else "user",
             "content": m.text} for m in conv.messages.all()[:20] if m.text]
    body = json.dumps({
        "model": cfg.get("model", "claude-haiku-4-5-20251001"),
        "max_tokens": 300,
        "system": "Ты — AI РОП (руководитель отдела продаж) компании по продаже покрытий для стен. "
                  "Помогай менеджеру: предлагай вежливый, продающий ответ клиенту на украинском.",
        "messages": msgs or [{"role": "user", "content": "Привітай клієнта"}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body,
        headers={"content-type": "application/json", "x-api-key": cfg["api_key"],
                 "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
        data = json.loads(r.read().decode())
    return data["content"][0]["text"]


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
