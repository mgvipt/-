from decimal import Decimal
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import BasePermission, SAFE_METHODS, AllowAny, IsAuthenticated
from rest_framework.views import APIView
from apps.common.permissions import HasPermCode
from django.http import HttpResponseRedirect, HttpResponseNotFound
from .models import Company, Contact, Funnel, Stage, Lead, Deal, DealItem, Payment, AutomationRule, GlobalRule, Task, AgentConfig
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
                qs = qs.filter(
                    _Q(owner=user)
                    | _Q(stage_id__in=list(_va))
                    | _Q(owner__isnull=True, stage__order=0)
                )
            else:
                # Нічиї картки першого статусу — спільна черга. Після ручного
                # переміщення ActivityLogMixin призначить менеджера власником.
                qs = qs.filter(_Q(owner=user) | _Q(owner__isnull=True, stage__order=0))
        return qs

    def perform_create(self, serializer):
        # новый лид/сделка по умолчанию закрепляется за создателем
        serializer.save(owner=serializer.validated_data.get("owner") or self.request.user)


class ContactViewSet(viewsets.ModelViewSet):
    queryset = Contact.objects.all()
    serializer_class = ContactSerializer

    @action(detail=True, methods=["get"], url_path="finance")
    def finance(self, request, pk=None):
        """Гроші по клієнту: доходи/витрати/аванси + останні операції журналу."""
        from apps.finance.models import Transaction as _Tx
        from django.db.models import Sum as _Sum
        from apps.finance.models import PlannedPayment as _PP
        from django.db.models import Q as _Qc
        c = self.get_object()
        _nm = (" ".join(filter(None, [c.first_name or "", c.last_name or ""])).strip() or (c.nickname or "")).strip()
        # операції: привʼязані до контакту АБО (легасі) де контрагент точно = імʼя клієнта
        _byname = None
        _match = _Qc(contact=c) | _Qc(deal__contact=c)
        if _nm:
            _byname = _Qc(counterparty__iexact=_nm) | _Qc(counterparty__istartswith=_nm + "/") | _Qc(counterparty__istartswith=_nm + " ") | _Qc(counterparty__istartswith=_nm + ".")
            _match = _match | _byname  # всі платежі цьому контрагенту, навіть привʼязані до обʼєкта (обʼєкт видно окремим стовпцем)
        qs = _Tx.objects.filter(_match)
        # фільтри блоку операцій (діють на список + лічильник + плитки Дохід/Витрата/Аванс)
        _ocp = (request.query_params.get("op_cp") or "").strip()
        if _ocp:
            qs = qs.filter(counterparty__icontains=_ocp)
        _oobj = (request.query_params.get("op_obj") or "").strip()
        if _oobj:
            qs = qs.filter(_Qc(contact__first_name__icontains=_oobj) | _Qc(contact__last_name__icontains=_oobj) | _Qc(contact__nickname__icontains=_oobj))
        _ofrom = (request.query_params.get("op_from") or "").strip()
        if _ofrom:
            qs = qs.filter(date__gte=_ofrom)
        _oto = (request.query_params.get("op_to") or "").strip()
        if _oto:
            qs = qs.filter(date__lte=_oto)
        inc = qs.filter(direction="in").aggregate(s=_Sum("amount_uah"))["s"] or 0
        exp = qs.filter(direction="out").aggregate(s=_Sum("amount_uah"))["s"] or 0
        # аванс = ВІЛЬНІ гроші клієнта = Дохід − Розхід − вже списано з авансу на оплати сделок.
        # ⚠️ ТА САМА формула, що й перевірка при «Прийняти оплату → З авансу клієнта» (accept_payment, _avail),
        # щоб плитка «Аванс» і перевірка ЗАВЖДИ збігались і аванс НЕ йшов у мінус через неоплачені won-угоди.
        from decimal import Decimal as _Dadv
        _adv_used = Payment.objects.filter(deal__contact=c, provider="advance", is_paid=True).aggregate(s=_Sum("amount"))["s"] or 0
        adv = _Dadv(str(inc or 0)) - _Dadv(str(exp or 0)) - _Dadv(str(_adv_used or 0))
        _ppq = _PP.objects.filter(status="planned").filter(_Qc(contact=c) | ((_Qc(is_internal=False) & _byname) if _byname is not None else _Qc(pk__in=[])))
        from django.db.models import F as _F
        debt = _ppq.filter(kind="payable").aggregate(s=_Sum(_F("amount") - _F("paid_amount")))["s"] or 0
        # ДЕБІТОРКА (нам винні): торгова (від продажу, майбутня прибуток) окремо від позики (мої гроші в борг, НЕ прибуток)
        recv_sale = _ppq.filter(kind="receivable", is_loan=False).aggregate(s=_Sum("amount"))["s"] or 0
        recv_loan = _ppq.filter(kind="receivable", is_loan=True).aggregate(s=_Sum("amount"))["s"] or 0
        # внутрішній борг між підрозділами: якщо цей контакт — КРЕДИТОР (counterparty_contact), йому винні
        recv_internal = _PP.objects.filter(status="planned", is_internal=True, counterparty_contact=c, kind="payable").aggregate(s=_Sum("amount"))["s"] or 0
        recv_sale = (recv_sale or 0) + (recv_internal or 0)
        # ── ПРИБУТОК ПО КЛІЄНТУ (загальний, без фільтра): виручка − собівартість складу − закупки/послуги ──
        from decimal import Decimal as _Dp
        _qf = _Tx.objects.filter(_match)
        _rev = _qf.filter(direction="in").aggregate(s=_Sum("amount_uah"))["s"] or 0     # виручка (усі надходження від клієнта)
        _cext = _qf.filter(direction="out").aggregate(s=_Sum("amount_uah"))["s"] or 0   # закупки під замовлення + послуги/майстри (журнал)
        from apps.crm.models import Deal as _Deal
        _cogs = _Dp("0")          # собівартість складських товарів у виграних угодах клієнта
        _planned_srv = _Dp("0")   # планова закупка послуг/робіт (мастеру) — щоб ловити переплату
        for _dl in _Deal.objects.filter(contact=c, stage__is_won=True).prefetch_related("items", "items__product"):
            for _it in _dl.items.all():
                _cu = _it.cost if (_it.cost or 0) > 0 else (getattr(_it.product, "cost", 0) or 0)
                try:
                    _line = _Dp(str(_it.quantity or 0)) * _Dp(str(_cu or 0))
                    if not getattr(_it.product, "track_stock", False):
                        _planned_srv += _line   # послуга/робота (track_stock=False) — плановая закупка мастеру
                    else:
                        _cogs += _line          # склад (track_stock=True) — себестоимость склада
                except Exception:
                    pass
        # факт: реально выплачено по журналу НЕ на материалы (категории материалов исключаем) = выплаты мастерам/услуги
        _MAT_KW = ("матер", "закуп", "постач", "товар", "оприбут")
        _actual_srv = _Dp("0")
        for _t in _qf.filter(direction="out").select_related("category"):
            _cn2 = ((_t.category.name if _t.category_id else "") or "").lower()
            if not any(_k in _cn2 for _k in _MAT_KW):
                _actual_srv += _Dp(str(_t.amount_uah or 0))
        _profit = float(_rev or 0) - float(_cext or 0) - float(_cogs)
        # пагінація історії: скільки рядків показувати і з якого зсуву (для >500 — перемикання сторінок)
        try:
            _lim = int(request.query_params.get("limit") or 15)
        except Exception:
            _lim = 15
        _lim = max(1, min(_lim, 500))
        try:
            _off = int(request.query_params.get("offset") or 0)
        except Exception:
            _off = 0
        _off = max(0, _off)
        def _cn(cc):
            if not cc:
                return ""
            return (getattr(cc, "display_name", "") or (" ".join(filter(None, [cc.first_name or "", cc.last_name or ""])).strip())
                    or cc.nickname or cc.phone or ("#%d" % cc.id))
        ops = [{"id": t.id, "date": t.date, "direction": t.direction, "amount_uah": t.amount_uah,
                "counterparty": t.counterparty, "category": t.category.name if t.category else "",
                "fin_direction": (t.fin_direction.name if t.fin_direction_id else ""),
                "comment": (t.comment or "")[:80], "deal": t.deal_id,
                "deal_title": (t.deal.title if t.deal_id else ""),
                "contact": t.contact_id, "contact_name": _cn(t.contact)}
               for t in qs.select_related("category", "deal", "contact", "fin_direction").order_by("-date", "-id")[_off:_off + _lim]]
        # список боргів клієнта (дебіторка+кредиторка, УСІ статуси) — щоб у картці бачити оплачені/неоплачені
        _all_pp = _PP.objects.filter(
            _Qc(contact=c) | ((_Qc(is_internal=False) & _byname) if _byname is not None else _Qc(pk__in=[]))
        ).select_related("deal").order_by("status", "-id")[:100]
        debts_list = [{"id": p.id, "kind": p.kind, "amount": float(p.amount or 0), "counterparty": p.counterparty or "",
                       "paid_amount": float(p.paid_amount or 0), "remaining": float((p.amount or 0) - (p.paid_amount or 0)),
                       "status": p.status, "is_loan": bool(p.is_loan),
                       "due_date": p.due_date.isoformat() if p.due_date else None,
                       "deal": p.deal_id, "deal_title": (p.deal.title if p.deal_id else ""),
                       "comment": (p.comment or "")[:70]} for p in _all_pp]
        return Response({"income": inc, "expense": exp, "advance": adv, "debt": debt,
                         "receivable": (recv_sale or 0) + (recv_loan or 0), "receivable_sale": recv_sale, "receivable_loan": recv_loan,
                         "count": qs.count(), "ops": ops, "debts_list": debts_list,
                         "revenue": float(_rev or 0), "cost_ext": float(_cext or 0), "cogs": float(_cogs), "profit": _profit,
                         "planned_srv": float(_planned_srv), "actual_srv": float(_actual_srv),
                         "is_supplier": ("supplier" in (getattr(c, "kinds", None) or []))})
    search_fields = ["first_name", "last_name", "phone", "email", "edrpou", "nickname"]
    filterset_fields = ["loyalty_tag", "source", "owner"]
    ordering_fields = ["created_at", "first_name", "last_touch_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.can_see_all_clients():
            from django.db.models import Q as _Q
            qs = qs.filter(_Q(owner=user) | _Q(leads__owner=user) | _Q(deals__owner=user) | _Q(shared_with=user)).distinct()
        li = self.request.query_params.get("loyalty_in")
        if li:
            qs = qs.filter(loyalty_tag__in=[x for x in li.split(",") if x])
        if self.request.query_params.get("has_phone") == "1":
            qs = qs.exclude(phone="")
        # ── ПРАВА ПО СЕГМЕНТАХ: видно лише дозволені типи (порожньо = всі) ──
        from django.db.models import Q as _Qk
        _ak = user.allowed_contact_kinds() if hasattr(user, "allowed_contact_kinds") else None
        if _ak is not None:
            _cond = _Qk(kinds=[])          # контрагенти без типу видні всім (ще не розмічені)
            for _k in _ak:
                _cond |= _Qk(kinds__contains=[_k])
            qs = qs.filter(_cond)
        # ── ФІЛЬТР списку за сегментом (вкладки Клієнти / Постачальники / ...) ──
        _kf = (self.request.query_params.get("kind") or "").strip()
        if _kf:
            qs = qs.filter(kinds__contains=[_kf])
        return qs

    def get_serializer_class(self):
        return ContactDetailSerializer if self.action == "retrieve" else ContactSerializer

    def destroy(self, request, *args, **kwargs):
        u = request.user
        if not (u.is_superuser or u.has_perm_code("contact.delete")):
            return Response({"detail": "Немає прав видаляти клієнтів. Зверніться до керівника."}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def reset(self, request, pk=None):
        """ТЕСТ: повністю стерти дані клієнта (ліди/сделки/чати/повідомлення + контакт) — зайде як новий. Лише адмін."""
        u = request.user
        if not (u.is_superuser or (hasattr(u, "has_perm_code") and u.has_perm_code("roles.manage"))):
            return Response({"detail": "Скидати клієнта може лише адмін"}, status=status.HTTP_403_FORBIDDEN)
        contact = self.get_object()
        from apps.crm.models import Lead, Deal
        from apps.inbox.models import Conversation
        cnt = {"deals": Deal.objects.filter(contact=contact).count(),
               "leads": Lead.objects.filter(contact=contact).count(),
               "conversations": Conversation.objects.filter(contact=contact).count()}
        Deal.objects.filter(contact=contact).delete()
        Lead.objects.filter(contact=contact).delete()
        Conversation.objects.filter(contact=contact).delete()
        cid = contact.id
        contact.delete()
        return Response({"ok": True, "deleted": cnt, "contact": cid})


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
        self._guard_write(); obj = serializer.save()
        if "source" in self.request.data:  # джерело — спільне для клієнта: розшарити на всі його ліди/сделки
            from .models import Lead, Deal
            Lead.objects.filter(contact=obj).update(source=obj.source or "other")
            Deal.objects.filter(contact=obj).update(source=obj.source or "other")

    def perform_destroy(self, instance):
        self._guard_write(); instance.delete()


class FunnelViewSet(viewsets.ModelViewSet):
    serializer_class = FunnelSerializer
    queryset = Funnel.objects.prefetch_related("stages").all()

    def _guard_manage(self):
        u = self.request.user
        if not (u.is_superuser or u.has_perm_code("funnel.manage") or u.has_perm_code("roles.manage")):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Налаштовувати воронки може лише той, кому видано право «Налаштовувати воронки»")

    def perform_create(self, serializer):
        self._guard_manage(); serializer.save()

    def perform_update(self, serializer):
        self._guard_manage(); serializer.save()

    def perform_destroy(self, instance):
        self._guard_manage(); instance.delete()

    def get_queryset(self):
        qs = super().get_queryset()
        allowed = self.request.user.allowed_funnel_ids()
        return qs if allowed is None else qs.filter(id__in=allowed)

    @action(detail=False, methods=["post"])
    def reorder(self, request):
        """Зберегти порядок воронок. body: {ids: [id, id, ...]} у потрібній послідовності."""
        self._guard_manage()
        ids = [int(x) for x in (request.data.get("ids") or []) if str(x).isdigit()]
        for idx, fid in enumerate(ids):
            Funnel.objects.filter(id=fid).update(order=idx)
        return Response({"ok": True, "count": len(ids)})

    @action(detail=True, methods=["post"])
    def save_stages(self, request, pk=None):
        """Зберегти весь набір стадій воронки (перейменування/колір/порядок/+/видалення)."""
        self._guard_manage()
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

    def _guard(self):
        u = self.request.user
        if not (u.is_superuser or u.has_perm_code("funnel.manage") or u.has_perm_code("roles.manage")):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Змінювати стадії може лише той, у кого право «Налаштовувати воронки»")

    def perform_create(self, serializer):
        self._guard(); serializer.save()

    def perform_update(self, serializer):
        self._guard(); serializer.save()

    def perform_destroy(self, instance):
        self._guard(); instance.delete()


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
    delete_perm = None   # право для видалення (lead.delete / deal.delete)
    edit_perm = None     # право редагувати ЧУЖІ (lead.edit.all / deal.edit.all)

    def _can_edit(self, obj):
        u = self.request.user
        if u.is_superuser:
            return True
        if self.edit_perm and u.has_perm_code(self.edit_perm):
            return True
        return obj.owner_id in (None, u.id)  # свою або ще нічию (взяти в роботу) — можна

    def _guard(self, deal, money=False, fulfill=False):
        """Дозвіл на ДІЮ по сделці (не плутати з «бачити»). Власник/edit.all — завжди.
        Гроші — ще й право payment.process. Відгрузка/ТТН — ще й склад (warehouse.edit)."""
        from rest_framework.response import Response as _R
        from rest_framework import status as _st
        u = self.request.user
        if self._can_edit(deal):
            return None
        if (money or fulfill) and u.has_perm_code("payment.process"):
            return None
        if fulfill and u.has_perm_code("warehouse.edit"):
            return None
        return _R({"detail": "Немає прав на цю дію по чужій сделці. Зверніться до керівника."}, status=_st.HTTP_403_FORBIDDEN)

    def destroy(self, request, *args, **kwargs):
        u = request.user
        if not (u.is_superuser or (self.delete_perm and u.has_perm_code(self.delete_perm))):
            from rest_framework.response import Response as _R
            from rest_framework import status as _st
            return _R({"detail": "Немає прав видаляти. Зверніться до керівника."}, status=_st.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)

    def perform_create(self, serializer):
        u = self.request.user
        if self.log_kind == "deal" and not (u.is_superuser or u.has_perm_code("deal.create")):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Немає права створювати сделки")
        # власник = створювач (інакше менеджер зі «своїми» сделками не бачить власну картку)
        kwargs = {}
        if hasattr(serializer.Meta.model, "owner") and not serializer.validated_data.get("owner"):
            kwargs["owner"] = u
        obj = serializer.save(**kwargs)
        from .models import log_activity
        log_activity(self.log_kind, obj.id, "Створено", getattr(obj, "title", ""), u)

    @action(detail=True, methods=["post"])
    def agent_run(self, request, pk=None):
        """Запустити вбудованого AI-агента вручну по картці."""
        from .agent import run_agent
        obj = self.get_object()
        out = run_agent(obj, self.log_kind, trigger="manual", user=request.user,
                        model=(request.data.get("model") or "claude-opus-4-8"))
        return Response(out)

    def update(self, request, *args, **kwargs):
        from .models import log_activity
        obj = self.get_object()
        if not self._can_edit(obj):
            from rest_framework.response import Response as _Re
            from rest_framework import status as _ste
            return _Re({"detail": "Немає прав редагувати цю картку (лише свою або з правом «редагувати всі»)."}, status=_ste.HTTP_403_FORBIDDEN)
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
            if self.log_kind == "deal" and obj.stage and _is_pay_stage(obj.stage.name):
                try:
                    from apps.warehouse.services import create_warehouse_job
                    create_warehouse_job(obj)
                except Exception:
                    pass
            if self.log_kind == "deal" and obj.stage and getattr(obj.stage, "is_won", False):
                try:
                    from apps.warehouse.services import realize_deal
                    realize_deal(obj, request.user)  # успішна стадія → списання товару + документ реалізації
                except Exception:
                    pass
            if self.log_kind == "deal" and obj.stage and "ттн створена" in (obj.stage.name or "").lower():
                try:
                    obj.items.update(reserved=True)  # ТТН створена → товари в РЕЗЕРВ (списання буде на Успішній)
                except Exception:
                    pass
            if self.log_kind == "deal":
                from django.utils import timezone as _tzc
                _stc = obj.stage
                _closedc = bool(_stc and (getattr(_stc, "is_won", False) or getattr(_stc, "is_lost", False)))
                if _closedc and not obj.closed_at:
                    obj.closed_at = _tzc.now(); obj.save(update_fields=["closed_at"])
                elif not _closedc and obj.closed_at:
                    obj.closed_at = None; obj.save(update_fields=["closed_at"])
                if _closedc:
                    try:  # закрита угода → активні задачі складу скасовуємо (не висять у канбані)
                        from apps.warehouse.models import WarehouseJob as _WJc
                        _WJc.objects.filter(deal=obj).exclude(status__in=("shipped", "cancelled")).update(status="cancelled")
                    except Exception:
                        pass
            if hasattr(obj, "stage_changed_at"):
                from django.utils import timezone as _tzs
                obj.stage_changed_at = _tzs.now(); obj.save(update_fields=["stage_changed_at"])
            if not obj.owner_id:  # взяв у роботу і ще немає відповідального → призначити того, хто взяв
                obj.owner_id = request.user.id
                obj.save(update_fields=["owner"])
                log_activity(self.log_kind, obj.id, "Призначено відповідального", f"Взяв у роботу: {actor}", request.user, actor)
                auto = True
        if not auto and obj.owner_id != old_owner:
            new_owner = obj.owner.get_full_name() if obj.owner else "—"
            log_activity(self.log_kind, obj.id, "Зміна відповідального", f"→ {new_owner}", request.user, actor)
        return resp


def convert_lead_to_deal(lead, funnel, user, actor):
    """Конвертація: гарантуємо контакт (створюємо якщо нема) -> створюємо сделку -> ВИДАЛЯЄМО лід."""
    from .models import Contact, Deal, log_activity
    contact = lead.contact
    if not contact:
        parts = (lead.title or "Клієнт").split()
        contact = Contact.objects.create(
            first_name=(parts[0][:150] if parts else "Клієнт"),
            last_name=(" ".join(parts[1:])[:150] if len(parts) > 1 else ""),
            source=lead.source or "other")
    from django.db import transaction as _txn
    stage = funnel.stages.order_by("order").first()
    with _txn.atomic():
        deal = Deal.objects.create(
            title=lead.title, contact=contact, funnel=funnel, stage=stage,
            amount=lead.amount, source=lead.source, owner=lead.owner,
            qualification=lead.qualification, card_fields=lead.card_fields)
    log_activity("deal", deal.id, "Створено з ліда (лід видалено)",
                 "Воронка %s · лід #%s · контакт #%s" % (funnel.name, lead.id, contact.id), user, actor)
    # перенести задачі + AI-прогони ліда на сделку (не сиротити при каскаді)
    from .models import Task, AgentRun
    Task.objects.filter(lead=lead).update(lead=None, deal=deal)
    AgentRun.objects.filter(lead=lead).update(lead=None, deal=deal, kind="deal")
    lead.delete()
    return deal


class LeadViewSet(ActivityLogMixin, ScopedByRoleMixin, viewsets.ModelViewSet):
    log_kind = "lead"
    queryset = Lead.objects.select_related("owner", "contact", "funnel", "stage")
    serializer_class = LeadSerializer
    view_all_method = "can_see_all_leads"
    delete_perm = "lead.delete"
    edit_perm = "lead.edit.all"

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        """Конвертувати лід у сделку (той самий контакт/owner)."""
        lead = self.get_object()
        funnel = (Funnel.objects.filter(is_lead_funnel=False, name__icontains="Основний продукт").exclude(name__contains="·").first()
                  or Funnel.objects.filter(is_lead_funnel=False).order_by("order", "id").first())
        if not funnel:
            return Response({"detail": "Немає воронки продажів"}, status=status.HTTP_400_BAD_REQUEST)
        actor = request.user.get_full_name() or request.user.username
        deal = convert_lead_to_deal(lead, funnel, request.user, actor)
        return Response({"deal_id": deal.id})

    @action(detail=True, methods=["get", "post"])
    def sales_analysis(self, request, pk=None):
        """Аналітик-коуч: глибокий розбір діалогу ліда. GET=кеш, POST=новий розбір."""
        lead = self.get_object()
        return Response(_run_sales_analysis(lead, "lead", user=request.user, refresh=(request.method == "POST")))

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
            funnel = Funnel.objects.filter(is_lead_funnel=False, name__icontains="Тестовий набір").exclude(name__contains="·").first()
        elif prod in ("main", "основной", "основний"):
            funnel = Funnel.objects.filter(is_lead_funnel=False, name__icontains="Основний продукт").exclude(name__contains="·").first()
        if not funnel:
            funnel = Funnel.objects.filter(is_lead_funnel=False).order_by("order", "id").first()
        if not funnel:
            return Response({"detail": "Немає воронки продажів"}, status=status.HTTP_400_BAD_REQUEST)
        actor = (request.user.get_full_name() or request.user.username) if request.user.is_authenticated else "AI"
        u = request.user if request.user.is_authenticated else None
        deal = convert_lead_to_deal(lead, funnel, u, actor)
        return Response({"deal_id": deal.id, "funnel": funnel.name})
    filterset_fields = ["funnel", "stage", "source", "is_seen", "owner", "contact"]
    search_fields = ["title", "contact__phone", "contact__first_name", "contact__last_name"]


def _short_code():
    import random, string
    return "".join(random.choice(string.ascii_letters + string.digits) for _ in range(7))


def paylink_redirect(request, code):
    from .models import PayLink
    pl = PayLink.objects.filter(code=code).first()
    if not pl:
        return HttpResponseNotFound("Посилання не знайдено або застаріло")
    PayLink.objects.filter(id=pl.id).update(clicks=pl.clicks + 1)
    return HttpResponseRedirect(pl.target)


def _normalize_phone(raw):
    """Нормалізувати телефон у формат 380XXXXXXXXX."""
    d = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if d.startswith("380"):
        return d[:12]
    if d.startswith("0") and len(d) >= 10:
        return "38" + d[:10]
    if len(d) == 9:
        return "380" + d
    return d


def _find_product(name):
    from apps.warehouse.models import Product
    q = (name or "").strip()
    if not q:
        return None
    p = Product.objects.filter(is_active=True, name__iexact=q).first()
    if not p:
        p = Product.objects.filter(is_active=True, name__icontains=q[:30]).first()
    return p


def _is_test_kit_item(it):
    """Товар — тестовий набір? (за категорією або назвою)"""
    if not it.product_id:
        return False
    cat = (it.product.category.name if it.product.category_id else "") or ""
    nm = it.product.name.lower()
    return "тестов" in cat.lower() or "тест-наб" in nm or "тестовий набір" in nm


def _route_deal_funnel(deal, user=None):
    """Якщо ВСІ товари сделки — тестові набори, а воронка інша →
    переносимо сделку у воронку «22 Тестовий набір» на ту саму стадію (за order).
    Викликається після додавання товарів у make_offer."""
    from .models import Funnel, Stage, log_activity
    from django.db.models import Count
    items = list(deal.items.select_related("product__category"))
    if not items or not all(_is_test_kit_item(i) for i in items):
        return False
    target = (Funnel.objects.filter(name__icontains="тестовий наб")
              .annotate(n=Count("deals")).order_by("-n", "id").first())
    if not target or deal.funnel_id == target.id:
        return False
    cur_order = deal.stage.order if deal.stage_id else 0
    new_stage = (Stage.objects.filter(funnel=target, order=cur_order).first()
                 or Stage.objects.filter(funnel=target).order_by("order").first())
    if not new_stage:
        return False
    old = "%s / %s" % (deal.funnel.name, deal.stage.name if deal.stage_id else "—")
    deal.funnel = target
    deal.stage = new_stage
    deal.save(update_fields=["funnel", "stage"])
    log_activity("deal", deal.id, "Авто: зміна воронки",
                 "%s → %s / %s (клієнт обрав тестовий набір)" % (old, target.name, new_stage.name),
                 user, "AI-автоматика")
    return True


def make_offer(deal, items_spec, user=None, send_pay=True):
    """АВТО-оффер тест-набору: товари з номенклатури -> прорахунок + LiqPay -> стадії «Розрахунок здійснено» → «Домовились про оплату»."""
    from django.conf import settings as _s
    from apps.inbox.models import Conversation
    from apps.inbox.services import send_message
    from .models import DealItem, log_activity, PayLink
    from .liqpay import build_checkout_url
    if deal.items.exists():
        return {"ok": False, "msg": "товари вже є — оффер не повторюємо"}
    if deal.stage_id and deal.stage.order >= 2:
        return {"ok": False, "msg": "сделка вже на оплаті/далі"}
    added, missing = [], []
    for spec in (items_spec or []):
        prod = _find_product((spec or {}).get("name"))
        if not prod:
            missing.append((spec or {}).get("name")); continue
        qty = Decimal(str((spec or {}).get("qty") or 1))
        DealItem.objects.create(deal=deal, product=prod, quantity=qty, price=prod.price, cost=_deal_item_cost(prod, prod.price, qty))
        added.append("%s x %s" % (prod.name[:40], qty))
    if not added:
        return {"ok": False, "missing": missing, "msg": "товар не знайдено в номенклатурі"}
    items = list(deal.items.all())
    total = sum((i.total for i in items), Decimal("0"))
    deal.amount = total
    deal.save(update_fields=["amount"])
    _route_deal_funnel(deal, user=user)  # тест-набір → воронка «22 Тестовий набір»
    conv = Conversation.objects.filter(contact_id=deal.contact_id, status="open").order_by("-last_message_at").first() if deal.contact_id else None

    def _g(x):
        return ("%g" % float(x))

    lines = ["\u2022 %s \u2014 %s \u00d7 %s \u0433\u0440\u043d = %s \u0433\u0440\u043d" % (((i.product.name if i.product_id else i.custom_name) or "Позиція")[:55], _g(i.quantity), _g(i.price), _g(i.total)) for i in items]
    quote = "\U0001f9fe \u0412\u0430\u0448 \u043f\u0440\u043e\u0440\u0430\u0445\u0443\u043d\u043e\u043a:\n" + "\n".join(lines) + ("\n\n\u0420\u0430\u0437\u043e\u043c \u0434\u043e \u0441\u043f\u043b\u0430\u0442\u0438: %s \u0433\u0440\u043d" % _g(total))
    text_quote = "\u041f\u0456\u0434\u0433\u043e\u0442\u0443\u0432\u0430\u043b\u0438 \u0434\u043b\u044f \u0432\u0430\u0441 \u043f\u0440\u043e\u0440\u0430\u0445\u0443\u043d\u043e\u043a \U0001f60a\n\n" + quote
    sent_q = False
    if conv:
        try:
            send_message(conv, text_quote, user=user); sent_q = True
        except Exception:
            pass
    _advance_deal_stage(deal, 1, "\u0430\u0432\u0442\u043e: \u043f\u0440\u043e\u0440\u0430\u0445\u0443\u043d\u043e\u043a")
    log_activity("deal", deal.id, "AI: \u043f\u0440\u043e\u0440\u0430\u0445\u0443\u043d\u043e\u043a", "%s \u0433\u0440\u043d; %s" % (total, "; ".join(added)), user, "AI-\u0430\u0433\u0435\u043d\u0442")
    sent_p = False
    url = ""
    if send_pay and total > 0:
        pub = getattr(_s, "LIQPAY_PUBLIC_KEY", "")
        prv = getattr(_s, "LIQPAY_PRIVATE_KEY", "")
        if pub and prv:
            order_id = "WCCRM-%s-%s" % (deal.id, str(deal.id * 7919 + int(total))[-6:])
            base = "https://crm.wallcovdec.com.ua"
            full = build_checkout_url(pub, prv, total, order_id, "Wallcov #%s" % deal.id, server_url=base + "/api/crm/liqpay/callback/", result_url=base, paytypes="card,apay,gpay,privat24")
            code = _short_code()
            while PayLink.objects.filter(code=code).exists():
                code = _short_code()
            PayLink.objects.create(code=code, deal=deal, target=full)
            url = "%s/p/%s/" % (base, code)
            paytext = "\U0001f4b3 \u041e\u043f\u043b\u0430\u0442\u0438\u0442\u0438 \u043e\u043d\u043b\u0430\u0439\u043d \U0001f449 %s\n\u0421\u0443\u043c\u0430: %s \u0433\u0440\u043d" % (url, _g(total))
            if conv:
                try:
                    send_message(conv, paytext, user=user); sent_p = True
                except Exception:
                    pass
            _advance_deal_stage(deal, 2, "\u0430\u0432\u0442\u043e: \u043f\u043e\u0441\u0438\u043b\u0430\u043d\u043d\u044f \u043d\u0430 \u043e\u043f\u043b\u0430\u0442\u0443")
            log_activity("deal", deal.id, "AI: \u043e\u043f\u043b\u0430\u0442\u0430", "%s \u0433\u0440\u043d; %s" % (total, url), user, "AI-\u0430\u0433\u0435\u043d\u0442")
    return {"ok": True, "added": added, "missing": missing, "amount": str(total), "sent_quote": sent_q, "sent_pay": sent_p, "url": url}


def _issue_checkbox_for_deal(deal, user=None):
    """Авто-чек Checkbox для найстаршого оплаченого платежу БЕЗ чека.
    Податковий ланцюг: аванс → (дод. аванс) → фінал (sell) через pre_payment_relation_id.
    Аванс якщо накопичена оплата < суми товарів; фінал коли закриває суму (з ТТН для НП).
    None = немає що чекувати або Checkbox вимкнено; {"error":..} = помилка."""
    from django.conf import settings as _s
    from . import checkbox as cb
    from .models import log_activity, Payment as _P
    from decimal import Decimal as _D
    if not (_s.CHECKBOX_LICENSE_KEY and _s.CHECKBOX_PASSWORD):
        return None
    pay = _P.objects.filter(deal=deal, is_paid=True, checkbox_receipt_id="").order_by("id").first()
    if not pay:
        # наложка НП: клієнт ВЖЕ розрахувався на відділенні (фіскальний момент настав),
        # хоча виплата від НоваПей ще в дорозі (is_paid=False до надходження на рахунок)
        pay = _P.objects.filter(deal=deal, provider="np_cod", checkbox_receipt_id="").order_by("id").first()
    if not pay:
        return None
    goods = []
    for it in deal.items.all():
        nm = ((it.product.name if it.product_id else "") or it.custom_name or "Товар")[:200]
        qty = float(it.quantity) or 1
        unit_kop = int(round(float(it.total) / qty * 100))  # ціна за одиницю ЗІ знижкою (щоб чек = сплаченому)
        goods.append({"good": {"code": str(getattr(it, "product_id", None) or it.id), "name": nm,
                               "price": unit_kop},
                      "quantity": int(round(qty * 1000))})
    if not goods:
        goods = [{"good": {"code": "DEAL-%s" % deal.id, "name": (deal.title or "Замовлення Wallcov")[:200],
                           "price": int(round(float(deal.amount or 0) * 100))}, "quantity": 1000}]
    goods_total = sum(g["good"]["price"] * g["quantity"] // 1000 for g in goods)
    from django.db.models import Q as _Qcb
    cum = sum((p.amount for p in _P.objects.filter(deal=deal, id__lte=pay.id).filter(_Qcb(is_paid=True) | _Qcb(id=pay.id))), _D("0"))
    cum_kop = int(round(float(cum) * 100))
    this_kop = int(round(float(pay.amount) * 100))
    if this_kop <= 0:
        return None
    pm = "CASH" if pay.provider in ("cash", "np") else "CASHLESS"  # np_cod = переказ НоваПей → CASHLESS
    pay_label = {"liqpay": "Інтернет еквайринг", "terminal": "Картка", "card": "Картка",
                 "np_cod": "Накладений платіж Нова Пошта", "reqs": "Оплата за реквізитами"}.get(pay.provider)
    relation = deal.checkbox_relation_id or None
    closes = cum_kop >= goods_total
    ext = "WCCRM-%s-P%s" % (deal.id, pay.id)
    client_name = getattr(deal.contact, "name", None) if deal.contact_id else None
    ttn = (deal.ttn or None) if closes else None
    try:
        r = cb.create_receipt(goods, this_kop, ext, payment_method=pm, payment_label=pay_label,
                              advance=(not closes), relation_id=relation,
                              client_name=client_name, ttn=ttn)
    except cb.CheckboxError as e:
        log_activity("deal", deal.id, "Checkbox помилка", str(e)[:400], user, "Checkbox")
        return {"error": str(e)}
    pay.checkbox_receipt_id = r["id"]
    pay.save(update_fields=["checkbox_receipt_id"])
    # ссылка на фискальный чек → в комментарий связанной операции журнала (видно/копируется в карточке платежа)
    try:
        _tx = getattr(pay, "transaction", None)
        if _tx is not None and r.get("url"):
            _cl = "🧾 Чек: " + r["url"]
            if _cl not in (_tx.comment or ""):
                _tx.comment = (((_tx.comment or "").strip() + " " + _cl).strip())[:255]
                _tx.save(update_fields=["comment"])
    except Exception:
        pass
    deal.checkbox_status = "фіскальний" if closes else "аванс"
    deal.checkbox_url = r["url"]
    deal.checkbox_receipt_id = r["id"]
    if r["relation_id"]:
        deal.checkbox_relation_id = r["relation_id"]
    deal.save(update_fields=["checkbox_status", "checkbox_url", "checkbox_receipt_id", "checkbox_relation_id"])
    sent = False
    if deal.contact_id and r["url"]:
        from apps.inbox.models import Conversation
        from apps.inbox.services import send_message
        conv = Conversation.objects.filter(contact_id=deal.contact_id, status="open").order_by("-last_message_at").first()
        if conv:
            # РОП пише тепле живе повідомлення (без слова "фіскальний")
            body = ("Дякуємо за оплату! 😊 Вже почали готувати ваше замовлення." if closes
                    else "Дякуємо за передоплату! 😊 Бронюємо замовлення за вами.")
            try:
                from .ai import claude_json
                dmsgs = list(conv.messages.order_by("id").values("direction", "text"))[-12:]
                dlg = "\n".join((("Клієнт: " if m["direction"] == "in" else "Ми: ") + (m["text"] or "")) for m in dmsgs if m.get("text"))
                items = ", ".join(((i.product.name if i.product_id else i.custom_name) or "Позиція")[:40] for i in deal.items.all()[:3])
                step = "повна оплата пройшла, починаємо готувати і скоро відправимо" if closes else "отримали передоплату, бронюємо і готуємо замовлення"
                pr = ("Ти РОП Wallcov (декоративні покриття для стін). Напиши КОРОТКЕ (2-3 речення) тепле живе повідомлення клієнту: %s. "
                      "Подякуй, згадай що замовив, додай приємний наступний крок. НЕ пиши слова 'фіскальний' і 'чек' — посилання я додам сам. "
                      "ЗАВЖДИ українською. JSON {\"message\":\"...\"}.\nЗамовлення: %s\nДіалог:\n%s") % (step, items or "тест-набір", dlg or "(нема)")
                rr = claude_json(pr, source="Помощник CRM (советы и расчёты)")
                if rr.get("message"):
                    body = rr["message"].strip()
            except Exception:
                pass
            try:
                send_message(conv, "%s\n\n🧾 %s" % (body, r["url"]), user=user)
                sent = True
            except Exception:
                pass
    log_activity("deal", deal.id, "Чек Checkbox",
                 "%s · %s грн · код %s · %s" % (deal.checkbox_status, pay.amount, r.get("fiscal_code") or "—", "надіслано" if sent else "створено"),
                 user, "Checkbox")
    return {"ok": True, "url": r["url"], "fiscal_code": r.get("fiscal_code"), "sent": sent, "status": deal.checkbox_status}


def _ser_analysis(da):
    return {"id": da.id, "overall": da.overall_score, "scores": da.scores or {},
            "strengths": da.strengths, "why_not_selling": da.why_not_selling,
            "recommended_reply": da.recommended_reply, "coaching": da.coaching,
            "kind": da.kind, "created_at": da.created_at.isoformat()}


def _run_sales_analysis(entity, field, user=None, refresh=False):
    """Глибокий коучинг-розбір діалогу для ліда/сделки. field = 'deal' | 'lead'."""
    from .models import DialogAnalysis
    from .sales_analyst import analyze_dialog
    from apps.inbox.models import Conversation
    if not refresh:
        last = DialogAnalysis.objects.filter(**{field: entity}).first()
        if last:
            return _ser_analysis(last)
        from .models import AgentConfig
        if not AgentConfig.get().analyst_auto:
            return {"empty": True, "why_not_selling": "Натисніть «Оцінити якість діалогу» для розбору."}
    conv = None
    if entity.contact_id:
        conv = Conversation.objects.filter(contact_id=entity.contact_id).order_by("-last_message_at").first()
    if not conv:
        return {"empty": True, "why_not_selling": "Немає чату з клієнтом для розбору."}
    msgs = list(conv.messages.order_by("id").values("direction", "text"))[-40:]
    stage_name = entity.stage.name if entity.stage_id else ""
    ctx = "Сума %s грн, стадія: %s" % (getattr(entity, "amount", "") or "—", stage_name)
    r = analyze_dialog(msgs, context=ctx, kind="чат")
    if r.get("empty") or r.get("error"):
        return r
    da = DialogAnalysis.objects.create(
        conversation=conv, manager=(entity.owner if getattr(entity, "owner_id", None) else user),
        kind="chat", overall_score=r.get("overall", 0), scores=r.get("scores", {}),
        strengths=r.get("strengths", ""), why_not_selling=r.get("why_not_selling", ""),
        recommended_reply=r.get("recommended_reply", ""), coaching=r.get("coaching", ""),
        **{field: entity})
    return _ser_analysis(da)


_PAY_STAGE_KEYS = ("оплату отримано", "оплата отримано", "оплата отримана", "оплата/предоплата")


def _is_pay_stage(name):
    """Стадія «оплата отримана» у БУДЬ-якому написанні (воронки називають її по-різному)."""
    low = (name or "").lower()
    return any(k in low for k in _PAY_STAGE_KEYS)


def _advance_deal_stage(deal, target_order, reason, actor="Автоматизація", create_wh=True):
    """Рух сделки на стадію за order (тільки вперед). Лог + stage_changed_at."""
    if not deal.stage_id or not deal.funnel_id:
        return False
    if deal.stage.order >= target_order:
        return False
    target = deal.funnel.stages.filter(order=target_order).first()
    if not target:
        return False
    from .models import log_activity
    from django.utils import timezone as _tz
    old = deal.stage.name
    deal.stage = target
    flds = ["stage"]
    if hasattr(deal, "stage_changed_at"):
        deal.stage_changed_at = _tz.now(); flds.append("stage_changed_at")
    if (getattr(target, "is_won", False) or getattr(target, "is_lost", False)) and not deal.closed_at:
        deal.closed_at = _tz.now(); flds.append("closed_at")
    deal.save(update_fields=flds)
    log_activity("deal", deal.id, "\u0410\u0432\u0442\u043e-\u0441\u0442\u0430\u0434\u0456\u044f", "%s \u2192 %s (%s)" % (old, target.name, reason), None, actor)
    if create_wh and _is_pay_stage(target.name):
        try:
            from apps.warehouse.services import create_warehouse_job
            create_warehouse_job(deal)
        except Exception:
            pass
    if getattr(target, "is_won", False) or getattr(target, "is_lost", False):
        try:  # закрита угода → активні задачі складу скасовуємо
            from apps.warehouse.models import WarehouseJob as _WJa
            _WJa.objects.filter(deal=deal).exclude(status__in=("shipped", "cancelled")).update(status="cancelled")
        except Exception:
            pass
    if getattr(target, "is_won", False):
        try:
            from apps.warehouse.services import realize_deal
            realize_deal(deal, None)  # успішна стадія → списання товару + документ реалізації
        except Exception:
            pass
    if "ттн створена" in (target.name or "").lower():
        try:
            deal.items.update(reserved=True)  # авто-резерв на ТТН створена
        except Exception:
            pass
        try:
            from apps.warehouse.services import sync_job_status_after_ttn
            sync_job_status_after_ttn(deal)  # задача складу → колонка «ТТН + Фото»
        except Exception:
            pass
    return True


def _deal_item_cost(product, unit_price, qty=1):
    """Себестоимость ЗА ЕДИНИЦУ, с учётом МИНИМАЛКИ. База строки = max(qty*price, min_price).
    Если cost_pct>0 (услуга с долей мастеру) — себест. строки = база*cost_pct%% (мастеру % от того,
    что платит клиент, включая минимум). Иначе — фикс. product.cost*qty. Возврат на единицу (cost*qty = себест. строки)."""
    if product is None:
        return Decimal("0")
    try:
        q = Decimal(str(qty or 1)) or Decimal("1")
        base = q * Decimal(str(unit_price or 0))
        mp = getattr(product, "min_price", 0) or 0
        if mp and base < Decimal(str(mp)):
            base = Decimal(str(mp))
        pct = getattr(product, "cost_pct", 0) or 0
        if pct and Decimal(str(pct)) > 0:
            line_cost = base * Decimal(str(pct)) / Decimal("100")
        else:
            line_cost = (product.cost or Decimal("0")) * q
        return (line_cost / q).quantize(Decimal("0.01")) if q else Decimal("0")
    except Exception:
        return product.cost or Decimal("0")


class DealViewSet(ActivityLogMixin, ScopedByRoleMixin, viewsets.ModelViewSet):
    log_kind = "deal"
    queryset = Deal.objects.select_related("owner", "contact", "funnel", "stage")
    serializer_class = DealSerializer

    def perform_update(self, serializer):
        old_stage_id = serializer.instance.stage_id
        new_stage = serializer.validated_data.get("stage")
        if new_stage is not None and getattr(new_stage, "id", None) != old_stage_id:
            u = self.request.user
            if not (u.is_superuser or u.has_perm_code("deal.stage.move") or u.has_perm_code("deal.stage.move.all") or u.has_perm_code("roles.manage")):
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied("Стадію рухає автоматика (оплата/склад/ТТН). Право «Пересувати сделки вручну» видає керівник у Ролях.")
        super().perform_update(serializer)
        deal = serializer.instance
        # менеджер ВРУЧНУ пересунув сделку на «Оплату отримано» → задача складу (ідемпотентно)
        try:
            if deal.stage_id and deal.stage_id != old_stage_id and _is_pay_stage(deal.stage.name):
                from apps.warehouse.services import create_warehouse_job
                create_warehouse_job(deal)
        except Exception:
            pass
    view_all_method = "can_see_all_deals"
    delete_perm = "deal.delete"
    edit_perm = "deal.edit.all"

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        stages = p.get("stages")
        if stages:
            try:
                qs = qs.filter(stage_id__in=[int(x) for x in stages.split(",") if x.strip()])
            except ValueError:
                pass
        if p.get("created_from"):
            qs = qs.filter(created_at__date__gte=p["created_from"])
        if p.get("created_to"):
            qs = qs.filter(created_at__date__lte=p["created_to"])
        if p.get("deal_id"):
            try:
                qs = qs.filter(id=int(p["deal_id"]))
            except ValueError:
                pass
        return qs

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        """Масове видалення сделок {ids: [...]}. Право deal.delete."""
        u = request.user
        if not (u.is_superuser or u.has_perm_code("deal.delete")):
            return Response({"detail": "Потрібне право «Видаляти сделки»"}, status=403)
        ids = request.data.get("ids") or []
        qs = Deal.objects.filter(id__in=ids)
        n = qs.count()
        for d in qs:
            log_activity("deal", d.id, "Видалено (масово)", d.title[:80], request.user)
        qs.delete()
        return Response({"ok": True, "deleted": n})

    def get_object(self):
        # Стандартний scope (власник/«всі»). Якщо не знайдено — дозволити СКЛАДУ доступ
        # до сделки, у якої є складська задача (щоб заповнити Нову Пошту / ТТН).
        obj = self.get_queryset().filter(pk=self.kwargs.get("pk")).first()
        if obj is None:
            u = self.request.user
            if hasattr(u, "has_perm_code") and u.has_perm_code("warehouse.view"):
                from apps.warehouse.models import WarehouseJob
                pk = self.kwargs.get("pk")
                if WarehouseJob.objects.filter(deal_id=pk).exists():
                    obj = Deal.objects.filter(pk=pk).first()
        if obj is None:
            from rest_framework.exceptions import NotFound
            raise NotFound()
        self.check_object_permissions(self.request, obj)
        return obj
    filterset_fields = ["funnel", "stage", "source", "owner", "contact"]
    search_fields = ["title", "contact__phone", "contact__first_name", "contact__last_name"]
    ordering_fields = ["amount", "created_at", "updated_at", "closed_at"]

    def get_serializer_class(self):
        # в карточке (retrieve) отдаём расширенные данные: товары, оплаты
        if self.action in ("retrieve", "update", "partial_update"):
            return DealDetailSerializer
        return DealSerializer

    def _recalc_amount(self, deal):
        deal.amount = sum((i.total for i in deal.items.all()), Decimal("0"))
        deal.save(update_fields=["amount"])

    @action(detail=True, methods=["post"])
    def add_item(self, request, pk=None):
        deal = self.get_object()
        g = self._guard(deal)
        if g: return g
        # своя позиція НЕ з номенклатури (без складського обліку) — окреме право
        if str(request.data.get("custom_name") or "").strip():
            u = request.user
            if not (u.is_superuser or u.has_perm_code("deal.items.custom") or u.has_perm_code("roles.manage")):
                return Response({"detail": "Немає права «Товари: своя позиція (не з номенклатури)» — видається у Ролях/Правах."},
                                status=status.HTTP_403_FORBIDDEN)
            qty = Decimal(str(request.data.get("quantity", 1)))
            price = Decimal(str(request.data.get("price", 0) or 0))
            if qty <= 0 or price < 0:
                return Response({"detail": "Кількість > 0, ціна ≥ 0."}, status=status.HTTP_400_BAD_REQUEST)
            DealItem.objects.create(deal=deal, product=None,
                                    custom_name=str(request.data["custom_name"]).strip()[:200],
                                    quantity=qty, price=price, cost=0)
            self._recalc_amount(deal)
            return Response(DealDetailSerializer(deal, context={"request": request}).data)
        from apps.warehouse.models import Product
        product = Product.objects.get(pk=request.data["product"])
        qty = Decimal(str(request.data.get("quantity", 1)))
        price = Decimal(str(request.data.get("price", product.price)))
        disc = Decimal(str(request.data.get("discount_pct", 0) or 0))
        disc_amt = Decimal(str(request.data.get("discount_amount", 0) or 0))
        if qty <= 0 or price < 0 or disc < 0 or disc > 100 or disc_amt < 0:  # #14 захист від дурня/від'ємних
            return Response({"detail": "Кількість > 0, ціна ≥ 0, знижка 0–100% або сума ≥ 0."}, status=status.HTTP_400_BAD_REQUEST)
        DealItem.objects.create(deal=deal, product=product, quantity=qty, price=price, cost=_deal_item_cost(product, price, qty),
                                discount_pct=disc, discount_amount=disc_amt, reserved=bool(request.data.get("reserved")))
        self._recalc_amount(deal)
        return Response(DealDetailSerializer(deal, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def confirm_items(self, request, pk=None):
        """Зберегти список товарів (як у Бітриксі) → стадія Розрахунок здійснено (КП)."""
        deal = self.get_object()
        if not deal.items.exists():
            return Response({"detail": "Спочатку додайте товари"}, status=status.HTTP_400_BAD_REQUEST)
        self._recalc_amount(deal)
        _advance_deal_stage(deal, 1, "список товарів збережено")
        return Response(DealDetailSerializer(deal, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def change_funnel(self, request, pk=None):
        """Перенос угоди в ІНШУ воронку зі ЗБЕРЕЖЕННЯМ стадії за назвою.
        НЕ скидає на першу стадію і НЕ ретригерить автоматизації входу в стадію
        (склад/реалізація вже відпрацювали раніше). Угода лишається на тій самій
        логічній стадії, а всі МАЙБУТНІ автоматизації (НП-поллер, оплати, пріоритети)
        продовжують працювати вже у новій воронці. Якщо у новій воронці немає стадії
        з такою назвою — fallback на першу стадію (структури воронок різні)."""
        from .models import log_activity
        deal = self.get_object()
        if not self._can_edit(deal):
            return Response({"detail": "Немає прав редагувати цю картку."}, status=status.HTTP_403_FORBIDDEN)
        try:
            nf = Funnel.objects.prefetch_related("stages").get(id=request.data.get("funnel"))
        except (Funnel.DoesNotExist, ValueError, TypeError):
            return Response({"detail": "Воронку не знайдено."}, status=status.HTTP_400_BAD_REQUEST)
        if nf.id == deal.funnel_id:
            return Response(DealDetailSerializer(deal, context={"request": request}).data)
        old_funnel_name = deal.funnel.name if deal.funnel_id else ""
        old_stage_name = (deal.stage.name if deal.stage_id else "").strip()
        stages = list(nf.stages.all())
        if not stages:
            return Response({"detail": "У новій воронці немає стадій."}, status=status.HTTP_400_BAD_REQUEST)
        # 1) точний збіг за назвою (реєстронезалежно) — головний шлях (21↔22 мають однакові стадії)
        target = next((st for st in stages if (st.name or "").strip().lower() == old_stage_name.lower()), None)
        same_stage = target is not None
        # 2) fallback — перша стадія за order (коли структури воронок різні)
        if target is None:
            target = sorted(stages, key=lambda st: st.order)[0]
        actor = request.user.get_full_name() or request.user.username
        deal.funnel = nf
        deal.stage = target
        fields = ["funnel", "stage"]
        # логічно та сама стадія → таймер НЕ чіпаємо (SLA/пріоритет як був);
        # впали на першу (інша структура) → оновлюємо таймер як новий вхід у стадію
        if not same_stage and hasattr(deal, "stage_changed_at"):
            from django.utils import timezone as _tz
            deal.stage_changed_at = _tz.now(); fields.append("stage_changed_at")
        deal.save(update_fields=fields)
        detail = ("%s \u2192 %s \u00b7 стадію збережено: %s" % (old_funnel_name, nf.name, target.name)) if same_stage \
            else ("%s \u2192 %s \u00b7 стадії «%s» немає у новій воронці, перенесено на «%s»" % (old_funnel_name, nf.name, old_stage_name or "\u2014", target.name))
        log_activity("deal", deal.id, "Зміна воронки", detail, request.user, actor)
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
        g = self._guard(deal)
        if g: return g
        DealItem.objects.filter(deal=deal, pk=request.data.get("item")).delete()
        self._recalc_amount(deal)
        return Response(DealDetailSerializer(deal, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def update_item(self, request, pk=None):
        """Інлайн-редагування позиції: {item, price?, quantity?, discount_pct?}."""
        deal = self.get_object()
        g = self._guard(deal)
        if g: return g
        it = DealItem.objects.filter(deal=deal, pk=request.data.get("item")).first()
        if not it:
            return Response({"detail": "Позицію не знайдено"}, status=status.HTTP_404_NOT_FOUND)
        # зміна ТОВАРУ в позиції (перевибір) — підставляємо ціну/собівартість нового товару
        _np = request.data.get("product")
        if _np:
            from apps.warehouse.models import Product as _Prod
            _prod = _Prod.objects.filter(id=_np).first()
            if _prod is not None:
                it.product = _prod; it.custom_name = ""
                it.price = _prod.price or Decimal("0")
                it.cost = _deal_item_cost(_prod, it.price, it.quantity)
        for f in ("price", "quantity", "discount_pct", "discount_amount"):
            val = request.data.get(f)
            if val not in (None, ""):
                try:
                    setattr(it, f, Decimal(str(val)))
                except Exception:
                    pass
        # услуга (cost_pct) или минималка (min_price): себестоимость авто-пересчёт от цены/кол-ва/минимума
        if it.product_id and ((getattr(it.product, "cost_pct", 0) or 0) > 0 or (getattr(it.product, "min_price", 0) or 0) > 0):
            it.cost = _deal_item_cost(it.product, it.price, it.quantity)
        if it.quantity <= 0 or it.price < 0 or (it.discount_pct or 0) < 0 or (it.discount_pct or 0) > 100:  # #14
            return Response({"detail": "Кількість > 0, ціна ≥ 0, знижка 0–100%."}, status=status.HTTP_400_BAD_REQUEST)
        it.save()
        self._recalc_amount(deal)
        return Response(DealDetailSerializer(deal, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def credit_sale(self, request, pk=None):
        """Товарний кредит (воронка салону): відвантажуємо БЕЗ грошей →
        дебіторка на клієнта зі сделки + (опційно) задача складу + стадія «Выдано в товарный кредит».
        Дохід зʼявиться, коли в Дт/Кт натиснуть «Оплачено»."""
        from apps.finance.models import PlannedPayment, Category as _FCat
        from datetime import date as _d, timedelta as _tdd
        deal = self.get_object()
        g = self._guard(deal, money=True)
        if g:
            return g
        _paidc = sum((p.amount for p in deal.payments.filter(is_paid=True)), Decimal("0"))
        _remc = (deal.amount or Decimal("0")) - _paidc
        amount = Decimal(str(request.data.get("amount") or (_remc if _remc > 0 else deal.amount) or 0))
        if amount <= 0:
            return Response({"detail": "Сума боргу має бути більше 0."}, status=status.HTTP_400_BAD_REQUEST)
        if not request.data.get("force"):
            _exc = PlannedPayment.objects.filter(deal=deal, kind="receivable", status="planned").first()
            if _exc:
                return Response({"detail": "По цій угоді ВЖЕ є непогашений товарний кредит на %s грн (Фінанси → Дт/Кт). Другий борг створюється лише після підтвердження." % _exc.amount,
                                 "need_force": True}, status=status.HTTP_409_CONFLICT)
        try:
            days = max(1, int(request.data.get("days") or 14))
        except (TypeError, ValueError):
            days = 14
        cp = ""
        c = deal.contact
        if c is not None:
            cp = (" ".join(filter(None, [c.first_name, c.last_name])).strip() or (c.nickname or ""))[:160]
        cat = _FCat.objects.filter(name="САЛОН(Оффлайн)", direction="in").first()
        pp = PlannedPayment.objects.create(
            kind="receivable", amount=amount, due_date=_d.today() + _tdd(days=days),
            counterparty=cp, deal=deal, contact=c, category=cat, channel="Салон",
            fin_direction=(cat.fin_direction if cat and cat.fin_direction_id else None),
            comment="Товарний кредит зі сделки #%s (%s дн.)" % (deal.id, days))
        ship = str(request.data.get("ship") or "1") in ("1", "true", "True")
        if ship:
            try:
                from apps.warehouse.services import create_warehouse_job
                create_warehouse_job(deal)
            except Exception:
                pass
        st = deal.funnel.stages.filter(name__icontains="кредит").order_by("order").first() if deal.funnel_id else None
        if st:
            _advance_deal_stage(deal, st.order, "видано в товарний кредит (борг %s грн)" % amount, "Менеджер", create_wh=False)
        from .models import log_activity
        log_activity("deal", deal.id, "Товарний кредит",
                     "Дебіторка %s грн, строк %s дн.%s" % (amount, days, " + задача складу" if ship else ""), None, "Менеджер")
        deal.refresh_from_db()
        return Response({"ok": True, "planned_id": pp.id,
                         "deal": DealDetailSerializer(deal, context={"request": request}).data})

    @action(detail=True, methods=["post"])
    def accept_payment(self, request, pk=None):
        """Приём оплаты -> запись Payment + доходная проводка в финансы."""
        from apps.finance.services import record_income
        from apps.finance.models import Account
        deal = self.get_object()
        g = self._guard(deal, money=True)
        if g: return g
        amount = Decimal(str(request.data.get("amount") or deal.amount))
        if amount <= 0:  # #15 від'ємна/нульова оплата — заборонено
            return Response({"detail": "Сума оплати має бути більше 0."}, status=status.HTTP_400_BAD_REQUEST)
        provider = request.data.get("provider", "cash")
        account = Account.objects.filter(pk=request.data.get("account")).first()
        if provider == "advance":
            _cc = deal.contact
            if not _cc:
                return Response({"detail": "У сделки нет клиента — из аванса платить не с кого."}, status=status.HTTP_400_BAD_REQUEST)
            from apps.finance.models import Transaction as _AdvTx
            from django.db.models import Sum as _AdvS, Q as _AdvQ
            _nm = (" ".join(filter(None, [_cc.first_name or "", _cc.last_name or ""])).strip() or (_cc.nickname or "")).strip()
            _m = _AdvQ(contact=_cc)
            if _nm:
                _m = _m | _AdvQ(counterparty__iexact=_nm) | _AdvQ(counterparty__istartswith=_nm + "/") | _AdvQ(counterparty__istartswith=_nm + " ") | _AdvQ(counterparty__istartswith=_nm + ".")
            _inc = _AdvTx.objects.filter(_m, direction="in").aggregate(s=_AdvS("amount_uah"))["s"] or 0
            _exp = _AdvTx.objects.filter(_m, direction="out").aggregate(s=_AdvS("amount_uah"))["s"] or 0
            _used = Payment.objects.filter(deal__contact=_cc, provider="advance", is_paid=True).aggregate(s=_AdvS("amount"))["s"] or 0
            _avail = Decimal(str(_inc)) - Decimal(str(_exp)) - Decimal(str(_used))
            if amount > _avail + Decimal("0.01"):
                return Response({"detail": "Недостатньо авансу клієнта. Доступно: %.2f грн." % float(_avail)}, status=status.HTTP_400_BAD_REQUEST)
        # ── РОЗПОДІЛ ПЛАТЕЖУ: частина на сделку, частина закриває дебіторки клієнта (транзит-матеріали БудМаркет тощо) ──
        _debt_ids = request.data.get("debt_ids") or []
        if _debt_ids:
            from apps.finance.models import PlannedPayment as _PPd, Transaction as _DTx
            from django.utils import timezone as _tzd
            from django.db import transaction as _txnd
            _cc = deal.contact
            _debts = [d0 for d0 in _PPd.objects.filter(id__in=_debt_ids, kind="receivable", status="planned") if (_cc and d0.contact_id == _cc.id)]
            _dtot = sum((Decimal(str(d0.amount)) for d0 in _debts), Decimal("0"))
            if _dtot > amount + Decimal("0.01"):
                return Response({"detail": "Сума боргів (%.2f) більша за платіж (%.2f)." % (float(_dtot), float(amount))}, status=status.HTTP_400_BAD_REQUEST)
            _deal_amt = amount - _dtot
            with _txnd.atomic():
                dlock = Deal.objects.select_for_update().get(pk=deal.pk)
                if _deal_amt > 0:
                    _accu = account or Account.objects.filter(name__icontains="Касса Салон").first() or account
                    _payd = Payment.objects.create(deal=dlock, provider=provider, amount=_deal_amt, is_paid=True)
                    record_income(_deal_amt, deal=dlock, account=_accu, payment=_payd,
                                  category=("САЛОН(Оффлайн)" if provider == "cash" else "Продаж товару"),
                                  channel=("Салон" if provider in ("cash", "terminal") else None))
                for d0 in _debts:  # закрити дебіторку транзиту → дохід (як mark-paid)
                    _acc0 = d0.account or account or Account.objects.filter(is_active=True).first()
                    _DTx.objects.create(direction="in", amount=d0.amount, amount_uah=d0.amount, account=_acc0,
                        date=_tzd.localdate(), op_time=_tzd.localtime().time(), category=d0.category,
                        counterparty=d0.counterparty, deal=d0.deal, contact=d0.contact,
                        fin_direction=d0.fin_direction, fin_article=d0.fin_article, channel=d0.channel or "",
                        comment=("Транзит-матеріали (оплата клієнта): " + (d0.comment or ""))[:255])
                    d0.status = "paid"; d0.save(update_fields=["status"])
                _paid = sum((pp.amount for pp in Payment.objects.filter(deal=dlock, is_paid=True)), Decimal("0"))
                if dlock.amount and _paid >= dlock.amount:
                    _advance_after_payment(dlock, "оплата отримана (розподіл: сделка + транзит-матеріали)", create_wh=True)
                elif _paid > 0:
                    _advance_deal_stage(dlock, 2, "часткова оплата (розподіл)")
                deal = dlock
            return Response(DealDetailSerializer(deal, context={"request": request}).data)
        from django.utils import timezone as _tz
        from datetime import timedelta as _td
        from django.db import transaction as _txn
        with _txn.atomic():
            dlock = Deal.objects.select_for_update().get(pk=deal.pk)
            if Payment.objects.filter(deal=dlock, amount=amount, provider=provider, created_at__gte=_tz.now() - _td(seconds=180)).exists():  # #7 вікно захисту від задвоєння 3 хв
                return Response(DealDetailSerializer(dlock, context={"request": request}).data)
            # ОНЛАЙН-воронки (Основний продукт / Тестовий набір): ручний прийом ЗАБОРОНЕНО.
            # Гроші фіксуються ТІЛЬКИ автоматично: LiqPay-callback (по ID платежу) або
            # оплата за реквізитами з банківської виписки. Ніяких дублів і зайвих чеків.
            _fn = (dlock.funnel.name if dlock.funnel_id else '').lower()
            # готівка/термінал = клієнт КУПУЄ В САЛОНІ — ручний прийом дозволено у будь-якій воронці
            if ('основний продукт' in _fn or 'тестовий набір' in _fn) and provider not in ('cash', 'terminal', 'advance'):
                return Response({'detail': 'У цій воронці оплати фіксуються лише автоматично: LiqPay (посилання) або оплата за реквізитами ФОП (підтягується з банку). Ручний прийом вимкнено, щоб не було дублів доходу і зайвих фіскальних чеків. Надішли клієнту посилання на оплату.'}, status=status.HTTP_403_FORBIDDEN)
            # ЗАХИСТ від дубля: по сделці є свіже LiqPay-посилання на ЦЮ Ж суму →
            # найімовірніше клієнт оплатить (або вже оплатив) онлайн. Ручна фіксація створить
            # другий дохід і другий фіскальний чек. Блокуємо (обхід: force=1 після підтвердження).
            if provider not in ("liqpay", "advance") and not request.data.get("force"):
                from .models import PayLink
                link_fresh = PayLink.objects.filter(deal=dlock, created_at__gte=_tz.now() - _td(hours=48)).exists()
                paid_liq = Payment.objects.filter(deal=dlock, provider="liqpay", is_paid=True,
                                                  amount=amount, created_at__gte=_tz.now() - _td(hours=48)).exists()
                if paid_liq:
                    return Response({"detail": "Ця сума ВЖЕ оплачена через LiqPay — не фіксуй її вдруге (буде подвійний дохід і другий чек). Якщо це справді ІНША оплата — натисни ще раз для підтвердження.", "need_force": True}, status=status.HTTP_409_CONFLICT)
                if link_fresh:
                    return Response({"detail": "По сделці надіслано посилання LiqPay. Якщо клієнт оплатить онлайн — оплата зʼявиться сама, і буде дубль. Прийняти вручну все одно? Натисни ще раз для підтвердження.", "need_force": True}, status=status.HTTP_409_CONFLICT)
            pay = Payment.objects.create(deal=dlock, provider=provider, amount=amount, is_paid=True)
            # готівка = продаж у салоні: рахунок «Касса Салон» + категорія «САЛОН(Оффлайн)»
            acc_use, cat_use = account, "Продаж товару"
            if provider == "cash":
                cat_use = "САЛОН(Оффлайн)"
                if not acc_use:
                    acc_use = Account.objects.filter(name__icontains="Касса Салон").first() or account
            tx = None
            if provider != "advance":  # оплата з авансу: дохід уже отримано раніше → новий НЕ створюємо
                tx = record_income(amount, deal=dlock, account=acc_use, payment=pay, category=cat_use,
                                   channel=('Салон' if provider in ('cash', 'terminal') else None))
            # вікно перевірки (воронка салону): ручні правки менеджера до полів операції
            try:
                ov = request.data
                _chg = []
                if ov.get("tx_account"):
                    _a = Account.objects.filter(pk=int(ov["tx_account"])).first()
                    if _a:
                        tx.account = _a; _chg.append("account")
                if ov.get("tx_category"):
                    from apps.finance.models import Category as _FCat
                    _c = _FCat.objects.filter(pk=int(ov["tx_category"]), direction="in").first()
                    if _c:
                        tx.category = _c; _chg.append("category")
                        if _c.fin_direction_id:
                            tx.fin_direction = _c.fin_direction; _chg.append("fin_direction")
                        if _c.fin_article_id:
                            tx.fin_article = _c.fin_article; _chg.append("fin_article")
                if ov.get("tx_direction"):
                    tx.fin_direction_id = int(ov["tx_direction"]); _chg.append("fin_direction")
                if str(ov.get("tx_counterparty") or "").strip():
                    tx.counterparty = str(ov["tx_counterparty"]).strip()[:160]; _chg.append("counterparty")
                if str(ov.get("tx_channel") or "").strip():
                    tx.channel = str(ov["tx_channel"]).strip()[:24]; _chg.append("channel")
                if str(ov.get("tx_comment") or "").strip():
                    tx.comment = str(ov["tx_comment"]).strip()[:255]; _chg.append("comment")
                if _chg:
                    tx.save(update_fields=sorted(set(_chg)))
            except Exception:
                pass
            paid = sum((p.amount for p in Payment.objects.filter(deal=dlock, is_paid=True)), Decimal("0"))
            no_wh = str(request.data.get("no_warehouse") or "") in ("1", "true", "True")
            pt = (dlock.pay_type or "").lower()
            is_np = any(x in pt for x in ["np", "післяплат", "послеоплат", "prepay", "передопл"])
            if dlock.amount and paid >= dlock.amount:
                _advance_after_payment(dlock, "оплата отримана повністю", create_wh=not no_wh)
            elif paid > 0:
                if is_np:
                    _advance_after_payment(dlock, "передоплату отримано (решта — післяплата НП)", create_wh=not no_wh)
                else:
                    _advance_deal_stage(dlock, 2, "часткова оплата (тип Повна — чекаємо решту)")
            deal = dlock
        # авто-чек Checkbox поза транзакцією; для «термінал» чек б'є застосунок Checkbox (Tap to Pay) — НЕ дублюємо
        cbres = None
        skip_receipt = str(request.data.get("no_receipt") or "") in ("1", "true", "True")
        if provider not in ("terminal", "advance") and not skip_receipt:
            try:
                cbres = _issue_checkbox_for_deal(deal, user=getattr(request, "user", None))
            except Exception as _e:
                cbres = {"error": str(_e)}
        resp = DealDetailSerializer(deal, context={"request": request}).data
        if cbres and cbres.get("error"):
            resp = dict(resp); resp["checkbox_error"] = cbres["error"]
        return Response(resp)

    @action(detail=True, methods=["post"])
    def send_quote(self, request, pk=None):
        """Надіслати клієнту прорахунок (КП) з позицій сделки ТЕКСТОМ (поки немає Meta-реєстрації — без PDF)
        + оновити суму + стадія «Розрахунок здійснено (КП)». Далі менеджер/агент шле LiqPay (send_pay_link)."""
        from .models import log_activity
        from apps.inbox.models import Conversation
        from apps.inbox.services import send_message
        deal = self.get_object()
        items = list(deal.items.all())
        if not items:
            return Response({"detail": "У сделці немає товарних позицій — спершу додай товари з номенклатури."},
                            status=status.HTTP_400_BAD_REQUEST)
        total = sum((i.total for i in items), Decimal("0"))
        if deal.amount != total:
            deal.amount = total
            deal.save(update_fields=["amount"])
        def _g(x):
            return ("%g" % float(x))
        lines = ["\u2022 %s \u2014 %s \u00d7 %s \u0433\u0440\u043d = %s \u0433\u0440\u043d" % (((i.product.name if i.product_id else i.custom_name) or "Позиція")[:55], _g(i.quantity), _g(i.price), _g(i.total)) for i in items]
        quote = "\U0001f9fe \u0412\u0430\u0448 \u043f\u0440\u043e\u0440\u0430\u0445\u0443\u043d\u043e\u043a:\n" + "\n".join(lines) + ("\n\n\u0420\u0430\u0437\u043e\u043c \u0434\u043e \u0441\u043f\u043b\u0430\u0442\u0438: %s \u0433\u0440\u043d" % _g(total))
        intro = "\u041f\u0456\u0434\u0433\u043e\u0442\u0443\u0432\u0430\u043b\u0438 \u0434\u043b\u044f \u0432\u0430\u0441 \u043f\u0440\u043e\u0440\u0430\u0445\u0443\u043d\u043e\u043a \U0001f60a"
        try:
            from .ai import claude_json
            conv0 = Conversation.objects.filter(contact_id=deal.contact_id).order_by("-last_message_at").first() if deal.contact_id else None
            dlg = ""
            if conv0:
                dmsgs = list(conv0.messages.order_by("id").values("direction", "text"))[-12:]
                dlg = "\n".join((("\u041a\u043b\u0456\u0454\u043d\u0442: " if m["direction"] == "in" else "\u041c\u0438: ") + (m["text"] or "")) for m in dmsgs if m.get("text"))
            nm = ", ".join(((i.product.name if i.product_id else i.custom_name) or "Позиція")[:40] for i in items[:3])
            pr = ("\u0422\u0438 \u0420\u041e\u041f Wallcov. \u041d\u0430\u043f\u0438\u0448\u0438 \u041a\u041e\u0420\u041e\u0422\u041a\u0415 (1-2 \u0440\u0435\u0447\u0435\u043d\u043d\u044f) \u0442\u0435\u043f\u043b\u0435 \u0456\u043d\u0442\u0440\u043e \u043f\u0435\u0440\u0435\u0434 \u043f\u0440\u043e\u0440\u0430\u0445\u0443\u043d\u043a\u043e\u043c. "
                  "\u0411\u0415\u0417 \u0446\u0456\u043d \u0456 \u0411\u0415\u0417 \u0441\u043f\u0438\u0441\u043a\u0443 (\u044f \u0434\u043e\u0434\u0430\u043c \u0441\u0430\u043c). \u0417\u0410\u0412\u0416\u0414\u0418 \u0443\u043a\u0440\u0430\u0457\u043d\u0441\u044c\u043a\u043e\u044e. JSON {\"message\":\"...\"}.\n\u0422\u043e\u0432\u0430\u0440\u0438: %s\n\u0414\u0456\u0430\u043b\u043e\u0433:\n%s") % (nm, dlg or "()")
            r = claude_json(pr, source="Помощник CRM (советы и расчёты)")
            if r.get("message"):
                intro = r["message"].strip()
        except Exception:
            pass
        text = "%s\n\n%s" % (intro, quote)
        sent = False
        if deal.contact_id:
            conv = Conversation.objects.filter(contact_id=deal.contact_id, status="open").order_by("-last_message_at").first()
            if conv:
                try:
                    send_message(conv, text, user=getattr(request, "user", None)); sent = True
                except Exception:
                    pass
        _advance_deal_stage(deal, 1, "\u043d\u0430\u0434\u0456\u0441\u043b\u0430\u043d\u043e \u043f\u0440\u043e\u0440\u0430\u0445\u0443\u043d\u043e\u043a (\u041a\u041f)")
        log_activity("deal", deal.id, "\u041f\u0440\u043e\u0440\u0430\u0445\u0443\u043d\u043e\u043a", "%s \u0433\u0440\u043d" % total, getattr(request, "user", None), "\u041c\u0435\u043d\u0435\u0434\u0436\u0435\u0440")
        return Response({"ok": True, "sent": sent, "amount": str(total), "text": text})

    @action(detail=True, methods=["post"])
    def send_pay_link(self, request, pk=None):
        """LiqPay/Реквізити: згенерувати посилання + надіслати клієнту в чат + стадія Домовились про оплату.
        НЕ позначає оплачено — оплата підтвердиться callback-ом LiqPay після реального платежу."""
        from django.conf import settings as _s
        from .liqpay import build_checkout_url
        from .models import log_activity
        deal = self.get_object()
        g = self._guard(deal, money=True)
        if g: return g
        kind = request.data.get("kind", "liqpay")
        amount = Decimal(str(request.data.get("amount") or deal.amount or 0))
        if amount <= 0:  # #9 не можна нульове/від'ємне посилання
            return Response({"detail": "Сума посилання має бути більше 0."}, status=status.HTTP_400_BAD_REQUEST)
        if deal.amount and amount > deal.amount:  # #9 не більше вартості замовлення (передоплата — можна менше)
            amount = deal.amount
        order_id = "WCCRM-%s-%s" % (deal.id, str(deal.id * 7919 + int(amount))[-6:])
        base = "https://crm.wallcovdec.com.ua"
        url = ""
        if kind == "requisites":
            iban = getattr(_s, "WALLCOV_IBAN", "") or "(вкажіть IBAN у Налаштуваннях)"
            payee = getattr(_s, "WALLCOV_PAYEE", "") or "ФОП"
            ipn = getattr(_s, "WALLCOV_IPN", "")
            text = ("Реквізити для оплати 💳\n\n"
                    "Отримувач: %s\n"
                    "IBAN: %s\n"
                    "ІПН/ЄДРПОУ: %s\n"
                    "Сума: %s грн\n\n"
                    "Призначення платежу (важливо — скопіюйте як є):\n"
                    "Оплата замовлення %s\n\n"
                    "Після надходження грошей оплата зафіксується автоматично, і ми одразу готуємо замовлення 😊") % (payee, iban, ipn, amount, deal.id)
        else:
            pub = getattr(_s, "LIQPAY_PUBLIC_KEY", ""); prv = getattr(_s, "LIQPAY_PRIVATE_KEY", "")
            if not (pub and prv):
                return Response({"detail": "LiqPay не налаштовано (немає ключів)"}, status=status.HTTP_400_BAD_REQUEST)
            # обмежуємо способи: звичайний LiqPay = тільки картка/Apple/Google/Приват24;
            # розстрочка/частинами — ТІЛЬКИ коли менеджер обрав "Розстрочка" у CRM
            paytypes = "paypart,moment_part,card" if kind == "installment" else "card,apay,gpay,privat24"
            full_url = build_checkout_url(pub, prv, amount, order_id, "Замовлення Wallcov #%s" % deal.id,
                                          server_url=base + "/api/crm/liqpay/callback/", result_url=base, paytypes=paytypes)
            # коротке посилання щоб не слати потвору
            from .models import PayLink
            code = _short_code()
            while PayLink.objects.filter(code=code).exists():
                code = _short_code()
            PayLink.objects.create(code=code, deal=deal, target=full_url)
            url = "%s/p/%s/" % (base, code)
            # шаблонне повідомлення (БЕЗ Claude — економія токенів; текст стабільний)
            items_txt = ", ".join(((i.product.name if i.product_id else i.custom_name) or "Позиція")[:40] for i in deal.items.all()[:3])
            body = ("Дякуємо за замовлення! 💚 %s готовий(і) до оплати — "
                    "щойно надійде оплата, одразу готуємо та відправляємо. Чекаємо на Вас! 😊"
                    % (items_txt or "Ваше замовлення"))
            text = "%s\n\n💳 Оплатити онлайн 👉 %s\nСума: %s грн" % (body, url, amount)
        sent = False
        if deal.contact_id:
            from apps.inbox.models import Conversation
            from apps.inbox.services import send_message
            conv = Conversation.objects.filter(contact_id=deal.contact_id, status="open").order_by("-last_message_at").first()
            if conv:
                try:
                    send_message(conv, text, user=request.user); sent = True
                except Exception:
                    pass
                if sent and kind == "requisites":
                    # окремими повідомленнями — щоб клієнт скопіював одним тапом
                    for extra in (iban, "Оплата замовлення %s" % deal.id):
                        try:
                            send_message(conv, extra, user=request.user)
                        except Exception:
                            pass
        _advance_deal_stage(deal, 2, "надіслано посилання на оплату")  # Домовились про оплату
        # посилання фіксується в історії — можна скопіювати і переслати вручну (ФБ тощо), навіть якщо чату нема
        log_activity("deal", deal.id, "Посилання на оплату", "%s · %s грн · %s · %s" % (kind, amount, "надіслано клієнту" if sent else "НЕ надіслано (немає відкритого чату)", url), request.user, "Менеджер")
        return Response({"ok": True, "sent": sent, "url": url, "text": text})

    @action(detail=True, methods=["post"])
    def issue_checkbox(self, request, pk=None):
        """Створити фіскальний чек Checkbox (ДПС) + надіслати клієнту (ручна кнопка)."""
        from django.conf import settings as _s
        deal = self.get_object()
        if not (_s.CHECKBOX_LICENSE_KEY and _s.CHECKBOX_PASSWORD):
            return Response({"detail": "Checkbox не налаштовано (немає ключів)"}, status=status.HTTP_400_BAD_REQUEST)
        r = _issue_checkbox_for_deal(deal, user=request.user)
        if r is None:
            return Response({"ok": True, "already": True, "url": deal.checkbox_url, "status": deal.checkbox_status})
        if r.get("error"):
            return Response({"detail": "Checkbox: %s" % r["error"]}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(r)

    @action(detail=True, methods=["get", "post"])
    def sales_analysis(self, request, pk=None):
        """Аналітик-коуч: глибокий розбір діалогу сделки. GET=кеш, POST=новий розбір."""
        deal = self.get_object()
        return Response(_run_sales_analysis(deal, "deal", user=request.user, refresh=(request.method == "POST")))

    @action(detail=False, methods=["get"])
    def kit_materials(self, request):
        """Матеріали тест-наборів з номенклатури (повний список для анкети/складу)."""
        import re as _re
        from apps.warehouse.models import Product

        def fam(name):
            n = _re.split(r"\s*[\u2014\-]?\s*[\u0442\u0422]\u0435\u0441\u0442", name.strip(), 1)[0]
            n = _re.sub(r"\u0412\u0435\u043b\u044c\u0432\u0435\u0442\s+", "", n)
            n = _re.sub(r"\s+Bianco\b", "", n, flags=_re.I)
            n = _re.sub(r"^[\s\"\u201c\u201d\u0027\u00ab\u00bb\u2014\-]+|[\s\"\u201c\u201d\u0027\u00ab\u00bb\u2014\-]+$", "", n)
            return n

        seen = {}
        for nm in Product.objects.filter(is_active=True, name__iregex=r"\u0442\u0435\u0441\u0442\u043e\u0432|\u043f\u0440\u043e\u0431\u043d\u0438").values_list("name", flat=True):
            f = fam(nm)
            if 2 <= len(f) <= 45:
                seen[f] = seen.get(f, 0) + 1
        return Response(sorted(seen.keys(), key=lambda k: (-seen[k], k)))

    @action(detail=False, methods=["get"])
    def np_cities(self, request):
        """Автокомпліт міст Нова Пошта."""
        from apps.integrations import adapters as ad
        try:
            return Response(ad.np_search_cities(request.GET.get("q", ""), 15))
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)

    @action(detail=False, methods=["get"])
    def np_warehouses(self, request):
        """Відділення/поштомати у вибраному місті."""
        from apps.integrations import adapters as ad
        try:
            return Response(ad.np_warehouses(request.GET.get("settlement_ref", ""), request.GET.get("q", ""), 40))
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)

    @action(detail=True, methods=["get"])
    def np_print(self, request, pk=None):
        """Друк ТТН у форматі НП (A4 / m100 / m85 / zebra) — проксі PDF з сервера."""
        deal = self.get_object()
        if not deal.ttn:
            return Response({"detail": "Немає ТТН"}, status=status.HTTP_400_BAD_REQUEST)
        from apps.integrations import adapters as ad
        import urllib.request
        from django.http import HttpResponse
        url = ad.np_print_url(deal.ttn, request.query_params.get("fmt", "A4"))
        try:
            with urllib.request.urlopen(url, timeout=40) as resp:  # noqa: S310
                data = resp.read(); ctype = resp.headers.get("Content-Type", "application/pdf")
        except Exception as e:
            return Response({"detail": "NP друк: %s" % e}, status=status.HTTP_502_BAD_GATEWAY)
        r = HttpResponse(data, content_type=ctype)
        r["Content-Disposition"] = 'inline; filename="ttn-%s.pdf"' % deal.ttn
        return r

    @action(detail=True, methods=["post"])
    def np_recreate(self, request, pk=None):
        """Перестворити ТТН: видалити поточну в НП (помилка в адресі/відділенні) + очистити,
        щоб зробити нову. Платіж, чек і угода ЛИШАЮТЬСЯ."""
        deal = self.get_object()
        g = self._guard(deal, fulfill=True)
        if g: return g
        from apps.integrations import adapters as ad
        from .models import log_activity
        old = deal.ttn
        ref = (deal.np_data or {}).get("ttn_ref") or ad.np_ref_by_number(old)
        warn = ""
        if ref:
            try:
                dr = ad.np_delete_ttn(ref)
                if not dr.get("success"):
                    warn = str(dr.get("errors") or dr.get("warnings") or "")
            except Exception as e:
                warn = str(e)
        else:
            warn = "Ref не знайдено в НП"
        deal.ttn = ""
        _nd = dict(deal.np_data or {}); _nd.pop("ttn_ref", None); deal.np_data = _nd
        deal.save(update_fields=["ttn", "np_data"])
        log_activity("deal", deal.id, "ТТН перестворення", "Видалено %s%s" % (old, (" · НП: " + warn) if warn else " (НП видалено)"), request.user, "НП")
        return Response({"ok": True, "deleted": old, "np_warning": warn})

    @action(detail=True, methods=["post"])
    def np_cancel(self, request, pk=None):
        """Скасувати замовлення: видалити ТТН + відкат стадії + позначка «потрібен повернення коштів».
        Гроші НЕ списуються автоматично — повернення робить менеджер вручну (безпека)."""
        deal = self.get_object()
        g = self._guard(deal, fulfill=True)
        if g: return g
        from apps.integrations import adapters as ad
        from .models import log_activity
        old = deal.ttn
        ref = (deal.np_data or {}).get("ttn_ref") or ad.np_ref_by_number(old)
        warn = ""
        if ref:
            try:
                dr = ad.np_delete_ttn(ref)
                if not dr.get("success"):
                    warn = str(dr.get("errors") or dr.get("warnings") or "")
            except Exception as e:
                warn = str(e)
        else:
            warn = "Ref не знайдено в НП"
        deal.ttn = ""
        _nd = dict(deal.np_data or {}); _nd.pop("ttn_ref", None); _nd["cancelled"] = True; deal.np_data = _nd
        upd = ["ttn", "np_data"]
        back = deal.funnel.stages.filter(is_lost=True).order_by("order").first() if deal.funnel_id else None
        if back:
            deal.stage = back; upd.append("stage")
        deal.save(update_fields=upd)
        log_activity("deal", deal.id, "Скасування замовлення", "ТТН %s видалено · ПОТРІБЕН ПОВЕРНЕННЯ КОШТІВ клієнту (вручну)%s" % (old, (" · НП: " + warn) if warn else ""), request.user, "НП")
        return Response({"ok": True, "deleted": old, "np_warning": warn, "refund_manual": True})

    @action(detail=True, methods=["post"])
    def np_save(self, request, pk=None):
        """Зберегти повну форму Доставка НП (спільна для менеджера і складу)."""
        deal = self.get_object()
        nd = request.data.get("np_data")
        if nd is not None:
            deal.np_data = nd
        dd = request.data.get("delivery_date")
        if dd is not None:
            deal.np_delivery_date = dd or None
        deal.save(update_fields=["np_data", "np_delivery_date"])
        return Response({"ok": True, "np_data": deal.np_data, "delivery_date": str(deal.np_delivery_date or "")})

    @action(detail=True, methods=["post"])
    def np_estimate(self, request, pk=None):
        """Оцінка вартості доставки НП (getDocumentPrice)."""
        from apps.integrations import adapters as ad
        props = request.data.get("props") or {}
        try:
            r = ad.np_document_price(props)
            rows = (r or {}).get("data") or []
            return Response(rows[0] if rows else {})
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)

    @action(detail=False, methods=["get"])
    def np_streets(self, request):
        from apps.integrations import adapters as ad
        ref = request.query_params.get("settlement_ref", "")
        q = request.query_params.get("q", "")
        city = request.query_params.get("city", "").strip()
        if not (ref or city) or len(q) < 2:
            return Response([])

        def _items(sref):
            r = ad.np_streets(sref, q)
            rows = (r or {}).get("data") or []
            return rows[0].get("Addresses", []) if rows else []

        try:
            items = _items(ref) if ref else []
            # старі чернетки зберігали city_ref замість settlement_ref → вулиць нема;
            # перерішаємо населений пункт за НАЗВОЮ міста і пробуємо ще раз
            if not items and city:
                for c in ad.np_search_cities(city)[:5]:
                    sref = c.get("settlement_ref") or ""
                    if sref and sref != ref:
                        items = _items(sref)
                        if items:
                            break
            return Response([{"name": (a.get("Present") or a.get("SettlementStreetDescription") or ""), "ref": a.get("SettlementStreetRef") or a.get("Ref")} for a in items])
        except Exception:
            return Response([])

    @action(detail=False, methods=["get"])
    def np_packlist(self, request):
        from apps.integrations import adapters as ad
        try:
            r = ad.np_packlist()
            rows = (r or {}).get("data") or []
            return Response([{"ref": p.get("Ref"), "descr": p.get("Description"), "w": p.get("Width"), "h": p.get("Height"), "l": p.get("Length")} for p in rows][:60])
        except Exception:
            return Response([])

    @action(detail=True, methods=["post"])
    def create_ttn(self, request, pk=None):
        """Створити РЕАЛЬНУ ТТН Нова Пошта + надіслати клієнту. Наложка (cod_amount) для післяплати НП."""
        from datetime import datetime as _dt
        from apps.integrations import adapters as ad
        from apps.integrations.models import IntegrationSettings
        from .models import log_activity
        deal = self.get_object()
        g = self._guard(deal, fulfill=True)
        if g: return g
        if deal.ttn:
            return Response({"ok": True, "already": True, "ttn": deal.ttn})
        p = request.data
        name = (p.get("recipient_name") or (getattr(deal.contact, "name", "") if deal.contact_id else "") or "").strip()
        phone = _normalize_phone(p.get("recipient_phone") or (getattr(deal.contact, "phone", "") if deal.contact_id else ""))
        city_name = (p.get("recipient_city_name") or "").strip()
        area = (p.get("recipient_area") or "").strip()
        region = (p.get("recipient_region") or "").strip()
        wh_number = str(p.get("warehouse_number") or "").strip()
        service = p.get("service_type") or "WarehouseWarehouse"
        street = str(p.get("street") or "").strip()
        house = str(p.get("house") or "").strip()
        flat = str(p.get("flat") or "").strip()
        if service == "WarehouseDoors":
            if not (name and phone and city_name and street and house):
                return Response({"detail": "Адресна доставка: потрібні отримувач, телефон, місто, вулиця, будинок"}, status=status.HTTP_400_BAD_REQUEST)
        elif not (name and phone and city_name and wh_number):
            return Response({"detail": "Потрібні: отримувач, телефон, місто, № відділення"}, status=status.HTTP_400_BAD_REQUEST)
        cfg_obj = IntegrationSettings.objects.filter(provider="novaposhta").first()
        cfg = (cfg_obj.config or {}) if cfg_obj else {}
        if not cfg.get("api_key"):
            return Response({"detail": "Нова Пошта не налаштована (немає ключа)"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            sender = ad.np_resolve_sender()
        except Exception as e:
            return Response({"detail": "NP відправник: %s" % e}, status=status.HTTP_502_BAD_GATEWAY)
        cod = float(p.get("cod_amount") or 0)
        props = {
            "PayerType": p.get("payer") or "Recipient",
            "PaymentMethod": p.get("payment_method") or "Cash",
            "DateTime": _dt.now().strftime("%d.%m.%Y"),
            "CargoType": "Parcel",
            "Weight": str(p.get("weight") or "0.5"),
            "ServiceType": service,
            "SeatsAmount": str(int(p.get("seats") or 1)),
            "Description": (p.get("description") or "Декоративні матеріали")[:100],
            "Cost": str(int(round(float(p.get("cost") or deal.amount or 300)))),
            "CitySender": cfg.get("sender_city_ref"),
            "Sender": sender.get("counterparty_ref"),
            "SenderAddress": cfg.get("sender_address_ref"),
            "ContactSender": sender.get("contact_ref"),
            "SendersPhone": _normalize_phone(sender.get("sender_phone") or ""),
            "RecipientName": name,
            "RecipientType": "PrivatePerson",
            "RecipientsPhone": phone,
            "NewAddress": "1",
            "RecipientCityName": city_name,
            "RecipientArea": area,
            "RecipientAreaRegions": region,
            "RecipientAddressName": (street if service == "WarehouseDoors" else wh_number),
        }
        if service == "WarehouseDoors":
            props["RecipientHouse"] = house
            if flat:
                props["RecipientFlat"] = flat
        if cod > 0:
            # післяплата через «Контроль оплати» (AfterpaymentOnGoodsCost) — класична
            # послуга Money-переказу у контрагента НП не підключена (НП: «Післяплата недоступна»)
            props["AfterpaymentOnGoodsCost"] = str(int(round(cod)))
        try:
            r = ad.np_create_ttn(props)
        except Exception as e:
            return Response({"detail": "NP: %s" % e}, status=status.HTTP_502_BAD_GATEWAY)
        if not r.get("success"):
            return Response({"detail": "NP: %s" % (r.get("errors") or r.get("warnings") or "невідома помилка")}, status=status.HTTP_502_BAD_GATEWAY)
        doc = (r.get("data") or [{}])[0]
        ttn = doc.get("IntDocNumber") or doc.get("Number") or ""
        deal.ttn = ttn
        _nd = dict(deal.np_data or {}); _nd["ttn_ref"] = doc.get("Ref") or ""
        if cod > 0:
            _nd["cod_amount"] = cod  # наложка: поллер НП створить Payment при отриманні
        deal.np_data = _nd
        deal.save(update_fields=["ttn", "np_data"])
        try:  # авто-рух на «НП_ТТН створена» (синхронно зі складом)
            _tc = deal.funnel.stages.filter(name__icontains="ТТН створена").order_by("order").first() if deal.funnel_id else None
            if _tc:
                _advance_deal_stage(deal, _tc.order, "ТТН створено в НП")
        except Exception:
            pass
        log_activity("deal", deal.id, "ТТН Нова Пошта", "Створено %s%s" % (ttn, (" · наложка %s грн" % int(cod)) if cod else ""), request.user, "НП")
        # фінальний чек НП (sell з relation_id+ttn) якщо є неоплачений-без-чека платіж що закриває суму
        try:
            _issue_checkbox_for_deal(deal, user=request.user)
        except Exception:
            pass
        sent = False
        if deal.contact_id:
            from apps.inbox.models import Conversation
            from apps.inbox.services import send_message
            conv = Conversation.objects.filter(contact_id=deal.contact_id, status="open").order_by("-last_message_at").first()
            if conv:
                try:
                    txt = "Ваше замовлення відправлено Новою Поштою! 📦\nНомер ТТН: %s\nВідстежити: https://novaposhta.ua/tracking/?cargo_number=%s" % (ttn, ttn)
                    if cod:
                        txt += "\nДо сплати при отриманні: %s грн" % int(cod)
                    send_message(conv, txt, user=request.user)
                    sent = True
                except Exception:
                    pass
        return Response({"ok": True, "ttn": ttn, "cost": doc.get("CostOnSite"), "est": doc.get("EstimatedDeliveryDate"), "sent": sent})

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
            data = claude_json(prompt, source="Подсказка ответа клиенту")
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(data)

    @action(detail=True, methods=["post"])
    def kp_save(self, request, pk=None):
        """Зберегти поточний КП/накладну (товари сделки) у ІСТОРІЮ — щоб бачити що прораховували клієнту."""
        deal = self.get_object()
        g = self._guard(deal)
        if g: return g
        from django.utils import timezone as _tz
        items = []
        subtotal = discount = total = 0.0
        for it in deal.items.select_related("product").all():
            qty = float(it.quantity or 0); price = float(it.price or 0); disc = float(it.discount_pct or 0)
            gross = qty * price; dsum = gross * disc / 100.0; line = gross - dsum
            subtotal += gross; discount += dsum; total += line
            items.append({"name": (it.product.name if it.product_id else ""), "qty": qty, "price": price, "discount_pct": disc, "total": round(line, 2)})
        snap = {"ts": _tz.now().isoformat(), "total": round(total, 2), "subtotal": round(subtotal, 2),
                "discount": round(discount, 2), "note": (request.data.get("note") or "")[:200],
                "by": (request.user.get_full_name() or request.user.username), "items": items}
        hist = list(deal.kp_history or []); hist.append(snap)
        deal.kp_history = hist; deal.save(update_fields=["kp_history"])
        from .models import log_activity
        log_activity("deal", deal.id, "КП збережено в історію", "Версія #%d · %s грн · %d позицій" % (len(hist), round(total, 2), len(items)), request.user, "Менеджер")
        return Response({"ok": True, "count": len(hist), "snap": snap})

    @action(detail=True, methods=["post"])
    def ship(self, request, pk=None):
        """Отгрузка: списание товаров сделки со склада + расход по себестоимости (COGS)."""
        from apps.warehouse.models import StockDocument
        from apps.warehouse.services import realize_deal
        deal = self.get_object()
        g = self._guard(deal, fulfill=True)
        if g: return g
        if not deal.items.exists():
            return Response({"detail": "В сделке нет товаров"}, status=status.HTTP_400_BAD_REQUEST)
        if StockDocument.objects.filter(kind="out", deal=deal).exists():
            return Response({"detail": "Сделку вже відвантажено"}, status=status.HTTP_409_CONFLICT)
        doc, cogs, created = realize_deal(deal, request.user)  # єдине списання по собівартості + COGS
        return Response({"ok": True, "cogs": float(cogs),
                         "deal": DealDetailSerializer(deal, context={"request": request}).data})


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
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
    permission_classes = [HasPermCode]
    required_perm = "analytics.view"

    def get(self, request):
        _u = request.user
        _see_all = _u.is_superuser or _u.can_see_all_deals()
        _deals_base = Deal.objects.all() if _see_all else Deal.objects.filter(owner=_u)
        _leads_base = Lead.objects.all() if _see_all else Lead.objects.filter(owner=_u)
        # доступ до воронок: співробітник бачить лише свої воронки СКРІЗЬ (список + цифри)
        _af = _u.allowed_funnel_ids()
        if _af is not None:
            _deals_base = _deals_base.filter(funnel_id__in=_af)
            _leads_base = _leads_base.filter(funnel_id__in=_af)
        funnel_id = request.GET.get("funnel")
        funnels = Funnel.objects.filter(is_lead_funnel=False)
        if _af is not None:
            funnels = funnels.filter(id__in=_af)
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
            "funnels": list((Funnel.objects.filter(is_lead_funnel=False) if _af is None else Funnel.objects.filter(is_lead_funnel=False, id__in=_af)).values("id", "name")),
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


def _staff_can_view(user):
    """Доступ до аналітики по співробітниках: адмін / roles.manage / finance.tab.salary (ЗП-KPI)."""
    if user.is_superuser:
        return True
    return (hasattr(user, "has_perm_code")
            and (user.has_perm_code("roles.manage") or user.has_perm_code("finance.tab.salary")))


def _month_range(period):
    """'YYYY-MM' → (перший день, останній день місяця). Порожнє → поточний місяць."""
    from datetime import date
    from django.utils import timezone
    import calendar
    today = timezone.localdate()
    try:
        y, m = period.split("-"); y, m = int(y), int(m)
    except Exception:
        y, m = today.year, today.month
    last = calendar.monthrange(y, m)[1]
    return date(y, m, 1), date(y, m, last)


class StaffAnalyticsView(APIView):
    """Аналітика по співробітниках за місяць: посещаемость (табель+зміни) + активність.
    GET /api/staff/analytics/?period=YYYY-MM[&dept=ID][&status=active|inactive|dismissed|all]
    Повертає рядки по кожному співробітнику + зведення по відділах."""
    def get(self, request):
        if not _staff_can_view(request.user):
            return Response({"detail": "Немає доступу"}, status=status.HTTP_403_FORBIDDEN)
        from apps.accounts.models import User
        from apps.finance.models import WorkSession, WorkDay
        from datetime import datetime, time
        from django.utils import timezone
        from .models import ActivityLog

        period = request.GET.get("period", "")
        d_from, d_to = _month_range(period)
        # межі для datetime-полів
        tz = timezone.get_current_timezone()
        dt_from = timezone.make_aware(datetime.combine(d_from, time.min), tz)
        dt_to = timezone.make_aware(datetime.combine(d_to, time.max), tz)

        qs = User.objects.filter(is_superuser=False).select_related("department", "role")
        st = (request.GET.get("status") or "").strip().lower()
        if st in ("active", "inactive", "dismissed"):
            qs = qs.filter(employment_status=st)
        elif st != "all":
            qs = qs.filter(is_active=True)
        dept = request.GET.get("dept")
        if dept:
            qs = qs.filter(department_id=dept)

        # хто ЗАРАЗ на робочому дні (зелений бейдж) — одним запитом
        live = dict(WorkSession.objects.filter(ended_at__isnull=True).values_list("user_id", "paused_at"))

        rows = []
        for u in qs:
            wds = WorkDay.objects.filter(user=u, date__gte=d_from, date__lte=d_to)
            by_status = {}
            for w in wds:
                by_status[w.status] = by_status.get(w.status, 0) + 1
            sessions = WorkSession.objects.filter(user=u, started_at__gte=dt_from, started_at__lte=dt_to)
            worked_seconds = sum(s.worked_seconds() for s in sessions)
            acts = ActivityLog.objects.filter(user=u, created_at__gte=dt_from, created_at__lte=dt_to).count()
            last_ses = WorkSession.objects.filter(user=u).order_by("-started_at").first()
            last_act = ActivityLog.objects.filter(user=u).order_by("-created_at").first()
            candidates = [x for x in (last_ses.started_at if last_ses else None,
                                      last_act.created_at if last_act else None) if x]
            last_seen = max(candidates) if candidates else None
            worked_days = by_status.get("worked", 0) + by_status.get("overtime", 0)
            rows.append({
                "id": u.id, "full_name": u.get_full_name() or u.username,
                "photo": u.photo or "", "position": u.position or "",
                "on_shift": u.id in live, "shift_paused": bool(live.get(u.id)),
                "department": u.department_id, "department_name": u.department.name if u.department else "—",
                "role_name": u.role.name if u.role else "—",
                "employment_status": u.employment_status, "dismissed_at": u.dismissed_at,
                "date_joined": u.date_joined,
                "worked_days": worked_days,
                "worked_hours": round(worked_seconds / 3600, 1),
                "sessions": sessions.count(),
                "sick": by_status.get("sick", 0), "vacation": by_status.get("vacation", 0),
                "absent": by_status.get("absent", 0), "dayoff": by_status.get("dayoff", 0),
                "overtime": by_status.get("overtime", 0),
                "actions": acts,
                "avg_hours_per_day": round(worked_seconds / 3600 / worked_days, 1) if worked_days else 0,
                "last_seen": last_seen,
            })
        rows.sort(key=lambda r: (-r["worked_hours"], -r["actions"]))

        # зведення по відділах
        depts = {}
        for r in rows:
            key = r["department_name"]
            d = depts.setdefault(key, {"department_name": key, "people": 0, "worked_hours": 0.0,
                                       "worked_days": 0, "actions": 0})
            d["people"] += 1; d["worked_hours"] += r["worked_hours"]
            d["worked_days"] += r["worked_days"]; d["actions"] += r["actions"]
        for d in depts.values():
            d["worked_hours"] = round(d["worked_hours"], 1)

        return Response({
            "period": {"from": d_from, "to": d_to},
            "rows": rows,
            "departments": sorted(depts.values(), key=lambda x: -x["worked_hours"]),
            "totals": {
                "people": len(rows),
                "worked_hours": round(sum(r["worked_hours"] for r in rows), 1),
                "worked_days": sum(r["worked_days"] for r in rows),
                "actions": sum(r["actions"] for r in rows),
            },
        })


class StaffActivityView(APIView):
    """Лента активності конкретного співробітника + таймлайн змін.
    GET /api/staff/activity/?user=ID[&from=YYYY-MM-DD&to=YYYY-MM-DD][&kind=]"""
    def get(self, request):
        if not _staff_can_view(request.user):
            return Response({"detail": "Немає доступу"}, status=status.HTTP_403_FORBIDDEN)
        from apps.accounts.models import User
        from apps.finance.models import WorkSession
        from datetime import datetime, time
        from django.utils import timezone
        from .models import ActivityLog

        uid = request.GET.get("user")
        if not uid:
            return Response({"detail": "Вкажіть user"}, status=status.HTTP_400_BAD_REQUEST)
        u = User.objects.filter(id=uid).select_related("department", "role").first()
        if not u:
            return Response({"detail": "Немає такого"}, status=status.HTTP_404_NOT_FOUND)

        tz = timezone.get_current_timezone()
        logs = ActivityLog.objects.filter(user=u)
        sess = WorkSession.objects.filter(user=u)
        f = request.GET.get("from"); tt = request.GET.get("to")
        if f:
            try:
                df = timezone.make_aware(datetime.combine(datetime.strptime(f, "%Y-%m-%d").date(), time.min), tz)
                logs = logs.filter(created_at__gte=df); sess = sess.filter(started_at__gte=df)
            except Exception:
                pass
        if tt:
            try:
                dt = timezone.make_aware(datetime.combine(datetime.strptime(tt, "%Y-%m-%d").date(), time.max), tz)
                logs = logs.filter(created_at__lte=dt); sess = sess.filter(started_at__lte=dt)
            except Exception:
                pass
        kind = request.GET.get("kind")
        if kind:
            logs = logs.filter(kind=kind)

        feed = [{"kind": a.kind, "object_id": a.object_id, "action": a.action,
                 "detail": a.detail, "at": a.created_at} for a in logs.order_by("-created_at")[:300]]
        sessions = [{"started_at": s.started_at, "ended_at": s.ended_at,
                     "worked_hours": round(s.worked_seconds() / 3600, 2),
                     "paused_seconds": s.paused_capped(),
                     "on_pause": bool(s.paused_at),
                     "pauses": s.pauses or []} for s in sess.order_by("-started_at")[:120]]
        return Response({
            "user": {"id": u.id, "full_name": u.get_full_name() or u.username,
                     "photo": u.photo or "", "position": u.position or "",
                     "about": u.about or "", "interests": u.interests or "",
                     "telegram": u.telegram or "", "birthday": u.birthday,
                     "department_name": u.department.name if u.department else "—",
                     "role_name": u.role.name if u.role else "—",
                     "employment_status": u.employment_status, "dismissed_at": u.dismissed_at,
                     "date_joined": u.date_joined},
            "feed": feed, "sessions": sessions,
        })


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


class _RolesManageOrRead(BasePermission):
    """Читати — будь-який авторизований; редагувати правила — лише керівник."""
    def has_permission(self, request, view):
        u = request.user
        if request.method in SAFE_METHODS:
            return bool(u and u.is_authenticated)
        return bool(u and (getattr(u, "is_superuser", False) or (hasattr(u, "has_perm_code") and u.has_perm_code("roles.manage"))))



def _advance_after_payment(deal, reason, actor="Автоматизація", create_wh=True):
    """Після оплати: тип оплати «Бронь» → стадія «Заброньовано»,
    інакше → «Оплату отримано» (пошук стадії ЗА НАЗВОЮ у воронці сделки)."""
    is_bron = "брон" in (deal.pay_type or "").lower()
    names = ["заброньов"] if is_bron else ["оплату отримано", "оплата отримано", "оплата отримана", "оплата/предоплата"]
    target = None
    for nm in names:
        target = deal.funnel.stages.filter(name__icontains=nm).order_by("order").first()
        if target:
            break
    if target:
        return _advance_deal_stage(deal, target.order, reason, actor, create_wh=create_wh)
    return _advance_deal_stage(deal, 3, reason, actor, create_wh=create_wh)


def sync_deal_payment_from_tx(tx):
    """Дохід у журналі/картці клієнта, привʼязаний до сделки = платіж клієнта.
    Створюємо Payment (щоб «Оплачено» сделки враховувало його) і рухаємо стадію вперед.
    Нічого не робимо, якщо: не income / без сделки / у операції вже є Payment (щоб не дублювати accept_payment).
    Склад авто-задачі НЕ створюємо (create_wh=False) — щоб журнальний запис не тригерив відвантаження."""
    try:
        from decimal import Decimal as _D
        if getattr(tx, "direction", "") != "in" or not getattr(tx, "deal_id", None) or getattr(tx, "payment_id", None):
            return
        deal = tx.deal
        amount = tx.amount_uah or tx.amount or _D("0")
        if amount is None or amount <= 0:
            return
        pay = Payment.objects.create(deal=deal, provider="cash", amount=amount, is_paid=True)
        tx.payment = pay
        tx.save(update_fields=["payment"])
        paid = sum((p.amount for p in Payment.objects.filter(deal=deal, is_paid=True)), _D("0"))
        if deal.amount and paid >= deal.amount:
            _advance_after_payment(deal, "оплата отримана повністю (журнал/картка клієнта)", create_wh=False)
        elif paid > 0:
            _advance_deal_stage(deal, 2, "часткова оплата (журнал/картка клієнта)", create_wh=False)
    except Exception:
        pass

def _manage_or_read(*extra_codes):
    """Читати — будь-який авторизований; редагувати — superuser / roles.manage / делегований settings-код."""
    class _P(BasePermission):
        def has_permission(self, request, view):
            u = request.user
            if request.method in SAFE_METHODS:
                return bool(u and u.is_authenticated)
            if not (u and u.is_authenticated):
                return False
            if getattr(u, "is_superuser", False):
                return True
            if hasattr(u, "has_perm_code"):
                return u.has_perm_code("roles.manage") or any(u.has_perm_code(c) for c in extra_codes)
            return False
    return _P


class AutomationRuleViewSet(viewsets.ModelViewSet):
    queryset = AutomationRule.objects.select_related("funnel", "from_stage", "to_stage").all()
    serializer_class = __import__("apps.crm.serializers", fromlist=["AutomationRuleSerializer"]).AutomationRuleSerializer
    permission_classes = [_manage_or_read("settings.automations")]
    filterset_fields = ["funnel", "from_stage", "trigger", "enabled"]


class GlobalRuleViewSet(viewsets.ModelViewSet):
    queryset = GlobalRule.objects.all()
    serializer_class = __import__("apps.crm.serializers", fromlist=["GlobalRuleSerializer"]).GlobalRuleSerializer
    permission_classes = [_manage_or_read("settings.rules")]
    filterset_fields = ["block", "funnel", "enabled"]

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_create(self, serializer):
        serializer.save(updated_by=self.request.user)


class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.select_related("department", "assignee", "deal", "lead").all()
    serializer_class = __import__("apps.crm.serializers", fromlist=["TaskSerializer"]).TaskSerializer
    filterset_fields = ["kind", "status", "department", "assignee", "deal", "lead"]

    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        see_all = u.is_superuser or u.can_see_all_deals()
        if not see_all or self.request.query_params.get("mine") == "1":
            from django.db.models import Q
            qs = qs.filter(Q(assignee=u) | Q(department_id=getattr(u, "department_id", None)))
        return qs

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        t = self.get_object(); t.assignee = request.user
        if t.status in ("proposed", "open"):
            t.status = "in_progress"
        t.save(update_fields=["assignee", "status"])
        return Response(self.get_serializer(t).data)

    @action(detail=True, methods=["post"])
    def done(self, request, pk=None):
        t = self.get_object(); t.status = "done"; t.save(update_fields=["status"])
        return Response(self.get_serializer(t).data)


class AiUsageView(APIView):
    """Детальний звіт витрат на Claude: по днях, механіках, моделях."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        u = request.user
        if not (u.is_superuser or u.has_perm_code("settings.agent") or u.has_perm_code("roles.manage")):
            return Response({"detail": "Немає права «AI-агент (модель, автономність, витрати)»"}, status=status.HTTP_403_FORBIDDEN)
        from apps.crm.models import AiUsage
        from django.db.models.functions import TruncDate
        from django.db.models import Sum, Count, Max
        qs = AiUsage.objects.all()
        dn = request.query_params.get("days")
        if dn and dn.isdigit():
            from django.utils import timezone
            from datetime import timedelta
            qs = qs.filter(created_at__gte=timezone.now() - timedelta(days=int(dn)))
        days = list(qs.annotate(d=TruncDate("created_at")).values("d").annotate(
            cost=Sum("cost_usd"), calls=Count("id")).order_by("-d")[:45])
        by_src = list(qs.values("source").annotate(cost=Sum("cost_usd"), calls=Count("id"),
            itok=Sum("in_tok"), otok=Sum("out_tok"), note=Max("note")).order_by("-cost"))
        by_model = list(qs.values("model").annotate(cost=Sum("cost_usd"), calls=Count("id")).order_by("-cost"))
        day_src = list(qs.annotate(d=TruncDate("created_at")).values("d", "source").annotate(
            cost=Sum("cost_usd"), calls=Count("id")).order_by("-d", "-cost")[:300])
        tot = qs.aggregate(cost=Sum("cost_usd"), calls=Count("id"))
        est_c = qs.filter(est=True).aggregate(s=Sum("cost_usd"))["s"] or 0
        live_c = qs.filter(est=False).aggregate(s=Sum("cost_usd"))["s"] or 0
        return Response({"days": days, "by_source": by_src, "by_model": by_model, "day_source": day_src,
                         "total_cost": tot["cost"] or 0, "total_calls": tot["calls"] or 0,
                         "est_cost": est_c, "live_cost": live_c})


class AgentConfigView(APIView):
    permission_classes = [_manage_or_read("settings.agent")]

    def get(self, request):
        c = AgentConfig.get()
        return Response({"enabled": c.enabled, "autonomous": c.autonomous, "auto_on_reply": c.auto_on_reply,
                         "model": c.model, "system_extra": c.system_extra,
                         "priority_enabled": c.priority_enabled, "priority_model": c.priority_model,
                         "analyst_model": c.analyst_model, "suggest_model": c.suggest_model,
                         "cache_enabled": c.cache_enabled, "analyst_auto": c.analyst_auto})

    def post(self, request):
        c = AgentConfig.get()
        for f in ["enabled", "autonomous", "auto_on_reply", "model", "system_extra", "priority_enabled", "priority_model", "analyst_model", "suggest_model", "cache_enabled", "analyst_auto"]:
            if f in request.data:
                setattr(c, f, request.data[f])
        c.save()
        return Response({"ok": True})


def _upsell_test_kit(deal):
    """Допродаж інструментів після ОПЛАТИ тест-набору.
    Шлеться ОДИН раз (прапор у deal.np_data), тільки якщо ВСІ товари сделки — тест-набори.
    Ціни тягнуться ЖИВЦЕМ з номенклатури (конфіг: Інтеграції → upsell_test_kit)."""
    from apps.integrations.models import IntegrationSettings
    from apps.warehouse.models import Product
    from apps.inbox.models import Conversation
    from apps.inbox.services import send_message
    from .models import log_activity
    nd = dict(deal.np_data or {})
    if nd.get("upsell_sent"):
        return
    items = list(deal.items.select_related("product__category"))
    if not items:
        return
    for it in items:
        if not it.product_id:
            return  # своя позиція — точно не тест-набір
        cat = (it.product.category.name if it.product.category_id else "") or ""
        if "тестов" not in cat.lower() and "тест-наб" not in it.product.name.lower() and "тестовий набір" not in it.product.name.lower():
            return  # у сделці не тільки тест-набори — допродаж не шлемо
    st = IntegrationSettings.objects.filter(provider="upsell_test_kit").first()
    cfg = (st.config or {}) if st else {}
    if st and not st.is_active:
        return
    ids = cfg.get("product_ids") or []
    prods = list(Product.objects.filter(id__in=ids, is_active=True)) if ids else []
    if not prods:
        return
    order = {pid: i for i, pid in enumerate(ids)}
    prods.sort(key=lambda p: order.get(p.id, 99))
    lines = "\n".join("%d. %s — %d грн" % (i + 1, p.name, round(float(p.price)))
                       for i, p in enumerate(prods))
    msg = ("Дякуємо за оплату! 💚 Ваш тест-набір вже готуємо.\n\n"
           "Підкажіть, чи є у вас інструменти для нанесення? Для Galateya та шовків потрібні "
           "пензель-макловиця і пензель для декору — з ними малюнок виходить як у дизайнерських "
           "інтерʼєрах, і вони знадобляться для основного обʼєму.\n\n"
           "Можемо додати до вашої відправки, щоб все приїхало разом:\n" + lines +
           "\n\nНапишіть номери — додамо 😊")
    conv = Conversation.objects.filter(contact_id=deal.contact_id, status="open").order_by("-last_message_at").first() if deal.contact_id else None
    if conv is None:
        return
    try:
        send_message(conv, msg, user=None)
        nd["upsell_sent"] = True
        deal.np_data = nd
        deal.save(update_fields=["np_data"])
        log_activity("deal", deal.id, "Допродаж (інструменти)", "надіслано список інструментів після оплати тест-набору", None, "AI-автоматика")
    except Exception:
        pass


class LiqPayCallbackView(APIView):
    """Callback LiqPay: підтвердження реальної оплати → Payment(paid) → стадія Оплату отримано."""
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        from django.conf import settings as _s
        from .liqpay import verify, decode_data
        from .models import log_activity
        data = request.data.get("data"); sig = request.data.get("signature")
        if not verify(data, sig, getattr(_s, "LIQPAY_PRIVATE_KEY", "")):
            return Response({"detail": "bad signature"}, status=status.HTTP_403_FORBIDDEN)
        try:
            d = decode_data(data)
        except Exception:
            return Response({"detail": "bad data"}, status=status.HTTP_400_BAD_REQUEST)
        st = d.get("status")
        order_id = str(d.get("order_id") or "")
        amount = Decimal(str(d.get("amount") or 0))
        if st not in ("success", "sandbox", "subscribed"):  # #6 wait_accept НЕ вважати оплатою
            return Response({"ok": True, "ignored": st})
        parts = order_id.split("-")
        if len(parts) < 2 or parts[0] != "WCCRM":
            return Response({"ok": True, "no_deal": order_id})
        deal = Deal.objects.filter(id=parts[1]).first()
        if not deal:
            return Response({"ok": True, "no_deal": order_id})
        pay_id = str(d.get("payment_id") or d.get("transaction_id") or order_id)
        from django.db import transaction as _txn
        with _txn.atomic():
            dlock = Deal.objects.select_for_update().get(pk=deal.pk)
            if pay_id and Payment.objects.filter(external_id=pay_id).exists():
                return Response({"ok": True, "dup": True})
            pay = Payment.objects.create(deal=dlock, provider="liqpay", amount=amount, is_paid=True, external_id=pay_id)
            try:
                from apps.finance.services import record_income, liqpay_account
                record_income(amount, deal=dlock, payment=pay, account=liqpay_account(), category="Онлайн (Instagram/TikTok/сайт)")  # правило: LiqPay-дохід → Онлайн + напрям Декор (авто з категорії)
                # той самий платіж міг бути зафіксований менеджером вручну заздалегідь → сигналізуємо
                try:
                    from django.utils import timezone as _tzz
                    from datetime import timedelta as _tdd
                    twin = Payment.objects.filter(deal=dlock, is_paid=True, amount=amount,
                                                  created_at__gte=_tzz.now() - _tdd(hours=48)).exclude(provider="liqpay").exclude(id=pay.id).first()
                    if twin:
                        from .models import Task as _Task, log_activity as _la
                        _Task.objects.create(title="⚠️ Можливий ДУБЛЬ оплати по угоді #%s" % dlock.id,
                                             kind="manager", body="Клієнт оплатив %s грн через LiqPay, але така ж сума вже була прийнята вручну (%s). Перевір: якщо це ТА САМА оплата — зніми ручний платіж і сторнуй його чек у Checkbox." % (amount, twin.provider),
                                             deal=dlock, assignee=dlock.owner)
                        _la("deal", dlock.id, "⚠️ Можливий дубль оплати", "LiqPay %s грн + ручна фіксація %s грн (%s) за 48 год" % (amount, twin.amount, twin.provider), None, "Автоматика")
                except Exception:
                    pass
            except Exception:
                pass
            paid = sum((p.amount for p in Payment.objects.filter(deal=dlock, is_paid=True)), Decimal("0"))
            _paid_advanced = False
            if dlock.amount and paid >= dlock.amount:
                _advance_after_payment(dlock, "LiqPay оплата отримана")
                _paid_advanced = True
            elif (dlock.pay_type or "") == "prepay_np" and paid > 0:
                # передоплата + післяплата НП: АВАНС вже рухає на «Оплату отримано»
                # (решту збере Нова Пошта наложкою — фінальний чек при отриманні)
                _advance_after_payment(dlock, "LiqPay аванс отримано (решта — післяплата НП)")
                _paid_advanced = True
            # Знімаємо AI-AutoTopup marker → передаємо естафету run_agent
            if _paid_advanced:
                try:
                    _cf = list(dlock.card_fields or [])
                    _changed = False
                    for _f in _cf:
                        if _f.get("label") == "AI-AutoTopup" and _f.get("value") == "waiting_for_payment":
                            _f["value"] = "paid"
                            from django.utils import timezone as _tzp
                            _f["paid_at"] = _tzp.now().isoformat()
                            _changed = True
                    if _changed:
                        dlock.card_fields = _cf
                        dlock.save(update_fields=["card_fields"])
                except Exception:
                    pass
            deal = dlock
        log_activity("deal", deal.id, "Оплата LiqPay", "%s грн отримано (callback, txn %s)" % (amount, pay_id[:12]), None, "LiqPay")
        try:
            _issue_checkbox_for_deal(deal, user=None)
        except Exception:
            pass
        try:
            _upsell_test_kit(deal)  # допродаж інструментів після оплати тест-набору
        except Exception:
            pass
        return Response({"ok": True})


class ContactFormConfigView(APIView):
    """Налаштування обовʼязкових полів контакту. Редагувати може лише адмін або призначений співробітник."""
    permission_classes = [IsAuthenticated]

    def _cfg(self):
        from apps.integrations.models import IntegrationSettings
        obj, _ = IntegrationSettings.objects.get_or_create(provider="contact_form", defaults={"config": {"required": [], "editors": []}})
        return obj, (obj.config or {})

    def _build(self, request, cfg):
        u = request.user
        is_admin = bool(u.is_superuser or (hasattr(u, "has_perm_code") and u.has_perm_code("roles.manage")))
        editors = cfg.get("editors", []) or []
        return Response({"required": cfg.get("required", []), "editors": editors,
                         "can_edit": is_admin or (hasattr(u, "has_perm_code") and u.has_perm_code("contact.fields.config")) or (u.id in editors), "is_admin": is_admin})

    def get(self, request):
        _, cfg = self._cfg()
        return self._build(request, cfg)

    def patch(self, request):
        obj, cfg = self._cfg()
        u = request.user
        is_admin = bool(u.is_superuser or (hasattr(u, "has_perm_code") and u.has_perm_code("roles.manage")))
        editors = cfg.get("editors", []) or []
        if not (is_admin or (hasattr(u, "has_perm_code") and u.has_perm_code("contact.fields.config")) or u.id in editors):
            return Response({"detail": "Тільки адмін або призначений співробітник"}, status=status.HTTP_403_FORBIDDEN)
        if "required" in request.data:
            cfg["required"] = list(request.data.get("required") or [])
        if "editors" in request.data and is_admin:
            cfg["editors"] = list(request.data.get("editors") or [])
        obj.config = cfg
        obj.save()
        return self._build(request, cfg)


class ChangeLogView(APIView):
    """Історія змін CRM (сторінка «Що нового»).
    GET — будь-який залогінений читає; POST — лише суперюзер додає запис."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import ChangeLogEntry
        rows = ChangeLogEntry.objects.all()[:500]
        return Response([{"id": e.id, "date": e.d.isoformat(), "section": e.section, "title": e.title, "body": e.body} for e in rows])

    def post(self, request):
        if not request.user.is_superuser:
            return Response({"detail": "Тільки адміністратор"}, status=status.HTTP_403_FORBIDDEN)
        from django.utils import timezone
        from .models import ChangeLogEntry
        d = request.data
        e = ChangeLogEntry.objects.create(d=(d.get("date") or timezone.now().date()),
                                          section=(d.get("section") or "")[:48],
                                          title=(d.get("title") or "")[:200], body=(d.get("body") or ""))
        return Response({"id": e.id}, status=status.HTTP_201_CREATED)
