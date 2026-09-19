"""Перевірка наявності і заявка на дозамовлення з кабінету складу (19.09.2026).

Олег: «склад перевіряє наявність і формує список дозамовлення прямо зі свого кабінету: вкладка, туди дзеркально
номенклатура, вони обирають потрібні позиції; у номенклатурі — контроль наявності (мінімальний залишок), щоб їм
автоматично підтягувалось те, що ми завжди тримаємо; заявка падає відповідальному (мені) в задачі, розділена
по постачальниках; у співробітників — просто товари, без постачальників».

• Product.min_stock — мінімальний залишок (0 = не контролюємо); Product.reorder_qty — скільки замовляти (0 = до
  мінімуму ×2); Product.supplier — постачальник (якщо порожньо — з останнього приходу цього товару).
• Склад бачить лише товар, одиницю, залишок, мінімум і «скільки треба» — без постачальників і цін.
• Заявка → ReorderRequest + по ОДНІЙ задачі на кожного постачальника для відповідального
  (IntegrationSettings provider="reorder" → config.assignee_id; за замовчуванням — власник).
"""
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Product, ReorderRequest, StockDocument, StockMovement

D0 = Decimal("0")


def _can_use(u):
    return bool(u.is_superuser or (hasattr(u, "has_perm_code") and (u.has_perm_code("warehouse.work")
                                                                       or u.has_perm_code("warehouse.view"))))


def stocks(product_ids):
    rows = (StockMovement.objects.filter(document__posted=True, product_id__in=list(product_ids))
            .values("product_id").annotate(s=Sum("quantity")))
    return {r["product_id"]: Decimal(r["s"] or 0) for r in rows}


def suggest_qty(p, stock):
    """Скільки дозамовити: задано «Замовляти по» → стільки; інакше — довести до мінімуму ×2."""
    need = (p.min_stock or D0) * 2 - stock
    if p.reorder_qty and p.reorder_qty > 0:
        need = max(need, D0)
        return p.reorder_qty if need <= p.reorder_qty else (need // p.reorder_qty + 1) * p.reorder_qty
    return max(need, D0)


def low_stock():
    """Товари нижче мінімального залишку (контроль наявності)."""
    ps = list(Product.objects.filter(is_active=True, track_stock=True, min_stock__gt=0).order_by("name"))
    st = stocks([p.id for p in ps])
    out = []
    for p in ps:
        s = st.get(p.id, D0)
        if s < p.min_stock:
            out.append({"id": p.id, "name": p.name, "unit": p.unit, "stock": float(s), "min_stock": float(p.min_stock),
                        "suggest": float(suggest_qty(p, s))})
    return out


def default_supplier(p):
    """Постачальник товару: з картки, інакше — з останнього проведеного приходу цього товару."""
    if p.supplier_id:
        return p.supplier
    doc = (StockDocument.objects.filter(kind="in", posted=True, supplier__isnull=False, items__product=p)
           .select_related("supplier").order_by("-id").first())
    return doc.supplier if doc else None


def _assignee():
    from django.contrib.auth import get_user_model
    U = get_user_model()
    try:
        from apps.integrations.models import IntegrationSettings
        cfg = (IntegrationSettings.objects.filter(provider="reorder").values_list("config", flat=True).first() or {})
        if cfg.get("assignee_id"):
            u = U.objects.filter(id=cfg["assignee_id"], is_active=True).first()
            if u:
                return u
    except Exception:
        pass
    return U.objects.filter(is_superuser=True, is_active=True).order_by("id").first()


def _fmt(q):
    q = Decimal(q)
    return ("%s" % q.normalize()) if q == q.to_integral() else ("%.3f" % q).rstrip("0").rstrip(".")


def submit(user, lines, comment=""):
    """lines: [{product, qty, note}] → ReorderRequest + задачі по постачальниках. Повертає ReorderRequest."""
    from apps.crm.models import Task, log_activity
    clean, by_sup = [], {}
    ps = {p.id: p for p in Product.objects.filter(id__in=[int(x.get("product") or 0) for x in lines])}
    st = stocks(ps.keys())
    for x in lines:
        p = ps.get(int(x.get("product") or 0))
        try:
            q = Decimal(str(x.get("qty") or 0).replace(",", "."))
        except Exception:
            q = D0
        if p is None or q <= 0:
            continue
        sup = default_supplier(p)
        row = {"product": p.id, "name": p.name, "unit": p.unit, "qty": float(q), "stock": float(st.get(p.id, D0)),
               "min_stock": float(p.min_stock or 0), "note": str(x.get("note") or "")[:200],
               "supplier_id": sup.id if sup else None, "supplier": (str(sup) if sup else "Постачальник не вказаний")}
        clean.append(row)
        by_sup.setdefault(row["supplier"], []).append(row)
    if not clean:
        return None
    req = ReorderRequest.objects.create(created_by=user, lines=clean, comment=str(comment or "")[:500])
    who = user.get_full_name() or user.username
    boss = _assignee()
    task_ids = []
    for sup, rows in sorted(by_sup.items()):
        body = "\n".join("• %s — %s %s (залишок %s, мін. %s)%s" % (
            r["name"], _fmt(r["qty"]), r["unit"], _fmt(r["stock"]), _fmt(r["min_stock"]),
            (" · " + r["note"]) if r["note"] else "") for r in rows)
        t = Task.objects.create(kind="other", title="🛒 Дозамовлення · %s — %d поз." % (sup[:60], len(rows)),
                                body="Заявка складу №%s від %s (%s)\n\n%s%s" % (
                                    req.id, who, timezone.localdate().strftime("%d.%m"), body,
                                    ("\n\nКоментар: " + req.comment) if req.comment else ""),
                                assignee=boss, created_by=user, contact_id=rows[0]["supplier_id"])
        task_ids.append(t.id)
    req.task_ids = task_ids
    req.save(update_fields=["task_ids"])
    log_activity("user", user.id, "Заявка на дозамовлення", "№%s · %d поз. · %d постач." % (req.id, len(clean), len(by_sup)), user)
    return req


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def reorder(request):
    """GET — що нижче мінімуму + мої заявки (?q= — пошук по номенклатурі); POST {lines, comment} — надіслати заявку."""
    u = request.user
    if not _can_use(u):
        return Response({"detail": "Немає доступу до складу"}, status=403)
    if request.method == "POST":
        req = submit(u, request.data.get("lines") or [], request.data.get("comment") or "")
        if req is None:
            return Response({"detail": "Додайте хоча б одну позицію з кількістю"}, status=400)
        return Response({"ok": True, "id": req.id, "tasks": len(req.task_ids or []), "lines": len(req.lines)})
    q = (request.query_params.get("q") or "").strip()
    if q:
        ps = list(Product.objects.filter(is_active=True, track_stock=True, name__icontains=q).order_by("name")[:30])
        st = stocks([p.id for p in ps])
        return Response({"results": [{"id": p.id, "name": p.name, "unit": p.unit, "stock": float(st.get(p.id, D0)),
                                      "min_stock": float(p.min_stock or 0)} for p in ps]})
    mine = ReorderRequest.objects.filter(created_by=u).order_by("-id")[:10]
    return Response({"low": low_stock(),
                     "mine": [{"id": r.id, "at": r.created_at, "lines": len(r.lines or []),
                               "items": ", ".join("%s %s" % (x["name"][:30], _fmt(x["qty"])) for x in (r.lines or [])[:4])}
                              for r in mine]})
