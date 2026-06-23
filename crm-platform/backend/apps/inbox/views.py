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
        data = request.data
        # бот підключили/відключили до Telegram-бізнесу
        bc = data.get("business_connection")
        if bc:
            cfg = channel.config or {}
            cfg["business_connection_id"] = bc.get("id")
            cfg["business_enabled"] = bool(bc.get("is_enabled", True))
            channel.config = cfg
            channel.save(update_fields=["config"])
            return Response({"ok": True})
        # бізнес-повідомлення (написали на особистий номер) — запамʼятати bcid для цього чату
        bm = data.get("business_message") or data.get("edited_business_message")
        if bm:
            cfg = channel.config or {}
            bchats = cfg.setdefault("business_chats", {})
            bchats[str((bm.get("chat") or {}).get("id"))] = bm.get("business_connection_id")
            channel.config = cfg
            channel.save(update_fields=["config"])
        inc = get_adapter(channel).parse_webhook(data)
        if inc:
            ingest(channel, inc)
        return Response({"ok": True})


class ViberWebhookView(APIView):
    """Точка приёма событий Viber-бота. URL: /api/inbox/viber/webhook/<channel_id>/"""
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, channel_id):
        channel = get_object_or_404(Channel, pk=channel_id, kind="viber", is_active=True)
        event = request.data.get("event")
        if event in ("webhook", "delivered", "seen", "failed", "subscribed", "unsubscribed"):
            return Response({"status": 0})  # сервісні події — просто 200
        inc = get_adapter(channel).parse_webhook(request.data)
        if inc:
            ingest(channel, inc)
        return Response({"status": 0, "status_message": "ok"})


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

    @action(detail=True, methods=["post"])
    def ai_reply(self, request, pk=None):
        """AI-РОП: аналіз діалогу + підказка відповіді клієнту (Claude)."""
        conv = self.get_object()
        msgs = list(conv.messages.order_by("id").values("direction", "text"))[-30:]
        dialog = "\n".join(
            ("Клієнт: " if m["direction"] == "in" else "Менеджер/AI: ") + (m["text"] or "")
            for m in msgs if m.get("text"))
        prompt = (
            "Ти — досвідчений РОП (керівник відділу продажів) компанії Wallcov "
            "(декоративні покриття та фарби для стін). Проаналізуй переписку і допоможи менеджеру закрити продаж. "
            "Переписка з клієнтом:\n" + (dialog or "(переписки ще немає)") + "\n\n"
            "Поверни СТРОГО JSON без пояснень: "
            '{"context": "1 коротке речення-підсумок", '
            '"points": ["3-6 коротких тез: на якому етапі клієнт, що хоче, площа/матеріал/бюджет якщо згадані, заперечення, наступний крок"], '
            '"suggestion": "готова відповідь клієнту ТІЄЮ Ж мовою, що й він — ввічливо, по суті, з наступним кроком до продажу"}')
        from apps.crm.ai import claude_json
        try:
            return Response(claude_json(prompt, max_tokens=1000))
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)

    @action(detail=True, methods=["post"])
    def send_media(self, request, pk=None):
        """Надіслати клієнту фото/відео/документ (base64 у JSON)."""
        import base64
        conv = self.get_object()
        b64 = request.data.get("content_b64") or ""
        filename = request.data.get("filename") or "file"
        kind = request.data.get("kind") or "document"
        if not b64:
            return Response({"detail": "Немає файлу"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            content = base64.b64decode(b64.split(",")[-1])
            msg_id = get_adapter(conv.channel).send_media(conv.external_chat_id, content, filename, kind)
        except NotImplementedError:
            return Response({"detail": "Цей канал поки не підтримує надсилання медіа"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        msg = Message.objects.create(conversation=conv, direction="out", text=f"[{kind}] {filename}",
                                     external_id=str(msg_id or ""), attachments=[{"type": kind, "name": filename}])
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


# ============================================================================
# КОНТАКТ-ЦЕНТР — каталог каналів звʼязку + статус підключення
# ============================================================================
class ContactCenterView(APIView):
    """Список каналів для сторінки Контакт-центру. Статус connected визначаємо
    за наявністю активного Channel у inbox (ChatPlace покриває IG/TG/TikTok)."""
    def get(self, request):
        from .models import Channel
        cp = Channel.objects.filter(config__chatplace=True, is_active=True).exists()
        kinds = set(Channel.objects.filter(is_active=True).values_list("kind", flat=True))

        def status(connected):
            return "connected" if connected else "available"

        catalog = [
            {"key": "instagram", "name": "Instagram", "sub": "Direct + Коментарі", "icon": "📸", "color": "#E1306C", "status": status(cp or "instagram" in kinds), "via": "ChatPlace" if cp else None},
            {"key": "facebook", "name": "Facebook", "sub": "Messenger + Коментарі", "icon": "f", "color": "#1877F2", "status": status("facebook" in kinds), "via": None},
            {"key": "telegram_bot", "name": "Telegram бот", "sub": "Бот для клієнтів", "icon": "✈", "color": "#229ED9", "status": status(cp or "telegram" in kinds), "via": "ChatPlace" if cp else None},
            {"key": "telegram_phone", "name": "Telegram (номер)", "sub": "Клієнт пише на ваш номер", "icon": "✈", "color": "#229ED9", "status": "available", "via": None},
            {"key": "tiktok", "name": "TikTok", "sub": "Повідомлення", "icon": "🎵", "color": "#111827", "status": status(cp or "tiktok" in kinds), "via": "ChatPlace" if cp else None},
            {"key": "viber_bot", "name": "Viber бот", "sub": "Бот для клієнтів", "icon": "V", "color": "#7360F2", "status": status("viber" in kinds), "via": None},
            {"key": "viber_phone", "name": "Viber (номер)", "sub": "Клієнт пише на ваш номер", "icon": "V", "color": "#7360F2", "status": "available", "via": None},
            {"key": "whatsapp", "name": "WhatsApp", "sub": "Повідомлення", "icon": "W", "color": "#25D366", "status": status("whatsapp" in kinds), "via": None},
        ]
        return Response(catalog)


# ============================================================================
# ПОЛІТИКА КОНФІДЕНЦІЙНОСТІ — публічна сторінка (для Meta App / месенджерів)
# ============================================================================
_PRIVACY_HTML = """<!doctype html><html lang="uk"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Політика конфіденційності — Wallcov</title>
<style>body{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:760px;margin:40px auto;padding:0 20px;color:#1e293b;line-height:1.6}h1{color:#C67D5F}h2{margin-top:28px}small{color:#64748b}</style>
</head><body>
<h1>Політика конфіденційності Wallcov</h1>
<small>Оновлено: 2026</small>
<p>Компанія <b>Wallcov</b> («Покриття для стін») поважає вашу приватність. Ця політика пояснює, які дані ми збираємо під час спілкування з клієнтами через месенджери та як їх використовуємо.</p>
<h2>Які дані ми збираємо</h2>
<ul>
<li>Повідомлення, які ви надсилаєте нам у Instagram Direct, Facebook Messenger, Telegram;</li>
<li>Ваше імʼя/нік у месенджері, ідентифікатор облікового запису;</li>
<li>Зміст переписки, фото та файли, якими ви ділитесь у діалозі;</li>
<li>Контактні дані, які ви добровільно надаєте (телефон, місто, обʼєкт).</li>
</ul>
<h2>Як ми використовуємо дані</h2>
<ul>
<li>Щоб відповідати на ваші запити та консультувати щодо декоративних покриттів;</li>
<li>Щоб оформити та доставити замовлення;</li>
<li>Для покращення якості обслуговування.</li>
</ul>
<h2>Зберігання та передача</h2>
<p>Дані зберігаються у нашій внутрішній CRM-системі та використовуються лише співробітниками Wallcov. Ми <b>не продаємо</b> і не передаємо ваші дані третім особам, окрім випадків, передбачених законом, та сервісів, потрібних для обробки замовлення (доставка, оплата).</p>
<h2>Ваші права</h2>
<p>Ви можете запросити видалення своїх даних або відмовитись від спілкування, написавши нам у будь-якому месенджері або на пошту.</p>
<h2>Контакти</h2>
<p>Wallcov · сайт <a href="https://wallcovdec.com.ua">wallcovdec.com.ua</a> · Instagram @dekor_dlia_stin</p>
</body></html>"""


class PrivacyPolicyView(APIView):
    """Публічна сторінка політики конфіденційності (для Meta App)."""
    permission_classes = [_AllowAny]
    authentication_classes = []

    def get(self, request):
        return _HttpResponse(_PRIVACY_HTML, content_type="text/html; charset=utf-8")


# ============================================================================
# ВИДАЛЕННЯ ДАНИХ КОРИСТУВАЧА — публічна сторінка (для Meta App)
# ============================================================================
_DATADEL_HTML = """<!doctype html><html lang="uk"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Видалення даних — Wallcov</title>
<style>body{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:760px;margin:40px auto;padding:0 20px;color:#1e293b;line-height:1.6}h1{color:#C67D5F}</style>
</head><body>
<h1>Видалення ваших даних — Wallcov</h1>
<p>Ви маєте право у будь-який момент попросити видалити всі дані, які Wallcov зберіг про вас (переписку, контактні дані, ідентифікатори месенджерів).</p>
<h2>Як видалити свої дані</h2>
<ol>
<li>Напишіть нам у будь-якому месенджері (Instagram @dekor_dlia_stin, Facebook, Telegram) фразу «Видаліть мої дані» / «Удалите мои данные»;</li>
<li>або надішліть запит на пошту <b>salonstukaturka@gmail.com</b> з темою «Видалення даних»;</li>
<li>Ми видалимо всі ваші персональні дані з нашої CRM протягом <b>30 днів</b> і підтвердимо це у відповідь.</li>
</ol>
<p>Wallcov · <a href="https://wallcovdec.com.ua">wallcovdec.com.ua</a></p>
</body></html>"""


class DataDeletionView(APIView):
    """Публічна сторінка інструкцій з видалення даних (для Meta App)."""
    permission_classes = [_AllowAny]
    authentication_classes = []

    def get(self, request):
        return _HttpResponse(_DATADEL_HTML, content_type="text/html; charset=utf-8")
