"""API повернень (16.09.2026).
GET  /api/returns/deal/<deal_id>/     — позиції угоди, повернення, що можна робити (угода у видимості користувача)
POST /api/returns/deal/<deal_id>/     — оформити повернення товару (менеджер / склад / бухгалтер / власник)
POST /api/returns/<id>/photos/        — додати фото (multipart, поле file, можна кілька)
GET  /api/returns/photos/<id>/        — фото
POST /api/returns/<id>/money/         — рішення по грошах: ЛИШЕ право deal.refund (бухгалтер) або власник
GET  /api/returns/report/?from=&to=   — звіт «Повернення» (право analytics.view)
"""
from datetime import date, timedelta

from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import DealReturn, DealReturnLine, DealReturnPhoto
from .services import ReturnError, contact_name, fmt, user_name

MONEY_PERM = "deal.refund"


def _is_client(u):
    return getattr(u, "account_kind", "staff") == "client"


def can_money(u):
    """Гроші за повернення — лише відповідальний бухгалтер (право deal.refund) або власник (рішення Олега 16.09)."""
    return bool(u and u.is_authenticated and not _is_client(u)
                and (u.is_superuser or (hasattr(u, "has_perm_code") and u.has_perm_code(MONEY_PERM))))


def _can_cost(u):
    return bool(u.is_superuser or (hasattr(u, "has_perm_code") and u.has_perm_code("product.cost.view")))


def _visible_deal(request, deal_id):
    """Та сама видимість, що в списку угод (ScopedByRoleMixin + deal.view.all); склад — угоди зі складською задачею
    (як DealViewSet.get_object); бухгалтер з правом deal.refund — будь-яка угода."""
    from apps.crm.models import Deal
    from apps.crm.views import DealViewSet, ScopedByRoleMixin
    u = request.user
    if _is_client(u):
        return None

    class _Base:
        def get_queryset(self):
            return Deal.objects.all()

    class _Scoped(ScopedByRoleMixin, _Base):
        view_all_method = DealViewSet.view_all_method

        def __init__(self, req):
            self.request = req

    d = _Scoped(request).get_queryset().filter(pk=deal_id).first()
    if d is None and (can_money(u) or (hasattr(u, "has_perm_code") and u.has_perm_code("warehouse.view"))):
        from apps.warehouse.models import WarehouseJob
        if can_money(u) or WarehouseJob.objects.filter(deal_id=deal_id).exists():
            d = Deal.objects.filter(pk=deal_id).first()
    return d


def return_dict(r, show_cost=False):
    e = r.error
    out = {
        "id": r.pk, "deal": r.deal_id, "created_at": r.created_at, "created_by": user_name(r.created_by),
        "reason": r.reason, "reason_label": r.get_reason_display(), "amount": float(r.amount),
        "delivery_payer": r.delivery_payer, "delivery_payer_label": r.get_delivery_payer_display(),
        "delivery_cost": float(r.delivery_cost), "comment": r.comment, "stock_note": r.stock_note,
        "receipt_doc": ({"id": r.receipt_doc_id, "number": r.receipt_doc.number} if r.receipt_doc_id else None),
        "lines": [{"name": ln.name, "unit": ln.unit, "quantity": float(ln.quantity), "sold_quantity": float(ln.sold_quantity),
                   "amount": float(ln.amount), "destination": ln.destination,
                   "destination_label": ln.get_destination_display()} for ln in r.lines.all()],
        "photos": [{"id": p.pk, "url": "/api/returns/photos/%d/" % p.pk} for p in r.photos.all()],
        "money_status": r.money_status, "money_label": r.get_money_status_display(),
        "money_due": float(r.money_due), "money_amount": float(r.money_amount), "money_comment": r.money_comment,
        "money_by": user_name(r.money_by), "money_at": r.money_at, "refund_tx": r.refund_tx_id,
        "error": ({"id": e.pk, "status": e.status, "status_label": e.get_status_display(), "deduction": float(e.deduction_uah),
                   "blamed": user_name(e.blamed_user)} if e is not None else None),
    }
    if show_cost:
        out.update({"cost_back": float(r.cost_back), "cost_loss": float(r.cost_loss)})
    return out


def _returns_qs(deal_id):
    return (DealReturn.objects.filter(deal_id=deal_id)
            .select_related("created_by", "money_by", "receipt_doc", "error", "error__blamed_user")
            .prefetch_related("lines", "photos"))


class DealReturnsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, deal_id):
        deal = _visible_deal(request, deal_id)
        if deal is None:
            return Response({"detail": "Угоду не знайдено"}, status=404)
        u = request.user
        money = can_money(u)
        show_cost = _can_cost(u)
        from apps.warehouse.models import StockDocument
        items = []
        for it in deal.items.select_related("product").order_by("id"):
            p = it.product if it.product_id else None
            items.append({"id": it.id, "name": (p.name if p is not None else it.custom_name) or "позиція",
                          "unit": (p.unit if p is not None else ""), "quantity": float(it.quantity),
                          "price": float(it.price), "total": float(it.total),
                          "stock": bool(p is not None and (p.track_stock or p.components.exists()))})
        out = {
            "can_register": True, "can_money": money, "show_cost": show_cost,
            "realized": StockDocument.objects.filter(kind="out", deal=deal, posted=True).exists(),
            "items": items, "amount": float(deal.amount or 0),
            "paid": float(services.deal_paid(deal) - services.journal_refunded(deal.pk)),
            "reasons": [{"code": c, "label": lbl} for c, lbl in DealReturn.REASONS],
            "destinations": [{"code": c, "label": lbl} for c, lbl in DealReturnLine.DESTINATIONS],
            "payers": [{"code": c, "label": lbl} for c, lbl in DealReturn.PAYERS],
            "error_reasons": list(services.ERROR_REASONS),
            "returns": [return_dict(r, show_cost) for r in _returns_qs(deal.pk)],
        }
        from apps.accounts.models import User
        out["staff"] = [{"id": s.id, "name": user_name(s)} for s in
                        User.objects.filter(is_active=True).exclude(account_kind="client").order_by("first_name", "username")]
        if money:
            from apps.finance.models import Account, Transaction
            out["accounts"] = [{"id": a.id, "name": a.name} for a in Account.objects.filter(is_active=True)]
            used = set(DealReturn.objects.exclude(refund_tx__isnull=True).values_list("refund_tx_id", flat=True))
            out["liqpay_refunds"] = [
                {"id": t.id, "date": t.date.isoformat(), "amount": float(t.amount_uah or t.amount), "comment": t.comment}
                for t in Transaction.objects.filter(deal=deal, direction="out", category_id__in=services.refund_category_ids(),
                                                    comment__startswith=services.LIQPAY_REFUND_PREFIX).order_by("-date", "-id")
                if t.id not in used]
        return Response(out)

    def post(self, request, deal_id):
        deal = _visible_deal(request, deal_id)
        if deal is None:
            return Response({"detail": "Угоду не знайдено"}, status=404)
        try:
            ret, created = services.register_return(deal, request.user, request.data)
        except ReturnError as e:
            return Response({"detail": str(e)}, status=e.status)
        ret = _returns_qs(deal.pk).get(pk=ret.pk)
        return Response({"ok": True, "created": created, "return": return_dict(ret, _can_cost(request.user))},
                        status=201 if created else 200)


class ReturnPhotoUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        ret = DealReturn.objects.filter(pk=pk).first()
        if ret is None or ret.deal_id is None or _visible_deal(request, ret.deal_id) is None:
            return Response({"detail": "Повернення не знайдено"}, status=404)
        files = request.FILES.getlist("file") + request.FILES.getlist("image")
        if not files:
            return Response({"detail": "Додайте фото"}, status=400)
        if ret.photos.count() + len(files) > services.MAX_PHOTOS:
            return Response({"detail": "Не більше %d фото на одне повернення" % services.MAX_PHOTOS}, status=400)
        for f in files:
            if not (getattr(f, "content_type", "") or "").startswith("image/"):
                return Response({"detail": "«%s» — не фото" % f.name}, status=400)
            if f.size > services.MAX_PHOTO_BYTES:
                return Response({"detail": "«%s» більше 15 МБ" % f.name}, status=400)
        for f in files:
            DealReturnPhoto.objects.create(ret=ret, image=f, uploaded_by=request.user)
        return Response({"ok": True, "photos": [{"id": p.pk, "url": "/api/returns/photos/%d/" % p.pk} for p in ret.photos.all()]})


class ReturnPhotoView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        p = DealReturnPhoto.objects.select_related("ret").filter(pk=pk).first()
        if p is None or p.ret.deal_id is None or _visible_deal(request, p.ret.deal_id) is None:
            return Response({"detail": "Фото не знайдено"}, status=404)
        import mimetypes
        try:
            with p.image.open("rb") as fh:
                data = fh.read()
        except Exception:
            return Response({"detail": "Файл відсутній"}, status=404)
        return HttpResponse(data, content_type=mimetypes.guess_type(p.image.name)[0] or "image/jpeg")


class ReturnMoneyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not can_money(request.user):
            return Response({"detail": "Гроші за повернення повертає лише відповідальний бухгалтер або власник "
                                       "(право «Повертати гроші клієнту за повернений товар»)."}, status=403)
        try:
            ret = services.settle_money(pk, request.user, request.data)
        except ReturnError as e:
            return Response({"detail": str(e)}, status=e.status)
        ret = _returns_qs(ret.deal_id).get(pk=ret.pk)
        return Response({"ok": True, "return": return_dict(ret, _can_cost(request.user))})


def _date(s, default):
    try:
        return date.fromisoformat(str(s)[:10]) if s else default
    except ValueError:
        return default


class ReturnsReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        u = request.user
        if _is_client(u) or not (u.is_superuser or u.has_perm_code("analytics.view")):
            return Response({"detail": "Немає доступу до аналітики"}, status=403)
        from django.utils import timezone
        today = timezone.localdate()
        d2 = _date(request.query_params.get("to"), today)
        d1 = _date(request.query_params.get("from"), d2 - timedelta(days=89))
        if d1 > d2:
            d1, d2 = d2, d1
        return Response(services.report(d1, d2, show_cost=_can_cost(u)))


__all__ = ["DealReturnsView", "ReturnPhotoUploadView", "ReturnPhotoView", "ReturnMoneyView", "ReturnsReportView",
           "contact_name", "fmt"]
