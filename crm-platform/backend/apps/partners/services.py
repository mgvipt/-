"""Логіка партнерської програми: маржа, підказка ATM, яка знижка діє, оборот, рівні.

Маржа m — у % РОЗДРІБНОЇ ціни: m = (ціна − собівартість) / ціна × 100.
Собівартість: cost_pct > 0 (послуга) → ціна × cost_pct%, інакше Product.cost. Немає → «немає собівартості» → знижка 0.
Підказка ATM: floor_step( min(частка_рівня × m, m − мін_маржа), крок ), не менше 0.
Діюча знижка: виняток товару → правило папки → батьківської папки → … → немає правила = 0.
Правило папки автоматично урізається до floor(m − мін_маржа). Виняток товару вище межі — лише з причиною.
Тест-набори (no_discount_category_ids) — завжди 0.
"""
import math
from datetime import timedelta
from decimal import Decimal, ROUND_FLOOR
from types import SimpleNamespace

from django.db import transaction
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import (PartnerDiscountRule, PartnerLevel, PartnerRuleLog, PartnerSettings, PartnerStatus,
                     PartnerStatusHistory)

D0 = Decimal("0")
D100 = Decimal("100")


def d(value):
    try:
        return Decimal(str(value if value is not None else 0))
    except Exception:
        return D0


def q2(value):
    return None if value is None else float(Decimal(value).quantize(Decimal("0.01")))


# ─────────────────────────── маржа і підказка ───────────────────────────

def unit_cost(product):
    """Собівартість одиниці за роздрібною ціною. None — невідома."""
    price = d(product.price)
    if price <= 0:
        return None
    pct = d(getattr(product, "cost_pct", 0))
    if pct > 0:
        return price * pct / D100
    cost = d(product.cost)
    return cost if cost > 0 else None


def margin_pp(product):
    """Маржа товару в % роздрібної ціни (може бути від'ємною). None — немає ціни чи собівартості."""
    price = d(product.price)
    cost = unit_cost(product)
    if cost is None or price <= 0:
        return None
    return (price - cost) / price * D100


def floor_step(value, step):
    value = d(value)
    step = d(step) if d(step) > 0 else Decimal("1")
    if value <= 0:
        return D0
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def max_discount(m, min_pp):
    """Найбільша знижка, після якої лишається min_pp маржі (цілі %). None — немає собівартості."""
    if m is None:
        return None
    return floor_step(d(m) - d(min_pp), 1)


def atm_suggest(m, share, min_pp, step):
    """Підказка за правилом ATM. None — немає собівартості."""
    if m is None:
        return None
    raw = min(d(share) * d(m), d(m) - d(min_pp))
    return floor_step(raw, step)


def growth_needed(m, s):
    """На скільки % мають вирости продажі, щоб знижка s окупилась (ATM: s / (m − s))."""
    if m is None or s is None or d(s) <= 0:
        return None
    left = d(m) - d(s)
    if left <= 0:
        return None
    return d(s) / left * D100


def median_low(values):
    vals = sorted(values)
    if not vals:
        return None
    return vals[(len(vals) - 1) // 2]


# ─────────────────────────── книга правил ───────────────────────────

class RuleBook:
    """Усі рівні, правила й дерево категорій в памʼяті — один запит на кожну таблицю."""

    def __init__(self, st=None, levels=None):
        from apps.warehouse.models import ProductCategory
        self.st = st or PartnerSettings.get()
        self.min_pp = d(self.st.min_margin_pp)
        self.step = d(self.st.round_step)
        self.levels = levels if levels is not None else list(PartnerLevel.objects.filter(is_active=True).order_by("order"))
        cats = list(ProductCategory.objects.values_list("id", "parent_id", "name"))
        self.parent = {c[0]: c[1] for c in cats}
        self.cat_name = {c[0]: c[2] for c in cats}
        self.cat_rules = {}
        self.prod_rules = {}
        for r in PartnerDiscountRule.objects.all():
            if r.product_id:
                self.prod_rules[(r.level_id, r.product_id)] = r
            else:
                self.cat_rules[(r.level_id, r.category_id)] = r
        self.no_disc = {int(x) for x in (self.st.no_discount_category_ids or []) if str(x).isdigit()}
        self.start_fixed = {int(k): d(v) for k, v in (self.st.start_fixed or {}).items() if str(k).isdigit()}

    def copy_with(self, cat_over=None, prod_over=None):
        """Копія з тимчасовими змінами (для попереднього перегляду). None у значенні = прибрати правило."""
        other = object.__new__(RuleBook)
        other.__dict__.update(self.__dict__)
        other.cat_rules = dict(self.cat_rules)
        other.prod_rules = dict(self.prod_rules)
        for key, val in (cat_over or {}).items():
            if val is None:
                other.cat_rules.pop(key, None)
            else:
                other.cat_rules[key] = SimpleNamespace(pct=d(val), excluded=False, below_min_reason="")
        for key, val in (prod_over or {}).items():
            if val is None:
                other.prod_rules.pop(key, None)
            else:
                other.prod_rules[key] = SimpleNamespace(**val)
        return other

    def chain(self, cat_id):
        out, seen = [], set()
        while cat_id and cat_id not in seen and len(out) < 10:
            seen.add(cat_id)
            out.append(cat_id)
            cat_id = self.parent.get(cat_id)
        return out

    def lowest_level(self):
        return self.levels[0] if self.levels else None

    def resolve(self, product, level):
        """(правило, звідки): виняток товару → папка → батьківські папки → (None, 'none')."""
        rule = self.prod_rules.get((level.id, product.id))
        if rule is not None:
            return rule, "product", ""
        for cid in self.chain(product.category_id):
            rule = self.cat_rules.get((level.id, cid))
            if rule is not None:
                return rule, "category", self.cat_name.get(cid, "")
        return None, "none", ""

    def effective(self, product, level):
        m = margin_pp(product)
        mx = max_discount(m, self.min_pp)
        price = d(product.price)
        out = {"level_id": level.id, "pct": D0, "rule_pct": None, "source": "none", "source_name": "",
               "capped": False, "override": False, "no_cost": m is None, "margin_pp": m, "max_pct": mx, "note": ""}
        if any(c in self.no_disc for c in self.chain(product.category_id)):
            out.update(source="no_discount", note="тест-набір — без партнерської знижки")
        else:
            rule, src, src_name = self.resolve(product, level)
            if rule is None:
                out["note"] = "немає правила"
            elif src == "product" and rule.excluded:
                out.update(source="excluded", note="товар виключено з програми")
            else:
                out.update(source=src, source_name=src_name, rule_pct=d(rule.pct))
                if m is None:
                    out["note"] = "немає собівартості"
                elif src == "product" and (rule.below_min_reason or ""):
                    out.update(pct=d(rule.pct), override=True, note="нижче мінімуму: " + rule.below_min_reason)
                else:
                    pct = min(d(rule.pct), mx)
                    out.update(pct=pct, capped=pct < d(rule.pct))
                    if out["capped"]:
                        out["note"] = "урізано до %s%% — мінімальна маржа" % q2(pct)
        out["left_pp"] = None if m is None else m - out["pct"]
        out["price_after"] = price * (D100 - out["pct"]) / D100
        return out

    # ── підказки ──
    def product_suggestion(self, product, level):
        if any(c in self.no_disc for c in self.chain(product.category_id)):
            return D0, "no_discount"
        m = margin_pp(product)
        if m is None:
            return D0, "no_cost"
        return atm_suggest(m, level.margin_share, self.min_pp, self.step), "atm"

    def category_suggestions(self, cat_id, products_by_cat, children):
        """{level_id: (pct, src)} для папки: медіана підказок по товарах папки та підпапок;
        «Старт» на затверджених Олегом кореневих папках — його число. Вищий рівень не менший за нижчий."""
        prods = list(iter_subtree_products(cat_id, products_by_cat, children))
        margins = [m for m in (margin_pp(p) for p in prods
                               if not any(c in self.no_disc for c in self.chain(p.category_id))) if m is not None]
        out, prev = {}, D0
        for idx, level in enumerate(self.levels):
            if idx == 0 and cat_id in self.start_fixed:
                val, src = self.start_fixed[cat_id], "oleg"
            elif not margins:
                val, src = None, "no_cost"
            else:
                val = floor_step(median_low([atm_suggest(m, level.margin_share, self.min_pp, self.step)
                                              for m in margins]), self.step)
                src = "atm"
            if val is not None:
                val = max(val, prev)
                prev = val
            out[level.id] = (val, src)
        return out


def load_products(category_ids=None, product_ids=None):
    from apps.warehouse.models import Product
    qs = Product.objects.filter(is_active=True, price__gt=0).only(
        "id", "name", "sku", "price", "cost", "cost_pct", "min_price", "category_id", "unit")
    if product_ids is not None:
        qs = qs.filter(id__in=list(product_ids))
    if category_ids is not None:
        qs = qs.filter(category_id__in=list(category_ids))
    return list(qs.order_by("name"))


def tree_maps(book):
    children = {}
    for cid, pid in book.parent.items():
        children.setdefault(pid, []).append(cid)
    return children


def subtree_ids(cat_id, children):
    out, stack, seen = [], [cat_id], set()
    while stack:
        cid = stack.pop()
        if cid in seen:
            continue
        seen.add(cid)
        out.append(cid)
        stack.extend(children.get(cid, []))
    return out


def iter_subtree_products(cat_id, products_by_cat, children):
    for cid in subtree_ids(cat_id, children):
        for p in products_by_cat.get(cid, []):
            yield p


def stats_for(book, products, level):
    """Скільки товарів, скільки урізано маржею, мін./сер. залишок маржі — для папки/вибору."""
    n = n_no_cost = n_capped = n_disc = 0
    lefts, margins, pcts = [], [], []
    for p in products:
        eff = book.effective(p, level)
        n += 1
        if eff["no_cost"]:
            n_no_cost += 1
            continue
        if eff["capped"]:
            n_capped += 1
        if eff["pct"] > 0:
            n_disc += 1
        lefts.append(eff["left_pp"])
        margins.append(eff["margin_pp"])
        pcts.append(eff["pct"])
    avg_m = sum(margins) / len(margins) if margins else None
    avg_s = sum(pcts) / len(pcts) if pcts else None
    return {"n_products": n, "n_no_cost": n_no_cost, "n_capped": n_capped, "n_discounted": n_disc,
            "min_left_pp": q2(min(lefts)) if lefts else None, "avg_left_pp": q2(sum(lefts) / len(lefts)) if lefts else None,
            "avg_pct": q2(avg_s), "growth_needed_pct": q2(growth_needed(avg_m, avg_s))}


# ─────────────────────────── запис правил ───────────────────────────

def upsert_rule(level, user, source, note="", category=None, product=None, pct=None, excluded=False,
                reason="", suggested=None, remove=False):
    """Записати/прибрати правило + рядок історії. Повертає True, якщо щось змінилось."""
    flt = {"level": level, "category": category, "product": product}
    rule = PartnerDiscountRule.objects.filter(**flt).first()
    old_pct = rule.pct if rule else None
    old_exc = rule.excluded if rule else None
    if remove:
        if rule is None:
            return False
        rule.delete()
        new_pct, new_exc = None, None
    else:
        new_pct = d(pct) if not excluded else D0
        new_exc = bool(excluded)
        if rule and rule.pct == new_pct and rule.excluded == new_exc and (rule.below_min_reason or "") == (reason or ""):
            return False
        if rule is None:
            rule = PartnerDiscountRule(**flt)
        rule.pct = new_pct
        rule.excluded = new_exc
        rule.below_min_reason = (reason or "")[:200]
        rule.suggested_pct = suggested
        rule.updated_by = user if getattr(user, "is_authenticated", False) else None
        rule.save()
    PartnerRuleLog.objects.create(
        level_id_ref=level.id, level_name=level.name, category_id_ref=category.id if category else None,
        product_id_ref=product.id if product else None,
        target_name=(category.name if category else product.name if product else "")[:255],
        old_pct=old_pct, new_pct=new_pct, old_excluded=old_exc, new_excluded=new_exc, source=source,
        note=(note or reason or "")[:200], user=user if getattr(user, "is_authenticated", False) else None)
    return True


# ─────────────────────────── оборот і рівні ───────────────────────────

def _int_list(values):
    return [int(x) for x in (values or []) if str(x).lstrip("-").isdigit()]


def turnover_map(contact_ids=None, st=None):
    """{contact_id: оборот ₴}. Надходження (in) по угодах клієнта + без угоди з contact=клієнт,
    з дати turnover_from, без тестових воронок і не-виручки; мінус повернення клієнту (out у категоріях повернень)."""
    from apps.finance.models import Transaction
    st = st or PartnerSettings.get()
    base = Transaction.objects.filter(date__gte=st.turnover_from).annotate(
        cid=Coalesce("deal__contact_id", "contact_id"))
    excl_f = _int_list(st.exclude_funnel_ids)
    if excl_f:
        base = base.filter(Q(deal__isnull=True) | ~Q(deal__funnel_id__in=excl_f))
    if contact_ids is not None:
        base = base.filter(cid__in=list(contact_ids))
    else:
        base = base.filter(cid__isnull=False)
    inc = base.filter(direction="in")
    excl_in = _int_list(st.exclude_in_category_ids)
    if excl_in:
        inc = inc.filter(Q(category_id__isnull=True) | ~Q(category_id__in=excl_in))
    out = {r["cid"]: d(r["s"]) for r in inc.values("cid").annotate(s=Sum("amount_uah"))}
    refunds = _int_list(st.refund_category_ids)
    if refunds:
        for r in base.filter(direction="out", category_id__in=refunds).values("cid").annotate(s=Sum("amount_uah")):
            out[r["cid"]] = max(D0, out.get(r["cid"], D0) - d(r["s"]))
    return out


def level_for(turnover, levels):
    best = None
    for lv in levels:
        if d(lv.threshold_uah) <= d(turnover) and (best is None or lv.order > best.order):
            best = lv
    return best


def next_level(level, levels):
    higher = [lv for lv in levels if lv.order > level.order]
    return min(higher, key=lambda x: x.order) if higher else None


def _log_contact(contact_id, action, detail, user=None):
    try:
        from apps.crm.models import log_activity
        log_activity("contact", contact_id, action, detail, user=user)
    except Exception:
        pass


def recompute(contact_id, user=None, apply=True, st=None, levels=None):
    """Перерахувати оборот партнера і, якщо дозволено, ПІДВИЩИТИ рівень. Понижень немає ніколи.
    Повертає dict {old, new, turnover, changed} або None, якщо клієнт не в програмі."""
    st = st or PartnerSettings.get()
    levels = levels if levels is not None else list(PartnerLevel.objects.filter(is_active=True).order_by("order"))
    with transaction.atomic():
        qs = PartnerStatus.objects.select_related("level").filter(contact_id=contact_id)
        status = (qs.select_for_update() if apply else qs).first()
        if status is None:
            return None
        turnover = turnover_map([contact_id], st).get(contact_id, D0)
        target = level_for(turnover, levels)
        old = status.level
        raise_to = target if (status.is_active and st.auto_raise and target is not None
                              and target.order > old.order) else None
        if apply:
            status.turnover_uah = turnover
            status.turnover_at = timezone.now()
            if raise_to is not None:
                status.level = raise_to
                status.level_at = timezone.now()
                PartnerStatusHistory.objects.create(contact_id=contact_id, old_level=old, new_level=raise_to,
                                                    reason="auto_raise", turnover_uah=turnover, user=None,
                                                    note="оборот %s ₴ ≥ поріг %s ₴" % (q2(turnover), q2(raise_to.threshold_uah)))
            status.save()
        if apply and raise_to is not None:
            _log_contact(contact_id, "Партнер: рівень підвищено",
                         "%s → %s (оборот %s ₴)" % (old.name, raise_to.name, q2(turnover)), user=user)
    return {"old": old, "new": raise_to or old, "turnover": turnover, "changed": raise_to is not None}


class StatusError(Exception):
    pass


def mark_partner(contact, user, note=""):
    """Галочка «Партнер»: немає статусу → найнижчий рівень (Старт); був знятий → повертаємо ТОЙ САМИЙ рівень.
    Потім одразу перерахунок обороту — може підвищити."""
    levels = list(PartnerLevel.objects.filter(is_active=True).order_by("order"))
    if not levels:
        raise StatusError("Немає жодного активного рівня")
    now = timezone.now()
    with transaction.atomic():
        status = PartnerStatus.objects.select_for_update().filter(contact=contact).first()
        if status is None:
            status = PartnerStatus.objects.create(contact=contact, level=levels[0], since=timezone.localdate(),
                                                  level_at=now, assigned_by=user)
            PartnerStatusHistory.objects.create(contact=contact, old_level=None, new_level=levels[0], reason="assign",
                                                user=user, note=note[:200])
            _log_contact(contact.id, "Партнер: відмічено", "рівень %s" % levels[0].name, user=user)
        elif not status.is_active:
            status.is_active = True
            status.save(update_fields=["is_active", "updated_at"])
            PartnerStatusHistory.objects.create(contact=contact, old_level=status.level, new_level=status.level,
                                                reason="remark", user=user, note=note[:200])
            _log_contact(contact.id, "Партнер: галочку повернуто", "рівень %s" % status.level.name, user=user)
    recompute(contact.id, user=user, levels=levels)
    return PartnerStatus.objects.select_related("level").get(contact=contact)


def unmark_partner(contact, user, note=""):
    """Зняти галочку: знижки не діють, але рівень і історія лишаються (статус не падає)."""
    with transaction.atomic():
        status = PartnerStatus.objects.select_for_update().filter(contact=contact).first()
        if status is None or not status.is_active:
            return status
        status.is_active = False
        status.save(update_fields=["is_active", "updated_at"])
        PartnerStatusHistory.objects.create(contact=contact, old_level=status.level, new_level=status.level,
                                            reason="unmark", turnover_uah=status.turnover_uah, user=user, note=note[:200])
    _log_contact(contact.id, "Партнер: галочку знято", "рівень %s збережено" % status.level.name, user=user)
    return status


def raise_level(contact, level, user, note=""):
    """Ручне ПІДВИЩЕННЯ. Нижчий або той самий рівень — помилка (статус лише зростає)."""
    with transaction.atomic():
        status = PartnerStatus.objects.select_for_update().select_related("level").filter(contact=contact).first()
        if status is None or not status.is_active:
            raise StatusError("Спершу відмітьте клієнта партнером")
        if not level.is_active:
            raise StatusError("Рівень вимкнено")
        if level.order <= status.level.order:
            raise StatusError("Статус лише підвищується: зараз «%s», знизити не можна" % status.level.name)
        old = status.level
        status.level = level
        status.level_at = timezone.now()
        status.save(update_fields=["level", "level_at", "updated_at"])
        PartnerStatusHistory.objects.create(contact=contact, old_level=old, new_level=level, reason="manual",
                                            turnover_uah=status.turnover_uah, user=user, note=note[:200])
    _log_contact(contact.id, "Партнер: рівень підвищено вручну", "%s → %s. %s" % (old.name, level.name, note), user=user)
    return status


# ─────────────────────────── перевірка маржі угоди ───────────────────────────

def deal_margin(deal, can_cost):
    """Лише попередження: скільки маржі лишається в кожній позиції угоди партнера. Нічого не змінює."""
    status = PartnerStatus.objects.select_related("level").filter(contact_id=deal.contact_id, is_active=True).first() \
        if deal.contact_id else None
    if status is None:
        return {"deal_id": deal.id, "is_partner": False}
    book = RuleBook()
    rows, n_below = [], 0
    for it in deal.items.select_related("product").order_by("id"):
        product = it.product
        if product is None:
            continue
        qty = d(it.quantity)
        price = d(product.price)
        retail = qty * price
        mp = d(getattr(product, "min_price", 0))
        if mp > 0 and retail < mp:
            retail = mp
        paid = d(it.total)
        unit_c = d(it.cost) if d(it.cost) > 0 else unit_cost(product)
        cost_line = unit_c * qty if unit_c is not None and unit_c > 0 else None
        left = (paid - cost_line) / retail * D100 if (cost_line is not None and retail > 0) else None
        fact = (D100 - paid / retail * D100) if retail > 0 else None
        eff = book.effective(product, status.level)
        below = left is not None and left < book.min_pp
        n_below += 1 if below else 0
        rows.append({
            "item_id": it.id, "name": product.name, "quantity": q2(qty), "retail_line": q2(retail), "total": q2(paid),
            "discount_fact_pct": q2(fact), "recommended_pct": q2(eff["pct"]), "recommended_note": eff["note"],
            "max_pct": q2(eff["max_pct"]), "no_cost": cost_line is None, "below_min": below,
            "left_pp": q2(left) if can_cost else None,
        })
    lv = status.level
    return {"deal_id": deal.id, "is_partner": True, "level": {"id": lv.id, "name": lv.name, "color": lv.color},
            "min_margin_pp": q2(book.min_pp), "can_cost": can_cost, "rows": rows, "n_below": n_below,
            "auto_apply": bool(book.st.auto_apply)}


def since_days(days):
    return timezone.now() - timedelta(days=days)


def floor_int(x):
    return int(math.floor(float(x)))
