"""15.09.2026 (whpay): «Як прорахувалась ЗП» — розшифровка кожного рядка ЗП за ставками до угод, оплат і записів складу.

GET /api/payroll/calc-detail/?user=<id>&period=YYYY-MM — право payroll.rates.view (за замовчуванням лише власник).

Лише читання, у БД нічого не пише. Кожна розшифровка повторює ТУ САМУ вибірку, що й apps.payroll.engine
(_c_base, _c_fixed, _c_standard, _c_margin, _c_revenue, _c_event, _c_piece, гарантія, страховий місяць); рушій не
змінюється. «Разом за розшифровкою» = сума рядка (tests_calc_detail). Затверджений місяць не переписується: розшифровка
завжди наживо, поруч — затверджена сума. Один запит на людину; маржа угод — engine.margin_map одним махом, без N+1.
"""
import logging
import re
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import engine

log = logging.getLogger(__name__)

PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
MAX_ROWS = 1500                                   # запобіжник для екрана; «Разом» — завжди з повної вибірки
AFTER_KINDS = ("guarantee", "insurance", "bounty")  # рядки, які engine.calc додає після основних
TIER = {"T5": "5 кг", "T10": "10 кг", "T20": "20 кг"}


def _can(u, code):
    return bool(u and u.is_authenticated and (u.is_superuser or (hasattr(u, "has_perm_code") and u.has_perm_code(code))))


def _f(x, nd=2):
    return round(float(x or 0), nd)


def _n2(x):
    """1234.5 → «1 234,50»."""
    return f"{float(x or 0):,.2f}".replace(",", " ").replace(".", ",")


def _dm(d):
    return d.strftime("%d.%m") if d else ""


def _col(k, label, t="text"):
    """t: date | deal | money | pct | num | text — як показувати в таблиці."""
    return {"k": k, "label": label, "t": t}


def _client(deal):
    if not deal:
        return ""
    c = deal.contact if deal.contact_id else None
    if c:
        name = " ".join(x for x in (c.first_name, c.last_name) if x).strip()
        return name or c.nickname or c.phone or ""
    return deal.title or ""


def _funnel_names(ids):
    from apps.crm.models import Funnel
    ids = list(ids or [])
    names = dict(Funnel.objects.filter(id__in=ids).values_list("id", "name"))
    return ", ".join(names.get(i, str(i)) for i in ids) or "—"


def _out(total, explain="", summary=None, columns=None, rows=None, groups=None, warnings=None, notes=None, links=None,
         truncated=False):
    return {"total": total, "explain": explain, "summary": summary or [], "columns": columns or [], "rows": rows or [],
            "groups": groups or [], "warnings": warnings or [], "notes": notes or [], "links": links or [],
            "truncated": bool(truncated)}


# ─────────────────────────── ставка / оклад ───────────────────────────

def _d_base(comp, sc, user, d1, d2):
    """= engine._c_base: оклад × відпрацьовані дні табеля / робочі дні (+ вихід у вихідний); без табеля — по календарю."""
    from apps.finance.models import WorkDay
    amt = float((comp.params or {}).get("amount") or 0)
    norm = engine.workdays(d1, d2) or 1
    start = d1 if getattr(sc, "_preview", False) else max(d1, sc.valid_from)
    days = list(WorkDay.objects.filter(user=user, date__gte=start, date__lte=d2).order_by("date"))
    labels = dict(WorkDay.STATUS)
    if user and days:
        worked = sum(1 for x in days if x.status in ("worked", "overtime"))
        over = sum(1 for x in days if x.status == "overtime")
        a = amt * min(worked, norm) / norm + over * amt / norm
        by = {}
        for x in days:
            by[x.status] = by.get(x.status, 0) + 1
        expl = (f"Оклад {engine._n(amt)} ₴ — за {norm} робочих днів місяця. За табелем відпрацьовано {worked}"
                + (f" (з них {over} — вихід у вихідний)" if over else "")
                + f": {engine._n(amt)} × {min(worked, norm)} / {norm}"
                + (f" + {over} × {engine._n(amt)} / {norm}" if over else "") + f" = {_n2(a)} ₴.")
        rows = [{"date": x.date.isoformat(), "status": labels.get(x.status, x.status),
                 "paid": "так" if x.status in ("worked", "overtime") else "ні", "note": x.note or ""} for x in days]
        return _out(round(a), expl, [{"label": labels.get(k, k), "value": f"{v} дн."} for k, v in by.items()],
                    [_col("date", "Дата", "date"), _col("status", "Табель"), _col("paid", "Оплачується"), _col("note", "Примітка")],
                    rows)
    k = engine._prorate(sc, d1, d2)
    a = amt * k
    expl = (f"Табель за місяць не заповнено — оклад {engine._n(amt)} ₴ пораховано по календарю: "
            + ("повний місяць" if k >= 0.999 else f"{round(k * 100)}% місяця (з {sc.valid_from:%d.%m})") + f" = {_n2(a)} ₴.")
    return _out(round(a), expl, warnings=["Табель не заповнено — Фінанси → Табель"] if user else [])


def _d_fixed(comp, sc, d1, d2):
    """= engine._c_fixed: сума × частка місяця, коли схема діяла."""
    amt = float((comp.params or {}).get("amount") or 0)
    k = engine._prorate(sc, d1, d2)
    if k >= 0.999:
        expl = f"Фіксована ставка {engine._n(amt)} ₴ за повний місяць."
    else:
        start = max(d1, sc.valid_from)
        end = min(d2, sc.valid_to) if sc.valid_to else d2
        expl = (f"Фіксована ставка {engine._n(amt)} ₴ × частка місяця: робочих днів з {_dm(start)} по {_dm(end)} — "
                f"{engine.workdays(start, end) if start <= end else 0} з {engine.workdays(d1, d2)} ({round(k * 100)}%) "
                f"= {_n2(amt * k)} ₴.")
    return _out(round(amt * k), expl, warnings=["Ставку не задано — Налаштування → Ставки співробітників"] if amt <= 0 else [])


def _d_standard(comp, period):
    """= engine._c_standard: максимум × оцінка стандарту за місяць (немає оцінки — 100%)."""
    p = comp.params or {}
    mx = float(p.get("max") or 0)
    s = (p.get("scores") or {}).get(period)
    score = float(s) if s is not None else 1.0
    expl = (f"Стандарт роботи: до {engine._n(mx)} ₴ × оцінка за місяць {round(score * 100)}% = {_n2(mx * score)} ₴."
            + ("" if s is not None else " Оцінку за місяць не виставлено — узято 100%."))
    return _out(round(mx * score), expl)


# ─────────────────────────── % з маржі / з обороту ───────────────────────────

def _margin_sources(deal_ids):
    """Звідки маржа угоди (лише підпис; саме число — engine.margin_map): «економіка угоди» чи товари."""
    ids = {i for i in deal_ids if i}
    econ, items = set(), set()
    if not ids:
        return econ, items
    try:
        from apps.dealecon.models import DealEconomics
        econ = set(DealEconomics.objects.filter(deal_id__in=ids, revenue__gt=0).values_list("deal_id", flat=True))
    except Exception:
        econ = set()
    from apps.crm.models import DealItem
    items = set(DealItem.objects.filter(deal_id__in=ids - econ).values_list("deal_id", flat=True))
    return econ, items


def _src(did, est, econ, items):
    if did in econ:
        return "економіка угоди" + (" (є оцінки)" if est else "")
    if did in items:
        return "товари − собівартість" + (" (не в усіх товарів є собівартість — оцінка)" if est else "")
    return "норматив воронки (оцінка)"


def _d_margin(comp, user, period, d1, d2, pol, std_score):
    """= engine._c_margin: оплати місяця по угодах людини у воронках × маржа угоди; частина понад план — за ставкою
    понад план (якщо стандарт не нижче порогу). План ділить маржу пропорційно, як у рушії."""
    p = comp.params or {}
    funnels = p.get("funnels") or pol["funnels"]["online"]
    txs = list(engine._income(d1, d2, deal__owner=user, deal__funnel_id__in=funnels)
               .select_related("deal", "deal__contact", "deal__funnel").order_by("date", "id"))
    mm = engine.margin_map([t.deal_id for t in txs], pol)
    econ, items = _margin_sources([t.deal_id for t in txs])
    rev = margin = 0.0
    raw, deals, est_n = [], set(), 0
    for t in txs:
        r, e = mm.get(t.deal_id, (0.5, True))
        amt = float(t.amount_uah or 0)
        rev += amt
        margin += amt * r
        est_n += 1 if e else 0
        deals.add(t.deal_id)
        raw.append((t, amt, r, e))
    to_pct = float(p.get("pct_to_plan", 10))
    over_pct = float(p.get("pct_over_plan", to_pct))
    plan = engine._plan(user, period)
    over_share = max(0.0, rev - plan) / rev if (plan and rev) else 0.0
    gate_min = float(p.get("gate_standard_min", 0.75))
    gate = std_score >= gate_min
    eff_over = over_pct if gate else to_pct
    amount = margin * (1 - over_share) * to_pct / 100 + margin * over_share * eff_over / 100
    k = (1 - over_share) * to_pct / 100 + over_share * eff_over / 100
    rows = [{"date": t.date.isoformat(), "deal_id": t.deal_id, "client": _client(t.deal),
             "funnel": t.deal.funnel.name if t.deal_id and t.deal.funnel_id else "", "paid": _f(amt),
             "margin_pct": _f(r * 100, 1), "margin": _f(amt * r), "source": _src(t.deal_id, e, econ, items),
             "estimate": bool(e), "pct": _f(k * 100, 3), "earn": _f(amt * r * k)} for t, amt, r, e in raw]
    m_to, m_over = margin * (1 - over_share), margin * over_share
    summary = [{"label": "Оплати за місяць", "value": f"{engine._n(rev)} ₴ · {len(txs)} оплат по {len(deals)} угодах"},
               {"label": "Маржа з цих оплат", "value": f"{engine._n(margin)} ₴"},
               {"label": "План місяця", "value": f"{engine._n(plan)} ₴" if plan else "не встановлено — усе за ставкою до плану"}]
    if plan:
        summary.append({"label": "Частка понад план", "value": f"{engine._p(round(over_share * 100, 1))}% оплат "
                                                             f"({engine._n(max(0.0, rev - plan))} ₴ понад {engine._n(plan)} ₴)"})
    summary.append({"label": "До плану", "value": f"маржа {engine._n(m_to)} ₴ × {engine._p(to_pct)}% = {_n2(m_to * to_pct / 100)} ₴"})
    if over_share > 0:
        summary.append({"label": "Понад план", "value": f"маржа {engine._n(m_over)} ₴ × {engine._p(eff_over)}% = {_n2(m_over * eff_over / 100)} ₴"
                                                       + ("" if gate else f" (стандарт {round(std_score * 100)}% нижче "
                                                                          f"{round(gate_min * 100)}% — понад план за ставкою до плану)")})
    expl = (f"{engine._p(to_pct)}% з маржі оплат, що прийшли цього місяця по угодах людини (воронки: {_funnel_names(funnels)})"
            + (f"; з частини понад план — {engine._p(over_pct)}%" if over_pct != to_pct else "")
            + ". Рахуються гроші з журналу (без переказів), а не сума угоди. Кожна оплата × маржа її угоди × ставка"
            + (f" (разом {engine._p(round(k * 100, 3))}% з маржі з урахуванням плану)." if plan and over_share > 0 else "."))
    notes = []
    if not pol["conv_coef"].get("enabled"):
        notes.append("Коефіцієнт конверсії = 1,0 (вмикається, коли назбирається 2 міс. позначок якості).")
    warnings = [f"{est_n} оплат по угодах без повної собівартості — маржа оцінкою (колонка «Звідки маржа»)"] if est_n else []
    return _out(round(amount), expl, summary,
                [_col("date", "Дата оплати", "date"), _col("deal_id", "Угода", "deal"), _col("client", "Клієнт"),
                 _col("funnel", "Воронка"), _col("paid", "Оплачено", "money"), _col("margin_pct", "Маржа, %", "pct"),
                 _col("margin", "Маржа, ₴", "money"), _col("source", "Звідки маржа"), _col("pct", "Ставка", "pct"),
                 _col("earn", "Заробіток", "money")],
                rows[:MAX_ROWS], warnings=warnings, notes=notes, truncated=len(rows) > MAX_ROWS)


def _d_revenue(comp, user, period, d1, d2, pol):
    """= engine._c_revenue: % з обороту (оплати угод / приходи «Обʼєктів» / закриті акти)."""
    from .models import ObjectAct
    p = comp.params or {}
    pct = float(p.get("pct") or 0)
    basis = p.get("basis", "funnels")
    if basis == "object_acts":
        acts = list(ObjectAct.objects.filter(status="closed", payroll_period=period, manager=user)
                    .select_related("contact").order_by("act_date", "id"))
        base = float(sum((a.amount_total or Decimal("0")) for a in acts))
        comm = float(sum((a.commission_amount or Decimal("0")) for a in acts))
        amt = comm or base * pct / 100
        rows = [{"date": a.act_date.isoformat(), "act": (a.number or f"№{a.id}") + (f" · {a.title}" if a.title else ""),
                 "client": (" ".join(x for x in (a.contact.first_name, a.contact.last_name) if x) if a.contact_id else ""),
                 "base": _f(a.amount_total), "earn": _f(a.commission_amount if comm else float(a.amount_total or 0) * pct / 100)}
                for a in acts]
        expl = (f"{engine._p(pct)}% від усієї суми закритих цього місяця актів обʼєктів: {len(acts)} актів на {engine._n(base)} ₴"
                + (" (комісію взято з актів)" if comm else "") + f" = {_n2(amt)} ₴.")
        return _out(round(amt), expl, columns=[_col("date", "Дата акту", "date"), _col("act", "Акт"), _col("client", "Клієнт"),
                                               _col("base", "Сума акту", "money"), _col("earn", "Заробіток", "money")],
                    rows=rows, warnings=[] if acts else ["Актів, закритих цього місяця, немає"])
    if basis == "objects_income":
        txs = list(engine._income(d1, d2, fin_direction_id=pol["objects_direction_id"], deal__isnull=True).order_by("date", "id"))
        base = float(sum((t.amount_uah or Decimal("0")) for t in txs))
        rows = [{"date": t.date.isoformat(), "who": t.counterparty or "", "comment": (t.comment or "")[:120],
                 "paid": _f(t.amount_uah), "earn": _f(float(t.amount_uah or 0) * pct / 100)} for t in txs]
        return _out(round(base * pct / 100), f"{engine._p(pct)}% з приходів напрямку «Обʼєкти» без угод: {engine._n(base)} ₴ "
                                             f"= {_n2(base * pct / 100)} ₴.",
                    columns=[_col("date", "Дата", "date"), _col("who", "Від кого"), _col("comment", "Коментар"),
                             _col("paid", "Прихід", "money"), _col("earn", "Заробіток", "money")],
                    rows=rows[:MAX_ROWS], truncated=len(rows) > MAX_ROWS)
    flt = {}
    if basis == "own_payments" or p.get("own_only", True):
        flt["deal__owner"] = user
    if basis == "funnels":
        flt["deal__funnel_id__in"] = p.get("funnels") or []
    else:
        flt["deal__isnull"] = False
    txs = list(engine._income(d1, d2, **flt).select_related("deal", "deal__contact", "deal__funnel").order_by("date", "id"))
    base = float(sum((t.amount_uah or Decimal("0")) for t in txs))
    rows = [{"date": t.date.isoformat(), "deal_id": t.deal_id, "client": _client(t.deal),
             "funnel": t.deal.funnel.name if t.deal_id and t.deal.funnel_id else "", "paid": _f(t.amount_uah),
             "earn": _f(float(t.amount_uah or 0) * pct / 100)} for t in txs]
    where = (f"у воронках: {_funnel_names(p.get('funnels') or [])}" if basis == "funnels" else "по угодах")
    whose = "по угодах людини " if "deal__owner" in flt else ""
    return _out(round(base * pct / 100), f"{engine._p(pct)}% з оплат за місяць {whose}{where}: {engine._n(base)} ₴ = {_n2(base * pct / 100)} ₴.",
                columns=[_col("date", "Дата оплати", "date"), _col("deal_id", "Угода", "deal"), _col("client", "Клієнт"),
                         _col("funnel", "Воронка"), _col("paid", "Оплачено", "money"), _col("earn", "Заробіток", "money")],
                rows=rows[:MAX_ROWS], truncated=len(rows) > MAX_ROWS)


# ─────────────────────────── бонус «тест-набір → основне» ───────────────────────────

def _d_event(comp, user, d1, d2, pol):
    """= engine._c_event, але угоди клієнтів — одним запитом (у рушії — запит на кожну угоду)."""
    from apps.crm.models import Deal
    p = comp.params or {}
    tiers = p.get("tiers") or {"fast_days": 30, "min_order": 3000, "fast": 300, "slow": 200, "small": 100}
    test_f = {int(x) for x in pol["funnels"]["test"]}
    main_f = {int(x) for x in pol["funnels"]["main"]}
    fp = {r["deal_id"]: r for r in engine._first_pay()}
    mine = list(Deal.objects.filter(owner=user, funnel_id__in=list(main_f),
                                    id__in=[i for i, r in fp.items() if d1 <= r["first"] <= d2]).select_related("contact"))
    cids = {d.contact_id for d in mine if d.contact_id}
    by_c = {}
    for x in Deal.objects.filter(contact_id__in=cids, funnel_id__in=list(test_f | main_f)).values("id", "contact_id", "funnel_id"):
        by_c.setdefault(x["contact_id"], []).append(x)
    total, rows, no_contact, no_test, had_main = 0, [], [], [], []
    for d in sorted(mine, key=lambda z: (fp[z.id]["first"], z.id)):
        if not d.contact_id:
            no_contact.append(d.id)
            continue
        first_main = fp[d.id]["first"]
        cd = by_c.get(d.contact_id, [])
        tests = [(fp[x["id"]]["first"], x["id"]) for x in cd
                 if x["funnel_id"] in test_f and x["id"] in fp and fp[x["id"]]["first"] <= first_main]
        if not tests:
            no_test.append(d.id)
            continue
        t_first, t_id = min(tests)
        earlier = [x["id"] for x in cd if x["funnel_id"] in main_f and x["id"] != d.id and x["id"] in fp
                   and t_first <= fp[x["id"]]["first"] < first_main]
        if earlier:
            had_main.append(d.id)
            continue
        days = (first_main - t_first).days
        order = float(fp[d.id]["total"] or d.amount or 0)
        if order < tiers["min_order"]:
            b, rule = tiers["small"], f"замовлення менше {engine._n(tiers['min_order'])} ₴"
        elif days <= tiers["fast_days"]:
            b, rule = tiers["fast"], f"{days} дн. — не пізніше {tiers['fast_days']} дн."
        else:
            b, rule = tiers["slow"], f"{days} дн. — пізніше {tiers['fast_days']} дн."
        total += b
        rows.append({"deal_id": d.id, "client": _client(d), "test_deal_id": t_id, "test_paid": t_first.isoformat(),
                     "main_paid": first_main.isoformat(), "days": days, "order": _f(order), "rule": rule, "bonus": _f(b)})
    expl = (f"Бонус за перше основне замовлення клієнта після оплаченого тест-набору: +{engine._n(tiers['fast'])} ₴ — "
            f"не пізніше {tiers['fast_days']} дн., +{engine._n(tiers['slow'])} ₴ — пізніше, +{engine._n(tiers['small'])} ₴ — "
            f"якщо основне менше {engine._n(tiers['min_order'])} ₴. Місяць — місяць першої оплати основного; раз на клієнта; "
            f"отримує відповідальний за основну угоду.")
    notes = [f"Основних замовлень людини з першою оплатою цього місяця: {len(mine)}; бонус дали {len(rows)}."]
    if no_test:
        notes.append(f"Без оплаченого тест-набору перед основним ({len(no_test)}): " + ", ".join(f"#{i}" for i in no_test[:15])
                     + (" …" if len(no_test) > 15 else ""))
    if had_main:
        notes.append(f"У клієнта вже було основне після тест-набору ({len(had_main)}): " + ", ".join(f"#{i}" for i in had_main[:15]))
    if no_contact:
        notes.append(f"Угоди без клієнта ({len(no_contact)}): " + ", ".join(f"#{i}" for i in no_contact[:15]))
    return _out(round(total), expl,
                columns=[_col("deal_id", "Основна угода", "deal"), _col("client", "Клієнт"), _col("test_deal_id", "Тест-набір", "deal"),
                         _col("test_paid", "Оплата тест-набору", "date"), _col("main_paid", "Оплата основного", "date"),
                         _col("days", "Днів", "num"), _col("order", "Сума основного", "money"), _col("rule", "Правило"),
                         _col("bonus", "Бонус", "money")],
                rows=rows, notes=notes)


# ─────────────────────────── відрядно (склад) ───────────────────────────

def _piece_rate_txt(e):
    r = e.rate_applied or Decimal("0")
    op = e.op_type
    if op == "shipment_weight":
        return f"{engine._p(r)} ₴/кг"
    if op == "packing":
        return f"{engine._p(r)} ₴ · місце до {TIER.get(e.pack_tier, e.pack_tier or '?')}"
    if op == "tinting":
        pct = engine._p(round(float(r) * 100, 2))
        return f"{pct}% від {_n2(e.base_value)} ₴" if e.base_value else f"{pct}%"
    if op == "test_set":
        return f"{engine._p(r)} ₴/набір"
    if op == "workday":
        return f"{engine._p(r)} ₴/день"
    if op in ("error", "wrong_material"):
        return "утримання"
    if op.startswith("bonus"):
        return "премія"
    return engine._p(r) if r else ""


def _piece_qty(e):
    r = float(e.rate_applied or 0)
    if e.op_type == "shipment_weight":
        return _f(e.quantity_kg, 3)
    if e.op_type in ("packing", "test_set") and r:
        return round(float(e.amount or 0) / r, 2)
    if e.op_type == "workday":
        return 1
    return None


def _d_piece(comp, comps, user, d1, d2):
    """= engine._c_piece: сума підтверджених записів складу за місяць (кожен — зі ставкою на день дії)."""
    from apps.warehouse import wh_views as whv
    from apps.warehouse.models import WarehouseJob, WarehousePayrollEntry as W
    qs = W.objects.filter(employee=user, work_date__gte=d1, work_date__lte=d2, status="confirmed")
    total = round(float(qs.aggregate(s=Sum("amount"))["s"] or 0))
    entries = list(qs.select_related("deal", "deal__contact", "job", "job__deal", "job__deal__contact").order_by("work_date", "id"))
    labels = dict(whv.PIECE_OPS)
    labels.update({k: v for k, v in W.OP if k not in labels})
    rows, groups = [], {}
    for e in entries:
        deal = e.deal if e.deal_id else (e.job.deal if e.job_id else None)
        rows.append({"date": e.work_date.isoformat(), "op": labels.get(e.op_type, e.op_type),
                     "deal_id": deal.id if deal else None, "client": _client(deal), "kg": _f(e.quantity_kg, 3) if e.quantity_kg else None,
                     "qty": _piece_qty(e), "rate": _piece_rate_txt(e), "amount": _f(e.amount), "note": e.note or ""})
        g = groups.setdefault(e.op_type, {"op": e.op_type, "label": labels.get(e.op_type, e.op_type), "count": 0, "amount": 0.0, "kg": 0.0})
        g["count"] += 1
        g["amount"] += float(e.amount or 0)
        g["kg"] += float(e.quantity_kg or 0)
    order = [op for op, _l in whv.PIECE_OPS]
    glist = sorted(groups.values(), key=lambda g: (order.index(g["op"]) if g["op"] in order else 99, g["op"]))
    for g in glist:
        g["amount"] = _f(g["amount"])
        g["kg"] = _f(g["kg"], 1) if g["kg"] else None
    warnings, links, notes = [], [], []
    shipped = WarehouseJob.objects.filter(assignee=user, status="shipped", shipped_at__date__gte=d1, shipped_at__date__lte=d2)
    n_all = shipped.count()
    zero_qs = shipped.filter(shipped_weight_kg=0)
    n_zero = zero_qs.count()
    if n_zero:
        warnings.append(f"{n_zero} з {n_all} відвантажень місяця пройшли з вагою 0 кг — за них оплата за кг і упаковку "
                        f"не нарахувалась (0 ₴). Вагу вказують у картці товару («Вага нетто, кг»).")
        for j in zero_qs.select_related("deal", "deal__contact").order_by("shipped_at")[:200]:
            links.append({"deal_id": j.deal_id, "label": f"#{j.deal_id} · {_client(j.deal)} · "
                                                          f"{_dm(timezone.localtime(j.shipped_at).date()) if j.shipped_at else ''}"})
    day_n = groups.get("workday", {}).get("count", 0)
    if day_n and any(c.kind in ("fixed_monthly", "base_by_days") for c in comps):
        warnings.append(f"У схемі є ставка на місяць і водночас {day_n} записів «Робочий день» "
                        f"({_n2(groups['workday']['amount'])} ₴) — день може оплачуватись двічі. Перевірте, чи потрібна оплата "
                        f"кнопкою «Завершити день» для цієї людини.")
    other = W.objects.filter(employee=user, work_date__gte=d1, work_date__lte=d2).exclude(status="confirmed").count()
    if other:
        notes.append(f"Не враховано {other} записів, які ще не підтверджені.")
    notes.append("Кожен запис — за ставкою на день дії (ставка записана в самому записі). Змінили ставку — нові відвантаження "
                 "рахуються по-новому, старі записи не переписуються.")
    try:
        notes.append(whv.rates_short())
    except Exception:
        pass
    expl = ("Відрядно — сума всіх підтверджених записів складу за місяць: вага відвантаження, упаковка, тонування, "
            f"тест-набори, робочі дні, премії мінус утримання. Записів: {len(entries)}, відвантажень: {n_all}.")
    return _out(total, expl, columns=[_col("date", "Дата", "date"), _col("op", "За що"), _col("deal_id", "Угода", "deal"),
                                      _col("client", "Клієнт"), _col("kg", "Кг", "num"), _col("qty", "К-сть", "num"),
                                      _col("rate", "Ставка"), _col("amount", "Сума", "money"), _col("note", "Примітка")],
                rows=rows[:MAX_ROWS], groups=glist, warnings=warnings, notes=notes, links=links,
                truncated=len(rows) > MAX_ROWS)


# ─────────────────────────── гарантія / страховий місяць / інше ───────────────────────────

def _d_guarantee(comp, period, d1, d2, pol, subtotal):
    """= гарантія в engine.calc: доплата до гарантії (частка місяця) лише коли умови за місяць підтверджено."""
    p = comp.params or {}
    g_start, g_end = engine.guarantee_window(comp)
    g_amt = float(p.get("amount") or pol["guarantee"]["amount"])
    s, e = max(d1, g_start), min(d2, g_end)
    wd, full = engine.workdays(s, e), (engine.workdays(d1, d2) or 1)
    target = g_amt * wd / full
    topup = max(0.0, target - subtotal)
    ok = bool(((p.get("checks") or {}).get(period) or {}).get("ok"))
    summary = [{"label": "Гарантія на місяць", "value": f"{engine._n(g_amt)} ₴ (діє {g_start:%d.%m.%Y} – {g_end:%d.%m.%Y})"},
               {"label": "Частка місяця під гарантією", "value": f"{wd} з {full} роб. днів → {engine._n(target)} ₴"},
               {"label": "За схемою вийшло (до гарантії)", "value": f"{engine._n(subtotal)} ₴"},
               {"label": "Доплата до гарантії", "value": f"{_n2(topup)} ₴" + ("" if ok else " — лише після підтвердження умов")}]
    expl = (f"Гарантія {engine._n(target)} ₴ за цей місяць мінус нараховане за схемою {engine._n(subtotal)} ₴ = доплата {_n2(topup)} ₴. "
            + ("Умови за місяць підтверджено — доплата нарахована." if ok else "Умови за місяць не підтверджено — доплата 0 ₴."))
    return _out(round(topup) if ok else 0, expl, summary, notes=list(p.get("conditions") or engine.GUARANTEE_CONDITIONS))


def _d_insurance(line, res):
    lg = res.get("legacy") or {}
    amt = line["amount"]
    rows = [{"title": x.get("title") or "", "amount": _f(x.get("amount"))} for x in (lg.get("lines") or [])]
    expl = (f"Перший місяць нової схеми: стара схема «{lg.get('title') or '—'}» дала б {engine._n(lg.get('total'))} ₴, "
            f"нова — {engine._n((lg.get('total') or 0) - amt)} ₴ → доплачуємо різницю {engine._n(amt)} ₴.")
    return _out(amt, expl, columns=[_col("title", "Стара схема: рядок"), _col("amount", "Сума", "money")], rows=rows)


def build(user, period):
    """Розрахунок наживо (engine.calc) + розшифровка кожного рядка. Лише читання."""
    pol = engine.policy()
    d1, d2 = engine.period_bounds(period)
    res = engine.calc(user, period)
    sc = engine.active_scheme(user, d2) if res.get("scheme") else None
    comps = list(sc.components.filter(active=True)) if sc else []
    by_id = {c.id: c for c in comps}
    std_score = 1.0
    for c in comps:
        if c.kind == "standard":
            _l, std_score = engine._c_standard(c, period)
    subtotal = sum(l["amount"] for l in res["lines"] if l.get("kind") not in AFTER_KINDS)
    lines = []
    for i, l in enumerate(res["lines"]):
        comp = by_id.get(l.get("component"))
        k = l.get("kind")
        try:
            if comp is None and k == "insurance":
                d = _d_insurance(l, res)
            elif comp is None:
                d = _out(l["amount"], l.get("detail") or "", notes=["Детально — у відповідному розділі CRM (наприклад, «Біржа задач»)."])
            elif k == "base_by_days":
                d = _d_base(comp, sc, user, d1, d2)
            elif k == "fixed_monthly":
                d = _d_fixed(comp, sc, d1, d2)
            elif k == "standard":
                d = _d_standard(comp, period)
            elif k == "margin_share":
                d = _d_margin(comp, user, period, d1, d2, pol, std_score)
            elif k == "revenue_share":
                d = _d_revenue(comp, user, period, d1, d2, pol)
            elif k == "event_bonus":
                d = _d_event(comp, user, d1, d2, pol)
            elif k == "piece_rate":
                d = _d_piece(comp, comps, user, d1, d2)
            elif k == "guarantee":
                d = _d_guarantee(comp, period, d1, d2, pol, subtotal)
            else:
                d = _out(l["amount"], l.get("detail") or "")
        except Exception as e:  # розшифровка не має ламати відомість — рядок лишається, розшифровки немає
            log.exception("calc-detail user=%s period=%s kind=%s", getattr(user, "id", None), period, k)
            d = _out(None, l.get("detail") or "", warnings=[f"Розшифровку цього рядка не вдалося зібрати ({e.__class__.__name__})"])
        d.update({"index": i, "component": l.get("component"), "kind": k, "title": l.get("title"), "rate": l.get("rate"),
                  "amount": l["amount"], "matches": d["total"] == l["amount"]})
        lines.append(d)
    return {"user_id": user.id, "user_name": res.get("user_name"), "period": period, "scheme": res.get("scheme"),
            "total": res.get("total"), "lines": lines, "warnings": res.get("warnings") or [],
            "all_match": all(x["matches"] for x in lines)}


class CalcDetailView(APIView):
    """GET ?user=<id>&period=YYYY-MM — «Як прорахувалась ЗП» для однієї людини (Фінанси → ЗП/KPI). Лише власник."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _can(request.user, "payroll.rates.view"):
            return Response({"detail": "Розшифровку ЗП бачить лише той, у кого є право на ставки співробітників"}, status=403)
        period = (request.query_params.get("period") or timezone.localdate().strftime("%Y-%m")).strip()[:7]
        if not PERIOD_RE.match(period):
            return Response({"detail": "Місяць у форматі РРРР-ММ"}, status=400)
        uid = str(request.query_params.get("user") or "").strip()
        if not uid.isdigit():
            return Response({"detail": "Не вказано співробітника"}, status=400)
        u = get_user_model().objects.filter(pk=int(uid)).first()
        if not u:
            return Response({"detail": "Співробітника не знайдено"}, status=404)
        data = build(u, period)
        from .runs import active_run
        r = active_run(u, period)
        data["run"] = None
        if r:
            data["run"] = {"id": r.id, "version": r.version, "total": round(float(r.total)),
                           "approved_at": r.approved_at.isoformat() if r.approved_at else None,
                           "lines": [{"component": x.get("component"), "kind": x.get("kind"), "amount": x.get("amount")}
                                     for x in (r.lines or [])]}
            data["frozen_note"] = f"Розшифровка наживо; затверджена сума — {engine._n(r.total)} ₴"
        return Response(data)
