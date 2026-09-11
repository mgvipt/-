"""«Закрити день»: знімок усіх операцій журналу за день — замість скріна в Telegram о 18:00.

Знімок заморожує значення (суми, рахунки, назви), а diff() показує, що змінилось після нього:
змінено гроші, видалено, перенесено дату, додано після знімка. Блокування правок закритих днів —
окремий крок (P2, права finance.day.close / finance.day.edit_closed вже заведені).
"""
from django.db import transaction as dbtx
from django.db.models import Q

from .models import DaySnapshot, Transaction

MONEY = ("amount", "currency", "rate", "direction", "account_id", "transfer_account_id", "transfer_amount")
SOFT = ("category_id", "counterparty", "comment", "deal_id", "contact_id")


def _src(t):
    b = t.import_batch or ""
    if t.payment_id:
        return "оплата угоди"
    if b.startswith("PB-") or b.lower().startswith("mono"):
        return "банк"
    if b.startswith("ST-"):
        return "виписка"
    if b.startswith("QUICK-"):
        return "швидкий"
    if b.startswith(("FIX", "SPLIT", "FM-")):
        return "службова"
    return "вручну"


def _num(v):
    return float(v) if v is not None else None


def row_of(t):
    """Рядок знімка з замороженими значеннями й назвами (щоб знімок не «поплив» після перейменувань)."""
    return {
        "id": t.id, "date": t.date.isoformat(), "op_time": t.op_time.strftime("%H:%M") if t.op_time else "",
        "direction": t.direction, "amount": _num(t.amount), "currency": t.currency, "rate": _num(t.rate),
        "amount_uah": _num(t.amount_uah),
        "account_id": t.account_id, "account": t.account.name if t.account_id else "",
        "transfer_account_id": t.transfer_account_id,
        "transfer_account": t.transfer_account.name if t.transfer_account_id else "",
        "transfer_amount": _num(t.transfer_amount), "counterparty": t.counterparty or "",
        "category_id": t.category_id, "category": t.category.name if t.category_id else "",
        "deal_id": t.deal_id, "contact_id": t.contact_id, "payment_id": t.payment_id,
        "comment": (t.comment or "")[:140], "created_at": t.created_at.isoformat() if t.created_at else None,
        "src": _src(t),
    }


def _day_qs(d):
    return (Transaction.objects.filter(date=d).select_related("account", "transfer_account", "category")
            .order_by("op_time", "id"))


def totals_of(rows):
    """Підсумки по рахунках (у валюті рахунку) і загалом у гривні."""
    tot = {}

    def acc(aid, name):
        return tot.setdefault(str(aid), {"name": name, "in": 0.0, "out": 0.0, "tr_in": 0.0, "tr_out": 0.0, "n": 0})

    for r in rows:
        a = acc(r["account_id"], r["account"])
        a["n"] += 1
        amt = r["amount"] or 0
        if r["direction"] == "in":
            a["in"] += amt
        elif r["direction"] == "out":
            a["out"] += amt
        elif r["direction"] == "transfer":
            a["tr_out"] += amt
            if r["transfer_account_id"]:
                acc(r["transfer_account_id"], r["transfer_account"])["tr_in"] += (
                    r["transfer_amount"] if r["transfer_amount"] is not None else amt)
    for a in tot.values():
        for k in ("in", "out", "tr_in", "tr_out"):
            a[k] = round(a[k], 2)
        a["net"] = round(a["in"] - a["out"] + a["tr_in"] - a["tr_out"], 2)
    return {"accounts": tot, "all": {
        "in": round(sum(r["amount_uah"] or 0 for r in rows if r["direction"] == "in"), 2),
        "out": round(sum(r["amount_uah"] or 0 for r in rows if r["direction"] == "out"), 2),
        "n": len(rows)}}


def active_snapshot(d):
    return DaySnapshot.objects.filter(date=d, reopened_at__isnull=True).order_by("-version").first()


def day_closed_until():
    """Остання дата, закрита активним знімком (для блокування в P2)."""
    s = DaySnapshot.objects.filter(reopened_at__isnull=True).order_by("-date").first()
    return s.date if s else None


def close_day(d, user=None, kind="manual", note=""):
    """Зробити знімок дня. Ідемпотентно: активний знімок уже є і це не перезнімок → повертає його."""
    real_user = user if (user is not None and getattr(user, "is_authenticated", False)) else None
    with dbtx.atomic():
        last = DaySnapshot.objects.select_for_update().filter(date=d).order_by("-version").first()
        if last and last.reopened_at is None and kind != "reclose":
            return last, False
        rows = [row_of(t) for t in _day_qs(d)]
        s = DaySnapshot.objects.create(date=d, version=(last.version + 1) if last else 1, kind=kind,
                                       closed_by=real_user, rows=rows, totals=totals_of(rows), note=(note or "")[:255])
        return s, True


def diff(s):
    """Що змінилось після знімка."""
    snap = {r["id"]: r for r in (s.rows or [])}
    cur = {t.id: t for t in Transaction.objects.filter(Q(date=s.date) | Q(id__in=list(snap)))
           .select_related("account", "transfer_account", "category")}
    out = {"changed": [], "deleted": [], "moved": [], "added_after": [], "appeared": [], "other": []}
    for tid, was in snap.items():
        t = cur.get(tid)
        if t is None:
            out["deleted"].append(was)
            continue
        now = row_of(t)
        if now["date"] != was["date"]:
            out["moved"].append({"id": tid, "was": was, "now": now})
            continue
        money = [k for k in MONEY if now.get(k) != was.get(k)]
        soft = [k for k in SOFT if now.get(k) != was.get(k)]
        if money:
            out["changed"].append({"id": tid, "fields": money, "was": was, "now": now})
        elif soft:
            out["other"].append({"id": tid, "fields": soft, "was": was, "now": now})
    for tid, t in cur.items():
        if tid in snap or t.date != s.date:
            continue
        now = row_of(t)
        (out["added_after"] if (t.created_at and t.created_at > s.closed_at) else out["appeared"]).append(now)
    out["totals_now"] = totals_of([row_of(t) for t in cur.values() if t.date == s.date])
    # «Тривожні» зміни: гроші, видалення, перенесення, ручне додавання після знімка (банк — норма)
    out["count"] = (len(out["changed"]) + len(out["deleted"]) + len(out["moved"]) + len(out["appeared"])
                    + sum(1 for r in out["added_after"] if r["src"] == "вручну"))
    return out
