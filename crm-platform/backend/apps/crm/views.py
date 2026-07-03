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
        obj = serializer.save()
        from .models import log_activity
        u = getattr(self.request, "user", None)
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
            if self.log_kind == "deal" and obj.stage and "оплату отримано" in (obj.stage.name or "").lower():
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
        DealItem.objects.create(deal=deal, product=prod, quantity=qty, price=prod.price, cost=prod.cost or 0)
        added.append("%s x %s" % (prod.name[:40], qty))
    if not added:
        return {"ok": False, "missing": missing, "msg": "товар не знайдено в номенклатурі"}
    items = list(deal.items.all())
    total = sum((i.total for i in items), Decimal("0"))
    deal.amount = total
    deal.save(update_fields=["amount"])
    conv = Conversation.objects.filter(contact_id=deal.contact_id, status="open").order_by("-last_message_at").first() if deal.contact_id else None

    def _g(x):
        return ("%g" % float(x))

    lines = ["\u2022 %s \u2014 %s \u00d7 %s \u0433\u0440\u043d = %s \u0433\u0440\u043d" % (i.product.name[:55], _g(i.quantity), _g(i.price), _g(i.total)) for i in items]
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
        return None
    goods = []
    for it in deal.items.all():
        nm = (getattr(it.product, "name", None) or "Товар")[:200]
        qty = float(it.quantity) or 1
        unit_kop = int(round(float(it.total) / qty * 100))  # ціна за одиницю ЗІ знижкою (щоб чек = сплаченому)
        goods.append({"good": {"code": str(getattr(it, "product_id", None) or it.id), "name": nm,
                               "price": unit_kop},
                      "quantity": int(round(qty * 1000))})
    if not goods:
        goods = [{"good": {"code": "DEAL-%s" % deal.id, "name": (deal.title or "Замовлення Wallcov")[:200],
                           "price": int(round(float(deal.amount or 0) * 100))}, "quantity": 1000}]
    goods_total = sum(g["good"]["price"] * g["quantity"] // 1000 for g in goods)
    cum = sum((p.amount for p in _P.objects.filter(deal=deal, is_paid=True, id__lte=pay.id)), _D("0"))
    cum_kop = int(round(float(cum) * 100))
    this_kop = int(round(float(pay.amount) * 100))
    if this_kop <= 0:
        return None
    pm = "CASH" if pay.provider in ("cash", "np") else "CASHLESS"
    pay_label = {"liqpay": "\u0406\u043d\u0442\u0435\u0440\u043d\u0435\u0442 \u0435\u043a\u0432\u0430\u0439\u0440\u0438\u043d\u0433", "terminal": "\u041a\u0430\u0440\u0442\u043a\u0430", "card": "\u041a\u0430\u0440\u0442\u043a\u0430"}.get(pay.provider)
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
                items = ", ".join(i.product.name[:40] for i in deal.items.all()[:3])
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


def _advance_deal_stage(deal, target_order, reason, actor="Автоматизація"):
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
    if "\u043e\u043f\u043b\u0430\u0442\u0443 \u043e\u0442\u0440\u0438\u043c\u0430\u043d\u043e" in (target.name or "").lower():
        try:
            from apps.warehouse.services import create_warehouse_job
            create_warehouse_job(deal)
        except Exception:
            pass
    if getattr(target, "is_won", False):
        try:
            from apps.warehouse.services import realize_deal
            realize_deal(deal, None)  # успішна стадія → списання товару + документ реалізації
        except Exception:
            pass
    return True


class DealViewSet(ActivityLogMixin, ScopedByRoleMixin, viewsets.ModelViewSet):
    log_kind = "deal"
    queryset = Deal.objects.select_related("owner", "contact", "funnel", "stage")
    serializer_class = DealSerializer
    view_all_method = "can_see_all_deals"
    delete_perm = "deal.delete"
    edit_perm = "deal.edit.all"

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
        from apps.warehouse.models import Product
        product = Product.objects.get(pk=request.data["product"])
        qty = Decimal(str(request.data.get("quantity", 1)))
        price = Decimal(str(request.data.get("price", product.price)))
        disc = Decimal(str(request.data.get("discount_pct", 0) or 0))
        if qty <= 0 or price < 0 or disc < 0 or disc > 100:  # #14 захист від дурня/від'ємних
            return Response({"detail": "Кількість > 0, ціна ≥ 0, знижка 0–100%."}, status=status.HTTP_400_BAD_REQUEST)
        DealItem.objects.create(deal=deal, product=product, quantity=qty, price=price, cost=(product.cost or 0),
                                discount_pct=disc, reserved=bool(request.data.get("reserved")))
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
        for f in ("price", "quantity", "discount_pct"):
            val = request.data.get(f)
            if val not in (None, ""):
                try:
                    setattr(it, f, Decimal(str(val)))
                except Exception:
                    pass
        if it.quantity <= 0 or it.price < 0 or (it.discount_pct or 0) < 0 or (it.discount_pct or 0) > 100:  # #14
            return Response({"detail": "Кількість > 0, ціна ≥ 0, знижка 0–100%."}, status=status.HTTP_400_BAD_REQUEST)
        it.save()
        self._recalc_amount(deal)
        return Response(DealDetailSerializer(deal, context={"request": request}).data)

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
        from django.utils import timezone as _tz
        from datetime import timedelta as _td
        from django.db import transaction as _txn
        with _txn.atomic():
            dlock = Deal.objects.select_for_update().get(pk=deal.pk)
            if Payment.objects.filter(deal=dlock, amount=amount, provider=provider, created_at__gte=_tz.now() - _td(seconds=180)).exists():  # #7 вікно захисту від задвоєння 3 хв
                return Response(DealDetailSerializer(dlock, context={"request": request}).data)
            pay = Payment.objects.create(deal=dlock, provider=provider, amount=amount, is_paid=True)
            record_income(amount, deal=dlock, account=account, payment=pay)
            paid = sum((p.amount for p in Payment.objects.filter(deal=dlock, is_paid=True)), Decimal("0"))
            pt = (dlock.pay_type or "").lower()
            is_np = any(x in pt for x in ["np", "післяплат", "послеоплат", "prepay", "передопл"])
            if dlock.amount and paid >= dlock.amount:
                _advance_deal_stage(dlock, 3, "оплата отримана повністю")  # → Оплату отримано
            elif paid > 0:
                if is_np:
                    _advance_deal_stage(dlock, 3, "передоплату отримано (решта — післяплата НП)")
                else:
                    _advance_deal_stage(dlock, 2, "часткова оплата (тип Повна — чекаємо решту)")
            deal = dlock
        # авто-чек Checkbox поза транзакцією; для «термінал» чек б'є застосунок Checkbox (Tap to Pay) — НЕ дублюємо
        cbres = None
        if provider != "terminal":
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
        lines = ["\u2022 %s \u2014 %s \u00d7 %s \u0433\u0440\u043d = %s \u0433\u0440\u043d" % (i.product.name[:55], _g(i.quantity), _g(i.price), _g(i.total)) for i in items]
        quote = "\U0001f9fe \u0412\u0430\u0448 \u043f\u0440\u043e\u0440\u0430\u0445\u0443\u043d\u043e\u043a:\n" + "\n".join(lines) + ("\n\n\u0420\u0430\u0437\u043e\u043c \u0434\u043e \u0441\u043f\u043b\u0430\u0442\u0438: %s \u0433\u0440\u043d" % _g(total))
        intro = "\u041f\u0456\u0434\u0433\u043e\u0442\u0443\u0432\u0430\u043b\u0438 \u0434\u043b\u044f \u0432\u0430\u0441 \u043f\u0440\u043e\u0440\u0430\u0445\u0443\u043d\u043e\u043a \U0001f60a"
        try:
            from .ai import claude_json
            conv0 = Conversation.objects.filter(contact_id=deal.contact_id).order_by("-last_message_at").first() if deal.contact_id else None
            dlg = ""
            if conv0:
                dmsgs = list(conv0.messages.order_by("id").values("direction", "text"))[-12:]
                dlg = "\n".join((("\u041a\u043b\u0456\u0454\u043d\u0442: " if m["direction"] == "in" else "\u041c\u0438: ") + (m["text"] or "")) for m in dmsgs if m.get("text"))
            nm = ", ".join(i.product.name[:40] for i in items[:3])
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
            text = "Реквізити для оплати 💳\nIBAN: %s\nПризначення: Оплата замовлення #%s\nСума: %s грн\nПісля оплати одразу почнемо готувати замовлення 😊" % (iban, deal.id, amount)
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
            # РОП пише тепле повідомлення (Claude) на основі діалогу
            body = "Ваше замовлення готове до оплати 😊"
            try:
                from apps.inbox.models import Conversation as _Cv
                from .ai import claude_json
                msgs = []
                if deal.contact_id:
                    _c = _Cv.objects.filter(contact_id=deal.contact_id).order_by("-last_message_at").first()
                    if _c:
                        msgs = list(_c.messages.order_by("id").values("direction", "text"))[-12:]
                dlg = "\n".join((("Клієнт: " if m["direction"] == "in" else "Ми: ") + (m["text"] or "")) for m in msgs if m.get("text"))
                items = ", ".join(i.product.name[:40] for i in deal.items.all()[:3])
                pr = ("Ти РОП Wallcov (декоративні покриття). Напиши КОРОТКЕ (2-3 речення) тепле повідомлення клієнту "
                      "що замовлення готове до оплати. Подякуй, згадай що замовив, додай що після оплати одразу готуємо/відправляємо. "
                      "БЕЗ посилання і БЕЗ суми (я додам сам). ЗАВЖДИ УКРАЇНСЬКОЮ мовою (навіть якщо клієнт пише російською). JSON {\"message\":\"...\"}.\n"
                      "Замовлення: %s\nДіалог:\n%s") % (items or "тест-набір", dlg or "(нема)")
                r = claude_json(pr, source="Помощник CRM (советы и расчёты)")
                if r.get("message"):
                    body = r["message"].strip()
            except Exception:
                pass
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
        _advance_deal_stage(deal, 2, "надіслано посилання на оплату")  # Домовились про оплату
        log_activity("deal", deal.id, "Посилання на оплату", "%s · %s грн · %s" % (kind, amount, "надіслано клієнту" if sent else "НЕ надіслано (немає відкритого чату)"), request.user, "Менеджер")
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
        if not ref or len(q) < 2:
            return Response([])
        try:
            r = ad.np_streets(ref, q)
            rows = (r or {}).get("data") or []
            items = rows[0].get("Addresses", []) if rows else []
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
        if not (name and phone and city_name and wh_number):
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
            "ServiceType": p.get("service_type") or "WarehouseWarehouse",
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
            "RecipientAddressName": wh_number,
        }
        if cod > 0:
            props["BackwardDeliveryData"] = [{"PayerType": "Recipient", "CargoType": "Money", "RedeliveryString": str(int(round(cod)))}]
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


class _RolesManageOrRead(BasePermission):
    """Читати — будь-який авторизований; редагувати правила — лише керівник."""
    def has_permission(self, request, view):
        u = request.user
        if request.method in SAFE_METHODS:
            return bool(u and u.is_authenticated)
        return bool(u and (getattr(u, "is_superuser", False) or (hasattr(u, "has_perm_code") and u.has_perm_code("roles.manage"))))


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
        deal = serializer.save(updated_by=self.request.user)
        st = getattr(deal, "stage", None)
        if st and (getattr(st, "is_won", False) or getattr(st, "is_lost", False)) and not deal.closed_at:
            from django.utils import timezone as _tz
            deal.closed_at = _tz.now(); deal.save(update_fields=["closed_at"])

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
                from apps.finance.services import record_income
                record_income(amount, deal=dlock, payment=pay)
            except Exception:
                pass
            paid = sum((p.amount for p in Payment.objects.filter(deal=dlock, is_paid=True)), Decimal("0"))
            if dlock.amount and paid >= dlock.amount:
                _advance_deal_stage(dlock, 3, "LiqPay оплата отримана")
            deal = dlock
        log_activity("deal", deal.id, "Оплата LiqPay", "%s грн отримано (callback, txn %s)" % (amount, pay_id[:12]), None, "LiqPay")
        try:
            _issue_checkbox_for_deal(deal, user=None)
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
