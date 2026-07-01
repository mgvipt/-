from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
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
        _sec = (channel.config or {}).get("webhook_secret")  # #11 якщо задано — вимагаємо збіг
        if _sec and request.headers.get("X-Telegram-Bot-Api-Secret-Token") != _sec:
            return Response({"detail": "bad secret"}, status=status.HTTP_403_FORBIDDEN)
        data = request.data
        # бот підключили/відключили до Telegram-бізнесу
        bc = data.get("business_connection")
        if bc:
            cfg = channel.config or {}
            cfg["business_connection_id"] = bc.get("id")
            cfg["business_enabled"] = bool(bc.get("is_enabled", True))
            if bc.get("user"):
                cfg["owner_id"] = (bc.get("user") or {}).get("id")
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
        _vk = (channel.config or {}).get("app_key")  # #11 підпис Viber, якщо ключ заданий
        if _vk:
            import hmac as _h, hashlib as _hl
            _good = _h.new(_vk.encode(), request.body, _hl.sha256).hexdigest()
            if request.headers.get("X-Viber-Content-Signature") != _good:
                return Response({"status": 1, "status_message": "bad signature"}, status=status.HTTP_403_FORBIDDEN)
        event = request.data.get("event")
        if event in ("webhook", "delivered", "seen", "failed", "subscribed", "unsubscribed"):
            return Response({"status": 0})  # сервісні події — просто 200
        inc = get_adapter(channel).parse_webhook(request.data)
        if inc:
            ingest(channel, inc)
        return Response({"status": 0, "status_message": "ok"})


class EchatWebhookView(APIView):
    """Приём входящих Viber-сообщений через e-chat.tech. URL: /api/inbox/echat/webhook/<channel_id>/"""
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, channel_id):
        channel = get_object_or_404(Channel, pk=channel_id, is_active=True)
        d = request.data
        direction = str(d.get("direction") or "")
        event = str(d.get("event") or "")
        if "outgoing" in direction or "outgoing" in event:
            return Response({"status": 0})  # власні вихідні / статуси — ігноруємо
        inc = get_adapter(channel).parse_webhook(d)
        if inc and inc.external_chat_id:
            ingest(channel, inc)
        return Response({"status": 0, "status_message": "ok"})


class EchatSetupView(APIView):
    """Налаштування Viber через e-chat: створення каналу + увімкнення вебхуків + лінк вебхука."""
    def _ch(self):
        return Channel.objects.filter(kind="echat").first()

    def get(self, request):
        ch = self._ch()
        if not ch:
            return Response({"connected": False, "number": "", "has_key": False, "webhook": "", "channel_id": None})
        return Response({"connected": bool(ch.is_active), "number": (ch.config or {}).get("number", ""),
                         "has_key": bool((ch.config or {}).get("api_key")), "channel_id": ch.id,
                         "webhook": request.build_absolute_uri("/api/inbox/echat/webhook/%d/" % ch.id)})

    def post(self, request):
        if not request.user.has_perm_code("roles.manage"):
            return Response({"detail": "Немає прав"}, status=status.HTTP_403_FORBIDDEN)
        api_key = (request.data.get("api_key") or "").strip()
        number = (request.data.get("number") or "").strip()
        if not number:
            return Response({"detail": "Вкажіть Viber-номер каналу"}, status=status.HTTP_400_BAD_REQUEST)
        ch = self._ch() or Channel.objects.create(kind="echat", name="Viber (e-chat)")
        cfg = ch.config or {}
        cfg["echat"] = True; cfg["number"] = number
        if api_key:
            cfg["api_key"] = api_key
        ch.config = cfg; ch.is_active = True; ch.name = "Viber (e-chat) " + number; ch.save()
        result = {}
        try:
            result = get_adapter(ch).connect()
        except Exception as e:
            result = {"warn": str(e)}
        return Response({"ok": True, "channel_id": ch.id,
                         "webhook": request.build_absolute_uri("/api/inbox/echat/webhook/%d/" % ch.id),
                         "connect_result": result})


class ChannelViewSet(viewsets.ModelViewSet):
    queryset = Channel.objects.all().order_by("name")
    serializer_class = ChannelSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        allowed = self.request.user.allowed_channel_ids()
        return qs if allowed is None else qs.filter(id__in=allowed)


def _close_contact_leads(contact_id):
    """При завершенні чату — фіналізувати відкриті ліди контакту (в lost),
    щоб не лишались дублі і аналітика рахувала їх як неконвертовані."""
    if not contact_id:
        return
    from apps.crm.models import Lead, Funnel, log_activity
    lf = Funnel.objects.filter(is_lead_funnel=True).first()
    if not lf:
        return
    lost = (lf.stages.filter(is_lost=True).order_by("-order").first()
            or lf.stages.filter(name__icontains="Не вдалося").first()
            or lf.stages.order_by("-order").first())
    if not lost:
        return
    for ld in Lead.objects.filter(contact_id=contact_id, funnel=lf).exclude(stage__is_lost=True).exclude(stage__is_won=True):
        old = ld.stage.name
        q = dict(ld.qualification or {})
        q["_reached_stage_id"] = ld.stage_id  # знімок стадії відвалу — для перенесення при поверненні
        q["_reached_stage_name"] = old
        ld.qualification = q
        ld.stage = lost
        ld.save(update_fields=["stage", "qualification"])
        log_activity("lead", ld.id, "Закрито разом з чатом", "%s → %s (зафіксовано для аналітики)" % (old, lost.name), None, "Система")


# Скільки хвилин чат лишається у загальному списку менеджера після того,
# як ВІН написав у чужий (закріплений за іншим) чат. Закріпити = назавжди.
_RECENT_REPLY_MIN = 30


class ConversationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Conversation.objects.select_related("channel", "contact", "assigned_to").prefetch_related("participants")
    serializer_class = ConversationSerializer
    filterset_fields = ["channel", "status", "assigned_to", "contact"]
    search_fields = ["title", "contact__first_name", "contact__last_name", "contact__phone", "contact__social_link"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        allowed = user.allowed_channel_ids()
        if allowed is not None:
            qs = qs.filter(channel_id__in=allowed)
        # RBAC: менеджер без права «все чаты» видит только свои —
        # по ответственному чата ИЛИ по ответственному контакта.
        can_all = user.can_see_all_conversations()
        # БАЗОВИЙ ДОСТУП (для retrieve/messages/send/відкриття через картку):
        # «бачити всі чати» (право відділу) → доступ до будь-якого; інакше — лише свої звʼязки
        # (призначений / контакт мій / учасник / у контакта є мій лід чи сделка).
        mine_q = (Q(assigned_to=user) | Q(contact__owner=user) | Q(participants=user)
                  | Q(contact__leads__owner=user) | Q(contact__deals__owner=user))
        if not can_all:
            # Незайняті чати (нічиї) — СПІЛЬНИЙ ПУЛ: доступні всім, хто має доступ до каналу
            # (бачить + може відкрити/відповісти/взяти). Призначені — лише свої (mine_q).
            qs = qs.filter(mine_q | Q(assigned_to__isnull=True)).distinct()
        # КОМАНДНА ЧЕРГА — фільтри ТІЛЬКИ у СПИСКУ. Чат, взятий ІНШИМ співробітником,
        # зникає зі списку (його все одно можна відкрити через картку ліда/сделки = retrieve,
        # і «Закріпити» за собою — тоді він стане видимий у того, хто останнім узяв).
        scope = self.request.query_params.get("scope")
        if scope == "mine":
            qs = qs.filter(Q(assigned_to=user) | Q(participants=user))
        elif scope == "unassigned":
            qs = qs.filter(assigned_to__isnull=True)
        elif scope == "clients":
            qs = qs.filter(contact__deals__isnull=False).distinct()
        elif self.action == "list":
            # «Всі»/за замовч.: незайняті + мої + ті, де Я НЕЩОДАВНО ПИСАВ (останні N хв),
            # навіть якщо чат закріплений за іншим (щоб дотиснути діалог). Закріпити = назавжди.
            from django.utils import timezone as _tzr
            from datetime import timedelta as _tdr
            recent_q = Q(messages__sender=user, messages__created_at__gte=_tzr.now() - _tdr(minutes=_RECENT_REPLY_MIN))
            qs = qs.filter(Q(assigned_to__isnull=True) | Q(assigned_to=user) | Q(participants=user) | recent_q)
        # У СПИСКУ показуємо лише ВІДКРИТІ чати. Закритий зникає; коли клієнт напише —
        # ingest створює новий open-діалог і він знову зʼявиться (у непризначених).
        if self.action == "list" and not self.request.query_params.get("status"):
            qs = qs.filter(status="open")
        pr = self.request.query_params.get("priority")
        if pr:
            qs = qs.filter(priority=pr)
        period = self.request.query_params.get("period")
        if period and period != "all":
            from django.utils import timezone as _tz
            from datetime import timedelta as _td
            now = _tz.now()
            if period == "today":
                qs = qs.filter(last_message_at__date=now.date())
            elif period == "yesterday":
                qs = qs.filter(last_message_at__date=(now - _td(days=1)).date())
            elif period == "7d":
                qs = qs.filter(last_message_at__gte=now - _td(days=7))
            elif period == "30d":
                qs = qs.filter(last_message_at__gte=now - _td(days=30))
        df = self.request.query_params.get("date_from")
        dt = self.request.query_params.get("date_to")
        if df:
            qs = qs.filter(last_message_at__date__gte=df)
        if dt:
            qs = qs.filter(last_message_at__date__lte=dt)
        if self.request.query_params.get("status") is None and self.action == "list":
            qs = qs.exclude(status="closed")
        return qs.distinct()

    @action(detail=False, methods=["post"])
    def bulk_close(self, request):
        """Масово завершити вибрані діалоги (тільки ті, що видно користувачу)."""
        ids = request.data.get("ids") or []
        rows = list(self.get_queryset().filter(id__in=ids).values("id", "contact_id"))
        Conversation.objects.filter(id__in=[r["id"] for r in rows]).update(status="closed")
        for r in rows:
            _close_contact_leads(r["contact_id"])
        return Response({"closed": len(rows)})

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        """Переброс чата на ответственного (только руководитель)."""
        u = request.user
        conv = self.get_object()
        if not (u.can_see_all_conversations() or u.has_perm_code("roles.manage") or conv.assigned_to_id == u.id):
            return Response({"detail": "Нет прав на переброс чата"}, status=status.HTTP_403_FORBIDDEN)
        conv.assigned_to_id = request.data.get("user_id") or None
        conv.save(update_fields=["assigned_to"])
        return Response(ConversationSerializer(conv).data)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        """Завершити діалог. Наступний лист клієнта створить НОВИЙ діалог + лід."""
        conv = self.get_object()
        conv.status = "closed"
        conv.save(update_fields=["status"])
        _close_contact_leads(conv.contact_id)
        return Response(ConversationSerializer(conv).data)

    @action(detail=True, methods=["post"])
    def take(self, request, pk=None):
        """Закріпити діалог за собою + стати відповідальним за контакт і його ВІДКРИТІ сделки.

        Чати, які вів ШІ-агент, не мали «живого» відповідального — беручи чат, менеджер
        одразу бачить сделку, контакт і діалог у розділі «Мої». Виграні/програні сделки
        НЕ перепризначаємо (щоб не зламати нарахування ЗП та історію власника)."""
        conv = self.get_object()
        conv.assigned_to = request.user
        conv.save(update_fields=["assigned_to"])
        if conv.contact_id:
            from apps.crm.models import Deal, Lead, Contact
            # Беручи чат — стаємо відповідальним за ВІДКРИТІ сделки + ліди + сам контакт клієнта,
            # щоб менеджер одразу бачив усе в розділі «Мої». Виграні/програні НЕ чіпаємо (історія+ЗП).
            Deal.objects.filter(contact_id=conv.contact_id).exclude(stage__is_won=True).exclude(stage__is_lost=True).update(owner=request.user)
            Lead.objects.filter(contact_id=conv.contact_id).exclude(stage__is_won=True).exclude(stage__is_lost=True).update(owner=request.user)
            Contact.objects.filter(id=conv.contact_id).update(owner=request.user)
        return Response(ConversationSerializer(conv).data)

    @action(detail=True, methods=["post"])
    def add_member(self, request, pk=None):
        """Додати ще одного менеджера у чат (учасник, бачить чат)."""
        u = request.user
        conv = self.get_object()
        if not (u.can_see_all_conversations() or u.has_perm_code("roles.manage")
                or conv.assigned_to_id == u.id or conv.participants.filter(id=u.id).exists()):
            return Response({"detail": "Немає прав"}, status=status.HTTP_403_FORBIDDEN)
        uid = request.data.get("user_id")
        if uid:
            conv.participants.add(uid)
            try:
                from .models import Notification
                if str(uid) != str(u.id):
                    who = u.get_full_name() or u.username
                    cl = (str(conv.contact) if conv.contact_id else None) or conv.title or "клієнтом"
                    Notification.objects.create(user_id=uid, kind="added_chat", actor=u, conversation=conv,
                                                text="%s додав(-ла) вас до чату з %s" % (who, cl))
            except Exception:
                pass
        return Response(ConversationSerializer(conv).data)

    @action(detail=True, methods=["post"])
    def remove_member(self, request, pk=None):
        u = request.user
        conv = self.get_object()
        if not (u.can_see_all_conversations() or u.has_perm_code("roles.manage") or conv.assigned_to_id == u.id):
            return Response({"detail": "Немає прав"}, status=status.HTTP_403_FORBIDDEN)
        uid = request.data.get("user_id")
        if uid:
            conv.participants.remove(uid)
        return Response(ConversationSerializer(conv).data)

    @action(detail=False, methods=["get"])
    def staff(self, request):
        """Список активних співробітників — для пікера «додати у чат»/«передати». Доступно всім авторизованим."""
        from django.contrib.auth import get_user_model
        U = get_user_model()
        qs = U.objects.filter(is_active=True).select_related("department").order_by("first_name", "username")
        return Response([{"id": u.id, "full_name": (u.get_full_name() or u.username),
                          "dept": (u.department.name if getattr(u, "department_id", None) else "")} for u in qs])

    @action(detail=False, methods=["get"])
    def by_contact(self, request):
        """Усі діалоги контакту БЕЗ scope-фільтра — для картки сделки/контакту.
        Доступ до сделки = доступ до чату клієнта (навіть якщо чат закріплений за іншим менеджером)."""
        cid = request.query_params.get("contact")
        if not cid:
            return Response([])
        u = request.user  # #10 доступ: свої/учасник АБО право бачити всі чати/сделки
        if not (u.is_superuser or u.has_perm_code("conversation.view.all") or u.can_see_all_deals()):
            from django.db.models import Q as _Q
            from apps.crm.models import Deal, Lead
            ok = (Deal.objects.filter(contact_id=cid, owner=u).exists() or
                  Lead.objects.filter(contact_id=cid, owner=u).exists() or
                  Conversation.objects.filter(contact_id=cid).filter(_Q(assigned_to=u) | _Q(participants=u)).exists())
            if not ok:
                return Response([])
        qs = (Conversation.objects.filter(contact_id=cid)
              .select_related("channel", "contact", "assigned_to").prefetch_related("participants")
              .order_by("-last_message_at"))
        return Response(ConversationSerializer(qs, many=True, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def create_deal(self, request, pk=None):
        """Створити/відкрити сделку з чату відкритої лінії. Гарантуємо контакт, лінк через контакт."""
        from apps.crm.models import Contact, Deal, Funnel
        conv = self.get_object()
        contact = conv.contact
        if not contact:
            raw = (str(conv.contact) if conv.contact else "") or conv.title or "Клієнт з чату"
            parts = raw.split()
            contact = Contact.objects.create(
                first_name=(parts[0][:150] if parts else "Клієнт"),
                last_name=(" ".join(parts[1:])[:150] if len(parts) > 1 else ""),
                source=(conv.channel.kind if conv.channel_id else "chat"))
            conv.contact = contact
            conv.save(update_fields=["contact"])
        existing = contact.deals.order_by("-updated_at").first()
        if existing:
            return Response({"deal_id": existing.id, "created": False})
        funnel = (Funnel.objects.filter(is_lead_funnel=False, name__icontains="Основний продукт").exclude(name__contains="·").first()
                  or Funnel.objects.filter(is_lead_funnel=False).first())
        stage = funnel.stages.order_by("order").first() if funnel else None
        deal = Deal.objects.create(
            title=(str(contact) or conv.title or "Сделка з чату"), contact=contact, funnel=funnel, stage=stage,
            amount=0, source=(conv.channel.kind if conv.channel_id else "chat"),
            owner=(conv.assigned_to or (request.user if request.user.is_authenticated else None)))
        return Response({"deal_id": deal.id, "created": True})

    @action(detail=True, methods=["get"])
    def messages(self, request, pk=None):
        conv = self.get_object()
        if (conv.channel.config or {}).get("chatplace"):
            # Троттл: живий запит у ChatPlace не частіше ніж раз на 30с на чат
            # (фронт опитує /messages кожні 6с → інакше 10 звернень/хв на чат → Cloudflare-бан).
            from django.core.cache import cache as _cache
            _ck = "cp_livesync_%s" % conv.id
            if not _cache.get(_ck):
                try:
                    from .chatplace import sync_one_chat, configured
                    if configured():
                        sync_one_chat(conv)
                        _cache.set(_ck, 1, timeout=30)
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
        if request.data.get("internal"):
            # внутрішня нотатка — НЕ йде клієнту, видно лише менеджерам у діалозі
            u = request.user
            msg = Message.objects.create(conversation=conv, direction="out", text=text, internal=True,
                                         sender=u, sender_name=(u.get_full_name() or u.username))
            return Response(MessageSerializer(msg).data, status=status.HTTP_201_CREATED)
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
            return Response(claude_json(prompt, max_tokens=1000, source="Подсказка ответа клиенту"))
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
            # Канал не приймає файли (IG/ChatPlace) → зберігаємо файл і шлемо ПОСИЛАННЯ текстом (обхід обмеження)
            from .models import SharedLink
            from .services import send_message as _send_text
            import secrets, mimetypes
            tok = secrets.token_urlsafe(16)
            ct = mimetypes.guess_type(filename)[0] or ("image/jpeg" if kind == "image" else "application/octet-stream")
            SharedLink.objects.create(token=tok, filename=filename[:255], content_type=ct, data=content)
            url = request.build_absolute_uri("/api/f/%s/" % tok)
            label = "\U0001F4F7 Фото" if kind == "image" else "\U0001F4CE Файл"
            try:
                msg = _send_text(conv, "%s — %s\n%s" % (label, filename, url), user=request.user)
            except Exception as e:
                return Response({"detail": "Не вдалося надіслати посилання: %s" % e}, status=status.HTTP_502_BAD_GATEWAY)
            return Response(MessageSerializer(msg).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        msg = Message.objects.create(conversation=conv, direction="out", text=f"[{kind}] {filename}",
                                     external_id=str(msg_id or ""), attachments=[{"type": kind, "name": filename}])
        return Response(MessageSerializer(msg).data, status=status.HTTP_201_CREATED)


from django.http import HttpResponse as _HttpResponse
from rest_framework.permissions import AllowAny as _AllowAny


class SharedFileView(APIView):
    """Публічна віддача файлу за токеном — для посилань клієнту (обхід IG)."""
    authentication_classes = []
    permission_classes = [_AllowAny]

    def get(self, request, token):
        from .models import SharedLink
        f = SharedLink.objects.filter(token=token).first()
        if not f:
            return _HttpResponse("not found", status=404)
        r = _HttpResponse(bytes(f.data), content_type=f.content_type)
        r["Content-Disposition"] = 'inline; filename="%s"' % f.filename
        return r


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


def _msg_vis(u):
    from django.db.models import Q as _Q
    return (_Q(conversation__assigned_to=u) | _Q(conversation__assigned_to__isnull=True)
            | _Q(conversation__participants=u) | _Q(conversation__contact__owner=u))


def _conv_vis(u):
    from django.db.models import Q as _Q
    return (_Q(assigned_to=u) | _Q(assigned_to__isnull=True)
            | _Q(participants=u) | _Q(contact__owner=u))


def _cname(conv, fallback=""):
    c = conv.contact
    nm = ((c.first_name + " " + c.last_name).strip() if c else "")
    return nm or conv.title or fallback or "Клієнт"


class InboxPingView(APIView):
    """Поллер сповіщень: max id вхідного + деталі останнього + лічильник непрочитаних."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import Max
        u = request.user
        qs = (Message.objects.filter(direction="in", internal=False, conversation__status="open")
              .filter(_msg_vis(u)))
        last = qs.aggregate(m=Max("id"))["m"] or 0
        latest = None
        m = qs.select_related("conversation", "conversation__contact", "conversation__channel").order_by("-id").first()
        if m:
            conv = m.conversation
            latest = {"conv_id": conv.id, "name": _cname(conv, m.sender_name),
                      "channel": conv.channel.name if conv.channel_id else "",
                      "preview": (m.text or "")[:90], "at": m.created_at.isoformat()}
        unread = (Conversation.objects.filter(status="open", unread__gt=0)
                  .filter(_conv_vis(u)).distinct().count())
        from .models import Notification as _Ntf
        unread += _Ntf.objects.filter(user=u, read=False).count()
        return Response({"last_in": last, "latest": latest, "unread": unread})


class NotificationsView(APIView):
    """Стрічка сповіщень: вхідні повідомлення + дзвінки (для вкладки «Сповіщення»)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        u = request.user
        items = []
        from .models import Notification
        _ntfs = list(Notification.objects.filter(user=u, read=False).select_related("conversation")[:30])
        for _nt in _ntfs:
            items.append({"type": "added", "conv_id": _nt.conversation_id, "name": _nt.text,
                          "preview": "", "at": _nt.created_at.isoformat()})
        if _ntfs:
            Notification.objects.filter(id__in=[x.id for x in _ntfs]).update(read=True)
        msgs = (Message.objects.filter(direction="in", internal=False, conversation__status="open")
                .filter(_msg_vis(u))
                .select_related("conversation", "conversation__contact", "conversation__channel")
                .order_by("-id")[:40])
        for m in msgs:
            conv = m.conversation
            items.append({"type": "message", "conv_id": conv.id, "name": _cname(conv, m.sender_name),
                          "channel": conv.channel.name if conv.channel_id else "",
                          "preview": (m.text or "")[:130], "unread": conv.unread,
                          "at": m.created_at.isoformat()})
        try:
            from apps.telephony.models import Call
            for ca in Call.objects.select_related("contact", "deal").order_by("-started_at", "-id")[:20]:
                cc = ca.contact
                nm = ((cc.first_name + " " + cc.last_name).strip() if cc else "") or ca.from_number or ca.to_number or "—"
                items.append({"type": "call", "deal_id": ca.deal_id, "name": nm, "line": ca.line,
                              "direction": ca.direction, "disposition": ca.disposition, "duration": ca.duration,
                              "at": ca.started_at.isoformat() if ca.started_at else None})
        except Exception:
            pass
        items = [i for i in items if i.get("at")]
        items.sort(key=lambda i: i["at"], reverse=True)
        return Response({"items": items[:60]})



def _tg_sig(message_id, idx):
    import hmac, hashlib
    from django.conf import settings as _s
    return hmac.new(_s.SECRET_KEY.encode(), ("%s:%s" % (message_id, idx)).encode(), hashlib.sha256).hexdigest()[:16]


class TgFileView(APIView):
    """Віддає медіа Telegram по file_id (токен лишається на сервері). Підпис ?s= захищає від перебору."""
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, message_id, idx):
        from django.http import HttpResponse
        import urllib.request as _u, json as _j
        if request.query_params.get("s") != _tg_sig(message_id, idx):
            return Response({"detail": "bad signature"}, status=status.HTTP_403_FORBIDDEN)
        msg = Message.objects.filter(id=message_id).select_related("conversation__channel").first()
        if not msg:
            return Response(status=404)
        atts = msg.attachments or []
        if idx < 0 or idx >= len(atts):
            return Response(status=404)
        att = atts[idx]
        fid = att.get("file_id")
        token = ((msg.conversation.channel.config or {}).get("bot_token")) if msg.conversation_id and msg.conversation.channel_id else None
        if not fid or not token:
            return Response(status=404)
        try:
            with _u.urlopen("https://api.telegram.org/bot%s/getFile?file_id=%s" % (token, fid), timeout=20) as r:
                fp = _j.loads(r.read().decode())["result"]["file_path"]
            with _u.urlopen("https://api.telegram.org/file/bot%s/%s" % (token, fp), timeout=40) as r:
                data = r.read()
        except Exception as e:
            return Response({"detail": str(e)[:80]}, status=502)
        ct = att.get("mime") or ("image/jpeg" if att.get("type") == "photo" else ("audio/ogg" if att.get("type") == "voice" else "application/octet-stream"))
        resp = HttpResponse(data, content_type=ct)
        nm = att.get("name") or (att.get("type", "file"))
        resp["Content-Disposition"] = 'inline; filename="%s"' % nm
        resp["Cache-Control"] = "private, max-age=86400"
        return resp


class TeamContactsView(APIView):
    """Список співробітників для внутрішнього чату + останнє повідомлення + непрочитані."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.contrib.auth import get_user_model
        from django.db.models import Q, Max
        from .models import TeamMessage
        U = get_user_model()
        me = request.user
        users = U.objects.filter(is_active=True).exclude(id=me.id).select_related("department").order_by("first_name", "username")
        out = []
        for u in users:
            last = TeamMessage.objects.filter(
                Q(sender=me, recipient=u) | Q(sender=u, recipient=me)).order_by("-id").first()
            unread = TeamMessage.objects.filter(sender=u, recipient=me, read=False).count()
            out.append({
                "id": u.id, "full_name": (u.get_full_name() or u.username),
                "dept": (u.department.name if getattr(u, "department_id", None) else ""),
                "last": (last.text[:60] if last else ""), "last_at": (last.created_at if last else None),
                "unread": unread,
            })
        out.sort(key=lambda x: (x["last_at"] is None, x["last_at"] and -x["last_at"].timestamp() if x["last_at"] else 0))
        return Response(out)


class TeamThreadView(APIView):
    """Переписка з конкретним співробітником. GET — повідомлення (помічаємо прочитаними). POST — відправити."""
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        from django.db.models import Q
        from .models import TeamMessage
        me = request.user
        qs = TeamMessage.objects.filter(Q(sender=me, recipient_id=user_id) | Q(sender_id=user_id, recipient=me)).select_related("sender")[:500]
        TeamMessage.objects.filter(sender_id=user_id, recipient=me, read=False).update(read=True)
        return Response([{
            "id": m.id, "text": m.text, "attachments": m.attachments or [], "mentions": m.mentions or [],
            "out": m.sender_id == me.id, "sender_name": (m.sender.get_full_name() or m.sender.username),
            "created_at": m.created_at,
        } for m in qs])

    def post(self, request, user_id):
        from django.contrib.auth import get_user_model
        from .models import TeamMessage
        me = request.user
        U = get_user_model()
        rec = U.objects.filter(id=user_id, is_active=True).first()
        if not rec:
            return Response({"detail": "Співробітник не знайдений"}, status=status.HTTP_404_NOT_FOUND)
        text = (request.data.get("text") or "").strip()
        atts = request.data.get("attachments") or []
        # файл як base64 → SharedLink → посилання
        b64 = request.data.get("content_b64")
        if b64:
            from .models import SharedLink
            import secrets, mimetypes
            fn = request.data.get("filename") or "file"
            tok = secrets.token_urlsafe(16)
            ct = mimetypes.guess_type(fn)[0] or "application/octet-stream"
            SharedLink.objects.create(token=tok, filename=fn[:255], content_type=ct, data=__import__("base64").b64decode(b64.split(",")[-1]))
            atts = list(atts) + [{"name": fn, "url": request.build_absolute_uri("/api/f/%s/" % tok), "kind": ("image" if ct.startswith("image") else "file")}]
        mentions = request.data.get("mentions") or []
        if not text and not atts:
            return Response({"detail": "Порожнє повідомлення"}, status=status.HTTP_400_BAD_REQUEST)
        m = TeamMessage.objects.create(sender=me, recipient=rec, text=text, attachments=atts, mentions=mentions)
        # сповіщення згаданим + отримувачу
        try:
            from .models import Notification
            who = me.get_full_name() or me.username
            targets = set([rec.id] + [int(x) for x in mentions if str(x).isdigit()])
            for tid in targets:
                Notification.objects.create(user_id=tid, text="\U0001F4AC %s: %s" % (who, (text or "файл")[:80]))
        except Exception:
            pass
        return Response({"id": m.id, "text": m.text, "attachments": m.attachments, "out": True,
                         "sender_name": (me.get_full_name() or me.username), "created_at": m.created_at}, status=201)
