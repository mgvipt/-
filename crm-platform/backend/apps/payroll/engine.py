"""Один розрахунок: ЗП за місяць, вартість людини для компанії, точка беззбитковості за ATM (план v9, 14.09.2026).

Звідки цифри:
- ставки — PayScheme/PayComponent (Налаштування → Ставки співробітників);
- гроші — журнал (Transaction «in», без переказів), угоди й їхні товари (маржа = товари − собівартість);
- інші фонди точки беззбитковості — Фінмодель (крім статей, замінених ставками: policy.replaced_articles).
Точка беззбитковості за ATM, знизу вгору: Маржа = (фонди СКД + тверді фонди маржі) ÷ (1 − Σ% фондів маржі);
Виручка = Маржа ÷ (1 − Σ% фондів виручки). Суми в схемах — «на руки»; вартість для компанії рахуємо з податками.
"""
import calendar
import copy
from datetime import date, timedelta

from django.db.models import Min, Q, Sum
from django.utils import timezone

DEFAULT_POLICY = {
    "funnels": {"online": [15, 16], "salon": [5], "diamond": [6], "test": [16], "main": [15, 5]},
    "objects_direction_id": 11,
    "margin_estimate_pct": {"15": 58, "16": 60, "5": 38, "6": 40},
    "no_deal_margin_pct": 40,
    "lookback_days": 90,
    "taxes": {"pdfo": 18, "vz": 5, "esv": 22, "fop_tax": 5, "fop_esv": 1902, "fop_compensate": True},
    "dividends_pct": 0,
    "replaced_articles": [46, 55, 59],
    "conv_coef": {"enabled": False, "min": 0.8, "max": 1.2, "dead_zone": 0.10},
    "cap": {"pct_of_margin": 17, "check": "quarter"},
    "guarantee": {"amount": 15000, "months": 2},
}
GUARANTEE_CONDITIONS = [
    "Вихід за табелем: без прогулів, не менше 90% робочих днів місяця",
    "Навчання: до кінця 2-го тижня — тест по продукту (від 80%), до кінця 3-го — по CRM і правилах відповіді",
    "Швидкість: у робочий час відповідь клієнту до 15 хв у 80% чатів і більше",
    "Кожен закритий чат — з позначкою якості й причиною; жодного чату, закритого без відповіді клієнту",
    "Дожими за правилом: 1-й через 2 дні особисто, 2-й теплим через 4–5 днів",
    "З 3-го тижня: прорахунок по площі кожному, хто назвав площу або надіслав фото — не менше 20 на тиждень",
    "2-й місяць: продажі не менше 50% плану новачка",
    "Перевірка на 4-му тижні: не виконано 2 умови і більше — з наступного місяця гарантія не діє, платимо за схемою",
]


def _merge(a, b):
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(a.get(k), dict):
            _merge(a[k], v)
        else:
            a[k] = v
    return a


def policy():
    from .models import PayPolicy
    out = copy.deepcopy(DEFAULT_POLICY)
    p = PayPolicy.objects.filter(pk=1).first()
    return _merge(out, p.params if p else {})


def period_bounds(period):
    y, m = int(period[:4]), int(period[5:7])
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def add_months(d, n):
    y, m = d.year + (d.month - 1 + n) // 12, (d.month - 1 + n) % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def workdays(d1, d2):
    n, d = 0, d1
    while d <= d2:
        n += d.weekday() < 5
        d += timedelta(days=1)
    return n


def active_scheme(user, on, purpose="official"):
    from .models import PayScheme
    return (PayScheme.objects.filter(user=user, purpose=purpose, status="active", valid_from__lte=on)
            .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=on)).order_by("-valid_from", "-id").first())


def employer_cost(net, employment, pol=None):
    """Скільки компанії коштує сума «на руки». Трудовий: ПДФО 18% + військовий збір 5% утримуються з нарахованої,
    зверху ЄСВ 22% (20 000 на руки → ≈31 700). ФОП 3 гр. з компенсацією: 5% податку + ЄСВ 1 902 (20 000 → ≈22 950)."""
    t = (pol or policy())["taxes"]
    net = float(net or 0)
    if net <= 0:
        return 0.0
    if employment == "labor":
        return net / (1 - (t["pdfo"] + t["vz"]) / 100) * (1 + t["esv"] / 100)
    if employment == "fop" and t.get("fop_compensate"):
        return net / (1 - t["fop_tax"] / 100) + t["fop_esv"]
    return net


def _pct_ratio(employment, pol):
    """Множник для процентних частин (без фіксованого ЄСВ ФОП)."""
    t = pol["taxes"]
    if employment == "labor":
        return 1 / (1 - (t["pdfo"] + t["vz"]) / 100) * (1 + t["esv"] / 100)
    if employment == "fop" and t.get("fop_compensate"):
        return 1 / (1 - t["fop_tax"] / 100)
    return 1.0


# ───────── підказки «звідки ця сума» (14.09, payrates-ux: «незрозуміло, чому в Лаптева 23 766») ─────────
# Лише пояснення: числа fixed_net / fixed_cost рахуються як і раніше (employer_cost), тут вони розкладаються на кроки.

def _n(v):
    """15000 → «15 000»."""
    return f"{round(float(v or 0)):,}".replace(",", " ")


def _p(v):
    """18 → «18», 1.5 → «1,5»."""
    return f"{float(v or 0):g}".replace(".", ",")


def _dmy(d):
    return d.strftime("%d.%m.%Y") if d else ""


def cost_breakdown(net, employment, pol=None):
    """«На руки» → «компанії коштує» по кроках. Підсумок = round(employer_cost) — те саме число, що fixed_cost.
    Кожен крок округлено до гривні так, щоб кроки сходилися з підсумком (різниця копійок — в останньому кроці)."""
    pol = pol or policy()
    t = pol["taxes"]
    net = float(net or 0)
    total = round(employer_cost(net, employment, pol))
    net_r = round(net)
    if net <= 0:
        return {"steps": [], "text": "Тверду частину не задано — компанії вона нічого не коштує.", "total": 0}
    if employment == "labor":
        gross = net / (1 - (t["pdfo"] + t["vz"]) / 100)
        gross_r = round(gross)
        vz = round(gross * t["vz"] / 100)
        pdfo = gross_r - net_r - vz
        esv = total - gross_r
        steps = [
            {"label": "На руки людині", "amount": net_r},
            {"label": "Нараховано (до утримань)", "amount": gross_r,
             "hint": f"{_n(net_r)} ÷ (1 − {_p(t['pdfo'])}% − {_p(t['vz'])}%): з нарахованої суми податки утримуються, щоб на руки лишилось {_n(net_r)}"},
            {"label": f"ПДФО {_p(t['pdfo'])}% — утримується з людини", "amount": pdfo, "sub": True},
            {"label": f"Військовий збір {_p(t['vz'])}% — утримується з людини", "amount": vz, "sub": True},
            {"label": f"ЄСВ {_p(t['esv'])}% — компанія платить зверху", "amount": esv, "plus": True},
            {"label": "Компанії коштує", "amount": total, "total": True},
        ]
        text = (f"На руки {_n(net_r)} → нараховано {_n(gross_r)} (ПДФО {_p(t['pdfo'])}% = {_n(pdfo)} і військовий збір "
                f"{_p(t['vz'])}% = {_n(vz)} утримуються з людини) → ЄСВ {_p(t['esv'])}% зверху = {_n(esv)} → компанії {_n(total)} ₴")
    elif employment == "fop" and t.get("fop_compensate"):
        before = net / (1 - t["fop_tax"] / 100)
        before_r = round(before)
        tax = before_r - net_r
        esv = total - before_r
        steps = [
            {"label": "На руки людині", "amount": net_r},
            {"label": "Платимо ФОПу", "amount": before_r,
             "hint": f"{_n(net_r)} ÷ (1 − {_p(t['fop_tax'])}%): щоб після єдиного податку лишилось {_n(net_r)}"},
            {"label": f"Єдиний податок {_p(t['fop_tax'])}% — ФОП сплачує з цієї суми", "amount": tax, "sub": True},
            {"label": "ЄСВ ФОП за місяць — компенсуємо зверху", "amount": esv, "plus": True},
            {"label": "Компанії коштує", "amount": total, "total": True},
        ]
        text = (f"На руки {_n(net_r)} → платимо ФОПу {_n(before_r)}, щоб після єдиного податку {_p(t['fop_tax'])}% "
                f"({_n(tax)}) лишилось {_n(net_r)} → + ЄСВ ФОП {_n(esv)} ₴/міс (компенсуємо) → компанії {_n(total)} ₴")
    elif employment == "fop":
        steps = [{"label": "На руки людині", "amount": net_r}, {"label": "Компанії коштує", "amount": total, "total": True}]
        text = (f"ФОП сам сплачує податок {_p(t['fop_tax'])}% і ЄСВ {_n(t['fop_esv'])} ₴ зі своїх — компанія не компенсує "
                f"(вкладка «Правила компанії») → компанії коштує рівно сума на руки: {_n(total)} ₴")
    else:
        steps = [{"label": "На руки людині", "amount": net_r}, {"label": "Компанії коштує", "amount": total, "total": True}]
        text = f"Без оформлення — податків немає → компанії коштує рівно сума на руки: {_n(total)} ₴"
    return {"steps": steps, "text": text, "total": total}


_FIXED_SHORT = {"base_by_days": "оклад за вихід", "fixed_monthly": "ставка", "standard": "стандарт до"}


def _cost_explain(sc, pol, on, fixed_sum, guarantee, out):
    """Чому тверда частина саме така (з чого складається, чи діє гарантія) + розшифровка податків.
    Та сама логіка, що в scheme_cost; повертає лише нові поля."""
    items, g = [], None
    for c in sc.components.filter(active=True):
        p = c.params or {}
        if c.kind in ("base_by_days", "fixed_monthly"):
            items.append({"kind": c.kind, "title": c.title or c.get_kind_display(), "amount": round(float(p.get("amount") or 0))})
        elif c.kind == "standard":
            items.append({"kind": c.kind, "title": c.title or "Стандарт (максимум)", "amount": round(float(p.get("max") or 0))})
        elif c.kind == "guarantee":
            g_start, g_end = guarantee_window(c)
            ref = sc.planned_start if sc.is_vacancy and sc.planned_start else on
            active = bool(sc.is_vacancy or (g_start and g_start <= ref <= g_end))
            if sc.is_vacancy:
                status = "vacancy"
            elif not g_start:
                status = "no_start"
            elif active:
                status = "active"
            elif ref < g_start:
                status = "not_started"
            else:
                status = "ended"
            info = {"amount": round(float(p.get("amount") or pol["guarantee"]["amount"])), "months": int(p.get("months", 2)),
                    "start": g_start.isoformat() if g_start else None, "end": g_end.isoformat() if g_end else None,
                    "active": active, "status": status}
            if active or g is None:
                g = info
    fixed_net = out["fixed_net"]
    base = " + ".join(f"{_FIXED_SHORT.get(i['kind'], 'ставка')} {_n(i['amount'])}" for i in items)
    if len(items) > 1:
        base += f" = {_n(fixed_sum)}"
    if not items and not g:
        text = "Твердої частини немає — лише % з продажів / відрядно."
    elif g and g["active"]:
        when = (f"на перші {g['months']} міс. після виходу" if g["status"] == "vacancy"
                else f"до {_dmy(date.fromisoformat(g['end']))}")
        if not items:
            text = f"Діє гарантія {_n(g['amount'])} {when} → {_n(fixed_net)} ₴"
        elif guarantee > fixed_sum:
            text = f"{base}, але діє гарантія {_n(g['amount'])} {when} → береться більша сума: {_n(fixed_net)} ₴"
        else:
            text = f"{base}; гарантія {_n(g['amount'])} ({when}) не більша → береться {_n(fixed_net)} ₴"
    elif g:
        why = {"ended": f"закінчилась {_dmy(date.fromisoformat(g['end'])) if g['end'] else ''}",
               "not_started": f"почнеться {_dmy(date.fromisoformat(g['start'])) if g['start'] else ''}",
               "no_start": "без дати початку"}.get(g["status"], "")
        text = f"{base or '0'} ₴ (гарантія {_n(g['amount'])} {why} — зараз не враховується)"
    else:
        text = f"{base} ₴"
    notes = []
    if any(i["kind"] == "standard" for i in items):
        notes.append("Стандарт узято за максимумом (оцінка 100%) — рахуємо найдорожчий місяць.")
    if any(i["kind"] == "base_by_days" for i in items):
        notes.append("Оклад за вихід — за повний місяць; якщо днів у табелі менше, у «Розрахунку за місяць» буде менше.")
    if g and g["status"] == "vacancy":
        notes.append("Вакансія: гарантію новачку рахуємо з першого місяця після виходу.")
    if g and g["active"] and guarantee > fixed_sum:
        notes.append("Гарантію тут враховано як виплачену (найдорожчий випадок). Насправді доплата до гарантії йде лише в місяці, "
                     "коли ви відмітили «умови виконано».")
    bd = cost_breakdown(max(float(fixed_sum or 0), float(guarantee or 0)), sc.employment, pol)
    return {"fixed_items": items, "fixed_sum": round(fixed_sum), "guarantee_info": g, "fixed_explain": text,
            "fixed_notes": notes, "breakdown": bd["steps"], "breakdown_text": bd["text"]}


# Ставки складу — ТІ САМІ статті Фінмоделі (категорія «Ставки складу»), які читає склад (wh_views._rate, bundle_assembly_fee).
# Тут лише підпис одиниці й чи нараховується автоматично; копій ставок немає.
WH_RATE_INFO = {
    "WH_RATE_KG": ("₴/кг", "yes", "так — при відвантаженні, з ваги замовлення"),
    "WH_PACK_5": ("₴/посилка", "yes", "так — при відвантаженні, якщо комірник відмітив «упаковано»"),
    "WH_PACK_10": ("₴/посилка", "yes", "так — при відвантаженні, якщо комірник відмітив «упаковано»"),
    "WH_PACK_20": ("₴/посилка", "yes", "так — при відвантаженні, якщо комірник відмітив «упаковано» (понад 20 кг — кілька посилок)"),
    "WH_TINT_PCT": ("% від суми тонованих наборів", "mark", "так — лише коли комірник відмітив тоновані набори"),
    "WH_RATE_DAY": ("₴/день", "day", "лише кнопкою «Завершити день» (мінус за перебір обіду)"),
    "bundle_assembly": ("₴/набір", "no", "ні — з наступного оновлення; зараз ставка входить лише в собівартість тестового набору"),
}
_WH_ORDER = list(WH_RATE_INFO)


def warehouse_rates():
    """Ставки складу для «Налаштування → Ставки співробітників» (читання; змінюються через /api/finmodel-articles/<id>/)."""
    from apps.finance.models import FinModelArticle
    arts = FinModelArticle.objects.filter(category="warehouse_rate", active=True, parent__isnull=True)
    out = []
    for a in sorted(arts, key=lambda x: (_WH_ORDER.index(x.code) if x.code in _WH_ORDER else 99, x.sort_order, x.id)):
        unit, auto, note = WH_RATE_INFO.get(a.code, (a.unit or ("%" if a.value_type == "percent" else "₴"), "", "—"))
        out.append({"id": a.id, "code": a.code, "name": a.name, "value": float(a.value or 0), "unit": unit,
                    "auto": auto, "auto_note": note})
    return out


# ─────────────────────────── факти ───────────────────────────

def _items_margin(deal, pol):
    """Товари − собівартість (нуль у рядку → поточна собівартість товару); без товарів — норматив воронки (оцінка)."""
    items = list(deal.items.all())
    if items:
        sales = sum(float(i.total or 0) for i in items)
        if sales > 0:
            cost, est = 0.0, False
            for i in items:
                c = float(i.cost or 0) if (i.cost or 0) > 0 else float(getattr(i.product, "cost", 0) or 0)
                if c <= 0:
                    est = True
                cost += float(i.quantity or 0) * c
            return max(0.0, (sales - cost) / sales), est
    return pol["margin_estimate_pct"].get(str(deal.funnel_id), 50) / 100.0, True


def margin_map(deal_ids, pol=None):
    """Маржа багатьох угод одним махом: «економіка угоди» (apps.dealecon: уже мінус доставка, комісія, пакування, майстри),
    інакше товари − собівартість. Два запити замість сотень — вкладки ЗП і Плани гальмували."""
    pol = pol or policy()
    ids = {i for i in deal_ids if i}
    out = {}
    if not ids:
        return out
    try:
        from apps.dealecon.models import DealEconomics
        for r in DealEconomics.objects.filter(deal_id__in=ids).only("deal_id", "revenue", "margin_pct", "is_estimate"):
            if float(r.revenue or 0) > 0:
                out[r.deal_id] = (max(0.0, float(r.margin_pct or 0) / 100.0), bool(r.is_estimate))
    except Exception:
        pass
    rest = ids - set(out)
    if rest:
        from apps.crm.models import Deal
        for d in Deal.objects.filter(id__in=rest).prefetch_related("items__product"):
            out[d.id] = _items_margin(d, pol)
    return out


def deal_margin(deal, pol):
    """(частка маржі в сумі, оцінка?) для однієї угоди — те саме джерело, що margin_map."""
    return margin_map([deal.id], pol).get(deal.id) or _items_margin(deal, pol)


def _income(d1, d2, **flt):
    from apps.finance.models import Transaction
    return Transaction.objects.filter(direction="in", transfer_account__isnull=True, date__gte=d1, date__lte=d2, **flt)


def shares(pol=None, today=None):
    """Частки виручки й маржі за останні N днів — для процентних частин ставок. Кеш 5 хв."""
    from django.core.cache import cache
    pol = pol or policy()
    today = today or timezone.localdate()
    key = "payroll:shares:%s:%s" % (today.isoformat(), pol["lookback_days"])
    hit = cache.get(key)
    if hit:
        return hit
    d1 = today - timedelta(days=int(pol["lookback_days"]))
    txs = list(_income(d1, today).select_related("deal"))
    mm = margin_map([t.deal_id for t in txs], pol)
    rev_total = margin_total = objects_rev = 0.0
    by_funnel_rev, by_funnel_margin, by_owner_rev, by_owner_margin = {}, {}, {}, {}
    for t in txs:
        amt = float(t.amount_uah or 0)
        rev_total += amt
        if t.deal_id:
            m = amt * mm.get(t.deal_id, (0.5, True))[0]
            f = t.deal.funnel_id
            by_funnel_rev[f] = by_funnel_rev.get(f, 0) + amt
            by_funnel_margin[f] = by_funnel_margin.get(f, 0) + m
            key2 = (t.deal.owner_id, f)
            by_owner_rev[key2] = by_owner_rev.get(key2, 0) + amt
            by_owner_margin[key2] = by_owner_margin.get(key2, 0) + m
        else:
            m = amt * pol["no_deal_margin_pct"] / 100.0
            if t.fin_direction_id == pol["objects_direction_id"]:
                objects_rev += amt
        margin_total += m
    months = max(1.0, int(pol["lookback_days"]) / 30.0)
    res = {"rev_total": rev_total, "margin_total": margin_total, "by_funnel_rev": by_funnel_rev,
           "by_funnel_margin": by_funnel_margin, "by_owner_rev": by_owner_rev, "by_owner_margin": by_owner_margin,
           "objects_rev": objects_rev, "months": months,
           "margin_pct": (margin_total / rev_total) if rev_total else 0.0, "deals": len(mm), "from": d1, "to": today}
    cache.set(key, res, 300)
    return res


# ─────────────────────────── ЗП за місяць ───────────────────────────

def _line(comp, amount, basis=None, rate=None, detail="", estimate=False, warn=""):
    return {"component": comp.id if comp else None, "kind": comp.kind if comp else "insurance",
            "title": (comp.title or comp.get_kind_display()) if comp else "Страховочний місяць",
            "basis": round(basis) if isinstance(basis, (int, float)) else basis, "rate": rate,
            "amount": round(float(amount or 0)), "detail": detail, "estimate": estimate, "warn": warn}


def _prorate(sc, d1, d2):
    """Частка місяця, коли схема діяла (новачок вийшов 14-го → оплата за робочі дні з 14-го).
    Режим «приклад» (схема на місяць поза її дією) — повний місяць."""
    if getattr(sc, "_preview", False):
        return 1.0
    start = max(d1, sc.valid_from)
    end = min(d2, sc.valid_to) if sc.valid_to else d2
    full = workdays(d1, d2) or 1
    return (workdays(start, end) / full) if start <= end else 0.0


def _c_base(sc, comp, user, d1, d2, pol):
    from apps.finance.models import WorkDay
    amt = float(comp.params.get("amount") or 0)
    norm = workdays(d1, d2) or 1
    wd = WorkDay.objects.filter(user=user, date__gte=(d1 if getattr(sc, "_preview", False) else max(d1, sc.valid_from)), date__lte=d2)
    if user and wd.exists():
        worked = wd.filter(status__in=["worked", "overtime"]).count()
        over = wd.filter(status="overtime").count()
        a = amt * min(worked, norm) / norm + over * amt / norm
        return _line(comp, a, amt, None, f"{worked} з {norm} роб. днів" + (f", +{over} вихідних" if over else ""))
    k = _prorate(sc, d1, d2)
    return _line(comp, amt * k, amt, None, "повний місяць" if k >= 0.999 else f"{round(k * 100)}% місяця (з {sc.valid_from:%d.%m})",
                 warn="табель не заповнено — пораховано по календарю" if user else "")


def _c_fixed(sc, comp, d1, d2):
    amt = float(comp.params.get("amount") or 0)
    k = _prorate(sc, d1, d2)
    return _line(comp, amt * k, amt, None, "" if k >= 0.999 else f"{round(k * 100)}% місяця",
                 warn="ставку не задано — вкажіть суму" if amt <= 0 else "")


def _c_standard(comp, period):
    mx = float(comp.params.get("max") or 0)
    sc = (comp.params.get("scores") or {}).get(period)
    score = float(sc) if sc is not None else 1.0
    return _line(comp, mx * score, mx, f"{round(score * 100)}%", "оцінка стандарту за місяць",
                 warn="" if sc is not None else "оцінку стандарту не виставлено — узято 100%"), score


def _plan(user, period):
    from apps.finance.models import ManagerPlan
    p = ManagerPlan.objects.filter(user=user, period=period).first()
    return float(p.target_revenue) if p and p.target_revenue else 0.0


def _c_margin(comp, user, period, d1, d2, pol, std_score):
    p = comp.params
    funnels = p.get("funnels") or pol["funnels"]["online"]
    rev = margin = 0.0
    est, cache, deals = 0, {}, set()
    txs = list(_income(d1, d2, deal__owner=user, deal__funnel_id__in=funnels))
    cache.update(margin_map([t.deal_id for t in txs], pol))
    for t in txs:
        r, e = cache.get(t.deal_id, (0.5, True))
        amt = float(t.amount_uah or 0)
        rev += amt
        margin += amt * r
        est += 1 if e else 0
        deals.add(t.deal_id)
    to_pct = float(p.get("pct_to_plan", 10))
    over_pct = float(p.get("pct_over_plan", to_pct))
    plan = _plan(user, period)
    over_share = max(0.0, rev - plan) / rev if (plan and rev) else 0.0
    gate = std_score >= float(p.get("gate_standard_min", 0.75))
    amount = margin * (1 - over_share) * to_pct / 100 + margin * over_share * (over_pct if gate else to_pct) / 100
    coef = 1.0
    notes = []
    if not pol["conv_coef"].get("enabled"):
        notes.append("коефіцієнт конверсії = 1,0 (вмикається, коли назбирається 2 міс. позначок якості)")
    if not plan:
        notes.append(f"план не встановлено — все за ставкою {to_pct:g}%")
    elif over_share > 0 and not gate:
        notes.append(f"понад план {over_pct:g}% не нараховано: стандарт нижче {round(float(p.get('gate_standard_min', 0.75)) * 100)}%")
    det = f"оплати {round(rev):,} ₴ по {len(deals)} угодах, маржа {round(margin):,} ₴".replace(",", " ")
    if plan:
        det += f"; план {round(plan):,} ₴".replace(",", " ")
    return _line(comp, amount * coef, margin, f"{to_pct:g}% / {over_pct:g}%", det + ("; " + "; ".join(notes) if notes else ""),
                 estimate=est > 0, warn=f"{est} оплат по угодах без собівартості — маржа оцінкою" if est else "")


def _c_revenue(comp, user, period, d1, d2, pol):
    from .models import ObjectAct
    p = comp.params
    pct = float(p.get("pct") or 0)
    basis = p.get("basis", "funnels")
    if basis == "object_acts":
        acts = ObjectAct.objects.filter(status="closed", payroll_period=period, manager=user)
        base = float(acts.aggregate(s=Sum("amount_total"))["s"] or 0)
        amt = float(acts.aggregate(s=Sum("commission_amount"))["s"] or 0) or base * pct / 100
        return _line(comp, amt, base, f"{pct:g}%", f"закриті акти за місяць: {acts.count()}",
                     warn="" if acts.exists() else "актів, закритих цього місяця, немає")
    if basis == "objects_income":
        base = float(_income(d1, d2, fin_direction_id=pol["objects_direction_id"], deal__isnull=True)
                     .aggregate(s=Sum("amount_uah"))["s"] or 0)
        return _line(comp, base * pct / 100, base, f"{pct:g}%", "приходи напрямку «Обʼєкти» без угод", estimate=True)
    flt = {}
    if basis == "own_payments" or p.get("own_only", True):
        flt["deal__owner"] = user
    if basis == "funnels":
        flt["deal__funnel_id__in"] = p.get("funnels") or []
    else:
        flt["deal__isnull"] = False
    base = float(_income(d1, d2, **flt).aggregate(s=Sum("amount_uah"))["s"] or 0)
    return _line(comp, base * pct / 100, base, f"{pct:g}%", "оплати за місяць")


def _first_pay():
    from apps.finance.models import Transaction
    return (Transaction.objects.filter(direction="in", transfer_account__isnull=True, deal__isnull=False)
            .values("deal_id").annotate(first=Min("date"), total=Sum("amount_uah")))


def _c_event(comp, user, d1, d2, pol):
    """Бонус «тест-набір → основне»: перше оплачене основне замовлення клієнта після оплаченого тест-набору;
    місяць — місяць оплати основного; кому — власнику основної угоди; раз на клієнта."""
    from apps.crm.models import Deal
    p = comp.params
    tiers = p.get("tiers") or {"fast_days": 30, "min_order": 3000, "fast": 300, "slow": 200, "small": 100}
    test_f = pol["funnels"]["test"]
    main_f = pol["funnels"]["main"]
    fp = {r["deal_id"]: r for r in _first_pay()}
    mine = Deal.objects.filter(owner=user, funnel_id__in=main_f, id__in=[i for i, r in fp.items() if d1 <= r["first"] <= d2])
    total, n, rows = 0, 0, []
    for d in mine.select_related("contact"):
        if not d.contact_id:
            continue
        first_main = fp[d.id]["first"]
        tests = [fp[x]["first"] for x in Deal.objects.filter(contact_id=d.contact_id, funnel_id__in=test_f).values_list("id", flat=True)
                 if x in fp and fp[x]["first"] <= first_main]
        if not tests:
            continue
        earlier_main = [x for x in Deal.objects.filter(contact_id=d.contact_id, funnel_id__in=main_f).exclude(id=d.id)
                        .values_list("id", flat=True) if x in fp and min(tests) <= fp[x]["first"] < first_main]
        if earlier_main:
            continue
        days = (first_main - min(tests)).days
        order = float(fp[d.id]["total"] or d.amount or 0)
        b = tiers["small"] if order < tiers["min_order"] else (tiers["fast"] if days <= tiers["fast_days"] else tiers["slow"])
        total += b
        n += 1
        rows.append(d.id)
    return _line(comp, total, n, "300 / 200 / 100 ₴", f"основних після тест-набору: {n}" + (f" (угоди {', '.join(map(str, rows[:8]))})" if rows else ""))


def _c_piece(comp, user, d1, d2):
    from apps.warehouse.models import WarehousePayrollEntry
    s = float(WarehousePayrollEntry.objects.filter(employee=user, work_date__gte=d1, work_date__lte=d2, status="confirmed")
              .aggregate(s=Sum("amount"))["s"] or 0)
    return _line(comp, s, None, None, "відрядні записи складу (вага, пакування, тонування, день)")


def guarantee_window(comp):
    p = comp.params
    start = date.fromisoformat(p["start"]) if p.get("start") else None
    if not start:
        return None, None
    return start, add_months(start, int(p.get("months", 2))) - timedelta(days=1)


def calc(user, period, scheme=None, purpose="official", _nested=False):
    pol = policy()
    d1, d2 = period_bounds(period)
    sc = scheme or active_scheme(user, d2, purpose)
    if sc is not None and scheme is not None:
        # «приклад»: схему рахують на місяць, коли вона ще/вже не діяла (Олег: «показати на наявних даних, як буде»)
        sc._preview = not (sc.valid_from <= d2 and (sc.valid_to is None or sc.valid_to >= d1))
    who = (user.get_full_name() or user.username) if user else ""
    if not sc:
        return {"user_id": user.id if user else None, "user_name": who, "period": period, "scheme": None,
                "lines": [], "total": 0, "company_cost": 0, "warnings": ["ставку не задано — Налаштування → Ставки співробітників"]}
    comps = list(sc.components.filter(active=True))
    lines, std_score = [], 1.0
    for c in comps:
        if c.kind == "base_by_days":
            lines.append(_c_base(sc, c, user, d1, d2, pol))
        elif c.kind == "fixed_monthly":
            lines.append(_c_fixed(sc, c, d1, d2))
        elif c.kind == "standard":
            ln, std_score = _c_standard(c, period)
            lines.append(ln)
    for c in comps:
        if c.kind == "margin_share" and user:
            lines.append(_c_margin(c, user, period, d1, d2, pol, std_score))
        elif c.kind == "revenue_share" and user:
            lines.append(_c_revenue(c, user, period, d1, d2, pol))
        elif c.kind == "event_bonus" and user:
            lines.append(_c_event(c, user, d1, d2, pol))
        elif c.kind == "piece_rate" and user:
            lines.append(_c_piece(c, user, d1, d2))
    subtotal = sum(l["amount"] for l in lines)
    for c in comps:
        if c.kind != "guarantee":
            continue
        g_start, g_end = guarantee_window(c)
        if not g_start or d2 < g_start or d1 > g_end:
            continue
        g_amt = float(c.params.get("amount") or pol["guarantee"]["amount"])
        s, e = max(d1, g_start), min(d2, g_end)
        k = workdays(s, e) / (workdays(d1, d2) or 1)
        target = g_amt * k
        topup = max(0.0, target - subtotal)
        chk = (c.params.get("checks") or {}).get(period) or {}
        if chk.get("ok"):
            lines.append(_line(c, topup, round(target), None, f"доплата до гарантії {round(target):,} ₴ (умови виконано)".replace(",", " ")))
        else:
            lines.append(_line(c, 0, round(target), None,
                               f"доплата до гарантії: +{round(topup):,} ₴ — лише після підтвердження умов".replace(",", " "),
                               warn="умови гарантії за місяць не підтверджено" if topup > 0 else ""))
    total = sum(l["amount"] for l in lines)
    legacy = None
    if purpose == "official" and not _nested and user:
        lsc = active_scheme(user, d1, "legacy")
        if lsc:
            legacy = calc(user, period, scheme=lsc, purpose="legacy", _nested=True)
            first = (sc.valid_from.year, sc.valid_from.month) == (d1.year, d1.month)
            if (sc.options or {}).get("insurance_first_month") and first and legacy["total"] > total:
                lines.append(_line(None, legacy["total"] - total, legacy["total"], None,
                                   "перший місяць нової схеми: платимо більшу з двох (стара дала б більше)"))
                total = sum(l["amount"] for l in lines)
    return {"user_id": user.id if user else None, "user_name": who, "period": period,
            "scheme": {"id": sc.id, "position": sc.position, "title": sc.title, "valid_from": sc.valid_from.isoformat(),
                       "employment": sc.employment, "employment_label": sc.get_employment_display()},
            "preview": bool(getattr(sc, "_preview", False)),
            "lines": lines, "total": round(total), "company_cost": round(employer_cost(total, sc.employment, pol)),
            "warnings": [l["warn"] for l in lines if l.get("warn")],
            "legacy": {"total": legacy["total"], "lines": legacy["lines"], "title": legacy["scheme"]["title"]} if legacy and legacy.get("scheme") else None}


def staff_on(on, purpose="official"):
    """Діючі схеми на дату: по одній на співробітника + посади без акаунта (не вакансії)."""
    from .models import PayScheme
    qs = (PayScheme.objects.filter(purpose=purpose, status="active", valid_from__lte=on)
          .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=on)).select_related("user").order_by("-valid_from", "-id"))
    seen, out = set(), []
    for s in qs:
        key = ("u", s.user_id) if s.user_id else ("p", s.id)
        if s.is_vacancy or key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def calc_team(period):
    d1, d2 = period_bounds(period)
    rows = [calc(s.user, period) for s in staff_on(d2) if s.user_id]
    rows.sort(key=lambda r: -r["total"])
    return {"period": period, "rows": rows, "total": sum(r["total"] for r in rows),
            "company_cost": sum(r["company_cost"] for r in rows)}


# ─────────────────────────── вартість людини і точка беззбитковості ───────────────────────────

def scheme_cost(sc, pol=None, sh=None, on=None):
    """Скільки схема коштує компанії на місяць: тверда частина (₴) і процентні частини (% маржі / % виручки)."""
    pol = pol or policy()
    sh = sh or shares(pol)
    on = on or timezone.localdate()
    fixed_net, m_pct, r_pct, parts = 0.0, 0.0, 0.0, []
    piece_pct = 0.0
    guarantee = 0.0
    for c in sc.components.filter(active=True):
        p = c.params or {}
        if c.kind in ("base_by_days", "fixed_monthly"):
            fixed_net += float(p.get("amount") or 0)
            parts.append((c.title or c.get_kind_display(), float(p.get("amount") or 0), "₴"))
        elif c.kind == "standard":
            fixed_net += float(p.get("max") or 0)
            parts.append((c.title or "Стандарт (максимум)", float(p.get("max") or 0), "₴"))
        elif c.kind == "guarantee":
            g_start, g_end = guarantee_window(c)
            ref = sc.planned_start if sc.is_vacancy and sc.planned_start else on
            if sc.is_vacancy or (g_start and g_start <= ref <= g_end):
                guarantee = float(p.get("amount") or pol["guarantee"]["amount"])
        elif c.kind == "margin_share":
            funnels = p.get("funnels") or pol["funnels"]["online"]
            # % продавця — лише з маржі ЙОГО угод (частка за останні N днів); нова людина / вакансія = 0:
            # її % платиться з нових продажів, у точці беззбитковості — лише тверда частина
            own = sum(sh["by_owner_margin"].get((sc.user_id, f), 0) for f in funnels) if sc.user_id else 0.0
            share = (own / sh["margin_total"]) if (sh["margin_total"] and not sc.is_vacancy) else 0.0
            add = float(p.get("pct_to_plan", 10)) / 100 * share
            m_pct += add
            parts.append((c.title or "% з маржі", round(add * 100, 2), "% маржі"))
        elif c.kind == "revenue_share":
            pct = float(p.get("pct") or 0) / 100
            if p.get("basis") in ("object_acts", "objects_income"):
                share = sh["objects_rev"] / sh["rev_total"] if sh["rev_total"] else 0
            elif p.get("basis") == "own_payments":
                own = sum(v for (o, _f), v in sh["by_owner_rev"].items() if o == sc.user_id) if sc.user_id else 0.0
                share = own / sh["rev_total"] if sh["rev_total"] else 0
            elif p.get("own_only", True) and sc.user_id:
                own = sum(sh["by_owner_rev"].get((sc.user_id, f), 0) for f in (p.get("funnels") or []))
                share = own / sh["rev_total"] if sh["rev_total"] else 0
            else:
                share = (sum(sh["by_funnel_rev"].get(f, 0) for f in (p.get("funnels") or [])) / sh["rev_total"]) if sh["rev_total"] else 0
            add = pct * share
            r_pct += add
            parts.append((c.title or "% з обороту", round(add * 100, 2), "% виручки"))
        elif c.kind == "piece_rate" and sc.user_id and sh["rev_total"]:
            from apps.warehouse.models import WarehousePayrollEntry
            s = float(WarehousePayrollEntry.objects.filter(employee_id=sc.user_id, work_date__gte=sh["from"],
                                                           work_date__lte=sh["to"], status="confirmed")
                      .aggregate(x=Sum("amount"))["x"] or 0)
            add = s / sh["rev_total"]
            r_pct += add
            piece_pct += add
            parts.append((c.title or "Відрядно", round(add * 100, 2), "% виручки"))
    fixed_sum = fixed_net
    fixed_net = max(fixed_net, guarantee)
    ratio = _pct_ratio(sc.employment, pol)
    out = {"fixed_net": round(fixed_net), "fixed_cost": round(employer_cost(fixed_net, sc.employment, pol)),
           "margin_pct": m_pct * ratio, "revenue_pct": r_pct * ratio, "piece_pct": piece_pct * ratio, "taxes_ratio": round(ratio, 3),
           "guarantee": guarantee, "parts": parts}
    # 14.09 (payrates-ux): підказки «чому саме ця сума» — лише нові поля, числа вище не змінюються
    out.update(_cost_explain(sc, pol, on, fixed_sum, guarantee, out))
    return out


FUND_BY_DEPT = {"Продажі": 59, "Склад": 59, "Офіс": 59, "Маркетинг": 53}  # тверда частина → фонд Олега
PCT_FUND = 46     # «ФОТ % продажу (комісія менеджера)» — % з виручки
PIECE_FUND = 55   # «ФОТ упаковка/тонування/відгрузка» — ₴/міс
GROUP_LABELS = {"revenue": "Фонди виручки (ФВ)", "margin": "Фонди маржі (ФМ)", "skd": "Фонди СКД (ФСКД)",
                "upr": "Управлінські (УПР)", "other": "Інше"}


def fund_of(sc):
    """У який фонд «Планування» йде тверда частина цієї людини/вакансії (options.fund_article_id або за відділом)."""
    o = (sc.options or {}).get("fund_article_id")
    return int(o) if o else FUND_BY_DEPT.get(sc.department, 59)


def breakeven_atm(extra_ids=(), without_ids=(), today=None):
    """Точка беззбитковості — ОДНА для всієї CRM: її рахують Фінанси (compute_breakeven) з фондів, розставлених у «Плануванні».
    Тут лише розшифровка по групах фондів, порівняння «ФОТ у фонді / за ставками» і вакансії «що якщо».
    Ставки фонди НЕ підміняють: значення фонду міняє лише Олег (кнопка «Підставити зі ставок»)."""
    from apps.finance.models import FinModelArticle, WorkDay  # noqa: F401
    from apps.finance.services import _fin_articles, compute_breakeven
    from .models import PayScheme
    pol = policy()
    today = today or timezone.localdate()
    d1 = today.replace(day=1)
    d2 = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
    be = compute_breakeven(d1, d2)
    mpct = float(be.get("margin_pct") or 0)
    k = (100.0 / mpct) if mpct > 0 else None
    arts = _fin_articles()
    # групи — рівно як у «Плануванні» (FinModelArticle.fund_group); у ТБ входить те саме, що рахує compute_breakeven
    levels = {"revenue": [], "margin": [], "skd": [], "upr": [], "other": []}
    fund_sum = 0.0
    monthly_types = ("fixed_sum_per_month", "auto_meta_ads")
    for a in sorted(arts, key=lambda x: (x.category, x.sort_order, x.id)):
        v = float(a.value or 0)
        row = {"id": a.id, "name": a.name, "value": v, "auto": a.value_type == "auto_meta_ads"}
        if a.category in ("revenue_fund", "payment_fee") and a.value_type == "percent":
            levels["revenue"].append({**row, "unit": "%"})
        elif a.category in ("fixed", "variable") and a.value_type in monthly_types:
            levels["margin"].append({**row, "unit": "₴", "kind": "постійні" if a.category == "fixed" else "змінні"})
            fund_sum += v
        elif a.category == "skd" and a.value_type in monthly_types:
            levels["skd"].append({**row, "unit": "₴"})
            fund_sum += v
        elif a.category == "upr_cat2" and a.value_type in monthly_types:
            levels["upr"].append({**row, "unit": "₴"})
            fund_sum += v
    per_deal = round(float(be.get("monthly_costs") or 0) - fund_sum)
    if per_deal:
        levels["other"].append({"id": 50, "name": "AI-витрати на угоду × угоди місяця", "value": per_deal, "unit": "₴"})
    # ФОТ: що у фондах і що виходить за ставками
    sh = shares(pol, today)
    art_by_id = {a.id: a for a in arts}
    by_fund, pct_rev = {}, 0.0
    for s in staff_on(today):
        c = scheme_cost(s, pol, sh, today)
        f = fund_of(s)
        r = by_fund.setdefault(f, {"sum": 0.0, "people": []})
        r["sum"] += c["fixed_cost"]
        if c["fixed_cost"]:
            r["people"].append({"name": (s.user.get_full_name() or s.user.username) if s.user_id else s.position, "amount": c["fixed_cost"]})
        pct_rev += c["margin_pct"] * sh["margin_pct"] + c["revenue_pct"] - c.get("piece_pct", 0)
    piece_month = 0.0
    try:
        from apps.warehouse.models import WarehousePayrollEntry
        piece_month = float(WarehousePayrollEntry.objects.filter(work_date__gte=sh["from"], work_date__lte=sh["to"], status="confirmed")
                            .aggregate(x=Sum("amount"))["x"] or 0) / sh["months"]
    except Exception:
        pass
    fot = []
    for fid in sorted(set(by_fund) | {PCT_FUND, PIECE_FUND}):
        a = art_by_id.get(fid)
        if not a:
            continue
        if fid == PCT_FUND:
            sug, unit, people = round(pct_rev * 100, 2), "%", []
        elif fid == PIECE_FUND:
            sug, unit, people = round(piece_month), "₴", []
        else:
            sug, unit, people = round(by_fund[fid]["sum"]), "₴", by_fund[fid]["people"]
        cur = float(a.value or 0)
        fot.append({"fund_id": fid, "name": a.name, "unit": unit, "value": cur, "suggested": sug,
                    "diff": round(sug - cur, 2), "people": people,
                    # «Маркетинг СММ» містить і контент/рекламу, не лише людей — тільки порівняння, без кнопки
                    "syncable": a.name.strip().upper().startswith("ФОТ")})
    # вакансії «що якщо»: тверда частина з податками → у свій фонд → ТБ зростає на суму × k
    vac, add = [], 0.0
    for v in PayScheme.objects.filter(is_vacancy=True, status="active", purpose="official").order_by("planned_start", "id"):
        c = scheme_cost(v, pol, sh, today)
        included = (v.in_plan or v.id in extra_ids) and v.id not in without_ids
        delta = round(c["fixed_cost"] * k) if k else None
        if included and delta:
            add += delta
        a = art_by_id.get(fund_of(v))
        vac.append({"scheme_id": v.id, "position": v.position, "planned_start": v.planned_start.isoformat() if v.planned_start else None,
                    "employment": v.get_employment_display(), "included": included, "fixed_net": c["fixed_net"],
                    "fixed_cost": c["fixed_cost"], "fund": a.name if a else "", "delta_breakeven": delta, "payback_revenue": delta})
    base = float(be.get("breakeven") or 0)
    return {
        "breakeven": round(base), "breakeven_with": round(base + add), "with_delta": round(add),
        "k_fixed": round(k, 2) if k else None, "margin_pct": mpct, "rev_funds_pct": be.get("rev_funds_pct"),
        "monthly_costs": be.get("monthly_costs"), "margin_needed": round(base * mpct / 100) if mpct else None,
        "revenue_month": be.get("revenue"), "progress": be.get("progress"),
        "levels": levels, "group_labels": GROUP_LABELS,
        "formula": "ТБ = (фонди маржі + фонди СКД) ÷ маржинальність %d%%" % round(mpct) if mpct else "",
        "fot": fot, "vacancies": vac,
        "shares": {"from": sh["from"].isoformat(), "to": sh["to"].isoformat(), "margin_pct": round(sh["margin_pct"] * 100, 1)},
    }


def deal_bonus_preview(deal):
    """Бонус менеджера з угоди за його схемою (картка угоди). None — схеми немає (тоді стара формула)."""
    if not deal.owner_id:
        return None
    sc = active_scheme(deal.owner, timezone.localdate())
    if not sc:
        return None
    pol = policy()
    r, est = deal_margin(deal, pol)
    amount = float(deal.amount or 0)
    m_pct = r_pct = 0.0
    for c in sc.components.filter(active=True, kind__in=["margin_share", "revenue_share"]):
        p = c.params or {}
        if c.kind == "margin_share" and deal.funnel_id in (p.get("funnels") or pol["funnels"]["online"]):
            m_pct += float(p.get("pct_to_plan", 10))
        if c.kind == "revenue_share" and p.get("basis", "funnels") == "funnels" and deal.funnel_id in (p.get("funnels") or []):
            r_pct += float(p.get("pct") or 0)
        if c.kind == "revenue_share" and p.get("basis") == "own_payments":
            r_pct += float(p.get("pct") or 0)
    margin = amount * r
    from_m, from_r = margin * m_pct / 100, amount * r_pct / 100
    return {"total": round(from_m + from_r, 2), "from_revenue": round(from_r, 2), "from_margin": round(from_m, 2),
            "revenue_pct": r_pct, "margin_pct": m_pct, "scheme": sc.title or sc.position, "estimate": est,
            "note": "до плану; понад план і коефіцієнт конверсії — у ЗП за місяць"}
