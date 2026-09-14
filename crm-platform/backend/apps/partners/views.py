"""API партнерської програми (/api/partners/…).

Права:
  partners.view   — екран «Партнери» (список, рівні, знижки — перегляд)
  partners.manage — рівні, налаштування, знижки на категорії й товари
  partners.assign — галочка «Партнер» у картці клієнта і ручне ПІДВИЩЕННЯ рівня (менеджерам не давати)
  partners.below_min — виняток товару нижче мінімальної маржі (лише з причиною)
  product.cost.view — бачити маржу / залишок маржі / підказки ATM
Суперюзер може все. Рівні читає будь-який співробітник (для бейджів).
"""
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.crm.models import Contact, Deal
from .models import PartnerDiscountRule, PartnerLevel, PartnerRuleLog, PartnerSettings, PartnerStatus, PartnerStatusHistory
from .services import (D0, RuleBook, StatusError, d, deal_margin, level_for, load_products, margin_pp, mark_partner,
                       max_discount, next_level, q2, raise_level, stats_for, subtree_ids, tree_maps, turnover_map,
                       unmark_partner, upsert_rule)

PAGE = 50


def _has(user, code):
    return bool(user and user.is_authenticated and (user.is_superuser or user.has_perm_code(code)))


def can_view(user):
    return _has(user, "partners.view") or _has(user, "partners.manage")


def can_manage(user):
    return _has(user, "partners.manage")


def can_assign(user):
    return _has(user, "partners.assign")


def can_cost(user):
    return _has(user, "product.cost.view")


def can_below(user):
    return _has(user, "partners.below_min")


def _deny(text="Немає доступу до партнерської програми"):
    return Response({"detail": text}, status=403)


def _dec(value, lo=None, hi=None):
    try:
        v = Decimal(str(value).replace(",", ".").strip())
    except (InvalidOperation, AttributeError, ValueError):
        return None
    if v.is_nan() or (lo is not None and v < lo) or (hi is not None and v > hi):
        return None
    return v


def _iso(value):
    return timezone.localtime(value).isoformat() if value else None


def _user_name(u):
    return (u.get_full_name() or u.username) if u else ""


def level_json(lv, counts=None):
    return {"id": lv.id, "name": lv.name, "order": lv.order, "threshold_uah": q2(lv.threshold_uah),
            "margin_share": q2(lv.margin_share), "color": lv.color, "is_active": lv.is_active,
            "n_partners": (counts or {}).get(lv.id, 0)}


def _active_levels():
    return list(PartnerLevel.objects.filter(is_active=True).order_by("order"))


# ─────────────────────────── рівні ───────────────────────────

def _check_thresholds():
    levels = _active_levels()
    for a, b in zip(levels, levels[1:]):
        if d(b.threshold_uah) < d(a.threshold_uah):
            return "Поріг «%s» (%s ₴) менший за поріг нижчого рівня «%s» (%s ₴)" % (
                b.name, q2(b.threshold_uah), a.name, q2(a.threshold_uah))
    if not levels:
        return "Має лишитись хоча б один активний рівень"
    return None


def _apply_level_fields(lv, data):
    if "name" in data:
        name = str(data.get("name") or "").strip()
        if not name or len(name) > 40:
            return "Назва рівня — від 1 до 40 символів"
        lv.name = name
    if "threshold_uah" in data:
        v = _dec(data.get("threshold_uah"), Decimal("0"), Decimal("1000000000"))
        if v is None:
            return "Поріг — число ≥ 0"
        lv.threshold_uah = v
    if "margin_share" in data:
        v = _dec(data.get("margin_share"), Decimal("0"), Decimal("1"))
        if v is None:
            return "Частка маржі — від 0 до 1 (0.25 = 25% маржі)"
        lv.margin_share = v
    if "color" in data:
        color = str(data.get("color") or "").strip()
        if not (color.startswith("#") and len(color) in (4, 7)):
            return "Колір у форматі #rrggbb"
        lv.color = color
    return None


class LevelsView(APIView):
    def get(self, request):
        counts = dict(PartnerStatus.objects.filter(is_active=True).values("level_id")
                      .annotate(n=Count("id")).values_list("level_id", "n"))
        levels = [level_json(lv, counts) for lv in PartnerLevel.objects.order_by("order")]
        return Response({"levels": levels, "can_manage": can_manage(request.user), "can_view": can_view(request.user)})

    def post(self, request):
        if not can_manage(request.user):
            return _deny("Рівні змінює лише власник або відповідальний (право partners.manage)")
        lv = PartnerLevel(order=(PartnerLevel.objects.aggregate(m=Max("order"))["m"] or 0) + 1, updated_by=request.user)
        data = dict(request.data)
        data.setdefault("name", "")
        err = _apply_level_fields(lv, data)
        if err:
            return Response({"detail": err}, status=400)
        with transaction.atomic():
            lv.save()
            err = _check_thresholds()
            if err:
                transaction.set_rollback(True)
                return Response({"detail": err}, status=400)
        return Response(level_json(lv), status=201)


class LevelDetailView(APIView):
    def patch(self, request, pk):
        if not can_manage(request.user):
            return _deny("Рівні змінює лише власник або відповідальний (право partners.manage)")
        lv = get_object_or_404(PartnerLevel, pk=pk)
        err = _apply_level_fields(lv, request.data)
        if err:
            return Response({"detail": err}, status=400)
        if "is_active" in request.data:
            active = bool(request.data.get("is_active"))
            if not active and PartnerStatus.objects.filter(level=lv).exists():
                return Response({"detail": "На цьому рівні є партнери — вимкнути не можна (статус не знижується)"}, status=400)
            lv.is_active = active
        lv.updated_by = request.user
        with transaction.atomic():
            lv.save()
            err = _check_thresholds()
            if err:
                transaction.set_rollback(True)
                return Response({"detail": err}, status=400)
        return Response(level_json(lv))

    def delete(self, request, pk):
        return Response({"detail": "Рівень не видаляється — лише вимикається (історія партнерів посилається на нього)"},
                        status=405)


# ─────────────────────────── налаштування ───────────────────────────

def _names(model, ids, field="name"):
    ids = [int(x) for x in (ids or []) if str(x).isdigit()]
    rows = dict(model.objects.filter(id__in=ids).values_list("id", field))
    return [{"id": i, "name": rows.get(i, "#%s (немає)" % i)} for i in ids]


def settings_json(st, user):
    from apps.crm.models import Funnel
    from apps.finance.models import Category
    from apps.warehouse.models import ProductCategory
    start_ids = [int(k) for k in (st.start_fixed or {}) if str(k).isdigit()]
    cat_names = dict(ProductCategory.objects.filter(id__in=start_ids).values_list("id", "name"))
    return {
        "min_margin_pp": q2(st.min_margin_pp), "round_step": q2(st.round_step),
        "turnover_from": st.turnover_from.isoformat() if st.turnover_from else None,
        "auto_raise": st.auto_raise, "auto_apply": st.auto_apply,
        "start_fixed": [{"category_id": int(k), "name": cat_names.get(int(k), "#%s" % k), "pct": q2(v)}
                        for k, v in (st.start_fixed or {}).items() if str(k).isdigit()],
        "exclude_funnels": _names(Funnel, st.exclude_funnel_ids),
        "no_discount_categories": _names(ProductCategory, st.no_discount_category_ids),
        "refund_categories": _names(Category, st.refund_category_ids),
        "exclude_in_categories": _names(Category, st.exclude_in_category_ids),
        "can_manage": can_manage(user), "can_cost": can_cost(user),
        "updated_at": _iso(st.updated_at), "updated_by": _user_name(st.updated_by),
    }


class SettingsView(APIView):
    def get(self, request):
        return Response(settings_json(PartnerSettings.get(), request.user))

    def patch(self, request):
        if not can_manage(request.user):
            return _deny("Налаштування змінює лише власник або відповідальний (право partners.manage)")
        st = PartnerSettings.get()
        data = request.data
        if data.get("auto_apply"):
            return Response({"detail": "Автознижка в угодах — окремий крок 5, вмикається після перевірки й «ок» Олега"},
                            status=400)
        if "min_margin_pp" in data:
            v = _dec(data.get("min_margin_pp"), Decimal("0"), Decimal("90"))
            if v is None:
                return Response({"detail": "Мінімальна маржа — від 0 до 90 п.п."}, status=400)
            st.min_margin_pp = v
        if "round_step" in data:
            v = _dec(data.get("round_step"), Decimal("1"), Decimal("50"))
            if v is None:
                return Response({"detail": "Крок округлення — від 1 до 50"}, status=400)
            st.round_step = v
        if "turnover_from" in data:
            v = parse_date(str(data.get("turnover_from") or ""))
            if v is None or v > timezone.localdate():
                return Response({"detail": "Дата обороту — у форматі РРРР-ММ-ДД, не в майбутньому"}, status=400)
            st.turnover_from = v
        if "auto_raise" in data:
            st.auto_raise = bool(data.get("auto_raise"))
        if "start_fixed" in data:
            raw = data.get("start_fixed") or {}
            if not isinstance(raw, dict):
                return Response({"detail": "start_fixed — {id категорії: %}"}, status=400)
            out = {}
            for k, v in raw.items():
                pct = _dec(v, Decimal("0"), Decimal("100"))
                if not str(k).isdigit() or pct is None:
                    return Response({"detail": "Стартова знижка — від 0 до 100%"}, status=400)
                out[str(int(k))] = float(pct)
            st.start_fixed = out
        if "no_discount_category_ids" in data:
            ids = data.get("no_discount_category_ids") or []
            if not isinstance(ids, list) or not all(str(x).isdigit() for x in ids):
                return Response({"detail": "Список id категорій"}, status=400)
            st.no_discount_category_ids = [int(x) for x in ids]
        st.updated_by = request.user
        st.save()
        return Response(settings_json(st, request.user))


# ─────────────────────────── матриця знижок ───────────────────────────

def _tree_order(book, children):
    out = []

    def walk(pid, depth):
        kids = sorted(children.get(pid, []), key=lambda c: book.cat_name.get(c, ""))
        for cid in kids:
            out.append((cid, depth))
            walk(cid, depth + 1)
    walk(None, 0)
    return out


def _own_roots(book, children):
    own = set()
    for root in book.start_fixed:
        own.update(subtree_ids(root, children))
    return own


class MatrixView(APIView):
    """Папки × рівні: власне правило / успадковане, підказка ATM, скільки урізано маржею, залишок маржі."""

    def get(self, request):
        if not can_view(request.user):
            return _deny()
        show_cost = can_cost(request.user)
        book = RuleBook()
        children = tree_maps(book)
        by_cat = {}
        uncategorized = 0
        for p in load_products():
            if p.category_id:
                by_cat.setdefault(p.category_id, []).append(p)
            else:
                uncategorized += 1
        own = _own_roots(book, children)
        rows = []
        for cid, depth in _tree_order(book, children):
            prods = [p for sid in subtree_ids(cid, children) for p in by_cat.get(sid, [])]
            sugg = book.category_suggestions(cid, by_cat, children) if show_cost else {}
            no_disc = any(c in book.no_disc for c in book.chain(cid))
            cells = {}
            for lv in book.levels:
                own_rule = book.cat_rules.get((lv.id, cid))
                inherited, inherited_from = None, ""
                if own_rule is None:
                    for anc in book.chain(cid)[1:]:
                        r = book.cat_rules.get((lv.id, anc))
                        if r is not None:
                            inherited, inherited_from = q2(r.pct), book.cat_name.get(anc, "")
                            break
                st = stats_for(book, prods, lv)
                cell = {"own_pct": q2(own_rule.pct) if own_rule else None, "inherited_pct": inherited,
                        "inherited_from": inherited_from, "n_capped": st["n_capped"], "n_discounted": st["n_discounted"]}
                if show_cost:
                    val, src = sugg.get(lv.id, (None, ""))
                    cell.update(suggested_pct=q2(val), suggested_src=src, avg_left_pp=st["avg_left_pp"],
                                min_left_pp=st["min_left_pp"], growth_needed_pct=st["growth_needed_pct"],
                                avg_pct=st["avg_pct"])
                cells[lv.id] = cell
            n_no_cost = sum(1 for p in prods if margin_pp(p) is None)
            rows.append({"id": cid, "name": book.cat_name.get(cid, ""), "parent_id": book.parent.get(cid), "depth": depth,
                         "n_products": len(prods), "n_no_cost": n_no_cost, "no_discount": no_disc,
                         "own_brand": cid in own, "cells": cells})
        return Response({"levels": [level_json(lv) for lv in book.levels], "categories": rows,
                         "min_margin_pp": q2(book.min_pp), "round_step": q2(book.step), "can_cost": show_cost,
                         "can_manage": can_manage(request.user), "n_uncategorized": uncategorized,
                         "n_product_exceptions": len(book.prod_rules)})


def _product_row(book, p, show_cost):
    levels = {}
    for lv in book.levels:
        eff = book.effective(p, lv)
        rule = book.prod_rules.get((lv.id, p.id))
        cell = {"pct": q2(eff["pct"]), "rule_pct": q2(eff["rule_pct"]), "source": eff["source"],
                "source_name": eff["source_name"], "capped": eff["capped"], "override": eff["override"],
                "note": eff["note"], "exception": rule is not None,
                "exception_pct": q2(rule.pct) if rule is not None and not rule.excluded else None,
                "exception_excluded": bool(rule.excluded) if rule is not None else False}
        if show_cost:
            sug, _src = book.product_suggestion(p, lv)
            cell.update(left_pp=q2(eff["left_pp"]), max_pct=q2(eff["max_pct"]), suggested_pct=q2(sug),
                        price_after=q2(eff["price_after"]))
        levels[lv.id] = cell
    row = {"id": p.id, "name": p.name, "sku": p.sku, "price": q2(p.price), "unit": p.unit,
           "category_id": p.category_id, "category_name": book.cat_name.get(p.category_id, ""),
           "no_cost": margin_pp(p) is None, "levels": levels}
    if show_cost:
        row["margin_pp"] = q2(margin_pp(p))
    return row


class ProductsView(APIView):
    """Товари з діючою партнерською знижкою за рівнями (?category= разом з підпапками, ?q=, ?exceptions=1)."""

    def get(self, request):
        if not can_view(request.user):
            return _deny()
        show_cost = can_cost(request.user)
        book = RuleBook()
        children = tree_maps(book)
        qp = request.query_params
        cat = qp.get("category")
        from apps.warehouse.models import Product
        qs = Product.objects.filter(is_active=True, price__gt=0).only(
            "id", "name", "sku", "price", "cost", "cost_pct", "min_price", "category_id", "unit")
        if cat == "none":
            qs = qs.filter(category__isnull=True)
        elif cat and str(cat).isdigit():
            qs = qs.filter(category_id__in=subtree_ids(int(cat), children))
        q = (qp.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(sku__icontains=q))
        if qp.get("exceptions") == "1":
            qs = qs.filter(id__in={pid for (_l, pid) in book.prod_rules})
        try:
            page = max(1, int(qp.get("page") or 1))
        except ValueError:
            page = 1
        total = qs.count()
        items = list(qs.order_by("name")[(page - 1) * PAGE: page * PAGE])
        return Response({"results": [_product_row(book, p, show_cost) for p in items], "count": total, "page": page,
                         "page_size": PAGE, "levels": [level_json(lv) for lv in book.levels], "can_cost": show_cost,
                         "can_manage": can_manage(request.user), "can_below_min": can_below(request.user)})


class ProductDetailView(APIView):
    def get(self, request, pk):
        if not can_view(request.user):
            return _deny()
        from apps.warehouse.models import Product
        p = get_object_or_404(Product, pk=pk)
        book = RuleBook()
        row = _product_row(book, p, can_cost(request.user))
        return Response({"product": {k: row[k] for k in ("id", "name", "sku", "price", "category_name", "no_cost")},
                         "margin_pp": row.get("margin_pp"),
                         "levels": [dict(level_json(lv), **row["levels"][lv.id]) for lv in book.levels]})


# ─────────────────────────── зміна знижок: перегляд → застосувати ───────────────────────────

def _parse_values(raw, levels_by_id, allow_exclude):
    out, errors = {}, []
    if not isinstance(raw, dict) or not raw:
        return None, ["Вкажіть знижку хоча б для одного рівня"]
    for k, v in raw.items():
        if not str(k).isdigit() or int(k) not in levels_by_id:
            errors.append("Невідомий рівень #%s" % k)
            continue
        if v is None or v == "":
            out[int(k)] = None
        elif v == "exclude":
            if not allow_exclude:
                errors.append("«Виключити» — лише для окремих товарів")
            out[int(k)] = "exclude"
        else:
            pct = _dec(v, Decimal("0"), Decimal("100"))
            if pct is None:
                errors.append("Знижка — від 0 до 100%")
            else:
                out[int(k)] = pct
    return out, errors


def _plan(request):
    """Спільна частина перегляду й застосування. Повертає (plan, response_dict, errors)."""
    from apps.warehouse.models import Product, ProductCategory
    data = request.data
    book = RuleBook()
    levels_by_id = {lv.id: lv for lv in book.levels}
    children = tree_maps(book)
    target = data.get("target")
    reason = str(data.get("reason") or "").strip()[:200]
    errors, warnings, plan = [], [], []
    if target == "category":
        cat = ProductCategory.objects.filter(pk=data.get("category_id") or 0).first()
        if cat is None:
            return None, None, ["Папку не знайдено"]
        values, errs = _parse_values(data.get("values"), levels_by_id, allow_exclude=False)
        errors += errs
        if errors:
            return None, None, errors
        by_cat = {}
        for p in load_products(category_ids=subtree_ids(cat.id, children)):
            by_cat.setdefault(p.category_id, []).append(p)
        products = [p for sid in subtree_ids(cat.id, children) for p in by_cat.get(sid, [])]
        sugg = book.category_suggestions(cat.id, by_cat, children)
        over = {}
        for lid, val in values.items():
            over[(lid, cat.id)] = None if val is None else val
            plan.append({"level": levels_by_id[lid], "category": cat, "product": None, "value": val,
                         "suggested": sugg.get(lid, (None, ""))[0], "reason": ""})
        if any(c in book.no_disc for c in book.chain(cat.id)):
            warnings.append("Це тест-набори — партнерська знижка на них не діє (завжди 0)")
        new_book = book.copy_with(cat_over=over)
        title = cat.name
    elif target == "products":
        ids = [int(x) for x in (data.get("product_ids") or []) if str(x).isdigit()][:500]
        products = list(Product.objects.filter(id__in=ids).only(
            "id", "name", "sku", "price", "cost", "cost_pct", "min_price", "category_id", "unit").order_by("name"))
        if not products:
            return None, None, ["Не вибрано жодного товару"]
        values, errs = _parse_values(data.get("values"), levels_by_id, allow_exclude=True)
        errors += errs
        if errors:
            return None, None, errors
        below_ok = can_below(request.user)
        over = {}
        for p in products:
            m = margin_pp(p)
            mx = max_discount(m, book.min_pp)
            for lid, val in values.items():
                lv = levels_by_id[lid]
                rsn = ""
                if val is None:
                    over[(lid, p.id)] = None
                elif val == "exclude":
                    over[(lid, p.id)] = {"pct": D0, "excluded": True, "below_min_reason": ""}
                else:
                    if m is None and val > 0:
                        warnings.append("«%s»: немає собівартості — знижка діятиме 0, доки не заповнять собівартість" % p.name)
                    if mx is not None and val > mx:
                        if not below_ok:
                            errors.append("«%s», %s: %s%% — нижче мінімальної маржі. Максимум %s%%. Потрібне право "
                                          "«Знижка нижче мінімуму» і причина" % (p.name, lv.name, q2(val), q2(mx)))
                        elif not reason:
                            errors.append("«%s», %s: знижка %s%% більша за межу %s%% — вкажіть причину" % (
                                p.name, lv.name, q2(val), q2(mx)))
                        rsn = reason
                    over[(lid, p.id)] = {"pct": val, "excluded": False, "below_min_reason": rsn}
                sug, _src = book.product_suggestion(p, lv)
                plan.append({"level": lv, "category": None, "product": p, "value": val, "suggested": sug, "reason": rsn})
        new_book = book.copy_with(prod_over=over)
        title = "%s товар(ів)" % len(products)
    else:
        return None, None, ["target — category або products"]

    show_cost = can_cost(request.user)
    levels_out = []
    for lid in values:
        lv = levels_by_id[lid]
        before, after = stats_for(book, products, lv), stats_for(new_book, products, lv)
        changed, examples = 0, []
        for p in products:
            e0, e1 = book.effective(p, lv), new_book.effective(p, lv)
            if e0["pct"] != e1["pct"] or e0["source"] != e1["source"]:
                changed += 1
                if len(examples) < 10:
                    ex = {"id": p.id, "name": p.name, "before_pct": q2(e0["pct"]), "after_pct": q2(e1["pct"]),
                          "note": e1["note"]}
                    if show_cost:
                        ex["left_pp_after"] = q2(e1["left_pp"])
                    examples.append(ex)
        if not show_cost:
            for s in (before, after):
                s.update(min_left_pp=None, avg_left_pp=None, growth_needed_pct=None)
        levels_out.append({"level_id": lid, "level_name": lv.name, "before": before, "after": after,
                           "n_changed": changed, "examples": examples})
    resp = {"title": title, "n_products": len(products), "levels": levels_out, "warnings": sorted(set(warnings))[:20],
            "errors": errors, "can_apply": not errors}
    return plan, resp, errors


class DiscountPreviewView(APIView):
    """Крок 1 «Перевірити»: що зміниться, нічого не записує."""

    def post(self, request):
        if not can_manage(request.user):
            return _deny("Знижки змінює лише власник або відповідальний (право partners.manage)")
        _plan_rows, resp, errors = _plan(request)
        if resp is None:
            return Response({"detail": "; ".join(errors), "errors": errors}, status=400)
        return Response(dict(resp, dry_run=True))


class DiscountApplyView(APIView):
    """Крок 2 «Застосувати»: записує правила + історію. Старі угоди НЕ перераховуються."""

    def post(self, request):
        if not can_manage(request.user):
            return _deny("Знижки змінює лише власник або відповідальний (право partners.manage)")
        plan, resp, errors = _plan(request)
        if resp is None or errors:
            return Response({"detail": "; ".join(errors), "errors": errors}, status=400)
        source = "atm" if request.data.get("source") == "atm" else "manual"
        changed = 0
        with transaction.atomic():
            for row in plan:
                val = row["value"]
                changed += 1 if upsert_rule(
                    row["level"], request.user, source, category=row["category"], product=row["product"],
                    pct=None if val in (None, "exclude") else val, excluded=(val == "exclude"),
                    reason=row["reason"], suggested=row["suggested"], remove=val is None) else 0
        return Response(dict(resp, dry_run=False, changed=changed))


class SuggestView(APIView):
    """Підказки ATM для папок або товарів — лише показ; застосування — окремим кліком по рядку."""

    def post(self, request):
        if not can_manage(request.user):
            return _deny("Знижки змінює лише власник або відповідальний (право partners.manage)")
        if not can_cost(request.user):
            return _deny("Підказки рахуються від собівартості — потрібне право «Бачити собівартість»")
        book = RuleBook()
        children = tree_maps(book)
        if request.data.get("target") == "products":
            ids = [int(x) for x in (request.data.get("product_ids") or []) if str(x).isdigit()][:500]
            rows = []
            for p in load_products(product_ids=ids):
                levels = {}
                for lv in book.levels:
                    sug, src = book.product_suggestion(p, lv)
                    rule = book.prod_rules.get((lv.id, p.id))
                    levels[lv.id] = {"suggested": q2(sug), "src": src, "current_exception":
                                     (None if rule is None else ("exclude" if rule.excluded else q2(rule.pct))),
                                     "effective": q2(book.effective(p, lv)["pct"])}
                rows.append({"product_id": p.id, "name": p.name, "margin_pp": q2(margin_pp(p)), "levels": levels,
                             "differs": any(v["current_exception"] != v["suggested"] for v in levels.values())})
            return Response({"target": "products", "rows": rows, "levels": [level_json(lv) for lv in book.levels]})
        by_cat = {}
        for p in load_products():
            by_cat.setdefault(p.category_id, []).append(p)
        own = _own_roots(book, children)
        rows = []
        for cid, depth in _tree_order(book, children):
            if any(c in book.no_disc for c in book.chain(cid)):
                continue
            sugg = book.category_suggestions(cid, by_cat, children)
            levels, differs = {}, False
            for lv in book.levels:
                val, src = sugg[lv.id]
                rule = book.cat_rules.get((lv.id, cid))
                cur = q2(rule.pct) if rule else None
                levels[lv.id] = {"suggested": q2(val), "src": src, "current": cur}
                differs = differs or (val is not None and cur != q2(val))
            rows.append({"category_id": cid, "name": book.cat_name.get(cid, ""), "depth": depth, "own_brand": cid in own,
                         "is_root": book.parent.get(cid) is None, "levels": levels, "differs": differs})
        return Response({"target": "categories", "rows": rows, "levels": [level_json(lv) for lv in book.levels]})


class RuleLogView(APIView):
    def get(self, request):
        if not can_view(request.user):
            return _deny()
        rows = [{"id": r.id, "created_at": _iso(r.created_at), "level": r.level_name, "target": r.target_name,
                 "kind": "товар" if r.product_id_ref else "папка", "old_pct": q2(r.old_pct), "new_pct": q2(r.new_pct),
                 "old_excluded": r.old_excluded, "new_excluded": r.new_excluded, "source": r.source, "note": r.note,
                 "user": _user_name(r.user)} for r in PartnerRuleLog.objects.select_related("user")[:150]]
        return Response({"results": rows})


# ─────────────────────────── партнери ───────────────────────────

class PartnersListView(APIView):
    def get(self, request):
        if not can_view(request.user):
            return _deny()
        st = PartnerSettings.get()
        levels = _active_levels()
        statuses = list(PartnerStatus.objects.select_related("level", "contact").order_by("-level__order", "contact_id"))
        live = turnover_map([s.contact_id for s in statuses], st) if statuses else {}
        results = []
        for s in statuses:
            t = live.get(s.contact_id, D0)
            nxt = next_level(s.level, levels)
            results.append({"contact_id": s.contact_id, "name": str(s.contact), "is_active": s.is_active,
                            "level": level_json(s.level), "since": s.since.isoformat() if s.since else None,
                            "turnover_uah": q2(t), "next_level": nxt.name if nxt else None,
                            "to_next_uah": q2(max(D0, d(nxt.threshold_uah) - t)) if nxt else None})
        partner_ids = {s.contact_id for s in statuses}
        paid = [lv for lv in levels if d(lv.threshold_uah) > 0]
        candidates = []
        if paid:
            border = min(d(lv.threshold_uah) for lv in paid)
            top = sorted(((cid, t) for cid, t in turnover_map(None, st).items()
                          if cid not in partner_ids and t >= border), key=lambda x: -x[1])[:40]
            names = {c.id: str(c) for c in Contact.objects.filter(id__in=[cid for cid, _t in top])}
            candidates = [{"contact_id": cid, "name": names.get(cid, "#%s" % cid), "turnover_uah": q2(t),
                           "level_by_turnover": level_for(t, levels).name} for cid, t in top]
        return Response({"results": results, "candidates": candidates, "turnover_from": st.turnover_from.isoformat(),
                         "levels": [level_json(lv) for lv in levels]})


def contact_payload(contact, user):
    st = PartnerSettings.get()
    levels = _active_levels()
    status = PartnerStatus.objects.select_related("level").filter(contact=contact).first()
    turnover = turnover_map([contact.id], st).get(contact.id, D0)
    out = {"contact_id": contact.id, "is_partner": bool(status and status.is_active), "has_status": status is not None,
           "level": level_json(status.level) if status else None, "since": status.since.isoformat() if status else None,
           "level_at": _iso(status.level_at) if status else None, "turnover_uah": q2(turnover),
           "turnover_from": st.turnover_from.isoformat(), "next_level": None, "to_next_uah": None, "progress_pct": None,
           "level_by_turnover": (level_for(turnover, levels).name if level_for(turnover, levels) else None),
           "levels": [level_json(lv) for lv in levels], "can_assign": can_assign(user), "history": []}
    if status:
        nxt = next_level(status.level, levels)
        if nxt:
            base, top = d(status.level.threshold_uah), d(nxt.threshold_uah)
            out["next_level"] = level_json(nxt)
            out["to_next_uah"] = q2(max(D0, top - turnover))
            span = top - base
            out["progress_pct"] = q2(min(Decimal("100"), max(D0, (turnover - base) / span * 100))) if span > 0 else None
        out["history"] = [{"created_at": _iso(h.created_at), "reason": h.get_reason_display(),
                           "old_level": h.old_level.name if h.old_level else None,
                           "new_level": h.new_level.name if h.new_level else None,
                           "turnover_uah": q2(h.turnover_uah), "note": h.note, "user": _user_name(h.user) or "Система"}
                          for h in PartnerStatusHistory.objects.filter(contact=contact)
                          .select_related("old_level", "new_level", "user")[:30]]
    return out


class ContactPartnerView(APIView):
    """Блок «Партнер» у картці клієнта. Читати — хто бачить клієнта; змінювати — право partners.assign."""

    def _contact(self, request, pk):
        from apps.crm.zamer import visible_contacts
        return visible_contacts(request.user).filter(pk=pk).first()

    def get(self, request, pk):
        contact = self._contact(request, pk)
        if contact is None:
            return Response({"detail": "Клієнта не знайдено"}, status=404)
        return Response(contact_payload(contact, request.user))

    def post(self, request, pk):
        if not can_assign(request.user):
            return _deny("Статус партнера присвоює лише власник або відповідальний (право partners.assign)")
        contact = self._contact(request, pk)
        if contact is None:
            return Response({"detail": "Клієнта не знайдено"}, status=404)
        action = request.data.get("action")
        note = str(request.data.get("note") or "").strip()[:200]
        try:
            if action == "mark":
                mark_partner(contact, request.user, note)
            elif action == "unmark":
                unmark_partner(contact, request.user, note)
            elif action == "raise":
                level = PartnerLevel.objects.filter(pk=request.data.get("level_id") or 0).first()
                if level is None:
                    return Response({"detail": "Рівень не знайдено"}, status=400)
                raise_level(contact, level, request.user, note)
            else:
                return Response({"detail": "action — mark / unmark / raise"}, status=400)
        except StatusError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(contact_payload(contact, request.user))


class DealMarginView(APIView):
    """Крок 4: у угоді партнера — скільки маржі лишається в кожній позиції. ЛИШЕ попередження."""

    def get(self, request, pk):
        from apps.crm.zamer import visible_deals
        deal = visible_deals(request.user).filter(pk=pk).first()
        if deal is None:
            return Response({"detail": "Угоду не знайдено"}, status=404)
        return Response(deal_margin(deal, can_cost(request.user)))


def today():
    return date.today()
