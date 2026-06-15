from rest_framework import viewsets
from .models import Company, Contact, Funnel, Stage, Lead, Deal, Payment
from .serializers import (
    CompanySerializer, ContactSerializer, FunnelSerializer, StageSerializer,
    LeadSerializer, DealSerializer, PaymentSerializer,
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


class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.select_related("deal")
    serializer_class = PaymentSerializer
    filterset_fields = ["deal", "provider", "is_paid"]
