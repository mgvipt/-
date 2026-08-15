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
            # Wallcov: Telegram-DM ідуть через e-chat Telegram (окремий канал). Бот НЕ інгестить
            # бізнес-повідомлення особистого номера — інакше дублі й неправильний напрям
            # (той самий акаунт слухають і бот-Business, і e-chat). Вмикнути назад: config ingest_business=True.
            if not cfg.get("ingest_business", False):
                return Response({"ok": True})
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
    """Приём входящих Viber/Telegram-сообщений через e-chat.tech."""
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, channel_id):
        channel = get_object_or_404(Channel, pk=channel_id,
                                    kind__in=("echat", "echat_telegram", "echat_whatsapp"), is_active=True)
        d = request.data
        direction = str(d.get("direction") or "")
        event = str(d.get("event") or "")
        if "outgoing" in direction or "outgoing" in event:
            # статуси доставки вихідних (delivered/failed/read) — логуємо для діагностики
            try:
                import json as _j, sys as _sys
                print("ECHAT-OUT-STATUS ch=%s: %s" % (channel_id, _j.dumps(d, ensure_ascii=False)[:600]), file=_sys.stderr, flush=True)
            except Exception:
                pass
            return Response({"status": 0})  # власні вихідні / статуси — не створюємо повідомлень
        inc = get_adapter(channel).parse_webhook(d)
        if inc and inc.external_chat_id:
            ingest(channel, inc)
        return Response({"status": 0, "status_message": "ok"})


class EchatSetupView(APIView):
    """Налаштування Viber і Telegram особистого номера через e-chat.tech."""

    PLATFORMS = {
        "viber": ("echat", "echat", "Viber (e-chat)"),
        "telegram": ("echat_telegram", "echat_telegram", "Telegram (e-chat)"),
        "whatsapp": ("echat_whatsapp", "echat_whatsapp", "WhatsApp (e-chat)"),
    }

    @staticmethod
    def _number(raw):
        """E-chat очікує міжнародний номер без пробілів і символу +."""
        import re
        number = re.sub(r"\D", "", str(raw or ""))
        if len(number) == 10 and number.startswith("0"):
            number = "38" + number
        return number

    def _row(self, request, ch):
        old_config = dict(ch.config or {})
        old_name = ch.name
        cfg = dict(old_config)
        return {
            "connected": bool(ch.is_active),
            "platform": {"echat_telegram": "telegram", "echat_whatsapp": "whatsapp"}.get(ch.kind, "viber"),
            "number": cfg.get("number", ""),
            "has_key": bool(cfg.get("api_key")),
            "channel_id": ch.id,
            "webhook": request.build_absolute_uri("/api/inbox/echat/webhook/%d/" % ch.id),
        }

    def get(self, request):
        rows = [self._row(request, ch) for ch in
                Channel.objects.filter(kind__in=("echat", "echat_telegram", "echat_whatsapp")).order_by("kind", "id")]
        # Старі поля лишаємо для сумісності зі старим фронтендом під час rolling deploy.
        first = rows[0] if rows else {"connected": False, "number": "", "has_key": False,
                                     "webhook": "", "channel_id": None}
        return Response({**first, "channels": rows})

    def post(self, request):
        if not request.user.has_perm_code("roles.manage"):
            return Response({"detail": "Немає прав"}, status=status.HTTP_403_FORBIDDEN)
        platform = str(request.data.get("platform") or "viber").lower()
        if platform not in self.PLATFORMS:
            return Response({"detail": "Невідомий тип E-chat каналу"}, status=status.HTTP_400_BAD_REQUEST)
        kind, config_flag, title = self.PLATFORMS[platform]
        api_key = (request.data.get("api_key") or "").strip()
        number = self._number(request.data.get("number"))
        if not number:
            return Response({"detail": "Вкажіть номер каналу"}, status=status.HTTP_400_BAD_REQUEST)
        ch = next((row for row in Channel.objects.filter(kind=kind)
                   if self._number((row.config or {}).get("number")) == number), None)
        is_new = ch is None
        if ch is None:
            ch = Channel(kind=kind, name=title + " " + number, is_active=False)
        cfg = ch.config or {}
        if not api_key and not cfg.get("api_key"):
            return Response({"detail": "Для нового каналу вкажіть його API-ключ E-chat"},
                            status=status.HTTP_400_BAD_REQUEST)
        cfg[config_flag] = True; cfg["number"] = number
        if api_key:
            cfg["api_key"] = api_key
        was_active = bool(ch.is_active)
        ch.config = cfg; ch.name = title + " " + number; ch.save()
        try:
            result = get_adapter(ch).connect()
        except Exception as e:
            if is_new:
                ch.is_active = False
                ch.save(update_fields=["is_active"])
            else:
                ch.config = old_config
                ch.name = old_name
                ch.is_active = was_active
                ch.save(update_fields=["config", "name", "is_active"])
            return Response({"detail": str(e), "channel_id": ch.id}, status=status.HTTP_400_BAD_REQUEST)
        ch.is_active = True
        ch.save(update_fields=["is_active"])
        return Response({"ok": True, "channel_id": ch.id,
                         "platform": platform,
                         "number": number,
                         "webhook": request.build_absolute_uri("/api/inbox/echat/webhook/%d/" % ch.id),
                         "connect_result": result})


class ChannelViewSet(viewsets.ModelViewSet):
    queryset = Channel.objects.all().order_by("name")
    serializer_class = ChannelSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        allowed = self.request.user.allowed_channel_ids()
        return qs if allowed is None else qs.filter(id__in=allowed)

    @action(detail=True, methods=["post"])
    def set_active(self, request, pk=None):
        """Підключити/відключити канал від CRM (кнопка у Контакт-центрі)."""
        if not request.user.has_perm_code("roles.manage"):
            return Response({"detail": "Немає прав"}, status=status.HTTP_403_FORBIDDEN)
        ch = self.get_object()
        ch.is_active = bool(request.data.get("active"))
        ch.save(update_fields=["is_active"])
        if not ch.is_active and (ch.config or {}).get("echat_whatsapp"):
            try:
                get_adapter(ch)._post("/channel/disconnect", {"number": (ch.config or {}).get("number", "")})
            except Exception:
                pass
        return Response({"ok": True, "is_active": ch.is_active})

    @action(detail=True, methods=["get", "post"])
    def access(self, request, pk=None):
        """Доступ менеджерів до каналу. GET — список співробітників + доступ;
        POST {user_id, grant} — видати/зняти індивідуальний доступ (extra_open_lines)."""
        if not request.user.has_perm_code("roles.manage"):
            return Response({"detail": "Немає прав"}, status=status.HTTP_403_FORBIDDEN)
        ch = self.get_object()
        from apps.accounts.models import User
        if request.method == "POST":
            u = User.objects.filter(id=request.data.get("user_id")).first()
            if not u:
                return Response({"detail": "Немає користувача"}, status=status.HTTP_400_BAD_REQUEST)
            extra = [x for x in (u.extra_open_lines or []) if x != ch.id]
            if request.data.get("grant"):
                base = set(u.role.open_lines or []) if u.role_id else set()
                if u.department_id:
                    try:
                        base |= set(u.department.eff_open_lines())
                    except Exception:
                        pass
                if bool(base) or bool(u.extra_open_lines):
                    extra.append(ch.id)  # користувач вже обмежений — додаємо канал
                # інакше він бачить усі канали — не обмежуємо
            u.extra_open_lines = extra
            u.save(update_fields=["extra_open_lines"])
        rows = []
        for u in User.objects.filter(is_active=True).exclude(is_superuser=True).order_by("first_name", "last_name", "username"):
            allowed = u.allowed_channel_ids()
            individual = ch.id in set(u.extra_open_lines or [])
            eff = (allowed is None) or (ch.id in (allowed or []))
            rows.append({"id": u.id, "full_name": (u.get_full_name() or u.username),
                         "has_access": eff, "individual": individual, "via_role_dept": eff and not individual})
        return Response({"channel_id": ch.id, "channel_name": ch.name, "staff": rows})


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
# Мʼяке перехоплення «остиглого» клієнта: якщо клієнт закріплений за іншим,
# але той не писав йому стільки днів — беручи живий чат, забираємо клієнта собі.
_TAKEOVER_STALE_DAYS = 30


class ConversationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Conversation.objects.select_related("channel", "contact", "assigned_to").prefetch_related("participants")
    serializer_class = ConversationSerializer
    filterset_fields = ["channel", "status", "assigned_to", "contact"]
    search_fields = []  # poshuk robymo vruchnu v get_queryset (imya/nik/telefon/posylannya, po VSIH dostupnyh chatah)

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
                  | Q(contact__leads__owner=user) | Q(contact__deals__owner=user)
                  | Q(contact__deals__warehouse_jobs__assignee=user))  # склад: виконавець задачі бачить чат клієнта
        if not can_all:
            # Незайняті чати (нічиї) — СПІЛЬНИЙ ПУЛ: доступні всім, хто має доступ до каналу
            # (бачить + може відкрити/відповісти/взяти). Призначені — лише свої (mine_q).
            qs = qs.filter(mine_q | Q(assigned_to__isnull=True)).distinct()
        # КОМАНДНА ЧЕРГА — фільтри ТІЛЬКИ у СПИСКУ. Чат, взятий ІНШИМ співробітником,
        # зникає зі списку (його все одно можна відкрити через картку ліда/сделки = retrieve,
        # і «Закріпити» за собою — тоді він стане видимий у того, хто останнім узяв).
        scope = self.request.query_params.get("scope")
        # POSHUK: po imeni / niku / telefonu / posylannyu - po VSIH dostupnyh chatah
        # (ne obmezhuyuchys vkladkoyu "Moyi" i vklyuchno iz zakrytymy).
        _search = (self.request.query_params.get("search") or "").strip()
        _searching = bool(_search)
        if _searching:
            import re as _re2
            sq = (Q(title__icontains=_search) | Q(contact__first_name__icontains=_search)
                  | Q(contact__last_name__icontains=_search) | Q(contact__nickname__icontains=_search)
                  | Q(contact__social_link__icontains=_search) | Q(contact__phone__icontains=_search))
            _dig = _re2.sub(r"\D", "", _search)
            if len(_dig) >= 5:
                _vars = {_dig, _dig.lstrip("0"), "380" + _dig.lstrip("0")}
                if _dig.startswith("38"):
                    _vars.add("0" + _dig[2:])
                for _v in _vars:
                    if _v:
                        sq |= Q(contact__phone__icontains=_v)
            qs = qs.filter(sq).distinct()
        if _searching:
            pass  # poshuk - bez obmezhennya potochnoyu vkladkoyu
        elif scope == "mine":
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
            # ПІД-ФІЛЬТР черги (серед призначених у роботу): «потрібна відповідь» / «чекаємо клієнта».
            # Реальний фільтр на бекенді → сьогодні завжди зверху, лічильники правильні (не по підвантаженому).
            if scope in ("need", "waiting"):
                from django.db.models import OuterRef as _OR, Subquery as _SQ
                _last_dir = Message.objects.filter(conversation=_OR("pk")).order_by("-id").values("direction")[:1]
                qs = qs.annotate(_ld=_SQ(_last_dir)).filter(assigned_to__isnull=False)
                if scope == "need":
                    # останнє повідомлення від клієнта АБО вручну позначено неотвеченим
                    qs = qs.filter(Q(_ld="in") | Q(unread__gt=0))
                else:
                    # ми відповіли останніми і нічого не висить → чекаємо відповідь клієнта
                    qs = qs.filter(_ld="out").exclude(unread__gt=0)
        # У СПИСКУ показуємо лише ВІДКРИТІ чати. Закритий зникає; коли клієнт напише —
        # ingest створює новий open-діалог і він знову зʼявиться (у непризначених).
        if self.action == "list" and not self.request.query_params.get("status") and not _searching:
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

    # ── ПАКЕТНІ метадані для списку (усуває N+1: було ~10 запитів/чат) ──
    def _prefetch_conv_meta(self, objs):
        from django.db.models import OuterRef, Subquery, Count, Q, F
        ids = [o.id for o in objs]
        if not ids:
            self._conv_meta = {}
            return
        # останнє повідомлення на кожен чат (DISTINCT ON) — 1 запит
        last = {}
        for m in (Message.objects.filter(conversation_id__in=ids)
                  .order_by("conversation_id", "-id").distinct("conversation_id")
                  .values("conversation_id", "direction", "sender_id", "sender_name", "internal", "text")):
            last[m["conversation_id"]] = {"direction": m["direction"], "sender_id": m["sender_id"],
                "sender_name": m["sender_name"], "internal": m["internal"], "text": m["text"]}
        # unhandled_in: вхідні після останнього ЛЮДСЬКОГО вихідного — 1 запит на всю сторінку
        human = Q(sender__isnull=False) | Q(sender_name__in=("operator", "manager", "admin"))
        lh = (Message.objects.filter(conversation=OuterRef("conversation"), direction="out", internal=False)
              .filter(human).order_by("-id").values("id")[:1])
        unh = {}
        for r in (Message.objects.filter(conversation_id__in=ids, direction="in")
                  .annotate(_lh=Subquery(lh)).filter(Q(_lh__isnull=True) | Q(id__gt=F("_lh")))
                  .values("conversation_id").annotate(c=Count("id"))):
            unh[r["conversation_id"]] = r["c"]
        # остання сделка на кожен контакт (DISTINCT ON) — 1 запит
        deals = {}
        cids = [o.contact_id for o in objs if o.contact_id]
        if cids:
            from apps.crm.models import Deal
            for d in (Deal.objects.filter(contact_id__in=cids).select_related("stage")
                      .order_by("contact_id", "-updated_at").distinct("contact_id")):
                deals[d.contact_id] = d
        self._conv_meta = {o.id: {"last": last.get(o.id), "unhandled_in": unh.get(o.id, 0),
                                  "deal": deals.get(o.contact_id)} for o in objs}

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if getattr(self, "_conv_meta", None) is not None:
            ctx["conv_meta"] = self._conv_meta
        return ctx

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        objs = page if page is not None else list(qs)
        self._prefetch_conv_meta(objs)
        ser = self.get_serializer(objs, many=True)
        return self.get_paginated_response(ser.data) if page is not None else Response(ser.data)

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
        u = request.user
        # ── ЗАМОК ЧЕРГИ ── діалог уже взяв ІНШИЙ менеджер → перехопити НЕ можна,
        # навіть якщо сторінка не оновилась і чат ще видно як «вільний».
        # Перепризначити може лише керівник (через «Переадресувати»).
        is_boss = u.can_see_all_conversations() or u.has_perm_code("roles.manage")
        if conv.assigned_to_id and conv.assigned_to_id != u.id and not is_boss:
            _who = (conv.assigned_to.get_full_name() or conv.assigned_to.username) if conv.assigned_to else "інший менеджер"
            return Response(
                {"detail": "Діалог уже взяв у роботу %s. Перехопити не можна — зверніться до керівника." % _who,
                 "assigned_to": conv.assigned_to_id, "assigned_to_name": _who},
                status=status.HTTP_409_CONFLICT)
        conv.assigned_to = u
        conv.save(update_fields=["assigned_to"])
        if conv.contact_id:
            from apps.crm.models import Deal, Lead, Contact
            # Беручи чат — стаємо відповідальним за клієнта і його ВІДКРИТІ сделки/ліди,
            # АЛЕ тільки якщо клієнт ВІЛЬНИЙ (без власника) або вже наш. Чужого клієнта
            # закріплення чату НЕ забирає (виняток — адмін/право «Редагувати клієнтів»).
            _c = Contact.objects.filter(id=conv.contact_id).first()
            _can_take = bool(_c) and (
                _c.owner_id in (None, request.user.id)
                or request.user.is_superuser
                or request.user.has_perm_code("roles.manage")
                or request.user.has_perm_code("contact.edit.all"))
            # ── Мʼяке перехоплення «остиглого» клієнта (Wallcov: мало менеджерів) ──
            # Клієнт закріплений за ІНШИМ, але той давно (≥_TAKEOVER_STALE_DAYS днів) не
            # писав йому → живий чат важливіший за «заморожене» закріплення: забираємо
            # клієнта+відкриті сделки собі і повідомляємо попереднього відповідального.
            _prev_owner_id = _c.owner_id if _c else None
            if (not _can_take) and _prev_owner_id and _prev_owner_id != request.user.id:
                from django.utils import timezone as _tz
                from datetime import timedelta as _td
                _cutoff = _tz.now() - _td(days=_TAKEOVER_STALE_DAYS)
                _owner_active = Message.objects.filter(
                    conversation__contact_id=conv.contact_id,
                    direction="out", sender_id=_prev_owner_id,
                    created_at__gte=_cutoff).exists()
                if not _owner_active:
                    _can_take = True
                    try:
                        from .models import Notification
                        Notification.objects.create(
                            user_id=_prev_owner_id, kind="system", conversation=conv,
                            actor=request.user,
                            text=(f"Клієнта «{_c}» перехопив "
                                  f"{request.user.get_full_name() or request.user.username}: "
                                  f"ви давно не писали йому, а він знову звернувся."))
                    except Exception:
                        pass
            if _can_take:
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
            from apps.warehouse.models import WarehouseJob
            ok = (Deal.objects.filter(contact_id=cid, owner=u).exists() or
                  Lead.objects.filter(contact_id=cid, owner=u).exists() or
                  Conversation.objects.filter(contact_id=cid).filter(_Q(assigned_to=u) | _Q(participants=u)).exists() or
                  WarehouseJob.objects.filter(deal__contact_id=cid, assignee=u).exists())
            if not ok:
                return Response([])
        objs = list(Conversation.objects.filter(contact_id=cid)
              .select_related("channel", "contact", "assigned_to").prefetch_related("participants")
              .order_by("-last_message_at"))
        self._prefetch_conv_meta(objs)
        return Response(ConversationSerializer(objs, many=True, context=self.get_serializer_context()).data)

    def _allowed_reply_channels(self, request, conv):
        """Лінії, якими цьому контакту реально можна відповісти."""
        allowed = request.user.allowed_channel_ids()
        channels = Channel.objects.filter(is_active=True).order_by("kind", "name")
        if allowed is not None:
            channels = channels.filter(id__in=allowed)
        existing = {}
        if conv.contact_id:
            for row in (Conversation.objects.filter(contact_id=conv.contact_id, status="open")
                        .select_related("channel").order_by("-last_message_at", "-id")):
                existing.setdefault(row.channel_id, row)
        rows = []
        for channel in channels:
            current = existing.get(channel.id)
            can_start = bool(channel.kind in ("echat", "echat_telegram", "echat_whatsapp")
                             and conv.contact and conv.contact.phone)
            if not current and channel.id != conv.channel_id and not can_start:
                continue
            rows.append({
                "channel_id": channel.id,
                "channel_kind": channel.kind,
                "channel_name": channel.name,
                "number": (channel.config or {}).get("number", ""),
                "conversation_id": current.id if current else (conv.id if channel.id == conv.channel_id else None),
                "selected": channel.id == conv.channel_id,
            })
        return rows

    def _can_start_for_contact(self, request, contact_id):
        """Ті самі права, що й для чату у картці контакту/угоди."""
        u = request.user
        if u.is_superuser or u.has_perm_code("conversation.view.all") or u.can_see_all_deals():
            return True
        from apps.crm.models import Deal, Lead
        from apps.warehouse.models import WarehouseJob
        return (Deal.objects.filter(contact_id=contact_id, owner=u).exists()
                or Lead.objects.filter(contact_id=contact_id, owner=u).exists()
                or Conversation.objects.filter(contact_id=contact_id)
                .filter(Q(assigned_to=u) | Q(participants=u)).exists()
                or WarehouseJob.objects.filter(deal__contact_id=contact_id, assignee=u).exists())

    def _allowed_start_channels(self, request, contact):
        """Безпечний список E-chat ліній для першого вихідного повідомлення."""
        if not contact.phone:
            return []
        allowed = request.user.allowed_channel_ids()
        channels = Channel.objects.filter(
            is_active=True, kind__in=("echat", "echat_telegram", "echat_whatsapp")
        ).order_by("kind", "name")
        if allowed is not None:
            channels = channels.filter(id__in=allowed)
        return [{
            "channel_id": channel.id,
            "channel_kind": channel.kind,
            "channel_name": channel.name,
            "number": (channel.config or {}).get("number", ""),
        } for channel in channels]

    @action(detail=False, methods=["get"])
    def start_channels(self, request):
        """Лінії Viber/Telegram, через які можна почати чат за номером контакту."""
        from apps.crm.models import Contact
        try:
            contact_id = int(request.query_params.get("contact"))
        except (TypeError, ValueError):
            return Response({"detail": "Вкажіть контакт"}, status=status.HTTP_400_BAD_REQUEST)
        if not self._can_start_for_contact(request, contact_id):
            return Response({"detail": "Немає прав"}, status=status.HTTP_403_FORBIDDEN)
        contact = get_object_or_404(Contact, pk=contact_id)
        return Response(self._allowed_start_channels(request, contact))

    @action(detail=False, methods=["post"])
    def start_channel(self, request):
        """Надіслати перше повідомлення на номер і створити (або повторно використати) чат."""
        import re
        from django.db import transaction
        from apps.crm.models import Contact, Deal
        try:
            contact_id = int(request.data.get("contact_id"))
            channel_id = int(request.data.get("channel_id"))
        except (TypeError, ValueError):
            return Response({"detail": "Оберіть контакт і канал"}, status=status.HTTP_400_BAD_REQUEST)
        text = (request.data.get("text") or "").strip()
        if not text:
            return Response({"detail": "Напишіть повідомлення"}, status=status.HTTP_400_BAD_REQUEST)
        if not self._can_start_for_contact(request, contact_id):
            return Response({"detail": "Немає прав"}, status=status.HTTP_403_FORBIDDEN)
        contact = get_object_or_404(Contact, pk=contact_id)
        candidates = {row["channel_id"]: row for row in self._allowed_start_channels(request, contact)}
        if channel_id not in candidates:
            detail = "Додайте коректний номер телефону" if not contact.phone else "Цей канал недоступний"
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)
        external_chat_id = re.sub(r"\D", "", contact.phone)
        if len(external_chat_id) == 10 and external_chat_id.startswith("0"):
            external_chat_id = "38" + external_chat_id
        if len(external_chat_id) < 10:
            return Response({"detail": "У клієнта некоректний номер телефону"},
                            status=status.HTTP_400_BAD_REQUEST)
        target = Channel.objects.get(pk=channel_id)
        created = False
        try:
            with transaction.atomic():
                selected = (Conversation.objects.select_for_update()
                            .filter(contact=contact, channel=target, status="open")
                            .order_by("-last_message_at", "-id").first())
                if selected is None:
                    owner_id = (contact.owner_id
                                or Deal.objects.filter(contact=contact).exclude(stage__is_lost=True)
                                .order_by("-created_at").values_list("owner_id", flat=True).first()
                                or request.user.id)
                    selected = Conversation.objects.create(
                        channel=target, contact=contact, external_chat_id=external_chat_id,
                        title=str(contact), assigned_to_id=owner_id,
                    )
                    created = True
                msg = send_message(selected, text, user=request.user)
                channel_name = {"echat_telegram": "telegram", "echat_whatsapp": "whatsapp"}.get(target.kind, "viber")
                contact_channels = list(contact.channels or [])
                if channel_name not in contact_channels:
                    contact.channels = contact_channels + [channel_name]
                    contact.save(update_fields=["channels"])
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({
            "conversation": ConversationSerializer(selected, context={"request": request}).data,
            "message": MessageSerializer(msg).data,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def reply_channels(self, request, pk=None):
        """Повертає доступні вихідні канали/номери без секретів конфігурації."""
        conv = self.get_object()
        return Response(self._allowed_reply_channels(request, conv))

    @action(detail=True, methods=["post"])
    def use_channel(self, request, pk=None):
        """Вибрати існуючий діалог або підготувати E-chat-діалог за телефоном контакту."""
        import re
        conv = self.get_object()
        try:
            channel_id = int(request.data.get("channel_id"))
        except (TypeError, ValueError):
            return Response({"detail": "Оберіть канал"}, status=status.HTTP_400_BAD_REQUEST)
        candidates = {row["channel_id"]: row for row in self._allowed_reply_channels(request, conv)}
        if channel_id not in candidates:
            return Response({"detail": "Цей канал недоступний для контакту"}, status=status.HTTP_400_BAD_REQUEST)
        target = Channel.objects.get(pk=channel_id)
        selected = (Conversation.objects.filter(contact_id=conv.contact_id, channel=target, status="open")
                    .order_by("-last_message_at", "-id").first())
        if selected is None:
            if target.kind not in ("echat", "echat_telegram", "echat_whatsapp") or not conv.contact or not conv.contact.phone:
                return Response({"detail": "Немає адреси клієнта для цього каналу"},
                                status=status.HTTP_400_BAD_REQUEST)
            external_chat_id = re.sub(r"\D", "", conv.contact.phone)
            if len(external_chat_id) == 10 and external_chat_id.startswith("0"):
                external_chat_id = "38" + external_chat_id
            if len(external_chat_id) < 10:
                return Response({"detail": "У клієнта некоректний номер телефону"},
                                status=status.HTTP_400_BAD_REQUEST)
            selected = Conversation.objects.create(
                channel=target, contact=conv.contact, external_chat_id=external_chat_id,
                title=conv.title or str(conv.contact),
                assigned_to=conv.assigned_to,
            )
            selected.participants.set(conv.participants.all())
        return Response(ConversationSerializer(selected, context={"request": request}).data)

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

    @action(detail=True, methods=["post"], url_path="mark-unread")
    def mark_unread(self, request, pk=None):
        """Позначити чат непрочитаним. body: {from_message?: id} — з цього повідомлення клієнта;
        без нього — всі вхідні після останньої відповіді МЕНЕДЖЕРА."""
        conv = self.get_object()
        from_id = request.data.get("from_message")
        if from_id:
            n = conv.messages.filter(direction="in", internal=False, id__gte=int(from_id)).count()
        else:
            last_mgr = conv.messages.filter(direction="out", sender__isnull=False).last()
            n = conv.messages.filter(direction="in", internal=False, id__gt=last_mgr.id if last_mgr else 0).count()
        conv.unread = max(1, n)
        conv.save(update_fields=["unread"])
        return Response({"ok": True, "unread": conv.unread})

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
        # лічильник скидається ЛИШЕ коли менеджер свідомо дивиться чат (?seen=1);
        # фонові поллінги (склад, автоматика) його не чіпають
        if request.query_params.get("seen") and conv.unread:
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

    @action(detail=False, methods=["post"])
    def ai_compose(self, request):
        """Помічник менеджеру: покращити або перекласти ЙОГО чернетку ПЕРЕД відправкою.
        НЕ надсилає нічого клієнту — лише повертає варіант тексту, який менеджер сам
        вставляє у поле і сам тисне «Надіслати». Працює у всіх місцях чату."""
        draft = (request.data.get("draft") or "").strip()
        mode = (request.data.get("mode") or "improve").strip()
        if not draft:
            return Response({"detail": "Спочатку напишіть чернетку"}, status=status.HTTP_400_BAD_REQUEST)
        conv = None
        try:
            cid = request.data.get("conversation_id")
            contact = request.data.get("contact_id")
            if cid:
                conv = Conversation.objects.filter(id=cid).first()
            elif contact:
                conv = Conversation.objects.filter(contact_id=contact).order_by("-id").first()
        except Exception:
            conv = None
        dialog = ""
        if conv:
            msgs = list(conv.messages.order_by("id").values("direction", "text"))[-20:]
            dialog = "\n".join(
                ("Клієнт: " if m["direction"] == "in" else "Менеджер: ") + (m["text"] or "")
                for m in msgs if m.get("text"))
        style = (
            "Ти — Юля, досвідчений РОП (керівник відділу продажів) Wallcov — декоративні покриття та фарби для стін. "
            "Пишеш як жива людина-консультант, що любить свою справу: тепло, ввічливо, впевнено, на «Ви», з турботою про клієнта. "
            "Без канцеляриту, без сухих шаблонів, без роботності. Коротко і по суті, доречно 1-2 емодзі (не більше). "
            "Веди до продажу: підтверди запит, покажи цінність, м'яко підведи до наступного кроку (тест-набір, прорахунок, підбір, оплата), без тиску. "
            "НЕ вигадуй фактів, цін, домовленостей чи посилань — бери лише те, що є у чернетці менеджера. "
            "\n\n═══ БАЗА ЗНАНЬ WALLCOV (не вигадуй іншого) ═══\n\n"
            "💰 ЦІНИ ТЕСТ-НАБОРІВ (фіксовані з прайсу):\n"
            "• Pattera Fine (Травертин): 290 / 345 / 405 / 460 грн (без опцій / +дощечка / +тонування / обидва)\n"
            "• Vельvet Lux (Перламутровий марморин): 460 / 520 / 575 / 635 грн\n"
            "• Вельвет Luna (тонкошаровий, ефект мокрого шовку): 280 / 335 / 395 / 450 грн\n\n"
            "💳 ОПЛАТА — 3-етапна логіка:\n"
            "ЕТАП 1 — за замовчуванням: LiqPay онлайн (картка / Apple Pay / Google Pay / Приват24). Кнопка «Прийняти оплату → LiqPay» у CRM.\n"
            "ЕТАП 2 — клієнт відмовив від онлайн («не хочу онлайн», «не буду картою», «краще по реквізитах») → надіслати шаблон реквізитів IBAN:\n"
            "  Отримувач: ФОП Кріжевські О.Л. | IBAN: UA983052990000026002046111493 | ІПН: 3031640354\n"
            "  Призначення: Оплата замовлення {ID сделки}\n"
            "ЕТАП 3 — клієнт просить «номер карти» → м'яко пояснити: «Ми приймаємо тільки на рахунок ФОП (не на картку фізособи) — це для фіскального чека». Запропонувати LiqPay / IBAN / НП.\n"
            "❌ НІКОЛИ не пиши «номер карти» / «пришлю картку» / оплата на картку фізособи. Тільки IBAN або LiqPay.\n\n"
            "📦 НАКЛАДЕНИЙ ПЛАТІЖ НП — тільки коли клієнт САМ спитав. Ніколи не пропонуй першим.\n"
            "• Тест-набір: 100% передоплата (НП не пропонуємо)\n"
            "• Тонований матеріал: 50% передоплата (не перепродамо іншому)\n"
            "• Нетонований, чек <1000 грн: 100% передоплата\n"
            "• Нетонований, 1000-3000 грн: мін 300 грн передоплата\n"
            "• Нетонований, 3000-10000 грн: мін 500 грн передоплата\n"
            "• Нетонований, 10000-20000 грн: мін 10% чеку передоплата\n"
            "• Нетонований, >20000 грн: мін 15% чеку передоплата\n"
            "У чек рахуємо ВСЕ: матеріал + грунт + валик + дощечка + захист.\n\n"
            "📅 РОЗСТРОЧКА ПРИВАТ (paypart через LiqPay до 9 міс) — тільки коли клієнт САМ спитав. Пиши: «Зв'яжу з менеджером, він надішле спеціальне посилання з опцією Оплата частинами». Не генеруй розстрочку сама.\n\n"
            "🎨 БАГАТОЗНАЧНІ НАЗВИ МАТЕРІАЛІВ — не вгадуй:\n"
            "• «Вельвет» / «Velvet» — це НЕ конкретний матеріал. У нас Вельвет Луна (тонкошаровий, ефект мокрого шовку, дешевше) і Вельвет Люкс (структурний, перламутровий 3D, дорожче в ~3-4 рази). Якщо клієнт написав тільки «Вельвет» без уточнення — потрібно спочатку уточнити який саме.\n"
            "• «мокрий шовк» — може бути Sirena Silk / Mermi Silk / Velvet Luna. Дивись контекст, не вигадуй.\n\n"
            "🔁 ПОВТОРНІ КЛІЄНТИ («купувала минулого року», «повторити», «те що брав раніше»):\n"
            "❌ НЕ вгадуй матеріал з архіву\n"
            "✅ Пропонуй передати менеджеру щоб знайти в CRM історію і повторити точно те що клієнт брав.\n\n"
            "📐 ПРОРАХУНОК НА ОБ'ЄМ:\n"
            "❌ НІКОЛИ не давай підсумкову суму (ціна × м² = грн) без явно названого матеріалу з нашої лінії І підтвердження від клієнта.\n"
            "✅ Мінімальні орієнтири за м² (з фіксованого прайсу): Галатея 200 / Мокрий шовк 147 / Celestial 153 / Velvet Lux 426 / Патера 210 грн/м². Ціна за м² тільки за декоративний матеріал (без грунту та захисту). Точний кошторис — через менеджера.\n"
            "❌ Розхід не фіксований — залежить від техніки, стіни, майстра. Не гадай.\n"
            "❌ Тонування розраховується ІНДИВІДУАЛЬНО — не вигадуй його вартість.\n\n"
            "🚫 ТИ НЕ ПРИЙМАЄШ РІШЕНЬ ЗА КЛІЄНТА:\n"
            "• Не пропонуй знижки — тільки менеджер може\n"
            "• Не обіцяй дати майстер-клас безкоштовно — доступний тільки після покупки тест-набору\n"
            "• Тонування пробників (Pattera / Velvet Luna / Velvet Lux) — можна побачити ціни у прайсі тест-наборів вище")
        if mode == "translate":
            task = (
                "ЗАВДАННЯ: переклади чернетку менеджера на мову, якою спілкується КЛІЄНТ у переписці "
                "(українська або російська — визнач з його повідомлень; якщо переписки немає — українською). "
                "Переклад має бути ПРИРОДНИЙ, як писала б жива Юля тією мовою, а не дослівний. "
                "Пиши ЧИСТО однією мовою клієнта, БЕЗ змішування мов. Збережи зміст, факти й теплий тон.")
        else:
            task = (
                "ЗАВДАННЯ: перепиши чернетку менеджера так, як написав би топовий РОП Wallcov — "
                "грамотно, тепло, живо і переконливо, ТІЄЮ Ж МОВОЮ що й чернетка. "
                "Збережи всі факти, цифри, ціни й домовленості з чернетки — нічого не додавай і не вигадуй. "
                "Зроби текст людяним і таким, що наближає клієнта до наступного кроку.")
        # style (стабільний, ~2285 tokens) виносимо в system з cache=True (5-min TTL).
        # task + dialog + draft залишаються user-prompt (variable — не кешується).
        prompt = (
            task + "\n\n"
            "Переписка з клієнтом (для тону, мови та контексту):\n" + (dialog or "(переписки ще немає)") + "\n\n"
            "ЧЕРНЕТКА менеджера:\n" + draft + "\n\n"
            'Поверни СТРОГО JSON без пояснень: {"text": "готове повідомлення клієнту тією потрібною мовою"}')
        from apps.crm.ai import claude_json
        try:
            r = claude_json(prompt, model="claude-sonnet-4-6", max_tokens=1000,
                            source="Помічник у чаті",
                            system=style, cache=True)
            txt = (r.get("text") or r.get("suggestion") or "").strip()
            return Response({"text": txt})
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
        if request.data.get("internal"):
            # ВНУТРІШНЯ нотатка з файлом: зберігаємо і показуємо в CRM, клієнту НЕ надсилаємо
            from .models import SharedLink
            import secrets, mimetypes
            content = base64.b64decode(b64.split(",")[-1])
            tok = secrets.token_urlsafe(16)
            ct = mimetypes.guess_type(filename)[0] or ("image/jpeg" if kind in ("photo", "image") else "application/octet-stream")
            SharedLink.objects.create(token=tok, filename=filename[:255], content_type=ct, data=content)
            url = request.build_absolute_uri("/api/f/%s/" % tok)
            u = request.user
            note = Message.objects.create(conversation=conv, direction="out", internal=True, text="",
                                          attachments=[{"type": kind, "url": url, "name": filename}],
                                          sender=u, sender_name=(u.get_full_name() or u.username))
            return Response(MessageSerializer(note).data, status=status.HTTP_201_CREATED)
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

    def get(self, request, token, name=None):
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
    """Чиї вхідні ДЗВЕНЯТЬ: закріплений чат — тільки відповідальному та доданим учасникам;
    незакріплений (нічий) — лише тим, у кого право «Сповіщення про нові незакріплені чати»."""
    from django.db.models import Q as _Q
    q = _Q(conversation__assigned_to=u) | _Q(conversation__participants=u)
    if u.is_superuser or u.has_perm_code("inbox.notify.unassigned"):
        q = q | _Q(conversation__assigned_to__isnull=True)
    return q


def _conv_vis(u):
    from django.db.models import Q as _Q
    q = _Q(assigned_to=u) | _Q(participants=u)
    if u.is_superuser or u.has_perm_code("inbox.notify.unassigned"):
        q = q | _Q(assigned_to__isnull=True)
    return q


def _cname(conv, fallback=""):
    c = conv.contact
    nm = ((c.first_name + " " + c.last_name).strip() if c else "")
    return nm or conv.title or fallback or "Клієнт"


class DealBadgesView(APIView):
    """Бейджи чату для канбану сделок: {deal_id: {unread, ai}}. ?ids=1,2,3 (до 500)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        ids = [int(x) for x in (request.query_params.get("ids") or "").split(",") if x.strip().isdigit()][:500]
        from apps.crm.models import Deal
        deals = list(Deal.objects.filter(id__in=ids).values("id", "contact_id"))
        contact_ids = [d["contact_id"] for d in deals if d["contact_id"]]
        conv_by_contact = {}
        for c in Conversation.objects.filter(contact_id__in=contact_ids, status="open").order_by("last_message_at"):
            conv_by_contact[c.contact_id] = c
        out = {}
        for d in deals:
            c = conv_by_contact.get(d["contact_id"])
            if not c:
                continue
            m = c.messages.only("direction", "sender_id", "internal").last()
            ai = bool(m and m.direction == "out" and m.sender_id is None and not m.internal)
            out[d["id"]] = {"unread": c.unread, "ai": ai, "conv": c.id}
        return Response(out)


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
        from .models import TeamMessage as _TM
        tqs = _TM.objects.filter(recipient=u)
        team_last = tqs.aggregate(m=Max("id"))["m"] or 0
        team_unread = tqs.filter(read=False).count()
        team_latest = None
        _tmsg = tqs.select_related("sender").order_by("-id").first()
        if _tmsg:
            team_latest = {"name": (_tmsg.sender.get_full_name() or _tmsg.sender.username), "preview": (_tmsg.text or "")[:90]}
        unread += team_unread
        # склад: нові (нічиї) задачі на відвантаження — для полоси і звуку в кабінеті складу
        wh_queue = wh_last = 0
        try:
            _dep = (u.department.name if u.department_id else "") or ""
            _rl = (u.role.name if u.role_id else "") or ""
            if "склад" in _dep.lower() or "комірник" in _rl.lower():
                from apps.warehouse.models import WarehouseJob
                _qw = WarehouseJob.objects.filter(status="queued", assignee__isnull=True)
                wh_queue = _qw.count()
                wh_last = _qw.aggregate(m=Max("id"))["m"] or 0
        except Exception:
            pass
        bc = _TM.objects.filter(recipient__isnull=True).order_by("-id").first()
        bc_last = bc.id if bc else 0
        bc_latest = ({"name": (bc.sender.get_full_name() or bc.sender.username), "preview": (bc.text or "")[:200]} if bc else None)
        return Response({"last_in": last, "latest": latest, "unread": unread,
                         "team_last": team_last, "team_unread": team_unread, "team_latest": team_latest,
                         "bc_last": bc_last, "bc_latest": bc_latest,
                         "wh_queue": wh_queue, "wh_last": wh_last})


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
        # загальний чат — завжди зверху
        bc = TeamMessage.objects.filter(recipient__isnull=True).order_by("-id").first()
        out.insert(0, {"id": 0, "full_name": "📢 Загальний чат", "dept": "усі співробітники",
                       "last": (bc.text[:60] if bc else ""), "last_at": (bc.created_at if bc else None),
                       "unread": 0, "broadcast": True,
                       "can_write": bool(me.is_superuser or me.has_perm_code("team.broadcast"))})
        return Response(out)


class TeamThreadView(APIView):
    """Переписка з конкретним співробітником. GET — повідомлення (помічаємо прочитаними). POST — відправити."""
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        from django.db.models import Q
        from .models import TeamMessage
        me = request.user
        if int(user_id) == 0:  # загальний чат
            qs = TeamMessage.objects.filter(recipient__isnull=True).select_related("sender")[:500]
        else:
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
        rec = None
        if int(user_id) == 0:  # загальний чат — лише з правом
            if not (me.is_superuser or me.has_perm_code("team.broadcast")):
                return Response({"detail": "Писати у загальний чат може лише той, кому видано право «Писати ВСІМ»"}, status=403)
        else:
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

class ChatPlaceWebhookView(APIView):
    """PUSH від ChatPlace: нове повідомлення клієнта (IG/TikTok) → одразу в CRM, БЕЗ опитування.
    ChatPlace-автоматизація (http_request) шле сюди {clientId, username, fullName, text, platform}."""
    authentication_classes = []
    permission_classes = [AllowAny]

    def _secret(self):
        import hashlib
        from django.conf import settings as _s
        return hashlib.sha256((_s.SECRET_KEY + "|chatplace-webhook").encode()).hexdigest()[:32]

    def post(self, request):
        if request.headers.get("X-CP-Secret") != self._secret():
            return Response({"detail": "bad secret"}, status=status.HTTP_403_FORBIDDEN)
        d = request.data or {}
        text = (d.get("text") or "").strip()
        username = (d.get("username") or "").strip().lstrip("@")
        client_id = str(d.get("clientId") or "").strip()
        full_name = (d.get("fullName") or "").strip()
        platform = (d.get("platform") or "instagram").strip().lower()
        if platform not in ("instagram", "tiktok"):
            platform = "instagram"
        # ChatPlace-автоматизація може прислати ще й посилання на фото/медіа клієнта
        photo_url = (d.get("photo_url") or d.get("image") or d.get("media") or d.get("attachment")
                     or d.get("file") or d.get("url") or "").strip()
        if photo_url and not photo_url.lower().startswith(("http://", "https://")):
            photo_url = ""
        if not (text or username or client_id or photo_url):
            return Response({"detail": "empty"}, status=status.HTTP_400_BAD_REQUEST)
        from apps.crm.models import Contact, Funnel
        chan_name = "ChatPlace · TikTok" if platform == "tiktok" else "ChatPlace · Instagram"
        ch, _ = Channel.objects.get_or_create(name=chan_name, defaults={"kind": platform, "config": {"chatplace": True}})
        # 1) контакт по username (щоб влучити в наявний діалог з реальним chatId для відповіді)
        contact = None
        if username:
            # ТОЧНИЙ матч (icontains зливав різних клієнтів: «ira» ловив «kira_deco»)
            un = username.lstrip("@").lower()
            contact = (Contact.objects.filter(social_link__iendswith="/" + un).first()
                       or Contact.objects.filter(nickname__iexact="@" + un).first()
                       or Contact.objects.filter(nickname__iexact=un).first())
        # 2) діалог
        _bothcp = list(Channel.objects.filter(name__in=("ChatPlace · Instagram", "ChatPlace · TikTok")))
        conv = None
        if contact:
            conv = Conversation.objects.filter(channel__in=_bothcp, contact=contact).order_by("-created_at").first()
        if conv is None and client_id:
            conv = Conversation.objects.filter(channel__in=_bothcp, external_chat_id=client_id).order_by("-created_at").first()
        created = conv is None
        contact_created = False
        if created:
            link = ""
            if username:
                link = ("https://www.tiktok.com/@" + username) if platform == "tiktok" else ("https://instagram.com/" + username)
            if contact is None:
                contact = Contact.objects.create(first_name=(username or full_name or "Клієнт")[:120],
                                                 nickname=(("@" + username) if username else full_name)[:150],
                                                 channels=[platform], social_link=link, comment="ChatPlace " + platform)
                contact_created = True
            conv = Conversation.objects.create(channel=ch, external_chat_id=(client_id or username or ""),
                                               title=(("@" + username) if username else (full_name or "Клієнт"))[:160], contact=contact)
        if conv.status == "closed":
            conv.status = "open"; conv.assigned_to = None; conv.save(update_fields=["status", "assigned_to"])
        # 3) дедуп (ChatPlace може ретраїти http_request) + повідомлення
        from django.utils import timezone as _tz
        from datetime import timedelta as _td
        _win = _tz.now() - _td(seconds=90)
        if photo_url and Message.objects.filter(conversation=conv, direction="in",
                                                created_at__gte=_win,
                                                attachments__contains=[{"url": photo_url}]).exists():
            return Response({"ok": True, "dup": True})
        if text and not photo_url and Message.objects.filter(conversation=conv, direction="in", text=text[:5000],
                                            created_at__gte=_win).exists():
            return Response({"ok": True, "dup": True})
        atts = []
        if photo_url:
            low = photo_url.lower()
            if any(e in low for e in (".mp4", ".mov", ".webm")):
                kind = "video"
            elif any(e in low for e in (".mp3", ".ogg", ".m4a", ".wav")):
                kind = "voice"
            else:
                kind = "photo"
            atts = [{"type": kind, "url": photo_url, "name": ("фото" if kind == "photo" else kind)}]
        msg = Message.objects.create(conversation=conv, direction="in",
                                     text=(text or ("📷 Фото від клієнта" if photo_url else ""))[:5000],
                                     attachments=atts, external_id="")
        conv.last_message_at = msg.created_at
        conv.unread = (conv.unread or 0) + 1
        conv.save(update_fields=["last_message_at", "unread"])
        # 4) бейдж непрочитаного + авто-лід
        if contact:
            try:
                from apps.crm.automation import on_incoming
                on_incoming(contact, text)
            except Exception:
                pass
            if created and contact_created:
                try:
                    f = Funnel.objects.filter(name="Лиды").first() or Funnel.objects.order_by("id").first()
                    if f:
                        from apps.crm.lead_routing import make_lead_for_contact
                        make_lead_for_contact(contact, f, platform)
                except Exception:
                    pass
        return Response({"ok": True, "conv": conv.id, "created": created})


class SoundLibraryView(APIView):
    """Спільна бібліотека звуків: GET — список (усім), POST — завантажити (право settings.sounds.upload)."""
    permission_classes = [IsAuthenticated]

    def _can_upload(self, u):
        return bool(u.is_superuser or (hasattr(u, "has_perm_code") and (u.has_perm_code("settings.sounds.upload") or u.has_perm_code("roles.manage"))))

    def get(self, request):
        from .models import SoundLibrary
        items = [{"id": s.id, "name": s.name, "url": "/api/sounds/%d/file/" % s.id,
                  "by": ((s.uploaded_by.get_full_name() or s.uploaded_by.username) if s.uploaded_by_id else ""),
                  "size": s.size} for s in SoundLibrary.objects.all()]
        return Response({"items": items, "can_upload": self._can_upload(request.user)})

    def post(self, request):
        import base64, hashlib
        from .models import SoundLibrary
        u = request.user
        if not self._can_upload(u):
            return Response({"detail": "Немає права завантажувати звуки"}, status=403)
        name = (request.data.get("name") or "Звук").strip()[:160]
        data_url = request.data.get("data") or ""
        mime = "audio/mpeg"
        b64 = data_url
        if data_url.startswith("data:"):
            head, _, b64 = data_url.partition(",")
            try:
                mime = head[5:head.index(";")] or mime
            except Exception:
                pass
        try:
            raw = base64.b64decode(b64)
        except Exception:
            return Response({"detail": "Пошкоджений файл"}, status=400)
        if not raw or len(raw) > 3 * 1024 * 1024:
            return Response({"detail": "Файл порожній або завеликий (макс 3 МБ)"}, status=400)
        sha = hashlib.sha256(raw).hexdigest()
        exist = SoundLibrary.objects.filter(sha256=sha).first()
        if exist:
            return Response({"id": exist.id, "name": exist.name, "url": "/api/sounds/%d/file/" % exist.id, "dedup": True})
        s = SoundLibrary.objects.create(name=name, sha256=sha, mime=mime, data=raw, size=len(raw), uploaded_by=u)
        return Response({"id": s.id, "name": s.name, "url": "/api/sounds/%d/file/" % s.id}, status=201)


class SoundFileView(APIView):
    """Віддає байти звуку. Публічно (звук не секрет) — грається через Audio(url)."""
    permission_classes = [AllowAny]

    def get(self, request, pk):
        from django.http import HttpResponse
        from .models import SoundLibrary
        s = SoundLibrary.objects.filter(pk=pk).first()
        if not s:
            return Response(status=404)
        resp = HttpResponse(bytes(s.data), content_type=(s.mime or "audio/mpeg"))
        resp["Cache-Control"] = "public, max-age=86400"
        return resp


class SoundDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        from .models import SoundLibrary
        u = request.user
        if not (u.is_superuser or (hasattr(u, "has_perm_code") and (u.has_perm_code("settings.sounds.upload") or u.has_perm_code("roles.manage")))):
            return Response({"detail": "Немає права"}, status=403)
        SoundLibrary.objects.filter(pk=pk).delete()
        return Response(status=204)
