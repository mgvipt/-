"""Місця і вага відвантаження — з Нової Пошти (19.09.2026, Олег: «після закриття дня або коли пакуються
посилки — кількість місць тягнути з Нової Пошти цього клієнта, там же вага кожного місця, щоб правильно
внести в статистику»).

Чому: CRM рахує місця за правилом (відра, розфасовка, коробка набору), а НП бачить, що реально поїхало.
Приклади 19.09: #66537 — за правилом 3 місця, у НП 2 (1,61 + 1,87 кг); #66790 — за правилом 1 місце «до 5 кг»,
у НП 5,52 кг → місце «до 10 кг».

Джерело: TrackingDocument.getStatusDocuments — SeatsAmount (скільки місць), FactualWeight (фактична вага).
Вага КОЖНОГО місця є лише в нашій ТТН (np_data["seats"], якщо ТТН створювали з CRM і кількість збігається);
інакше — фактична вага ÷ кількість місць (позначено «оцінка»).

Результат лежить у job.done_snapshot["np"]; оплату упаковки це НЕ змінює (різниця показується окремо,
рішення — за Олегом).
"""
from decimal import Decimal

from django.utils import timezone

from . import weight_rules as WR


def _f(x):
    try:
        return float(str(x).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def fetch_np(deal):
    """Лише ЧИТАННЯ НП по ТТН сделки → {seats, weight, status} або None."""
    ttn = (deal.ttn or "").strip()
    if not ttn:
        return None
    from apps.integrations import adapters as ad
    phone = ""
    if deal.contact_id and deal.contact.phone:
        phone = "".join(ch for ch in deal.contact.phone if ch.isdigit())[-12:]
    r = ad._np_call("TrackingDocument", "getStatusDocuments", {"Documents": [{"DocumentNumber": ttn, "Phone": phone}]})
    row = ((r or {}).get("data") or [{}])[0] if isinstance(r, dict) else {}
    seats = int(_f(row.get("SeatsAmount")) or 0)
    weight = _f(row.get("FactualWeight")) or _f(row.get("DocumentWeight"))
    if seats <= 0 or weight <= 0:
        return None
    return {"seats": seats, "weight": round(weight, 3), "status": str(row.get("Status") or "")[:120]}


def per_seat(np, ours):
    """Вага кожного місця: наша ТТН (якщо кількість збігається і сума близька до факту) або факт ÷ місця."""
    kgs = [_f((s or {}).get("kg")) for s in (ours or [])]
    if len(kgs) == np["seats"] and all(k > 0 for k in kgs):
        total = sum(kgs)
        if total and abs(total - np["weight"]) <= max(0.5, np["weight"] * 0.25):
            return [round(k, 3) for k in kgs], "ТТН CRM"
    each = round(np["weight"] / np["seats"], 3)
    return [each] * np["seats"], "оцінка: вага НП ÷ місця"


def tiers_for(weights):
    t = {"T5": 0, "T10": 0, "T20": 0}
    for w in weights:
        for tier in (WR.split_tiers(Decimal(str(w))) or ["T5"]):
            t[tier] += 1
    return t


def sync_job(job, save=True):
    """Підтягнути місця/вагу НП у job.done_snapshot["np"]. Повертає dict або None."""
    deal = job.deal
    np = fetch_np(deal)
    if np is None:
        return None
    weights, src = per_seat(np, (deal.np_data or {}).get("seats"))
    np.update({"per_seat": weights, "per_seat_src": src, "tiers": tiers_for(weights),
               "at": timezone.now().isoformat(timespec="seconds")})
    snap = dict(job.done_snapshot or {})
    snap["np"] = np
    job.done_snapshot = snap
    if save:
        type(job).objects.filter(pk=job.pk).update(done_snapshot=snap)
    return np


def pack_diff(job, rates=None):
    """Скільки коштувала б упаковка за місцями НП проти нарахованого (для рішення Олега; нічого не змінює)."""
    from .wh_views import _rate, live_rates
    np = (job.done_snapshot or {}).get("np")
    if not np:
        return None
    lr = rates or live_rates()
    r = {"T5": _rate("WH_PACK_5", lr), "T10": _rate("WH_PACK_10", lr), "T20": _rate("WH_PACK_20", lr)}
    crm = job.pack_le5_count * r["T5"] + job.pack_le10_count * r["T10"] + job.pack_le20_count * r["T20"]
    by_np = sum(Decimal(np["tiers"][k]) * r[k] for k in r)
    return {"crm": crm, "np": by_np, "diff": by_np - crm}
