"""API економіки угоди.
GET  /api/deal-economics/<deal_id>/            — картка (право deal.economics.view + угода у видимості користувача;
                                                  з 14.09 окреме право замість product.cost.view)
GET  /api/deal-economics/<deal_id>/?recompute=1 — перерахувати і зберегти (лише власник)
GET  /api/deal-economics/settings/             — норми оцінок + фонд «Упаковка (матеріали)» з Фінмоделі (deal.economics.view)
PATCH /api/deal-economics/settings/            — змінити норми (лише власник)
"""
from datetime import date
from decimal import Decimal, InvalidOperation

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import COST_KEYS, DEFAULTS, NUM_FIELDS, get_settings, pack_fund, recompute, tables_ready

LINES = ("revenue",) + COST_KEYS


def _can_cost(u):
    # 14.09 (margin-perms): блок «Економіка угоди» — окреме право deal.economics.view (раніше product.cost.view)
    return bool(u and u.is_authenticated and (u.is_superuser or (hasattr(u, "has_perm_code") and u.has_perm_code("deal.economics.view"))))


def _is_owner(u):
    return bool(u and u.is_authenticated and u.is_superuser)


def _visible_deal(request, deal_id):
    """Та сама видимість, що й у списку угод (ScopedByRoleMixin + deal.view.all)."""
    from apps.crm.models import Deal
    from apps.crm.views import DealViewSet, ScopedByRoleMixin

    class _Base:
        def get_queryset(self):
            return Deal.objects.all()

    class _Scoped(ScopedByRoleMixin, _Base):
        view_all_method = DealViewSet.view_all_method

        def __init__(self, req):
            self.request = req

    return _Scoped(request).get_queryset().filter(pk=deal_id).first()


def payload(res, user):
    out = {k: float(res[k]) for k in NUM_FIELDS}
    out.update({"deal_id": res["deal_id"], "margin_pct": float(res["margin_pct"]), "is_estimate": bool(res["is_estimate"]),
                "flags": res.get("flags") or [], "sources": res.get("sources") or {}, "version": res.get("version"),
                "locked": bool(res.get("locked")), "saved": bool(res.get("saved")),
                "computed_at": res["computed_at"].isoformat() if res.get("computed_at") else None,
                "can_recompute": _is_owner(user), "can_edit_settings": _is_owner(user)})
    lines = []
    for k in LINES:
        s = (res.get("sources") or {}).get(k) or {}
        lines.append({"key": k, "amount": float(res[k]), "kind": s.get("kind", "none"),
                      "note_uk": s.get("uk", ""), "note_ru": s.get("ru", "")})
    out["lines"] = lines
    return out


class DealEconomicsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, deal_id):
        if not _can_cost(request.user):
            return Response({"detail": "Потрібне право «Бачити блок «Економіка угоди»»"}, status=403)
        deal = _visible_deal(request, deal_id)
        if deal is None:
            return Response({"detail": "Угоду не знайдено"}, status=404)
        want = str(request.query_params.get("recompute") or "").lower() in ("1", "true", "yes")
        if want and not _is_owner(request.user):
            return Response({"detail": "Перерахунок і збереження — лише власник"}, status=403)
        # Без recompute=1 — свіжий розрахунок на льоту (нічого не пишемо); закритий місяць — збережені цифри.
        res = recompute(deal, save=want)
        return Response(payload(res, request.user))


_NUM_LIMITS = {
    "pack_material_per_shipment": (Decimal("0"), Decimal("1000")),
    "liqpay_rate_pct": (Decimal("0"), Decimal("10")),
    "liqpay_rate_old_pct": (Decimal("0"), Decimal("10")),
    "novapay_rate_pct": (Decimal("0"), Decimal("10")),
    "fee_check_min_pct": (Decimal("0"), Decimal("10")),
    "fee_check_max_pct": (Decimal("0"), Decimal("20")),
}
_DATE_FIELDS = ("liqpay_rate_change_date", "auto_from")


def _settings_out(cfg):
    out = {}
    for k in DEFAULTS:
        v = cfg[k]
        out[k] = v.isoformat() if isinstance(v, date) else float(v)
    # 14.09: матеріали пакування рахуються від фонду Олега (Фінмодель); норма ₴ за відправлення — лише запасна
    fund = pack_fund()
    out["pack_material_fund_pct"] = float(fund["pct"]) if fund else None
    out["pack_material_fund_name"] = fund["name"] if fund else ""
    out["pack_material_fund_id"] = fund["id"] if fund else None
    return out


class DealEconSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _can_cost(request.user):
            return Response({"detail": "Потрібне право «Бачити блок «Економіка угоди»»"}, status=403)
        out = _settings_out(get_settings())
        out["can_edit"] = _is_owner(request.user)
        return Response(out)

    def patch(self, request):
        if not _is_owner(request.user):
            return Response({"detail": "Норми змінює лише власник"}, status=403)
        if not tables_ready():
            return Response({"detail": "Міграція dealecon ще не застосована"}, status=503)
        from .models import DealEconSettings
        row, _ = DealEconSettings.objects.get_or_create(pk=1)
        data = request.data or {}
        errors = {}
        for k, (lo, hi) in _NUM_LIMITS.items():
            if k in data:
                try:
                    v = Decimal(str(data[k]).replace(",", "."))
                except (InvalidOperation, ValueError):
                    errors[k] = "не число"
                    continue
                if not (lo <= v <= hi):
                    errors[k] = "від %s до %s" % (lo, hi)
                    continue
                setattr(row, k, v)
        for k in _DATE_FIELDS:
            if k in data:
                try:
                    setattr(row, k, date.fromisoformat(str(data[k])[:10]))
                except ValueError:
                    errors[k] = "дата РРРР-ММ-ДД"
        if row.fee_check_min_pct > row.fee_check_max_pct:
            errors["fee_check_min_pct"] = "мінімум більший за максимум"
        if errors:
            return Response({"detail": "Помилки в нормах", "errors": errors}, status=400)
        row.updated_by = request.user
        row.save()
        out = _settings_out(get_settings())
        out["can_edit"] = True
        return Response(out)
