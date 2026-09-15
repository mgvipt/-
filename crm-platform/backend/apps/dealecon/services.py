# -*- coding: utf-8 -*-
"""Економіка угоди (14.09.2026) — ЄДИНЕ місце формули маржі угоди.

    Маржа = Виручка − Собівартість товару − Доставка НП (лише коли платимо МИ) − Комісія оплати
            − Пакування (робота складу + матеріали) − Роботи майстра (+ транспорт) − Повернення

compute(deal)                → dict, нічого не пише
recompute(deal, save=True)   → dict + рядок DealEconomics (рядок з locked=True НЕ змінюється)
store_np_cost(deal, row)     → додає np_data["np_cost"] ОДНИМ ключем через jsonb `||` (інші ключі не чіпає)
schedule_recompute(deal_id)  → перерахунок після commit (для сигналів), без дублів у межах транзакції

Кожен компонент має джерело: fact (журнал / НП / склад) · estimate (норма, ставка) · mixed · none.
"""
import json
import logging
import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import connection, transaction
from django.utils import timezone

# v2 (14.09, margin-perms): матеріали пакування = % фонду «Упаковка (матеріали)» × виручка товарів (v1: 22 ₴/відправлення).
# models.FORMULA_VERSION лишається 1 — це лише default поля version (без міграції).
FORMULA_VERSION = 2

log = logging.getLogger(__name__)

D0 = Decimal("0")
Q2 = Decimal("0.01")
NUM_FIELDS = ("revenue", "cogs", "delivery", "commission", "packaging", "master_works", "returns", "margin")
COST_KEYS = ("cogs", "delivery", "commission", "packaging", "master_works", "returns")
FEE_TOLERANCE = Decimal("1")          # розбіжність факт/оцінка до 1 ₴ — округлення, не аномалія
NO_ITEMS_MARGIN_PCT = Decimal("35")   # як у картці зараз (get_margin): угода без позицій — оцінка 35% маржі
PAYROLL_OPS = ("packing", "shipment_weight", "tinting")
PAYROLL_BAD_STATUS = ("cancelled", "canceled", "rejected", "void", "deleted")
NP_LIKE = re.compile(r"нова\s*пошт|новапошт|nova\s*poshta|новапей|novapay|\bнп\b", re.I)

DEFAULTS = {
    "pack_material_per_shipment": Decimal("22"),
    "liqpay_rate_pct": Decimal("1.30"),
    "liqpay_rate_old_pct": Decimal("1.50"),
    "liqpay_rate_change_date": date(2026, 7, 14),
    "novapay_rate_pct": Decimal("1.30"),
    "fee_check_min_pct": Decimal("1.10"),
    "fee_check_max_pct": Decimal("3.00"),
    "auto_from": date(2026, 9, 14),
}


# ───────────────────────── дрібні помічники ─────────────────────────
def _d(x):
    try:
        return Decimal(str(x if x not in (None, "") else 0))
    except Exception:
        return D0


def _q(x):
    return _d(x).quantize(Q2, rounding=ROUND_HALF_UP)


def _f(x):
    return float(_q(x))


def _fmt(x):
    s = "%.2f" % float(_q(x))
    s = s.rstrip("0").rstrip(".") if "." in s else s
    return s.replace(".", ",")


def _local_date(dt):
    if not dt:
        return None
    try:
        return timezone.localtime(dt).date() if timezone.is_aware(dt) else dt.date()
    except Exception:
        return None


def _src(kind, uk, ru, **parts):
    out = {"kind": kind, "uk": uk, "ru": ru}
    if parts:
        out["parts"] = {k: (_f(v) if isinstance(v, (Decimal, int, float)) and not isinstance(v, bool) else v)
                        for k, v in parts.items()}
    return out


def _flag(code, uk, ru):
    return {"code": code, "uk": uk, "ru": ru}


def _merge_kinds(kinds):
    ks = set(k for k in kinds if k and k != "none")
    if not ks:
        return "none"
    if ks == {"fact"}:
        return "fact"
    if ks == {"estimate"}:
        return "estimate"
    return "mixed"


def _amt(t):
    return _d(t.amount_uah if (t.amount_uah or 0) else t.amount)


_TABLES = {}


def tables_ready():
    """Чи застосована міграція dealecon (DRY на бойовій базі до деплою — таблиць ще немає)."""
    if "ok" not in _TABLES:
        try:
            names = set(connection.introspection.table_names())
        except Exception:
            names = set()
        _TABLES["ok"] = {"dealecon_dealeconomics", "dealecon_dealeconsettings"} <= names
    return _TABLES["ok"]


def get_settings():
    cfg = dict(DEFAULTS)
    if tables_ready():
        from .models import DealEconSettings
        row = DealEconSettings.objects.filter(pk=1).first()
        if row:
            for k in DEFAULTS:
                cfg[k] = getattr(row, k)
    return cfg


_PACK_FUND_RE = re.compile(r"упаков|пакуван", re.I)
_PACK_MAT_RE = re.compile(r"матеріал|материал", re.I)


def pack_fund():
    """Фонд Олега «Упаковка (матеріали)» — Фінмодель → фонди виручки (на 14.09: #45, 1,92%, напрям «ДЕКОР_Товари»).
    Читається ЖИВИМ при кожному розрахунку: змінили % у Фінмоделі → змінилась економіка угоди.
    Пошук за назвою (упаков… + матеріал…), не за id — працює і в тестовій базі.
    None — такого фонду немає (тоді стара норма ₴ за відправлення)."""
    from apps.finance.models import FinModelArticle
    rows = (FinModelArticle.objects.filter(category="revenue_fund", active=True, value_type="percent")
            .order_by("id").values("id", "name", "value", "fin_direction_id"))
    for r in rows:
        n = r["name"] or ""
        if _PACK_FUND_RE.search(n) and _PACK_MAT_RE.search(n):
            return {"id": r["id"], "name": n, "pct": _d(r["value"]), "direction_id": r["fin_direction_id"]}
    return None


def build_ctx(cfg=None):
    """Норми + категорії журналу (за НАЗВАМИ, не за id — працює і в тестовій базі)."""
    from apps.finance.models import Category
    cats = {"fee": set(), "novapay": set(), "liqpay": set(), "master": set(), "transport": set(), "returns": set()}
    rows = list(Category.objects.values("id", "name", "parent_id"))
    byid = {r["id"]: r for r in rows}
    for r in rows:
        n = (r["name"] or "").strip().lower()
        pn = ((byid.get(r["parent_id"]) or {}).get("name") or "").strip().lower() if r["parent_id"] else ""
        if n.startswith("комиссии банка") or pn.startswith("комиссии банка") or re.search(r"ликпей|liqpay|новапей|novapay|еквайр|эквайр", n):
            cats["fee"].add(r["id"])
        if "новапей" in n or "novapay" in n:
            cats["novapay"].add(r["id"])
        if "ликпей" in n or "liqpay" in n:
            cats["liqpay"].add(r["id"])
        if n.startswith("зп мастерам") or pn.startswith("зп мастерам"):
            cats["master"].add(r["id"])
        if n.startswith("доставка / логистика") or pn.startswith("доставка / логистика"):
            cats["transport"].add(r["id"])
        if n.startswith("возврат товара") or n.startswith("возврат денег"):
            cats["returns"].add(r["id"])
    return {"cfg": cfg or get_settings(), "cats": cats, "pack_fund": pack_fund()}


# ───────────────────────── Нова Пошта ─────────────────────────
def np_cost_from_row(row):
    """Один запис TrackingDocument.getStatusDocuments → {payer, cost, weight, status, src}."""
    if not isinstance(row, dict):
        return None
    payer = str(row.get("PayerType") or "").strip()
    try:
        cost = float(row.get("DocumentCost")) if row.get("DocumentCost") not in (None, "") else None
    except (TypeError, ValueError):
        cost = None
    try:
        weight = float(row.get("DocumentWeight")) if row.get("DocumentWeight") not in (None, "") else None
    except (TypeError, ValueError):
        weight = None
    if not payer and cost is None:
        return None
    return {"payer": payer, "cost": cost, "weight": weight,
            "status": str(row.get("StatusCode") or ""), "src": "np_api"}


def store_np_cost(deal, row, schedule=True):
    """Зберегти платника/вартість НП у np_data["np_cost"] — ЛИШЕ новий ключ.
    Запис у базу — jsonb `||` (інші ключі np_data не перезаписуються навіть при паралельній зміні),
    плюс той самий ключ у памʼяті обʼєкта (щоб наступний deal.save(np_data) поллера його не загубив)."""
    val = np_cost_from_row(row)
    if not val or not getattr(deal, "pk", None):
        return False
    nd = deal.np_data if isinstance(deal.np_data, dict) else None
    old = nd.get("np_cost") if nd else None
    if isinstance(old, dict) and all(old.get(k) == val.get(k) for k in ("payer", "cost", "weight", "status")):
        return False
    val["at"] = timezone.now().isoformat(timespec="seconds")
    table = deal._meta.db_table
    with connection.cursor() as c:
        c.execute(
            "UPDATE " + table + " SET np_data = (CASE WHEN np_data IS NULL OR jsonb_typeof(np_data) = 'null' "
            "THEN '{}'::jsonb ELSE np_data END) || jsonb_build_object('np_cost', %s::jsonb) "
            "WHERE id = %s AND (np_data IS NULL OR jsonb_typeof(np_data) IN ('object', 'null'))",
            [json.dumps(val, ensure_ascii=False), deal.pk])
        done = c.rowcount
    if not done:
        return False
    new = dict(nd) if nd else {}
    new["np_cost"] = val
    deal.np_data = new
    if schedule:
        schedule_recompute(deal.pk)
    return True


def fetch_np_rows(ttns):
    """Лише ЧИТАННЯ НП: getStatusDocuments пачками по 100. → {ttn: raw_row}."""
    from apps.integrations import adapters as ad
    out = {}
    uniq = sorted({(t or "").strip() for t in ttns if (t or "").strip()})
    for i in range(0, len(uniq), 100):
        chunk = uniq[i:i + 100]
        try:
            r = ad._np_call("TrackingDocument", "getStatusDocuments",
                            {"Documents": [{"DocumentNumber": t} for t in chunk]})
        except Exception as e:  # мережа / ключ — просто без НП-факту
            log.warning("dealecon: NP fetch failed: %s", e)
            continue
        for row in (r or {}).get("data") or []:
            num = str(row.get("Number") or "").strip()
            if num:
                out[num] = row
    return out


def _np_cost_of(d, np_hint):
    ttn = (d.ttn or "").strip()
    if np_hint and ttn and ttn in np_hint:
        return np_hint[ttn]
    nd = d.np_data if isinstance(d.np_data, dict) else {}
    c = nd.get("np_cost")
    return c if isinstance(c, dict) else None


def _siblings(deal):
    """Угоди з тією самою ТТН (основна + дозамовлення — одна посилка)."""
    ttn = (deal.ttn or "").strip()
    if not ttn:
        return []
    from apps.crm.models import Deal
    sibs = list(Deal.objects.filter(ttn=ttn).only("id", "amount", "np_data", "parent_deal_id", "ttn"))
    if not any(s.pk == deal.pk for s in sibs):
        sibs.append(deal)
    return sibs


def _is_primary_shipment(deal, sibs):
    if not sibs:
        return False
    ids = {s.pk for s in sibs}
    prim = [s.pk for s in sibs if not s.parent_deal_id or s.parent_deal_id not in ids]
    return deal.pk == min(prim or ids)


# ───────────────────────── компоненти ─────────────────────────
def _delivery(deal, sibs, np_hint):
    if not sibs:
        return D0, _src("none", "немає ТТН", "нет ТТН"), []
    flags = []
    me_first = sorted(sibs, key=lambda s: s.pk != deal.pk)
    npc = None
    crm_payer = ""
    act = D0
    for s in me_first:
        c = _np_cost_of(s, np_hint)
        if npc is None and c:
            npc = c
        nd = s.np_data if isinstance(s.np_data, dict) else {}
        if not crm_payer:
            crm_payer = str(((nd.get("parcel") or {}) if isinstance(nd.get("parcel"), dict) else {}).get("payer") or "").strip()
        a = _d(nd.get("delivery_cost_total"))
        if a > act:
            act = a
    np_payer = str((npc or {}).get("payer") or "").strip()
    np_cost = _d((npc or {}).get("cost")) if npc and npc.get("cost") is not None else None
    payer = np_payer or crm_payer
    payer_src = "np_api" if np_payer else ("crm" if crm_payer else "none")

    total_amt = sum((_d(s.amount) for s in sibs), D0)
    share = (_d(deal.amount) / total_amt) if total_amt > 0 else (Decimal(1) / Decimal(len(sibs)))
    shared = len(sibs) > 1

    we_pay = payer == "Sender" or (payer_src == "none" and act > 0)
    if payer == "Recipient" and act > 0:
        # НП каже «платить клієнт», але є акт НП на нас — рахуємо гроші з акту і просимо перевірити
        we_pay = True
        flags.append(_flag("np_payer_act", "НП: платник «клієнт», але в акті НП %s ₴ на нас — перевірити" % _fmt(act),
                           "НП: плательщик «клиент», но в акте НП %s ₴ на нас — проверить" % _fmt(act)))
    if not we_pay:
        if payer == "Recipient":
            src = "НП" if payer_src == "np_api" else "ТТН у CRM"
            return D0, _src("fact" if payer_src == "np_api" else "estimate",
                            "доставку платить клієнт (%s)" % src, "доставку платит клиент (%s)" % src,
                            payer=payer, payer_src=payer_src), flags
        return D0, _src("none", "платник доставки невідомий", "плательщик доставки неизвестен",
                        payer_src=payer_src), flags

    if np_cost is not None and np_cost > 0:
        ttn_cost, how_uk, how_ru, cost_src = np_cost, "вартість з НП", "стоимость из НП", "np_api"
    elif act > 0:
        ttn_cost, how_uk, how_ru, cost_src = act, "акт НП", "акт НП", "np_act"
    else:
        flags.append(_flag("np_no_cost", "Доставку платимо ми, але вартості від НП ще немає",
                           "Доставку платим мы, но стоимости от НП ещё нет"))
        return D0, _src("none", "платимо ми, вартості ще немає", "платим мы, стоимости ещё нет",
                        payer=payer, payer_src=payer_src), flags
    amount = ttn_cost * share
    tail_uk = " · частка %s%% спільної ТТН" % _fmt(share * 100) if shared else ""
    tail_ru = " · доля %s%% общей ТТН" % _fmt(share * 100) if shared else ""
    return amount, _src("fact", "платимо ми · %s %s ₴%s" % (how_uk, _fmt(ttn_cost), tail_uk),
                        "платим мы · %s %s ₴%s" % (how_ru, _fmt(ttn_cost), tail_ru),
                        payer=payer, payer_src=payer_src, cost_src=cost_src, ttn_cost=ttn_cost,
                        share=_q(share * 100), act=act, ttn=(deal.ttn or "").strip()), flags


def _fee_kind(t, cats):
    cm = t.comment or ""
    cp = (t.counterparty or "").lower()
    if cm.startswith("PBFEE#"):
        return "liqpay"
    if t.category_id not in cats["fee"]:
        return None
    if t.category_id in cats["novapay"] or "новапей" in cp or "novapay" in cp or "нова пошта" in cp:
        return "novapay"
    if t.category_id in cats["liqpay"] or "liqpay" in cp:
        return "liqpay"
    return "other"


def _liq_rate(p, cfg):
    dt = _local_date(p.created_at) or timezone.localdate()
    return _d(cfg["liqpay_rate_old_pct"]) if dt < cfg["liqpay_rate_change_date"] else _d(cfg["liqpay_rate_pct"])


def _commission(deal, pays, txs, ctx):
    cfg, cats = ctx["cfg"], ctx["cats"]
    fact = {"liqpay": D0, "novapay": D0, "other": D0}
    for t in txs:
        k = _fee_kind(t, cats)
        if k:
            fact[k] += _amt(t)
    lo, hi = _d(cfg["fee_check_min_pct"]), _d(cfg["fee_check_max_pct"])
    liq = [p for p in pays if p.provider == "liqpay" and p.is_paid and _d(p.amount) > 0]
    cod = [p for p in pays if p.provider == "np_cod" and _d(p.amount) > 0]
    total, kinds, flags, uk, ru, parts = D0, [], [], [], [], {}

    liq_gross = sum((_d(p.amount) for p in liq), D0)
    if liq_gross > 0 or fact["liqpay"] > 0:
        est = sum((_d(p.amount) * _liq_rate(p, cfg) / 100 for p in liq), D0)
        f = fact["liqpay"]
        if f > 0 and liq_gross > 0:
            pct = f / liq_gross * 100
            if lo <= pct <= hi or abs(f - est) <= FEE_TOLERANCE:
                use, kind = f, "fact"
                uk.append("LiqPay %s ₴ факт банку (%s%%)" % (_fmt(f), _fmt(pct)))
                ru.append("LiqPay %s ₴ факт банка (%s%%)" % (_fmt(f), _fmt(pct)))
            else:
                use, kind = est, "estimate"
                flags.append(_flag(
                    "fee_liqpay_range",
                    "LiqPay: у журналі комісія %s ₴ = %s%% від %s ₴ (норма %s–%s%%) — взято оцінку, перевірити"
                    % (_fmt(f), _fmt(pct), _fmt(liq_gross), _fmt(lo), _fmt(hi)),
                    "LiqPay: в журнале комиссия %s ₴ = %s%% от %s ₴ (норма %s–%s%%) — взята оценка, проверить"
                    % (_fmt(f), _fmt(pct), _fmt(liq_gross), _fmt(lo), _fmt(hi))))
                uk.append("LiqPay %s ₴ оцінка (факт %s ₴ під сумнівом)" % (_fmt(est), _fmt(f)))
                ru.append("LiqPay %s ₴ оценка (факт %s ₴ под сомнением)" % (_fmt(est), _fmt(f)))
        elif f > 0:
            use, kind = f, "fact"
            flags.append(_flag("fee_liqpay_no_payment", "LiqPay: є комісія %s ₴, але оплати LiqPay немає (повернення?)" % _fmt(f),
                               "LiqPay: есть комиссия %s ₴, но оплаты LiqPay нет (возврат?)" % _fmt(f)))
            uk.append("LiqPay %s ₴ факт" % _fmt(f))
            ru.append("LiqPay %s ₴ факт" % _fmt(f))
        else:
            use, kind = est, "estimate"
            uk.append("LiqPay %s ₴ оцінка за ставкою" % _fmt(est))
            ru.append("LiqPay %s ₴ оценка по ставке" % _fmt(est))
        total += use
        kinds.append(kind)
        parts["liqpay"] = {"gross": _f(liq_gross), "fact": _f(f), "estimate": _f(est), "used": _f(use), "kind": kind}

    cod_gross = sum((_d(p.amount) for p in cod), D0)
    if cod_gross > 0 or fact["novapay"] > 0:
        f = fact["novapay"]
        est = cod_gross * _d(cfg["novapay_rate_pct"]) / 100
        if f > 0:
            use, kind = f, "fact"
            if cod_gross > 0 and f / cod_gross * 100 > hi and (f - est) > FEE_TOLERANCE:
                flags.append(_flag("fee_novapay_range", "НоваПей: комісія %s ₴ = %s%% від наложки %s ₴ — перевірити"
                                   % (_fmt(f), _fmt(f / cod_gross * 100), _fmt(cod_gross)),
                                   "НоваПей: комиссия %s ₴ = %s%% от наложки %s ₴ — проверить"
                                   % (_fmt(f), _fmt(f / cod_gross * 100), _fmt(cod_gross))))
            uk.append("НоваПей %s ₴ факт" % _fmt(f))
            ru.append("НоваПей %s ₴ факт" % _fmt(f))
        else:
            use, kind = est, "estimate"
            uk.append("НоваПей %s ₴ оцінка %s%%" % (_fmt(est), _fmt(cfg["novapay_rate_pct"])))
            ru.append("НоваПей %s ₴ оценка %s%%" % (_fmt(est), _fmt(cfg["novapay_rate_pct"])))
        total += use
        kinds.append(kind)
        parts["novapay"] = {"gross": _f(cod_gross), "fact": _f(f), "estimate": _f(est), "used": _f(use), "kind": kind}

    if fact["other"] > 0:
        total += fact["other"]
        kinds.append("fact")
        uk.append("інша банківська комісія %s ₴" % _fmt(fact["other"]))
        ru.append("другая банковская комиссия %s ₴" % _fmt(fact["other"]))
        parts["other"] = _f(fact["other"])

    kind = _merge_kinds(kinds)
    if kind == "none":
        if any(p.is_paid for p in pays):
            return D0, _src("fact", "без комісії (каса / реквізити)", "без комиссии (касса / реквизиты)"), flags
        return D0, _src("none", "оплат ще немає", "оплат ещё нет"), flags
    src = _src(kind, " · ".join(uk), " · ".join(ru))
    src["parts"] = parts
    return total, src, flags


def _packaging(deal, sibs, ctx, base=None):
    """Пакування = робота складу (ФАКТ: відрядні записи ЦІЄЇ угоди — упаковка, вага, тонування; ставки складу)
    + пакувальні матеріали (ОЦІНКА, 14.09: % фонду Олега «Упаковка (матеріали)» × виручка товарів угоди;
    послуги/роботи без товару матеріалів не мають). Фонду у Фінмоделі немає — стара норма ₴ за відправлення."""
    from apps.warehouse.models import WarehousePayrollEntry
    labor = {k: D0 for k in PAYROLL_OPS}
    for op, amt in (WarehousePayrollEntry.objects.filter(deal_id=deal.pk, op_type__in=PAYROLL_OPS)
                    .exclude(status__in=PAYROLL_BAD_STATUS).values_list("op_type", "amount")):
        labor[op] += _d(amt)
    lab = sum(labor.values(), D0)
    # 15.09.2026: збірка тест-набору (50 ₴) — довідково; вона вже в собівартості набору, окремо не віднімаємо
    ts = sum((_d(a) for a in WarehousePayrollEntry.objects.filter(deal_id=deal.pk, op_type="test_set")
              .exclude(status__in=PAYROLL_BAD_STATUS).values_list("amount", flat=True)), D0)
    fund = ctx["pack_fund"] if "pack_fund" in ctx else pack_fund()
    if fund is not None:
        base = max(_d(base), D0)
        pct = _d(fund["pct"])
        mat = base * pct / 100
        mat_uk = "матеріали %s ₴ = %s%% фонду «%s» × %s ₴ виручки товарів" % (_fmt(mat), _fmt(pct), fund["name"], _fmt(base))
        mat_ru = "материалы %s ₴ = %s%% фонда «%s» × %s ₴ выручки товаров" % (_fmt(mat), _fmt(pct), fund["name"], _fmt(base))
        empty = ("не пакували / товарів немає", "не упаковывали / товаров нет")
        extra = {"material_src": "fund", "fund": fund["name"], "fund_id": str(fund["id"]), "fund_pct": pct, "base": base}
    else:
        mat = _d(ctx["cfg"]["pack_material_per_shipment"]) if _is_primary_shipment(deal, sibs) else D0
        mat_uk = "матеріали %s ₴ (норма за відправлення: фонду «Упаковка (матеріали)» у Фінмоделі немає)" % _fmt(mat)
        mat_ru = "материалы %s ₴ (норма за отправку: фонда «Упаковка (материалы)» в Финмодели нет)" % _fmt(mat)
        empty = ("не пакували / посилка оплачена в основній угоді", "не упаковывали / посылка в основной сделке")
        extra = {"material_src": "norm"}
    # 15.09.2026 (Олег): видача в салоні без ТТН — коробки/скотч не витрачались; в економіці лише фактичні витрати
    from apps.warehouse.weight_rules import is_salon
    salon = is_salon(deal)
    if salon:
        mat = D0
        extra["salon"] = True
    kinds = (["fact"] if lab > 0 else []) + (["estimate"] if mat > 0 else [])
    kind = _merge_kinds(kinds)
    uk, ru = [], []
    if lab > 0:
        uk.append("робота складу %s ₴" % _fmt(lab))
        ru.append("работа склада %s ₴" % _fmt(lab))
    if mat > 0:
        uk.append(mat_uk)
        ru.append(mat_ru)
    if salon:
        uk.append("видача в салоні без ТТН — матеріали упаковки 0")
        ru.append("выдача в салоне без ТТН — материалы упаковки 0")
    if not uk:
        uk, ru = [empty[0]], [empty[1]]
    return lab + mat, _src(kind, " · ".join(uk), " · ".join(ru), packing=labor["packing"],
                           shipment_weight=labor["shipment_weight"], tinting=labor["tinting"], material=mat,
                           test_set=ts, **extra)


def _master(txs, svc_plan, ctx):
    cats = ctx["cats"]
    fact = D0
    transport = D0
    for t in txs:
        if t.category_id in cats["master"]:
            fact += _amt(t)
        elif t.category_id in cats["transport"] and not NP_LIKE.search("%s %s" % (t.counterparty or "", t.comment or "")):
            transport += _amt(t)
    tot = fact + transport
    if tot > 0:
        uk = "факт виплат %s ₴" % _fmt(fact) + (" + транспорт %s ₴" % _fmt(transport) if transport > 0 else "")
        ru = "факт выплат %s ₴" % _fmt(fact) + (" + транспорт %s ₴" % _fmt(transport) if transport > 0 else "")
        if svc_plan > 0:
            uk += " (замість плану %s ₴)" % _fmt(svc_plan)
            ru += " (вместо плана %s ₴)" % _fmt(svc_plan)
        return tot, _src("fact", uk, ru, fact=fact, transport=transport, plan=svc_plan)
    if svc_plan > 0:
        return svc_plan, _src("estimate", "план: частка майстра з позицій-послуг", "план: доля мастера из позиций-услуг",
                              plan=svc_plan)
    return D0, _src("none", "робіт немає", "работ нет")


def _returns(txs, pays, ctx, deal=None):
    # 16.09 (returns): повернення товару через CRM (apps.returns) уже зменшило позиції й суму угоди, тому гроші,
    #   повернені за НЬОГО, вдруге не віднімаємо; натомість — собівартість браку / списаного (товар не повернувся на полицю).
    extra = {"tx_ids": set(), "loss": D0}
    if deal is not None:
        try:
            from apps.returns.services import econ_extra
            extra = econ_extra(deal.pk)
        except Exception:
            log.exception("dealecon: returns extra failed for deal %s", getattr(deal, "pk", None))
    r = sum((_amt(t) for t in txs if t.category_id in ctx["cats"]["returns"] and t.id not in extra["tx_ids"]), D0)
    neg = sum((-_d(p.amount) for p in pays if _d(p.amount) < 0), D0)
    loss = _d(extra["loss"])
    tot = r + neg + loss
    if tot > 0:
        uk, ru = [], []
        if r + neg > 0:
            uk.append("повернуто клієнту %s ₴" % _fmt(r + neg))
            ru.append("возвращено клиенту %s ₴" % _fmt(r + neg))
        if loss > 0:
            uk.append("брак / списано після повернення %s ₴ (собівартість)" % _fmt(loss))
            ru.append("брак / списано после возврата %s ₴ (себестоимость)" % _fmt(loss))
        return tot, _src("fact", " · ".join(uk), " · ".join(ru), journal=r, negative_payments=neg, return_loss=loss)
    return D0, _src("none", "повернень немає", "возвратов нет")


def card_margin(deal):
    """Маржа «як зараз у картці» (дзеркало get_margin) — для порівняння «було → стало»."""
    items = list(deal.items.all())
    if not items:
        return _q(_d(deal.amount) * NO_ITEMS_MARGIN_PCT / 100)
    rev = sum((_d(i.total) for i in items), D0)
    cogs = sum((_d(i.quantity) * (_d(i.cost) if _d(i.cost) > 0 else _d(getattr(i.product, "cost", 0))) for i in items), D0)
    return _q(rev - cogs)


# ───────────────────────── головна функція ─────────────────────────
def compute(deal, ctx=None, np_hint=None):
    """Порахувати економіку угоди. Нічого не пише. np_hint={ttn: np_cost} — свіжі дані НП (команда DRY)."""
    ctx = ctx or build_ctx()
    from apps.finance.models import Transaction
    flags = []
    sources = {}

    # 1. Виручка і собівартість (як у картці: знімок собівартості, fallback — поточна собівартість товару)
    items = list(deal.items.select_related("product").all())
    revenue = goods = svc_plan = svc_rev = D0
    fb_n, fb_sum, zero_n, zero_rev = 0, D0, 0, D0
    for it in items:
        p = it.product
        qty = _d(it.quantity)
        total = _d(it.total)
        revenue += total
        unit = _d(it.cost)
        fallback = False
        if unit > 0:
            line = qty * unit
        elif p is not None and _d(getattr(p, "cost_pct", 0)) > 0:
            base = qty * _d(it.price)
            mp = _d(getattr(p, "min_price", 0))
            if mp > 0 and base < mp:
                base = mp
            line = base * _d(p.cost_pct) / 100
            fallback = line > 0
        elif p is not None:
            line = qty * _d(p.cost)
            fallback = line > 0
        else:
            line = D0
        if fallback:
            fb_n += 1
            fb_sum += line
        if line <= 0 and total > 0:
            zero_n += 1
            zero_rev += total
        if p is not None and not p.track_stock:
            svc_plan += line          # послуга/робота — частка майстра (план), йде в «Роботи майстра»
            svc_rev += total          # виручка послуг — без пакувальних матеріалів (фонд #45 — напрям «ДЕКОР_Товари»)
        else:
            goods += line
    if not items:
        revenue = _d(deal.amount)
        goods = revenue * (100 - NO_ITEMS_MARGIN_PCT) / 100
        sources["cogs"] = _src("estimate", "угода без позицій — оцінка (маржа 35%, як у картці)",
                               "сделка без позиций — оценка (маржа 35%, как в карточке)")
    else:
        uk = "знімок собівартості позицій"
        ru = "снимок себестоимости позиций"
        if fb_n:
            uk += " · %d поз. за поточною собівартістю товару (%s ₴)" % (fb_n, _fmt(fb_sum))
            ru += " · %d поз. по текущей себестоимости товара (%s ₴)" % (fb_n, _fmt(fb_sum))
        if zero_n:
            uk += " · %d поз. без собівартості на %s ₴ виручки" % (zero_n, _fmt(zero_rev))
            ru += " · %d поз. без себестоимости на %s ₴ выручки" % (zero_n, _fmt(zero_rev))
        sources["cogs"] = _src("estimate" if fb_n else "fact", uk, ru, goods=goods, services_plan=svc_plan,
                               fallback_lines=fb_n, zero_cost_lines=zero_n, zero_cost_revenue=zero_rev)
    sources["revenue"] = _src("fact" if items else "estimate",
                              "сума позицій угоди" if items else "сума угоди (позицій немає)",
                              "сумма позиций сделки" if items else "сумма сделки (позиций нет)")

    pays = list(deal.payments.all())
    txs = list(Transaction.objects.filter(deal_id=deal.pk, direction="out")
               .only("id", "amount", "amount_uah", "category_id", "comment", "counterparty"))
    sibs = _siblings(deal)

    delivery, sources["delivery"], fl = _delivery(deal, sibs, np_hint)
    flags += fl
    commission, sources["commission"], fl = _commission(deal, pays, txs, ctx)
    flags += fl
    packaging, sources["packaging"] = _packaging(deal, sibs, ctx, revenue - svc_rev)
    master, sources["master_works"] = _master(txs, svc_plan, ctx)
    returns, sources["returns"] = _returns(txs, pays, ctx, deal)

    vals = {"revenue": revenue, "cogs": goods, "delivery": delivery, "commission": commission,
            "packaging": packaging, "master_works": master, "returns": returns}
    vals = {k: _q(v) for k, v in vals.items()}
    margin = vals["revenue"] - sum((vals[k] for k in COST_KEYS), D0)
    pct = _q(margin / vals["revenue"] * 100) if vals["revenue"] > 0 else D0
    is_est = any(sources[k]["kind"] in ("estimate", "mixed") and vals[k] != 0 for k in COST_KEYS) or \
        (sources["revenue"]["kind"] == "estimate" and vals["revenue"] != 0)
    res = dict(vals)
    res.update({"deal_id": deal.pk, "margin": _q(margin), "margin_pct": pct, "is_estimate": bool(is_est),
                "sources": sources, "flags": flags, "version": FORMULA_VERSION})
    return res


def row_to_dict(row):
    res = {k: _q(getattr(row, k)) for k in NUM_FIELDS}
    res.update({"deal_id": row.deal_id, "margin_pct": _q(row.margin_pct), "is_estimate": row.is_estimate,
                "sources": row.sources or {}, "flags": row.flags or [], "version": row.version,
                "computed_at": row.computed_at, "locked": row.locked, "saved": True})
    return res


def recompute(deal, save=True, ctx=None, np_hint=None):
    """Перерахувати і (save=True) зберегти рядок. Рядок locked=True (закритий місяць) НЕ змінюється —
    повертаємо збережене. Без міграції (таблиці немає) — просто compute()."""
    from .models import DealEconomics
    ready = tables_ready()
    row = DealEconomics.objects.filter(deal_id=deal.pk).first() if ready else None
    if row is not None and row.locked:
        return row_to_dict(row)
    res = compute(deal, ctx=ctx, np_hint=np_hint)
    res["locked"] = False
    res["saved"] = row is not None
    res["computed_at"] = row.computed_at if row is not None else None
    if save and ready:
        defaults = {k: res[k] for k in NUM_FIELDS}
        defaults.update({"margin_pct": res["margin_pct"], "sources": res["sources"], "flags": res["flags"],
                         "is_estimate": res["is_estimate"], "version": res["version"], "computed_at": timezone.now()})
        row, _ = DealEconomics.objects.update_or_create(deal_id=deal.pk, defaults=defaults)
        res["saved"] = True
        res["computed_at"] = row.computed_at
    return res


# ───────────────────────── перерахунок із сигналів ─────────────────────────
def _run(deal_id):
    try:
        if not tables_ready():
            return
        from apps.crm.models import Deal
        from .models import DealEconomics
        row = DealEconomics.objects.filter(deal_id=deal_id).only("deal_id", "locked").first()
        if row is not None and row.locked:
            return
        deal = Deal.objects.filter(pk=deal_id).first()
        if deal is None:
            return
        if row is None:
            # старі продажі не чіпаємо: рядок для угод до дати запуску — лише командою (DRY → 2 → всі)
            created = _local_date(deal.created_at)
            if not created or created < get_settings()["auto_from"]:
                return
        recompute(deal, save=True)
    except Exception:
        log.exception("dealecon: recompute failed for deal %s", deal_id)


class _Job:
    """Відкладений перерахунок однієї угоди (після commit). done=True — вже виконано."""
    __slots__ = ("deal_id", "done")

    def __init__(self, deal_id):
        self.deal_id = deal_id
        self.done = False

    def __call__(self):
        self.done = True
        _run(self.deal_id)


def schedule_recompute(deal_id):
    """Після commit; одна угода — один перерахунок на транзакцію (без 300 перерахунків на імпорт банку)."""
    if not deal_id:
        return
    try:
        conn = transaction.get_connection()
        for entry in getattr(conn, "run_on_commit", []) or []:
            fn = entry[1] if len(entry) > 1 else None
            if isinstance(fn, _Job) and fn.deal_id == deal_id and not fn.done:
                return
        transaction.on_commit(_Job(deal_id))
    except Exception:
        log.exception("dealecon: schedule failed for deal %s", deal_id)
