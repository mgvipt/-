"""Сезонний рівень (Розвиток v2, 16.09.2026). Сезон = календарний квартал; з 1-го числа нового кварталу все з нуля.

Чому так: рівень «за бали за весь час» зробив обох досвідчених менеджерів «Легендами» назавжди, і далі рости не було
куди. Тепер рівень = як ти працюєш У ЦЬОМУ сезоні за тими ж мірками, від яких залежить ЗП:
  План      — % виконання свого плану (оплати ÷ план) у місяцях сезону, де план встановлено; максимум 100.
  Стандарт  — середня оцінка стандарту роботи, яку поставив керівник (ті самі оцінки, що в ЗП); неоцінений місяць не рахується.
  Якість    — середній бал розборів дзвінків за сезон ÷ ціль 70 × 100 (від 3 розборів); максимум 100.
Індекс сезону = середнє з наявних частин. Частини без даних не рахуються (і не тягнуть униз).
Рівні: 0–39 «Старт», 40–59 «Впевнений», 60–74 «Сильний», 75–89 «Профі», 90–100 «Майстер сезону».
"""
import calendar
from datetime import date

from django.db.models import Avg, Count, Sum
from django.utils import timezone

from apps.payroll import engine

QUALITY_TARGET = 70
QUALITY_MIN_N = 3
SEASON_LEVELS = [
    (0, "Старт", "\U0001f331", "#94a3b8"),
    (40, "Впевнений", "\U0001f7e6", "#2563eb"),
    (60, "Сильний", "\U0001f7e9", "#16a34a"),
    (75, "Профі", "\U0001f7e7", "#ea580c"),
    (90, "Майстер сезону", "\U0001f3c6", "#dc2626"),
]
Q_NAMES = ["I", "II", "III", "IV"]
MONTHS = ["", "січень", "лютий", "березень", "квітень", "травень", "червень", "липень", "серпень",
          "вересень", "жовтень", "листопад", "грудень"]


def quarter_bounds(d):
    q = (d.month - 1) // 3
    m1, m3 = 3 * q + 1, 3 * q + 3
    return date(d.year, m1, 1), date(d.year, m3, calendar.monthrange(d.year, m3)[1]), q


def level_of(index):
    if index is None:
        return None
    idx = 0
    for i, (thr, _n, _e, _c) in enumerate(SEASON_LEVELS):
        if index >= thr:
            idx = i
    thr, name, emoji, color = SEASON_LEVELS[idx]
    nxt = SEASON_LEVELS[idx + 1] if idx + 1 < len(SEASON_LEVELS) else None
    return {"no": idx + 1, "name": name, "emoji": emoji, "color": color, "from": thr,
            "next_name": nxt[1] if nxt else None, "next_from": nxt[0] if nxt else None,
            "to_next": (nxt[0] - index) if nxt else 0}


def _months(d1, d2):
    out, d = [], d1
    while d <= d2:
        out.append(d.strftime("%Y-%m"))
        d = engine.add_months(d.replace(day=1), 1)
    return out


def _plan_part(user, months):
    from apps.finance.models import ManagerPlan
    rows = []
    for p in months:
        pl = ManagerPlan.objects.filter(user=user, period=p).first()
        target = float(pl.target_revenue or 0) if pl else 0.0
        if target <= 0:
            continue
        d1, d2 = engine.period_bounds(p)
        sc = engine.active_scheme(user, d2)
        mc = sc.components.filter(active=True, kind="margin_share").first() if sc else None
        flt = {"deal__owner": user}
        if mc is not None:
            flt["deal__funnel_id__in"] = engine.online_funnels(mc.params, engine.policy())
        fact = float(engine._income(d1, d2, **flt).aggregate(s=Sum("amount_uah"))["s"] or 0)
        _refunds = getattr(engine, "_refunds", None)   # як «Моя ЗП → План» (пакет returns): мінус повернення клієнтам
        if _refunds:
            fact -= float(_refunds(d1, d2, **flt).aggregate(s=Sum("amount_uah"))["s"] or 0)
        rows.append((p, fact, target, min(100.0, fact / target * 100)))
    if not rows:
        return None
    v = round(sum(r[3] for r in rows) / len(rows))
    det = "; ".join(f"{MONTHS[int(p[5:7])]}: {engine._n(f)} з {engine._n(t)} ₴ = {round(x)}%" for p, f, t, x in rows)
    return {"key": "plan", "label": "План", "value": v, "detail": det}


def _standard_part(user, months):
    from apps.payroll.models import PayComponent
    comps = list(PayComponent.objects.filter(scheme__user=user, scheme__purpose="official", scheme__status="active",
                                             kind="standard", active=True))
    got = {}
    for c in comps:
        for p, v in ((c.params or {}).get("scores") or {}).items():
            if p in months:
                try:
                    got[p] = float(v)
                except (TypeError, ValueError):
                    pass
    if not got:
        return None if not comps else {"key": "standard", "label": "Стандарт", "value": None,
                                        "detail": "керівник ще не виставив оцінку стандарту в цьому сезоні — не рахується"}
    v = round(sum(got.values()) / len(got) * 100)
    det = "; ".join(f"{MONTHS[int(p[5:7])]}: {round(x * 100)}%" for p, x in sorted(got.items()))
    return {"key": "standard", "label": "Стандарт", "value": v, "detail": "оцінка керівника — " + det}


def _quality_part(uid, d1, d2):
    from .views import quality_qs
    agg = quality_qs(uid, d1, d2).aggregate(a=Avg("overall_score"), n=Count("id"))
    n, a = agg["n"] or 0, agg["a"]
    if n < QUALITY_MIN_N or a is None:
        return {"key": "quality", "label": "Якість дзвінків", "value": None,
                "detail": f"розборів дзвінків у сезоні: {n} — потрібно від {QUALITY_MIN_N}, поки не рахується"}
    v = min(100, round(a / QUALITY_TARGET * 100))
    return {"key": "quality", "label": "Якість дзвінків", "value": v,
            "detail": f"середній бал {round(a)} з {n} розборів ÷ ціль {QUALITY_TARGET} × 100 = {v}"}


def season(user, today=None):
    today = today or timezone.localdate()
    d1, d2, q = quarter_bounds(today)
    months = _months(d1, min(d2, today))
    parts = [p for p in (_plan_part(user, months), _standard_part(user, months), _quality_part(user.id, d1, d2)) if p]
    used = [p for p in parts if p.get("value") is not None]
    index = round(sum(p["value"] for p in used) / len(used)) if used else None
    if used:
        formula = "(" + " + ".join(f"{p['label']} {p['value']}" for p in used) + f") ÷ {len(used)} = {index}"
    else:
        formula = "Даних для сезону ще немає: потрібна оцінка стандарту, план на місяць або 3 розбори дзвінків."
    nq = q + 1
    nxt_start = date(d1.year + (1 if nq == 4 else 0), 1 if nq == 4 else 3 * nq + 1, 1)
    return {"label": f"{Q_NAMES[q]} квартал {d1.year}", "from": d1.isoformat(), "to": d2.isoformat(),
            "reset": nxt_start.isoformat(), "index": index, "level": level_of(index), "parts": parts,
            "formula": formula, "levels": [{"from": t, "name": n, "emoji": e} for t, n, e, _c in SEASON_LEVELS],
            "rule": "Індекс сезону = середнє з наявних частин (план, стандарт, якість дзвінків). "
                    "Частина без даних не рахується. З першого дня нового кварталу — все з нуля."}
