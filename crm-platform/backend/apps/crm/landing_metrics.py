"""Origin-based landing reporting; table pagination never truncates totals."""
from django.db.models import Count, Q, Sum
from .models import Deal


def source_kind(touch):
    medium = str(touch.get("utm_medium") or "").lower()
    source = str(touch.get("utm_source") or "").lower()
    if medium in {"cpc", "ppc", "paid", "paid_social", "paidsocial", "paid-social", "cpm", "display"} or touch.get("gclid"):
        return "paid"
    if touch.get("fbclid") or source in {"facebook", "fb", "instagram", "ig", "meta", "an", "msg"}:
        return "meta_click_unconfirmed"
    if medium == "organic":
        return "organic"
    return "other" if source else "unknown"


def landing_report(d_from, d_to):
    qs = Deal.objects.filter(Q(qualification__landing_id="wallcovdliastin.com.ua") |
        Q(funnel__name="Лендинг · wallcovdliastin.com.ua"), created_at__date__gte=d_from, created_at__date__lte=d_to)
    summary = qs.aggregate(total=Count("id"), contacts=Count("contact_id", distinct=True), won=Count("id", filter=Q(stage__is_won=True)))
    # Read all attribution records; keep only the latest 100 display rows.
    kinds = {"paid": 0, "meta_click_unconfirmed": 0, "organic": 0, "other": 0, "unknown": 0}
    for q in qs.values_list("qualification", flat=True).iterator():
        q = q if isinstance(q, dict) else {}
        touch = q.get("first_touch") or q.get("utm") or {}
        kinds[source_kind(touch if isinstance(touch, dict) else {})] += 1
    summary.update(from_ads=kinds["paid"], sources=kinds)
    from .models import Payment
    # Actual paid records linked to these original deals, not their quoted amount.
    summary["paid_amount"] = float(Payment.objects.filter(deal__in=qs, is_paid=True).aggregate(total=Sum("amount"))["total"] or 0)
    rows = []
    for deal in qs.select_related("contact", "stage").order_by("-created_at")[:100]:
        q = deal.qualification or {}
        touch = q.get("first_touch") or q.get("utm") or {}
        kind = source_kind(touch)
        rows.append({"id": deal.pk, "contact": str(deal.contact) if deal.contact_id else "—",
            "stage": deal.stage.name if deal.stage_id else "—", "won": bool(deal.stage_id and deal.stage.is_won),
            "amount": float(deal.amount or 0), "at": deal.created_at.strftime("%d.%m %H:%M"),
            "from_ads": kind == "paid", "source_kind": kind,
            "ad_source": str(touch.get("utm_source") or ("Meta-перехід, оплата не підтверджена" if kind == "meta_click_unconfirmed" else kind)),
            "campaign": str(touch.get("utm_campaign") or "")[:60]})
    return rows, summary
