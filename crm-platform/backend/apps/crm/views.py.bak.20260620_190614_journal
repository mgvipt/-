from decimal import Decimal
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Company, Contact, Funnel, Stage, Lead, Deal, DealItem, Payment
from .serializers import (
    CompanySerializer, ContactSerializer, FunnelSerializer, StageSerializer,
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
            qs = qs.filter(owner=user)
        return qs

    def perform_create(self, serializer):
        # новый лид/сделка по умолчанию закрепляется за создателем
        serializer.save(owner=serializer.validated_data.get("owner") or self.request.user)


class ContactViewSet(viewsets.ModelViewSet):
    queryset = Contact.objects.all()
    serializer_class = ContactSerializer
    search_fields = ["first_name", "last_name", "phone", "email"]


class CompanyViewSet(viewsets.ModelViewSet):
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    search_fields = ["name", "edrpou"]


class FunnelViewSet(viewsets.ModelViewSet):
    serializer_class = FunnelSerializer
    queryset = Funnel.objects.prefetch_related("stages").all()

    def get_queryset(self):
        qs = super().get_queryset()
        allowed = self.request.user.allowed_funnel_ids()
        return qs if allowed is None else qs.filter(id__in=allowed)


class StageViewSet(viewsets.ModelViewSet):
    queryset = Stage.objects.all()
    serializer_class = StageSerializer
    filterset_fields = ["funnel"]


class LeadViewSet(ScopedByRoleMixin, viewsets.ModelViewSet):
    queryset = Lead.objects.select_related("owner", "contact", "funnel", "stage")
    serializer_class = LeadSerializer
    view_all_method = "can_see_all_leads"
    filterset_fields = ["funnel", "stage", "source", "is_seen", "owner"]
    search_fields = ["title", "contact__phone", "contact__first_name", "contact__last_name"]


class DealViewSet(ScopedByRoleMixin, viewsets.ModelViewSet):
    queryset = Deal.objects.select_related("owner", "contact", "funnel", "stage")
    serializer_class = DealSerializer
    view_all_method = "can_see_all_deals"
    filterset_fields = ["funnel", "stage", "source", "owner"]
    search_fields = ["title", "contact__phone"]

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
        DealItem.objects.create(deal=deal, product=product, quantity=qty, price=price)
        self._recalc_amount(deal)
        return Response(DealDetailSerializer(deal, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def remove_item(self, request, pk=None):
        deal = self.get_object()
        DealItem.objects.filter(deal=deal, pk=request.data.get("item")).delete()
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


from rest_framework.views import APIView
from django.db.models import Count, Sum, Avg


class AnalyticsView(APIView):
    """Сводка по продажам: KPI + воронка по стадиям."""
    def get(self, request):
        funnel_id = request.GET.get("funnel")
        funnels = Funnel.objects.filter(is_lead_funnel=False)
        if funnel_id:
            funnels = funnels.filter(id=funnel_id)
        funnel = funnels.first()

        leads_total = Lead.objects.count()
        deals = Deal.objects.all()
        if funnel:
            deals = deals.filter(funnel=funnel)
        deals_total = deals.count()
        won = deals.filter(stage__is_won=True)
        revenue = won.aggregate(s=Sum("amount"))["s"] or 0
        avg_check = won.aggregate(a=Avg("amount"))["a"] or 0
        conv = round((deals_total / leads_total * 100), 1) if leads_total else 0

        stages = []
        if funnel:
            for st in funnel.stages.all():
                cnt = deals.filter(stage=st).count()
                amt = deals.filter(stage=st).aggregate(s=Sum("amount"))["s"] or 0
                stages.append({"name": st.name, "color": st.color, "count": cnt, "amount": float(amt)})

        # топ менеджеров
        managers = list(deals.values("owner__first_name", "owner__last_name")
                        .annotate(deals=Count("id"), sum=Sum("amount")).order_by("-sum")[:5])
        return Response({
            "leads_total": leads_total, "deals_total": deals_total,
            "conversion": conv, "revenue": float(revenue), "avg_check": float(avg_check),
            "funnel": funnel.name if funnel else "", "stages": stages,
            "managers": [{"name": (m["owner__first_name"] or "") + " " + (m["owner__last_name"] or ""),
                          "deals": m["deals"], "sum": float(m["sum"] or 0)} for m in managers],
            "funnels": list(Funnel.objects.filter(is_lead_funnel=False).values("id", "name")),
        })
