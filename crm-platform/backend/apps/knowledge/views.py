"""API єдиної бази знань (AI ЦЕНТР → «База знань ✓»).

Права:
  читати            — власник, knowledge.view / knowledge.edit / knowledge.approve або settings.agent (хто бачить AI ЦЕНТР);
  додавати/правити ЧЕРНЕТКИ, пропонувати правку — knowledge.edit (або knowledge.approve);
  затверджувати, змінювати затверджене, архів — knowledge.approve (за замовчуванням — лише власник);
  вмикати рецензента (витрачає гроші на ШІ) — лише власник (superuser).
"""
from django.db import connection, transaction
from django.db.models import Count, F, Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import KnowledgeItem, KnowledgeSettings, log_version
from .serializers import KnowledgeItemSerializer, VersionSerializer

REVIEWER_MODELS = ["claude-haiku-4-5", "claude-sonnet-4-6"]
ORDERINGS = {"-popularity": ["-popularity", "id"], "-updated_at": ["-updated_at"], "topic": ["topic", "priority", "id"],
             "id": ["id"], "-id": ["-id"]}

# Хто що читає і хто кого перевіряє (показується у вкладці «Команда агентів»)
ROLES = [
    {"agent": "yulia_ig", "name": "Юля Instagram (ChatPlace)", "does": "Відповідає клієнтам у Direct, веде до тест-набору й оплати",
     "reads": "Копію затверджених «Питання-відповідь/Факт/Шаблон» з позначкою «Юля IG» — публікує Олег кнопкою «Опублікувати в Юлю»",
     "checked_by": "Контролер (за запуском Олега) · Олег при кожній публікації · «Тестовий чат»"},
    {"agent": "yulia_tiktok", "name": "Юля TikTok (ChatPlace)", "does": "Те саме в TikTok",
     "reads": "Той самий набір, що IG (позначка «Юля TikTok»)", "checked_by": "Контролер · Олег при публікації"},
    {"agent": "yulia_web", "name": "Сайт — веб-чат (ШІ CRM)", "does": "Відповідає відвідувачам сайту; замовлення, оплата, сумнів → менеджер. ВИМКНЕНО, поки Олег не ввімкне",
     "reads": "Лише затверджене з позначкою «Сайт» + ціни каталогу CRM; знижки — лише за затвердженим правилом",
     "checked_by": "Запобіжник цифр і знижок (кодом) · «Тестовий чат» · менеджер бачить нотатку з причиною"},
    {"agent": "funnel_agent", "name": "Агент воронки CRM", "does": "Анкета, стадія (максимум «Розрахунок здійснено»), тест-набір + LiqPay",
     "reads": "Глобальні правила + затверджене з позначкою «Агент воронки» + каталог тест-наборів",
     "checked_by": "Рецензент · Олег (пороги, вимикач)"},
    {"agent": "rop_hint", "name": "AI-РОП підказка", "does": "За кнопкою: діагноз паузи клієнта + готова фраза менеджеру",
     "reads": "Стиль РОПа + затверджене «AI-РОП» + ціни каталогу для матеріалів із розмови; теми без затвердженого — рішення Олега 14.09",
     "checked_by": "Менеджер вирішує, чи відправляти · Рецензент"},
    {"agent": "compose_assist", "name": "Помічник ✨", "does": "Покращує/перекладає чернетку менеджера, нічого не надсилає",
     "reads": "Затверджене «Помічник ✨» по темах; тема без затвердженого — вбудований текст",
     "checked_by": "Менеджер · Рецензент"},
    {"agent": "analyst", "name": "Контролер (лише за запуском)", "does": "Коли Олег натисне «Запустити перевірку»: закриті чати за вчора / 7 днів / N останніх — суперечності, пропущені кроки, питання без відповіді. Розкладу немає",
     "reads": "Затверджене «Аналітик» + рішення Олега + вибрані закриті чати",
     "checked_by": "Олег: кожна пропозиція — чернетка з посиланням на діалог, затверджує або видаляє він"},
]


def _codes(u, *codes):
    return bool(u and u.is_authenticated and (u.is_superuser or any(u.has_perm_code(c) for c in codes)))


def can_view(u):
    return _codes(u, "knowledge.view", "knowledge.edit", "knowledge.approve", "settings.agent")


def can_edit(u):
    return _codes(u, "knowledge.edit", "knowledge.approve")


def can_approve(u):
    return _codes(u, "knowledge.approve")


def approve_item(item, user, note=""):
    """Чернетка → Затверджено. Якщо це правка до затвердженого — старий запис іде в архів."""
    with transaction.atomic():
        item.status = "approved"
        item.approved_by = user
        item.approved_at = timezone.now()
        item.approval_note = (note or "")[:200]
        item.version += 1
        item.updated_by = user
        old = item.replaces if item.replaces_id else None
        if old and old.status == "approved":
            item.external_ids = dict(old.external_ids or {}, **(item.external_ids or {}))
            item.popularity = max(item.popularity, old.popularity)
        item.save()
        log_version(item, "approve", user, note)
        if old and old.status == "approved":
            old.status = "archived"
            old.version += 1
            old.updated_by = user
            old.save()
            log_version(old, "archive", user, "замінено записом #%d" % item.id)
    return item


class KnowledgeItemViewSet(viewsets.ModelViewSet):
    serializer_class = KnowledgeItemSerializer
    permission_classes = [IsAuthenticated]
    queryset = (KnowledgeItem.objects.select_related("approved_by", "created_by", "updated_by", "precheck")
                .prefetch_related("products"))

    def check_permissions(self, request):
        super().check_permissions(request)
        if not can_view(request.user):
            self.permission_denied(request, message="Немає доступу до бази знань")

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        for f in ("kind", "topic", "status", "source"):
            v = (p.get(f) or "").strip()
            if v:
                qs = qs.filter(**{f: v})
        a = (p.get("audience") or "").strip()
        if a:
            qs = qs.filter(audience__contains=[a]) if connection.vendor == "postgresql" else qs.filter(audience__icontains='"%s"' % a)
        if p.get("flagged") in ("1", "true"):
            qs = qs.filter(internal_note__contains="⚠️")
        if p.get("replaces"):
            qs = qs.filter(replaces_id=p.get("replaces"))
        lb = (p.get("label") or "").strip()  # мітка попередньої перевірки (ai-kb2)
        if lb == "none":
            qs = qs.filter(precheck__isnull=True)
        elif lb == "stale":
            qs = qs.filter(precheck__isnull=False).exclude(precheck__item_version=F("version"))
        elif lb:
            qs = qs.filter(precheck__label=lb, precheck__item_version=F("version"))
        q = (p.get("search") or "").strip()
        if q:
            cond = Q(title__icontains=q) | Q(text__icontains=q) | Q(internal_note__icontains=q)
            if q.isdigit():
                cond |= Q(id=int(q))
            qs = qs.filter(cond)
        return qs.order_by(*ORDERINGS.get(p.get("ordering") or "-popularity", ORDERINGS["-popularity"]))

    def perform_create(self, serializer):
        u = self.request.user
        if not can_edit(u):
            raise PermissionDenied("Додавати знання може співробітник із правом «База знань: додавати й правити чернетки»")
        item = serializer.save(status="draft", source="manual", created_by=u, updated_by=u, version=1)
        log_version(item, "create", u, str(self.request.data.get("note") or ""))

    def perform_update(self, serializer):
        u = self.request.user
        item = serializer.instance
        if item.status in ("approved", "archived") and not can_approve(u):
            raise PermissionDenied("Затверджений запис змінює лише власник. Натисніть «Запропонувати правку».")
        if not can_edit(u):
            raise PermissionDenied("Немає права правити базу знань")
        with transaction.atomic():
            obj = serializer.save(updated_by=u, version=item.version + 1)
            if obj.status == "approved":
                obj.approved_by, obj.approved_at = u, timezone.now()
                obj.approval_note = "Змінено власником"
                obj.save(update_fields=["approved_by", "approved_at", "approval_note"])
            log_version(obj, "edit", u, str(self.request.data.get("note") or ""))

    def perform_destroy(self, instance):
        if not can_edit(self.request.user):
            raise PermissionDenied("Немає права правити базу знань")
        if instance.status != "draft":
            raise PermissionDenied("Затверджене не видаляється — лише «В архів» (історія зберігається)")
        instance.delete()

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        if not can_approve(request.user):
            return Response({"detail": "Затверджує лише власник (право «База знань: затверджувати»)"}, status=403)
        item = self.get_object()
        if item.status != "draft":
            return Response({"detail": "Затвердити можна лише чернетку"}, status=400)
        approve_item(item, request.user, str(request.data.get("note") or ""))
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        if not can_approve(request.user):
            return Response({"detail": "В архів переносить лише власник"}, status=403)
        item = self.get_object()
        if item.status == "archived":
            return Response({"detail": "Уже в архіві"}, status=400)
        item.status, item.updated_by = "archived", request.user
        item.version += 1
        item.save()
        log_version(item, "archive", request.user, str(request.data.get("note") or ""))
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        if not can_approve(request.user):
            return Response({"detail": "Повертає з архіву лише власник"}, status=403)
        item = self.get_object()
        if item.status != "archived":
            return Response({"detail": "Повернути можна лише запис з архіву"}, status=400)
        item.status, item.updated_by = "draft", request.user
        item.version += 1
        item.save()
        log_version(item, "restore", request.user, "")
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=["post"])
    def propose(self, request, pk=None):
        """Правка до затвердженого: створює чернетку-заміну. Після затвердження старий запис іде в архів."""
        if not can_edit(request.user):
            return Response({"detail": "Немає права пропонувати правки"}, status=403)
        src = self.get_object()
        if src.status != "approved":
            return Response({"detail": "Правку пропонують до затвердженого запису; чернетку можна правити напряму"}, status=400)
        data = {f: request.data.get(f, getattr(src, f)) for f in ("kind", "topic", "audience", "title", "text", "internal_note", "priority")}
        data["products"] = request.data.get("products", list(src.products.values_list("id", flat=True)))
        ser = self.get_serializer(data=data)
        ser.is_valid(raise_exception=True)
        u = request.user
        new = ser.save(status="draft", source="manual", source_ref="proposal:%d" % src.id, replaces=src,
                       created_by=u, updated_by=u, version=1, popularity=src.popularity)
        log_version(new, "propose", u, str(request.data.get("note") or "правка до #%d" % src.id))
        return Response(self.get_serializer(new).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        item = self.get_object()
        return Response(VersionSerializer(item.versions.select_related("changed_by")[:100], many=True).data)

    @action(detail=False, methods=["post"])
    def bulk(self, request):
        """Затвердити / в архів кілька записів (до 200) — лише власник."""
        if not can_approve(request.user):
            return Response({"detail": "Лише власник"}, status=403)
        ids = [int(i) for i in (request.data.get("ids") or []) if str(i).isdigit()][:200]
        act = request.data.get("action")
        if act not in ("approve", "archive") or not ids:
            return Response({"detail": "Потрібні ids і action: approve | archive"}, status=400)
        done = 0
        for item in KnowledgeItem.objects.filter(id__in=ids):
            if act == "approve" and item.status == "draft":
                approve_item(item, request.user, "масове затвердження")
                done += 1
            elif act == "archive" and item.status != "archived":
                item.status, item.updated_by = "archived", request.user
                item.version += 1
                item.save()
                log_version(item, "archive", request.user, "масово")
                done += 1
        return Response({"done": done})


def _choices(pairs):
    return [{"value": v, "label": l} for v, l in pairs]


def settings_dict(cfg):
    from .reader import approved_for
    from .views_v2 import webchat_estimate
    return {"reviewer_enabled": cfg.reviewer_enabled, "reviewer_model": cfg.reviewer_model,
            "reviewer_sample": cfg.reviewer_sample, "reviewer_models": REVIEWER_MODELS,
            "controller_scheduled": False, "webchat_ai_enabled": cfg.webchat_ai_enabled,
            "webchat_model": cfg.webchat_model, "webchat_items": len(approved_for("yulia_web")),
            "webchat_estimate": webchat_estimate(),
            # 17.09.2026 (Олег): ШІ у каналах — вмикач по кожному каналу і пауза після менеджера, усе тут
            "ai_silence_hours": cfg.ai_silence_hours, "ai_max_per_day": cfg.ai_max_per_day,
            "channels": channels_ai()}


def channels_ai():
    """Канали CRM: чи відповідає в них ШІ, для яких чатів і скільки там клієнтів за 30 днів."""
    import datetime
    from django.db.models import Count, Q
    from django.utils import timezone as _tz
    from apps.inbox.models import Channel
    since = _tz.now() - datetime.timedelta(days=30)
    rows = (Channel.objects.filter(is_active=True)
            .annotate(dialogs=Count("conversations", filter=Q(conversations__last_message_at__gte=since), distinct=True))
            .order_by("kind", "name"))
    out = []
    for ch in rows:
        cfg = ch.config or {}
        out.append({"id": ch.id, "name": ch.name, "kind": ch.kind, "dialogs30": ch.dialogs,
                    "ai_reply": bool(cfg.get("ai_reply")),
                    "only_chats": [str(x) for x in (cfg.get("ai_reply_only_chats") or [])],
                    "chatplace": bool(cfg.get("chatplace"))})
    return out


class MetaView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        u = request.user
        if not can_view(u):
            return Response({"detail": "Немає доступу"}, status=403)
        counts = dict(KnowledgeItem.objects.values_list("status").annotate(n=Count("id")).values_list("status", "n"))
        return Response({
            "kinds": _choices(KnowledgeItem.KINDS), "topics": _choices(KnowledgeItem.TOPICS),
            "audiences": _choices(KnowledgeItem.AGENTS), "statuses": _choices(KnowledgeItem.STATUS),
            "sources": _choices(KnowledgeItem.SOURCES), "counts": counts,
            "flagged_drafts": KnowledgeItem.objects.filter(status="draft", internal_note__contains="⚠️").count(),
            "reviewer_drafts": KnowledgeItem.objects.filter(status="draft", source="reviewer").count(),
            "can_view": True, "can_edit": can_edit(u), "can_approve": can_approve(u), "is_owner": bool(u.is_superuser),
            "settings": settings_dict(KnowledgeSettings.get()), "roles": ROLES,
        })


def agent_view(agent, query=None):
    """Точно той блок знань, який агент отримає зараз."""
    from .reader import context_for
    if agent == "compose_assist":
        from .fallbacks import compose_extra, compose_style
        return compose_style() + compose_extra(query)
    if agent == "rop_hint":
        from apps.crm.coach_prompt import knowledge_block
        return knowledge_block(query)
    if agent == "funnel_agent":
        return context_for("funnel_agent", limit=15, max_chars=3000, with_prices=False)
    if agent in ("yulia_ig", "yulia_tiktok"):
        from .publisher import desired
        rows = desired("ig" if agent == "yulia_ig" else "tt")
        head = "До ChatPlace піде %d записів (після публікації Олегом):" % len(rows)
        return head + "\n\n" + "\n\n".join("П: %s\nВ: %s" % (q, a) for _i, q, a in rows[:80])
    if agent == "yulia_web":
        return context_for("yulia_web", query, limit=15, max_chars=6000)
    if agent == "analyst":
        from .reviewer import knowledge_for_review
        return knowledge_for_review(query)
    return ""


class PreviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not can_view(request.user):
            return Response({"detail": "Немає доступу"}, status=403)
        agent = (request.query_params.get("agent") or "rop_hint").strip()
        if agent not in [c for c, _ in KnowledgeItem.AGENTS]:
            return Response({"detail": "Невідомий агент"}, status=400)
        q = (request.query_params.get("q") or "").strip()[:2000] or None
        from .reader import select
        text = agent_view(agent, q)
        return Response({"agent": agent, "query": q or "", "text": text, "chars": len(text or ""),
                         "items": [i.id for i in select(agent, q, 20)]})


class SettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not can_view(request.user):
            return Response({"detail": "Немає доступу"}, status=403)
        return Response(settings_dict(KnowledgeSettings.get()))

    def patch(self, request):
        if not request.user.is_superuser:
            return Response({"detail": "Вмикати ШІ, що витрачає гроші, може лише власник"}, status=403)
        cfg = KnowledgeSettings.get()
        d = request.data
        if "reviewer_enabled" in d:
            cfg.reviewer_enabled = bool(d.get("reviewer_enabled"))
        if "reviewer_model" in d:
            if d.get("reviewer_model") not in REVIEWER_MODELS:
                return Response({"detail": "Модель: " + ", ".join(REVIEWER_MODELS)}, status=400)
            cfg.reviewer_model = d["reviewer_model"]
        if "reviewer_sample" in d:
            try:
                cfg.reviewer_sample = max(1, min(100, int(d.get("reviewer_sample"))))
            except (TypeError, ValueError):
                return Response({"detail": "Кількість чатів — число 1–100"}, status=400)
        if "webchat_ai_enabled" in d:  # ai-kb2: веб-чат відповідає з бази знань (лише власник, див. вище)
            cfg.webchat_ai_enabled = bool(d.get("webchat_ai_enabled"))
        if "webchat_model" in d:
            if d.get("webchat_model") not in REVIEWER_MODELS:
                return Response({"detail": "Модель: " + ", ".join(REVIEWER_MODELS)}, status=400)
            cfg.webchat_model = d["webchat_model"]
        if "ai_silence_hours" in d:      # 17.09.2026: пауза ШІ після повідомлення менеджера
            try:
                cfg.ai_silence_hours = max(0, min(168, int(d.get("ai_silence_hours"))))
            except (TypeError, ValueError):
                return Response({"detail": "Години — число 0–168"}, status=400)
        if "ai_max_per_day" in d:
            try:
                cfg.ai_max_per_day = max(1, min(100, int(d.get("ai_max_per_day"))))
            except (TypeError, ValueError):
                return Response({"detail": "Відповідей на добу — число 1–100"}, status=400)
        if "channel" in d:               # вмикач ШІ у конкретному каналі (+ перелік чатів для перевірки)
            from apps.inbox.models import Channel
            ch = Channel.objects.filter(id=d.get("channel")).first()
            if not ch:
                return Response({"detail": "Канал не знайдено"}, status=404)
            cfg_ch = dict(ch.config or {})
            if "ai_reply" in d:
                cfg_ch["ai_reply"] = bool(d.get("ai_reply"))
            if "only_chats" in d:
                raw = d.get("only_chats") or []
                if isinstance(raw, str):
                    raw = [x.strip() for x in raw.replace(",", " ").split() if x.strip()]
                cfg_ch["ai_reply_only_chats"] = [str(x)[:128] for x in raw][:50]
            ch.config = cfg_ch
            ch.save(update_fields=["config"])
        cfg.updated_by = request.user
        cfg.save()
        return Response(settings_dict(cfg))
