"""Відомість місяця: затвердити / перевідкрити / привʼязати виплати + перевірка «ЗП продажників ≤ 17% маржі» раз на квартал.
Затверджений місяць заморожений: зміна ставок чи фактів лише показує «зараз вийшло б …», нічого не переписує."""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from . import engine
from .models import PayrollPayout, PayrollRun, PayScheme

PAYOUT_CATEGORIES = [15, 19, 23, 24, 27]  # ЗП мастерам, оклади, % з продажів, ФОТ упаковка/тонування, ЗП управління
SALES_DEPT = "Продажі"


def _who(u):
    return (u.get_full_name() or u.username) if u else ""


def active_run(user, period):
    return PayrollRun.objects.filter(user=user, period=period, status="approved").order_by("-version").first()


def run_json(r, live_total=None):
    payouts = [{"id": p.id, "transaction_id": p.transaction_id, "amount": float(p.amount),
                "date": p.transaction.date.isoformat() if p.transaction.date else None,
                "counterparty": p.transaction.counterparty or "", "comment": (p.transaction.comment or "")[:120]}
               for p in PayrollPayout.objects.filter(run__user_id=r.user_id, run__period=r.period).select_related("transaction")]
    paid = round(sum(p["amount"] for p in payouts))
    d = {"id": r.id, "version": r.version, "status": r.status, "status_label": r.get_status_display(),
         "total": round(float(r.total)), "company_cost": round(float(r.company_cost)), "lines": r.lines,
         "approved_by": _who(r.approved_by), "approved_at": r.approved_at.isoformat() if r.approved_at else None,
         "note": r.note, "payouts": payouts, "paid": paid, "remaining": round(float(r.total)) - paid}
    if live_total is not None:
        d["live_total"] = live_total
        d["live_diff"] = live_total - round(float(r.total))
    return d


def approve(user, period, by=None, note=""):
    if active_run(user, period):
        raise ValueError("Місяць для цієї людини вже затверджено — спершу «Перевідкрити»")
    c = engine.calc(user, period)
    if not c.get("scheme"):
        raise ValueError("Немає діючої ставки — Налаштування → Ставки співробітників")
    last = PayrollRun.objects.filter(user=user, period=period).order_by("-version").first()
    return PayrollRun.objects.create(
        period=period, user=user, scheme_id=c["scheme"]["id"], version=(last.version + 1) if last else 1,
        status="approved", lines=c["lines"], total=Decimal(str(c["total"])), company_cost=Decimal(str(c["company_cost"])),
        inputs={"scheme": c["scheme"], "legacy": c.get("legacy"), "warnings": c.get("warnings")},
        note=(note or "")[:255], approved_by=by)


def reopen(run, by=None):
    if run.status == "approved":
        run.status = "reopened"
        run.reopened_by = by
        run.reopened_at = timezone.now()
        run.save(update_fields=["status", "reopened_by", "reopened_at"])
    return run


def payout_candidates(run, pol=None):
    """Виплати ЗП з журналу для привʼязки: категорії ЗП, місяць відомості + 45 днів після. Жодного підбору по імені —
    Олег сам відмічає свої виплати."""
    from apps.finance.models import Transaction
    pol = pol or engine.policy()
    cats = pol.get("payout_categories") or PAYOUT_CATEGORIES
    d1, d2 = engine.period_bounds(run.period)
    used = set(PayrollPayout.objects.values_list("transaction_id", flat=True))
    qs = (Transaction.objects.filter(direction="out", category_id__in=cats, date__gte=d1, date__lte=d2 + timedelta(days=45))
          .exclude(id__in=used).select_related("category").order_by("date", "id"))
    return [{"id": t.id, "date": t.date.isoformat(), "amount": float(t.amount_uah or t.amount or 0), "counterparty": t.counterparty or "",
             "comment": (t.comment or "")[:120], "category": t.category.name if t.category_id else ""} for t in qs[:300]]


def link(run, tx_ids, by=None):
    from apps.finance.models import Transaction
    used = set(PayrollPayout.objects.filter(transaction_id__in=tx_ids).values_list("transaction_id", flat=True))
    n = 0
    for t in Transaction.objects.filter(id__in=tx_ids, direction="out"):
        if t.id in used:
            continue
        PayrollPayout.objects.create(run=run, transaction=t, amount=t.amount_uah or t.amount or 0, linked_by=by)
        n += 1
    return n


def _sales_total(user, period):
    r = active_run(user, period)
    if r:
        return float(r.total)
    d1, d2 = engine.period_bounds(period)
    if engine.active_scheme(user, d2, "official"):
        return float(engine.calc(user, period)["total"])
    if engine.active_scheme(user, d1, "legacy"):
        return float(engine.calc(user, period, purpose="legacy")["total"])
    return 0.0


def quarter_check(period):
    """Лише для останнього місяця кварталу (березень, червень, вересень, грудень): ЗП продажників за квартал ÷ маржа компанії."""
    y, m = int(period[:4]), int(period[5:7])
    if m % 3:
        return None
    pol = engine.policy()
    months = ["%d-%02d" % (y, mm) for mm in (m - 2, m - 1, m)]
    users = {s.user for s in PayScheme.objects.filter(department=SALES_DEPT, user__isnull=False).select_related("user")}
    pay = sum(_sales_total(u, per) for u in users for per in months)
    q1, _ = engine.period_bounds(months[0])
    _, q2 = engine.period_bounds(months[-1])
    margin, cache = 0.0, {}
    for t in engine._income(q1, q2).select_related("deal"):
        amt = float(t.amount_uah or 0)
        if t.deal_id:
            if t.deal_id not in cache:
                cache[t.deal_id] = engine.deal_margin(t.deal, pol)[0]
            margin += amt * cache[t.deal_id]
        else:
            margin += amt * pol["no_deal_margin_pct"] / 100.0
    cap = float(pol["cap"]["pct_of_margin"])
    pct = (pay / margin * 100) if margin else 0.0
    return {"months": months, "sales_pay": round(pay), "margin": round(margin), "pct": round(pct, 1), "cap": cap, "ok": pct <= cap,
            "note": "за решением Олега 14.09 ЗП за месяц не режем — только разбираем причины и правим ставки со следующего квартала"}


def team(period):
    d1, d2 = engine.period_bounds(period)
    users = {s.user for s in engine.staff_on(d2) if s.user_id}
    users |= {r.user for r in PayrollRun.objects.filter(period=period, status="approved").select_related("user")}
    rows = []
    for u in users:
        c = engine.calc(u, period)
        r = active_run(u, period)
        rows.append({**c, "run": run_json(r, live_total=c["total"]) if r else None})
    rows.sort(key=lambda x: -((x["run"] or {}).get("total") or x["total"]))
    total = sum((x["run"]["total"] if x["run"] else x["total"]) for x in rows)
    paid = sum((x["run"]["paid"] if x["run"] else 0) for x in rows)
    return {"period": period, "rows": rows, "total": total,
            "company_cost": sum((x["run"]["company_cost"] if x["run"] else x["company_cost"]) for x in rows),
            "approved": sum(1 for x in rows if x["run"]), "paid": paid, "quarter": quarter_check(period)}
