"""Мите відро і викраски з аркуша А3 (16.09.2026, Олег).

МИТЕ ВІДРО
  1) Склад помив заводське відро → «Фасування» → «Мите відро»: обирає розмір тари і скільки штук → «Провести».
     На складі зʼявляються «<Тара> · мите відро» (окрема картка-пара WashedTare, щоб нова і мита тара мали свої залишки).
  2) Менеджер продає тару як завжди (картка нової тари).
  3) При відвантаженні кладовщик позначає, скільки з цієї тари — мите відро. Після «Готово — відправлено»:
     зі складу списується мите відро замість нового, а складу нараховується WH_WASHED_PCT % від закупки нового відра.
     Позначити мите більше, ніж є на залишку, не можна — тому «помив, але відправив у нове» не зійдеться з залишками.

ВИКРАСКИ З А3
  Склад робить викраски: «Фасування» → «Викраски з А3»: матеріал (рецепт SampleRecipe) і скільки аркушів.
  Списується матеріал на аркуш (за рецептом, грами можна поправити перед проведенням) і аркуші А3,
  оприбутковується per_sheet викрасок цього матеріалу. Складу — WH_SAMPLE_SHEET ₴ за аркуш (якщо ставку увімкнено).
  Рецепт НЕ є комплектацією товару: інакше при продажу викраски матеріал списався б удруге.
"""
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (Product, SampleRecipe, StockDocument, StockMovement, Warehouse, WarehouseJob,
                     WarehousePayrollEntry, WashedTare)


def _D(x):
    try:
        return Decimal(str(x if x not in (None, "") else 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _wh():
    return Warehouse.objects.filter(is_default=True).first() or Warehouse.objects.first()


def _can(u):
    return bool(u.is_superuser or (hasattr(u, "has_perm_code") and (
        u.has_perm_code("warehouse.tab.inventory") or u.has_perm_code("warehouse.edit") or u.has_perm_code("warehouse.view"))))


def _stock(p):
    try:
        return _D(p.stock(_wh()))
    except Exception:
        return Decimal("0")


def _rate(code):
    from .wh_views import _rate as r
    return r(code)


def _new_cost_avg(cost_before, qty_before, add_cost, add_qty):
    if qty_before + add_qty <= 0 or qty_before <= 0:
        return add_cost
    return ((cost_before * qty_before) + (add_cost * add_qty)) / (qty_before + add_qty)


# ───────────────────────────── МИТЕ ВІДРО ─────────────────────────────
def _washed_payload():
    pct = _rate("WH_WASHED_PCT")
    pairs = []
    for w in WashedTare.objects.filter(active=True).select_related("new", "washed").order_by("new__name"):
        pairs.append({"new_id": w.new_id, "new_name": w.new.name, "washed_id": w.washed_id, "washed_name": w.washed.name,
                      "new_cost": float(w.new.cost or 0), "pay_per_bucket": float(((w.new.cost or 0) * pct / 100).quantize(Decimal("0.01"))),
                      "washed_stock": float(_stock(w.washed)), "new_stock": float(_stock(w.new))})
    recent = [{"id": d.id, "date": timezone.localtime(d.created_at).strftime("%d.%m %H:%M"), "comment": d.comment,
               "author": (d.author.get_full_name() or d.author.username) if d.author_id else ""}
              for d in StockDocument.objects.filter(kind="repack", number__startswith="МВ-").select_related("author").order_by("-created_at")[:15]]
    return {"pairs": pairs, "pct": float(pct), "recent": recent}


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def washed(request):
    u = request.user
    if not _can(u):
        return Response({"detail": "Немає доступу"}, status=403)
    if request.method == "GET":
        return Response(_washed_payload())
    pair = WashedTare.objects.filter(new_id=request.data.get("product"), active=True).select_related("new", "washed").first()
    qty = _D(request.data.get("qty"))
    if not pair or qty <= 0 or qty != qty.to_integral_value():
        return Response({"detail": "Оберіть тару і цілу кількість відер > 0"}, status=400)
    pct = _rate("WH_WASHED_PCT")
    unit_cost = ((pair.new.cost or Decimal("0")) * pct / 100).quantize(Decimal("0.01"))
    with transaction.atomic():
        before = _stock(pair.washed)
        doc = StockDocument.objects.create(kind="repack", warehouse=_wh(), number=("МВ-%s" % pair.washed_id)[:40],
                                           comment=("Мите відро: %s × %s" % (pair.new.name[:40], int(qty)))[:255],
                                           author=u, posted=True, doc_date=timezone.localdate())
        StockMovement.objects.create(document=doc, product=pair.washed, quantity=qty, price=unit_cost)
        if not pair.washed.track_stock:
            pair.washed.track_stock = True
        pair.washed.cost = _new_cost_avg(pair.washed.cost or Decimal("0"), max(before, Decimal("0")), unit_cost, qty).quantize(Decimal("0.01"))
        pair.washed.save(update_fields=["cost", "track_stock"])
    return Response(_washed_payload())


def tare_lines(job):
    """Рядки тари угоди, для яких є мите відро — для вибору «з них мите» при відвантаженні."""
    pairs = {w.new_id: w for w in WashedTare.objects.filter(active=True).select_related("washed")}
    if not pairs or not job.deal_id:
        return []
    chosen = job.washed_tare or {}
    out = []
    for it in job.deal.items.select_related("product"):
        if it.product_id in pairs:
            w = pairs[it.product_id]
            out.append({"product_id": it.product_id, "name": it.product.name, "qty": int(it.quantity or 0),
                        "washed_id": w.washed_id, "washed_stock": int(_stock(w.washed)),
                        "washed_qty": int(chosen.get(str(it.product_id), 0) or 0)})
    return out


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def job_washed(request, pk):
    from .wh_views import _job_dict
    job = WarehouseJob.objects.filter(pk=pk).select_related("deal").first()
    if not job:
        return Response({"detail": "no job"}, status=404)
    if job.status in ("shipped", "cancelled"):
        return Response({"detail": "Задача вже завершена"}, status=400)
    pid = str(request.data.get("product") or "")
    qty = int(_D(request.data.get("qty")))
    line = next((x for x in tare_lines(job) if str(x["product_id"]) == pid), None)
    if not line:
        return Response({"detail": "У цій угоді немає такої тари"}, status=400)
    if qty < 0 or qty > line["qty"]:
        return Response({"detail": "Мите відро: від 0 до %s шт" % line["qty"]}, status=400)
    if qty > line["washed_stock"]:
        return Response({"detail": "Митих відер на складі лише %s — спершу проведіть мийку у «Фасування»" % line["washed_stock"]}, status=400)
    wt = dict(job.washed_tare or {})
    if qty:
        wt[pid] = qty
    else:
        wt.pop(pid, None)
    job.washed_tare = wt
    job.save(update_fields=["washed_tare"])
    return Response(_job_dict(job, full=True))


def apply_washed_on_ship(job, user):
    """Після реалізації: мите відро списується замість нового + нарахування складу. Повторно не застосовується."""
    wt = job.washed_tare or {}
    if not wt or (job.done_snapshot or {}).get("washed_applied"):
        return []
    doc = StockDocument.objects.filter(kind="out", deal=job.deal).first()
    if not doc:
        return []
    pct = _rate("WH_WASHED_PCT")
    made = []
    with transaction.atomic():
        for pid, qty in wt.items():
            pair = WashedTare.objects.filter(new_id=int(pid)).select_related("new", "washed").first()
            m = StockMovement.objects.filter(document=doc, product_id=int(pid), quantity__lt=0).first()
            if not pair or not m:
                continue
            take = min(Decimal(int(qty)), abs(m.quantity))
            if take <= 0:
                continue
            m.quantity = m.quantity + take
            if m.quantity == 0:
                m.delete()
            else:
                m.save(update_fields=["quantity"])
            StockMovement.objects.create(document=doc, product=pair.washed, quantity=-take, price=m.price)
            per = ((pair.new.cost or Decimal("0")) * pct / 100).quantize(Decimal("0.01"))
            if per > 0:
                e = WarehousePayrollEntry.objects.create(
                    employee=user, work_date=timezone.localdate(), job=job, deal=job.deal, op_type="washed_bucket",
                    amount=(per * take).quantize(Decimal("0.01")), rate_applied=pct / 100, base_value=pair.new.cost,
                    note=("мите відро %s × %s шт (%s%% від закупки %s ₴)" % (pair.new.name[:24], int(take), pct.normalize(), pair.new.cost))[:255])
                made.append(e)
        snap = dict(job.done_snapshot or {})
        snap["washed_applied"] = {k: int(v) for k, v in wt.items()}
        job.done_snapshot = snap
        job.save(update_fields=["done_snapshot"])
    return made


# ───────────────────────────── ВИКРАСКИ З А3 ─────────────────────────────
def _samples_payload():
    recipes = []
    for r in SampleRecipe.objects.filter(active=True).select_related("target", "paper").order_by("name"):
        ids = [int(x.get("product")) for x in (r.lines or []) if x.get("product")]
        prods = {p.id: p for p in Product.objects.filter(id__in=ids)}
        recipes.append({
            "id": r.id, "name": r.name, "target_id": r.target_id, "target_name": r.target.name,
            "target_stock": float(_stock(r.target)), "per_sheet": r.per_sheet,
            "lines": [{"product": int(x["product"]), "name": prods[int(x["product"])].name if int(x["product"]) in prods else "?",
                       "kg": float(_D(x.get("kg"))), "stock": float(_stock(prods[int(x["product"])])) if int(x["product"]) in prods else 0}
                      for x in (r.lines or []) if x.get("product")],
            "paper": ({"id": r.paper_id, "name": r.paper.name, "cost": float(r.paper.cost or 0), "stock": float(_stock(r.paper))}
                      if r.paper_id else None)})
    recent = [{"id": d.id, "date": timezone.localtime(d.created_at).strftime("%d.%m %H:%M"), "comment": d.comment,
               "author": (d.author.get_full_name() or d.author.username) if d.author_id else ""}
              for d in StockDocument.objects.filter(kind="repack", number__startswith="ВИК-").select_related("author").order_by("-created_at")[:15]]
    return {"recipes": recipes, "rate_sheet": float(_rate("WH_SAMPLE_SHEET")), "recent": recent}


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def samples(request):
    u = request.user
    if not _can(u):
        return Response({"detail": "Немає доступу"}, status=403)
    if request.method == "GET":
        return Response(_samples_payload())
    r = SampleRecipe.objects.filter(id=request.data.get("recipe"), active=True).select_related("target", "paper").first()
    sheets = _D(request.data.get("sheets"))
    if not r or sheets <= 0 or sheets != sheets.to_integral_value():
        return Response({"detail": "Оберіть матеріал і цілу кількість аркушів > 0"}, status=400)
    override = {str(x.get("product")): _D(x.get("kg")) for x in (request.data.get("lines") or []) if x.get("product")}
    lines = []
    for x in (r.lines or []):
        pid = str(x.get("product"))
        kg = override.get(pid, _D(x.get("kg")))
        p = Product.objects.filter(id=int(pid)).first()
        if p and kg > 0:
            lines.append((p, (kg * sheets).quantize(Decimal("0.001"))))
    if not lines:
        return Response({"detail": "У рецепті немає матеріалу"}, status=400)
    out_qty = Decimal(r.per_sheet) * sheets
    with transaction.atomic():
        total_cost = sum(((p.cost or Decimal("0")) * q for p, q in lines), Decimal("0"))
        if r.paper_id:
            total_cost += (r.paper.cost or Decimal("0")) * sheets
        unit_cost = (total_cost / out_qty).quantize(Decimal("0.01"))
        before = _stock(r.target)
        doc = StockDocument.objects.create(
            kind="repack", warehouse=_wh(), number=("ВИК-%s" % r.target_id)[:40], author=u, posted=True, doc_date=timezone.localdate(),
            comment=("Викраски: %s — %s арк. А3 → %s шт" % (r.name[:40], int(sheets), int(out_qty)))[:255])
        for p, q in lines:
            StockMovement.objects.create(document=doc, product=p, quantity=-q, price=p.cost or 0)
        if r.paper_id:
            StockMovement.objects.create(document=doc, product=r.paper, quantity=-sheets, price=r.paper.cost or 0)
        StockMovement.objects.create(document=doc, product=r.target, quantity=out_qty, price=unit_cost)
        r.target.track_stock = True
        r.target.cost = _new_cost_avg(r.target.cost or Decimal("0"), max(before, Decimal("0")), unit_cost, out_qty).quantize(Decimal("0.01"))
        r.target.save(update_fields=["cost", "track_stock"])
        rate = _rate("WH_SAMPLE_SHEET")
        if rate > 0:
            WarehousePayrollEntry.objects.create(employee=u, work_date=timezone.localdate(), op_type="samples",
                                                 amount=(rate * sheets).quantize(Decimal("0.01")), rate_applied=rate,
                                                 note=("викраски %s: %s арк. × %s ₴" % (r.name[:30], int(sheets), rate.normalize()))[:255])
    data = _samples_payload()
    data["made"] = {"doc": doc.id, "qty": int(out_qty), "unit_cost": float(unit_cost)}
    return Response(data)
