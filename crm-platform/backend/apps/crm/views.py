from decimal import Decimal
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Company, Contact, Funnel, Stage, Lead, Deal, DealItem, Payment
from .serializers import (
    CompanySerializer, ContactSerializer, ContactDetailSerializer, FunnelSerializer, StageSerializer,
    LeadSerializer, DealSerializer, DealDetailSerializer, PaymentSerializer,
)


class ScopedByRoleMixin:
    """Фильтрация по правам: видимость (свои/все) и доступ к воронкам.

    Подклассы задают `view_all_method` ('can_see_all_leads' / 'can_see_all_deals').
    """
    view_all_method = None

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_superuser:
            return qs

        # 1) ограничение по воронкам роли
        allowed = user.allowed_funnel_ids()
        if allowed is not None:
            qs = qs.filter(funnel_id__in=allowed)

        # 2) свои vs все
        if self.view_all_method and not getattr(user, self.view_all_method)():
            from django.db.models import Q as _Q
            _va = user.viewable_all_stage_ids()
            if _va:
                qs = qs.filter(_Q(owner=user) | _Q(stage_id__in=list(_va)))
            else:
                qs = qs.filter(owner=user)
        return qs

    def perform_create(self, serializer):
        # новый лид/сделка по умолчанию закрепляется за создателем
        serializer.save(owner=serializer.validated_data.get("owner") or self.request.user)


class ContactViewSet(viewsets.ModelViewSet):
    queryset = Contact.objects.all()
    serializer_class = ContactSerializer
    search_fields = ["first_name", "last_name", "phone", "email"]
    filterset_fields = ["loyalty_tag", "source", "owner"]
    ordering_fields = ["created_at", "first_name", "last_touch_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.can_see_all_clients():
            from django.db.models import Q as _Q
            qs = qs.filter(_Q(owner=user) | _Q(leads__owner=user) | _Q(deals__owner=user)).distinct()
        li = self.request.query_params.get("loyalty_in")
        if li:
            qs = qs.filter(loyalty_tag__in=[x for x in li.split(",") if x])
        if self.request.query_params.get("has_phone") == "1":
            qs = qs.exclude(phone="")
        return qs

    def get_serializer_class(self):
        return ContactDetailSerializer if self.action == "retrieve" else ContactSerializer


class CompanyViewSet(viewsets.ModelViewSet):
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    search_fields = ["name", "edrpou"]

    def _guard_write(self):
        if not self.request.user.can_see_all_deals():
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Змінювати компанії може лише керівник")

    def perform_create(self, serializer):
        self._guard_write(); serializer.save()

    def perform_update(self, serializer):
        self._guard_write(); serializer.save()

    def perform_destroy(self, instance):
        self._guard_write(); instance.delete()


class FunnelViewSet(viewsets.ModelViewSet):
    serializer_class = FunnelSerializer
    queryset = Funnel.objects.prefetch_related("stages").all()

    def get_queryset(self):
        qs = super().get_queryset()
        allowed = self.request.user.allowed_funnel_ids()
        return qs if allowed is None else qs.filter(id__in=allowed)

    @action(detail=True, methods=["post"])
    def save_stages(self, request, pk=None):
        """Зберегти весь набір стадій воронки (перейменування/колір/порядок/+/видалення)."""
        funnel = self.get_object()
        blocked = _save_funnel_stages(funnel, request.data.get("stages", []))
        funnel.refresh_from_db()
        data = FunnelSerializer(funnel).data
        data["blocked"] = blocked
        return Response(data)


class StageViewSet(viewsets.ModelViewSet):
    queryset = Stage.objects.all()
    serializer_class = StageSerializer
    filterset_fields = ["funnel"]


def _save_funnel_stages(funnel, items):
    """Upsert стадій воронки одним запитом + безпечне видалення.
    items: [{id?|null, name, color, order?, is_won?, is_lost?}] у потрібному порядку.
    Стадію з картками (сделки/ліди) не видаляємо — повертаємо її назву у blocked."""
    keep_ids = set()
    for i, it in enumerate(items):
        fields = dict(
            name=(it.get("name") or "").strip() or "Стадія",
            color=it.get("color") or "#3b82f6",
            order=i,
            is_won=bool(it.get("is_won")),
            is_lost=bool(it.get("is_lost")),
        )
        if "auto_only" in it:
            fields["auto_only"] = bool(it.get("auto_only"))
        sid = it.get("id")
        if sid:
            Stage.objects.filter(id=sid, funnel=funnel).update(**fields)
            keep_ids.add(int(sid))
        else:
            st = Stage.objects.create(funnel=funnel, **fields)
            keep_ids.add(st.id)
    blocked = []
    for st in funnel.stages.exclude(id__in=keep_ids):
        if Deal.objects.filter(stage=st).exists() or Lead.objects.filter(stage=st).exists():
            blocked.append(st.name)
        else:
            st.delete()
    return blocked


class ActivityLogMixin:
    """Логує зміни стадії/відповідального + авто-призначення при взятті в роботу."""
    log_kind = "lead"

    def perform_create(self, serializer):
        obj = serializer.save()
        from .models import log_activity
        u = getattr(self.request, "user", None)
        log_activity(self.log_kind, obj.id, "Створено", getattr(obj, "title", ""), u)

    def update(self, request, *args, **kwargs):
        from .models import log_activity
        obj = self.get_object()
        old_owner, old_stage = obj.owner_id, obj.stage_id
        old_stage_name = obj.stage.name if obj.stage_id else ""
        old_funnel = obj.funnel_id
        old_funnel_name = obj.funnel.name if obj.funnel_id else ""
        _raw = request.data.get("stage")
        if _raw not in (None, ""):
            try:
                _ns = int(_raw)
            except (TypeError, ValueError):
                _ns = None
            if _ns and _ns != (old_stage or 0) and _ns in request.user.locked_move_stage_ids():
                from rest_framework.response import Response as _R
                from rest_framework import status as _stx
                return _R({"detail": "Цей статус змінюється автоматично — ручне переміщення заборонено."}, status=_stx.HTTP_403_FORBIDDEN)
        resp = super().update(request, *args, **kwargs)
        obj.refresh_from_db()
        actor = request.user.get_full_name() or request.user.username
        if obj.funnel_id != old_funnel:
            log_activity(self.log_kind, obj.id, "Зміна воронки", f"{old_funnel_name} → {obj.funnel.name}", request.user, actor)
        auto = False
        if obj.stage_id != old_stage:
            log_activity(self.log_kind, obj.id, "Зміна стадії", f"{old_stage_name} → {obj.stage.name}", request.user, actor)
            if not obj.owner_id:  # взяв у роботу і ще немає відповідального → призначити того, хто взяв
                obj.owner_id = request.user.id
                obj.save(update_fields=["owner"])
                log_activity(self.log_kind, obj.id, "Призначено відповідального", f"Взяв у роботу: {actor}", request.user, actor)
                auto = True
        if not auto and obj.owner_id != old_owner:
            new_owner = obj.owner.get_full_name() if obj.owner else "—"
            log_activity(self.log_kind, obj.id, "Зміна відповідального", f"→ {new_owner}", request.user, actor)
        return resp


class LeadViewSet(ActivityLogMixin, ScopedByRoleMixin, viewsets.ModelViewSet):
    log_kind = "lead"
    queryset = Lead.objects.select_related("owner", "contact", "funnel", "stage")
    serializer_class = LeadSerializer
    view_all_method = "can_see_all_leads"

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        """Конвертувати лід у сделку (той самий контакт/owner)."""
        lead = self.get_object()
        funnel = Funnel.objects.filter(is_lead_funnel=False).order_by("order", "id").first()
        if not funnel:
            return Response({"detail": "Немає воронки продажів"}, status=status.HTTP_400_BAD_REQUEST)
        stage = funnel.stages.order_by("order").first()
        deal = Deal.objects.create(
            title=lead.title, contact=lead.contact, funnel=funnel, stage=stage,
            amount=lead.amount, source=lead.source, owner=lead.owner,
            qualification=lead.qualification, card_fields=lead.card_fields)
        from .models import log_activity
        actor = request.user.get_full_name() or request.user.username
        log_activity("lead", lead.id, "Конвертовано в сделку", f"Сделка #{deal.id}", request.user, actor)
        log_activity("deal", deal.id, "Створено зі сделки", f"З ліда #{lead.id}", request.user, actor)
        return Response({"deal_id": deal.id})

    @action(detail=True, methods=["post"])
    def convert_to(self, request, pk=None):
        """Конвертація ліда у сделку в конкретну воронку за вибором продукту (для AI-продавця).
        body: {"product": "test"|"main"} або {"funnel": <id>}. Тест→«Тестовий набір», основний→«Основний продукт»."""
        lead = self.get_object()
        prod = (request.data.get("product") or "").lower()
        fid = request.data.get("funnel")
        funnel = None
        if fid:
            funnel = Funnel.objects.filter(id=fid, is_lead_funnel=False).first()
        elif prod in ("test", "тест", "пробник", "набір", "зразок"):
            funnel = Funnel.objects.filter(is_lead_funnel=False, name__icontains="Тестовий набір").first()
        elif prod in ("main", "основной", "основний"):
            funnel = Funnel.objects.filter(is_lead_funnel=False, name__icontains="Основний продукт").first()
        if not funnel:
            funnel = Funnel.objects.filter(is_lead_funnel=False).order_by("order", "id").first()
        if not funnel:
            return Response({"detail": "Немає воронки продажів"}, status=status.HTTP_400_BAD_REQUEST)
        stage = funnel.stages.order_by("order").first()
        deal = Deal.objects.create(
            title=lead.title, contact=lead.contact, funnel=funnel, stage=stage,
            amount=lead.amount, source=lead.source, owner=lead.owner,
            qualification=lead.qualification, card_fields=lead.card_fields)
        from .models import log_activity
        actor = (request.user.get_full_name() or request.user.username) if request.user.is_authenticated else "AI"
        u = request.user if request.user.is_authenticated else None
        log_activity("lead", lead.id, "Конвертовано в сделку", "%s · сделка #%s" % (funnel.name, deal.id), u, actor)
        log_activity("deal", deal.id, "Створено з ліда", "Воронка %s, лід #%s" % (funnel.name, lead.id), u, actor)
        return Response({"deal_id": deal.id, "funnel": funnel.name})
    filterset_fields = ["funnel", "stage", "source", "is_seen", "owner", "contact"]
    search_fields = ["title", "contact__phone", "contact__first_name", "contact__last_name"]


class DealViewSet(ActivityLogMixin, ScopedByRoleMixin, viewsets.ModelViewSet):
    log_kind = "deal"
    queryset = Deal.objects.select_related("owner", "contact", "funnel", "stage")
    serializer_class = DealSerializer
    view_all_method = "can_see_all_deals"
    filterset_fields = ["funnel", "stage", "source", "owner", "contact"]
    search_fields = ["title", "contact__phone", "contact__first_name", "contact__last_name"]
    ordering_fields = ["amount", "created_at", "updated_at", "closed_at"]

    def get_serializer_class(self):
        # в карточке (retrieve) отдаём расширенные данные: товары, оплаты
        if self.action == "retrieve":
            return DealDetailSerializer
        return DealSerializer

    def _recalc_amount(self, deal):
        deal.amount = sum((i.total for i in deal.items.all()), Decimal("0"))
        deal.save(update_fields=["amount"])

    @action(detail=True, methods=["post"])
    def add_item(self, request, pk=None):
        deal = self.get_object()
        from apps.warehouse.models import Product
        product = Product.objects.get(pk=request.data["product"])
        qty = Decimal(str(request.data.get("quantity", 1)))
        price = Decimal(str(request.data.get("price", product.price)))
        DealItem.objects.create(deal=deal, product=product, quantity=qty, price=price,
                                discount_pct=Decimal(str(request.data.get("discount_pct", 0) or 0)), reserved=bool(request.data.get("reserved")))
        self._recalc_amount(deal)
        return Response(DealDetailSerializer(deal, context={"request": request}).data)

    @action(detail=True, methods=["get"])
    def loyalty(self, request, pk=None):
        """Реальна статистика лояльності клієнта (тільки виграні угоди)."""
        from django.db.models import Count, Sum, Min, Max
        deal = self.get_object()
        if not deal.contact_id:
            return Response({"purchases": 0, "total": 0, "first": None, "last": None, "tag": ""})
        won = Deal.objects.filter(contact=deal.contact, stage__is_won=True)
        a = won.aggregate(n=Count("id"), s=Sum("amount"), f=Min("closed_at"), l=Max("closed_at"))
        return Response({"purchases": a["n"] or 0, "total": float(a["s"] or 0),
                         "first": a["f"], "last": a["l"], "tag": deal.contact.loyalty_tag or ""})

    @action(detail=True, methods=["post"])
    def set_reserve(self, request, pk=None):
        """Перемкнути резерв позиції: {item, reserved}."""
        deal = self.get_object()
        DealItem.objects.filter(deal=deal, pk=request.data.get("item")).update(reserved=bool(request.data.get("reserved")))
        return Response(DealDetailSerializer(deal, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def remove_item(self, request, pk=None):
        deal = self.get_object()
        DealItem.objects.filter(deal=deal, pk=request.data.get("item")).delete()
        self._recalc_amount(deal)
        return Response(DealDetailSerializer(deal, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def update_item(self, request, pk=None):
        """Інлайн-редагування позиції: {item, price?, quantity?, discount_pct?}."""
        deal = self.get_object()
        it = DealItem.objects.filter(deal=deal, pk=request.data.get("item")).first()
        if not it:
            return Response({"detail": "Позицію не знайдено"}, status=status.HTTP_404_NOT_FOUND)
        for f in ("price", "quantity", "discount_pct"):
            val = request.data.get(f)
            if val not in (None, ""):
                try:
                    setattr(it, f, Decimal(str(val)))
                except Exception:
                    pass
        it.save()
        self._recalc_amount(deal)
        return Response(DealDetailSerializer(deal, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def accept_payment(self, request, pk=None):
        """Приём оплаты -> запись Payment + доходная проводка в финансы."""
        from apps.finance.services import record_income
        from apps.finance.models import Account
        deal = self.get_object()
        amount = Decimal(str(request.data.get("amount") or deal.amount))
        provider = request.data.get("provider", "cash")
        account = Account.objects.filter(pk=request.data.get("account")).first()
        pay = Payment.objects.create(deal=deal, provider=provider, amount=amount, is_paid=True)
        record_income(amount, deal=deal, account=account, payment=pay)
        return Response(DealDetailSerializer(deal, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def ai_suggest(self, request, pk=None):
        """AI-помічник: аналіз діалогу + готова відповідь клієнту (Claude)."""
        deal = self.get_object()
        msgs = []
        if deal.contact_id:
            from apps.inbox.models import Conversation
            conv = Conversation.objects.filter(contact=deal.contact).order_by("-last_message_at").first()
            if conv:
                msgs = list(conv.messages.order_by("id").values("direction", "text"))[-30:]
        dialog = "\n".join(
            f"{'Клієнт' if m['direction'] == 'in' else 'Менеджер'}: {m['text']}"
            for m in msgs if m.get("text"))
        prompt = (
            "Ти — досвідчений ввічливий продавець-консультант компанії Wallcov "
            "(декоративні покриття та фарби для стін). "
            f"Сделка: «{deal.title}», сума {deal.amount} грн. "
            f"Ось переписка з клієнтом:\n{dialog or '(переписки ще немає)'}\n\n"
            "Поверни СТРОГО JSON без пояснень: "
            '{"context": "1-2 речення: про що діалог і що хоче клієнт", '
            '"suggestion": "готова дружня відповідь клієнту тією ж мовою, що й він"}')
        from .ai import claude_json
        try:
            data = claude_json(prompt)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(data)

    @action(detail=True, methods=["post"])
    def ship(self, request, pk=None):
        """Отгрузка: списание товаров сделки со склада + расход по себестоимости (COGS)."""
        from apps.warehouse.models import Warehouse, StockDocument, StockMovement
        from apps.finance.services import record_expense
        deal = self.get_object()
        items = list(deal.items.select_related("product"))
        if not items:
            return Response({"detail": "В сделке нет товаров"}, status=status.HTTP_400_BAD_REQUEST)
        wh = Warehouse.objects.filter(is_default=True).first() or Warehouse.objects.first()
        doc = StockDocument.objects.create(kind="out", number=f"РН-{deal.id}", warehouse=wh,
                                           deal=deal, comment=f"Відвантаження по угоді #{deal.id}",
                                           author=request.user)
        cogs = Decimal("0")
        for it in items:
            StockMovement.objects.create(document=doc, product=it.product,
                                         quantity=-it.quantity, price=it.product.cost)
            cogs += it.quantity * it.product.cost
        if cogs:
            record_expense(cogs, deal=deal)
        return Response({"ok": True, "cogs": float(cogs),
                         "deal": DealDetailSerializer(deal, context={"request": request}).data})


class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.select_related("deal")
    serializer_class = PaymentSerializer
    filterset_fields = ["deal", "provider", "is_paid"]

    def get_queryset(self):
        qs = super().get_queryset()
        if not self.request.user.can_see_all_deals():
            qs = qs.filter(deal__owner=self.request.user)
        return qs


from rest_framework.views import APIView
from django.db.models import Count, Sum, Avg


class AnalyticsView(APIView):
    """Сводка по продажам: KPI + воронка по стадиям."""
    def get(self, request):
        _u = request.user
        _see_all = _u.is_superuser or _u.can_see_all_deals()
        _deals_base = Deal.objects.all() if _see_all else Deal.objects.filter(owner=_u)
        _leads_base = Lead.objects.all() if _see_all else Lead.objects.filter(owner=_u)
        funnel_id = request.GET.get("funnel")
        funnels = Funnel.objects.filter(is_lead_funnel=False)
        if funnel_id:
            funnels = funnels.filter(id=funnel_id)
        funnel = funnels.first()

        leads_total = _leads_base.count()
        deals = _deals_base
        if funnel:
            deals = deals.filter(funnel=funnel)
        deals_total = deals.count()
        won = deals.filter(stage__is_won=True)
        revenue = won.aggregate(s=Sum("amount"))["s"] or 0
        avg_check = won.aggregate(a=Avg("amount"))["a"] or 0
        won_c = deals.filter(stage__is_won=True).count()
        lost_c = deals.filter(stage__is_lost=True).count()
        conv = round(won_c / (won_c + lost_c) * 100, 1) if (won_c + lost_c) else 0

        stages = []
        if funnel:
            for st in funnel.stages.all():
                cnt = deals.filter(stage=st).count()
                amt = deals.filter(stage=st).aggregate(s=Sum("amount"))["s"] or 0
                stages.append({"name": st.name, "color": st.color, "count": cnt, "amount": float(amt)})

        # ── Розподіл по каналах (джерелах лідів/сделок) ──
        from django.db.models import Q as _Q
        _LBL = {"instagram": "Instagram", "telegram": "Telegram", "facebook": "Facebook",
                "tiktok": "TikTok", "viber": "Viber", "call": "Дзвінок", "site": "Сайт",
                "wholesale": "Опт / дилери", "designers": "Дизайнери", "whatsapp": "WhatsApp",
                "google_business": "Google", "other": "Інше"}
        _lead_src = dict(_leads_base.values_list("source").annotate(n=Count("id")))
        _channels = []
        for _d in _deals_base.values("source").annotate(
                deals=Count("id"),
                won=Count("id", filter=_Q(stage__is_won=True)),
                lost=Count("id", filter=_Q(stage__is_lost=True)),
                rev=Sum("amount", filter=_Q(stage__is_won=True))):
            _s = _d["source"]; _wc = _d["won"] or 0; _lc = _d["lost"] or 0
            _channels.append({
                "source": _s, "label": _LBL.get(_s, _s or "—"),
                "leads": _lead_src.get(_s, 0), "deals": _d["deals"], "won": _wc,
                "revenue": float(_d["rev"] or 0),
                "conversion": round(_wc / (_wc + _lc) * 100, 1) if (_wc + _lc) else 0,
            })
        # додати канали, що є лише в лідах (ще без сделок)
        _seen = {c["source"] for c in _channels}
        for _src, _n in _lead_src.items():
            if _src not in _seen:
                _channels.append({"source": _src, "label": _LBL.get(_src, _src or "—"),
                                  "leads": _n, "deals": 0, "won": 0, "revenue": 0, "conversion": 0})
        _channels.sort(key=lambda x: (-x["revenue"], -x["leads"]))

        # топ менеджеров
        managers = list(deals.values("owner__first_name", "owner__last_name")
                        .annotate(deals=Count("id"), sum=Sum("amount")).order_by("-sum")[:5])
        return Response({
            "leads_total": leads_total, "deals_total": deals_total,
            "conversion": conv, "revenue": float(revenue), "avg_check": float(avg_check),
            "funnel": funnel.name if funnel else "", "stages": stages,
            "managers": [{"name": (m["owner__first_name"] or "") + " " + (m["owner__last_name"] or ""),
                          "deals": m["deals"], "sum": float(m["sum"] or 0)} for m in managers],
            "channels": _channels,
            "funnels": list(Funnel.objects.filter(is_lead_funnel=False).values("id", "name")),
        })


class ActivityLogView(APIView):
    """Аудит-журнал по сутності: /api/activity/?kind=lead&object_id=123"""
    def get(self, request):
        from .models import ActivityLog
        qs = ActivityLog.objects.all()
        kind = request.GET.get("kind"); oid = request.GET.get("object_id")
        if kind:
            qs = qs.filter(kind=kind)
        if oid:
            qs = qs.filter(object_id=oid)
        # доступ: менеджер бачить історію лише по СВОЇХ картках (захист від підглядання за id)
        u = request.user
        if oid and kind in ("lead", "deal") and not u.is_superuser:
            see_all = u.can_see_all_deals() if kind == "deal" else u.can_see_all_leads()
            if not see_all:
                from .models import Lead as _L, Deal as _D
                Model = _D if kind == "deal" else _L
                obj = Model.objects.filter(id=oid).first()
                if not obj or obj.owner_id != u.id:
                    return Response([])
        return Response([{
            "action": a.action, "detail": a.detail,
            "actor": a.user.get_full_name() if a.user else (a.actor or "Система"),
            "at": a.created_at,
        } for a in qs[:200]])


class GlobalSearchView(APIView):
    """Глибокий пошук по CRM: сделки, ліди, клієнти — за назвою/іменем/телефоном/ID.
    Поважає права: менеджер не знайде чужі сделки/ліди/клієнтів."""

    def get(self, request):
        from django.db.models import Q as _Q
        from .models import Contact
        q = (request.GET.get("q") or "").strip()
        if len(q) < 2:
            return Response({"deals": [], "leads": [], "clients": []})
        u = request.user
        digit = q.isdigit()

        def dname(c):
            if not c:
                return ""
            return ("%s %s" % (c.last_name or "", c.first_name or "")).strip() or c.phone or "Без імені"

        # ── сделки ──
        deals = Deal.objects.select_related("contact", "stage")
        af = u.allowed_funnel_ids()
        if af is not None:
            deals = deals.filter(funnel_id__in=af)
        if not (u.is_superuser or u.can_see_all_deals()):
            deals = deals.filter(owner=u)
        dq = (_Q(title__icontains=q) | _Q(b24_id__icontains=q) | _Q(ttn__icontains=q)
              | _Q(contact__first_name__icontains=q) | _Q(contact__last_name__icontains=q)
              | _Q(contact__phone__icontains=q))
        if digit:
            dq |= _Q(id=int(q))
        deals = deals.filter(dq).distinct()[:8]

        # ── ліди ──
        leads = Lead.objects.select_related("contact", "stage")
        if af is not None:
            leads = leads.filter(funnel_id__in=af)
        if not (u.is_superuser or u.can_see_all_leads()):
            leads = leads.filter(owner=u)
        lq = (_Q(title__icontains=q) | _Q(contact__first_name__icontains=q)
              | _Q(contact__last_name__icontains=q) | _Q(contact__phone__icontains=q))
        if digit:
            lq |= _Q(id=int(q))
        leads = leads.filter(lq).distinct()[:8]

        # ── клієнти ──
        clients = Contact.objects.all()
        if not (u.is_superuser or u.can_see_all_clients()):
            clients = clients.filter(_Q(owner=u) | _Q(leads__owner=u) | _Q(deals__owner=u)).distinct()
        cq = (_Q(first_name__icontains=q) | _Q(last_name__icontains=q)
              | _Q(phone__icontains=q) | _Q(email__icontains=q))
        clients = clients.filter(cq).distinct()[:8]

        return Response({
            "deals": [{"id": d.id, "title": d.title, "stage": d.stage.name if d.stage_id else "",
                       "amount": float(d.amount or 0), "client": dname(d.contact)} for d in deals],
            "leads": [{"id": l.id, "title": l.title, "stage": l.stage.name if l.stage_id else "",
                       "client": dname(l.contact)} for l in leads],
            "clients": [{"id": c.id, "name": dname(c), "phone": c.phone or "",
                         "deals": c.deals.count()} for c in clients],
        })
