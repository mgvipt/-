from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.common.permissions import HasPermCode
from apps.crm.models import Deal
from .models import IntegrationSettings
from . import adapters

PROVIDERS = {
    "liqpay": ["public_key", "private_key", "currency"],
    "checkbox": ["token", "license_key"],
    "novaposhta": ["api_key", "sender_ref", "sender_city_ref", "sender_contact", "sender_phone"],
}


def _mask(v: str) -> str:
    if not v or len(v) < 6:
        return "••••" if v else ""
    return v[:3] + "•••" + v[-2:]


from rest_framework.permissions import BasePermission as _BasePerm


class ManagePerm(_BasePerm):
    """roles.manage АБО делеговане settings.integrations (superuser — завжди)."""
    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        if getattr(u, "is_superuser", False):
            return True
        return hasattr(u, "has_perm_code") and (u.has_perm_code("roles.manage") or u.has_perm_code("settings.integrations"))


class IntegrationSettingsView(APIView):
    """Чтение (с маскировкой ключей) и сохранение настроек интеграций."""
    permission_classes = [ManagePerm]

    def get(self, request):
        out = []
        for prov, fields in PROVIDERS.items():
            obj = IntegrationSettings.objects.filter(provider=prov).first()
            cfg = (obj.config if obj else {}) or {}
            masked = {f: _mask(str(cfg.get(f, ""))) for f in fields}
            out.append({"provider": prov, "fields": fields, "values": masked,
                        "is_active": obj.is_active if obj else False})
        return Response(out)

    def post(self, request):
        prov = request.data.get("provider")
        if prov not in PROVIDERS:
            return Response({"detail": "Неизвестный провайдер"}, status=400)
        obj, _ = IntegrationSettings.objects.get_or_create(provider=prov)
        cfg = obj.config or {}
        # обновляем только переданные непустые поля (чтобы не затирать ключи маской)
        for f in PROVIDERS[prov]:
            val = request.data.get(f)
            if val:
                cfg[f] = val
        obj.config = cfg
        if "is_active" in request.data:
            obj.is_active = bool(request.data["is_active"])
        obj.save()
        return Response({"ok": True})


class LiqpayLinkView(APIView):
    def post(self, request):
        deal = Deal.objects.filter(pk=request.data.get("deal")).first()
        u = request.user
        if deal and not (u.is_superuser or u.can_see_all_deals() or deal.owner_id == u.id):
            return Response({"detail": "Немає доступу до цієї сделки"}, status=status.HTTP_403_FORBIDDEN)
        amount = request.data.get("amount") or (deal.amount if deal else 0)
        try:
            link = adapters.liqpay_checkout_link(
                amount, deal.id if deal else "test", f"Оплата за {deal.title if deal else 'замовлення'}")
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"link": link})


class NovaPoshtaTrackView(APIView):
    def post(self, request):
        try:
            data = adapters.np_track(request.data.get("ttn", ""))
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(data)
