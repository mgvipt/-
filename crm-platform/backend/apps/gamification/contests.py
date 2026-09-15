"""Змагання тижня (Розвиток v2, 16.09.2026) — короткі турніри з призами через «Біржу задач».

Правила:
- тиждень = понеділок–неділя; три категорії, щоб шанс був у кожного (і в новачка — через «ріст»):
    growth      найбільший ріст «тест → основне»: основні після тест-набору за тиждень − ваш середній тиждень за 4 попередні;
    conversion  найкраща конверсія: основні після тест-набору за тиждень ÷ ваші тест-набори, оплачені за 30 днів до кінця тижня
                (від 3 тест-наборів і 1 основного);
    quality     ріст якості дзвінків: середній бал розборів тижня − ваш середній за 4 попередні тижні (від +5 балів,
                від 3 розборів і в тижні, і до нього) — щоб приз ішов за покращення, а не «найменш слабкому» (зараз
                середні бали 27–38 з 100);
- «основне після тест-набору» — рівно та сама умова, що в бонусі ЗП (engine._c_event / rules.collect);
- приз = задача біржі з напряму «Змагання тижня» (ціну змінює власник на Біржі); на Біржі задачі лишаються
  НЕАКТИВНИМИ — «Беру» для них немає. Власник вмикає змагання в «Розвиток → Змагання тижня» і після кінця тижня
  тисне «Нарахувати приз»: CRM створює прийняту задачу переможцю через звичайне прийняття біржі (bounty.services.accept —
  ліміти, фонд, затверджена відомість) → сума йде в ЗП рядком «Задачі з біржі».
- Учасник бачить лише СВОЇ цифри; таблицю всіх — лише власник. Рейтингу між людьми на екрані співробітника немає.
"""
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Avg, Count, Min
from django.utils import timezone

from apps.payroll import engine

CONTESTS = [
    {"code": "growth", "title": "Змагання тижня: найбільший ріст «тест → основне»", "prize": 300, "unit": "шт",
     "rule": "Скільки ваших тест-наборів стали основним замовленням за тиждень, мінус ваш середній тиждень за 4 попередні. "
             "Перемагає найбільший плюс (від +1). Змагаєтесь із собою минулим — шанс є в кожного, і в новачка."},
    {"code": "conversion", "title": "Змагання тижня: найкраща конверсія тест → основне", "prize": 300, "unit": "%",
     "rule": "Основні замовлення тижня після тест-набору ÷ ваші тест-набори, оплачені за 30 днів до кінця тижня × 100. "
             "Беруть участь від 3 тест-наборів і 1 основного."},
    {"code": "quality", "title": "Змагання тижня: ріст якості дзвінків", "prize": 200, "unit": "бал",
     "rule": "Середній бал розборів ваших дзвінків за тиждень мінус ваш середній бал за 4 попередні тижні. "
             "Перемагає найбільший ріст від +5 балів (від 3 розборів і в тижні, і за 4 тижні до нього)."},
]
BY_CODE = {c["code"]: c for c in CONTESTS}
CATEGORY_NAME = "Змагання тижня"
MIN_TESTS = 3
MIN_CALLS = 3
QUALITY_MIN_GROWTH = 5


class ContestError(Exception):
    def __init__(self, text, status=400):
        super().__init__(text)
        self.text, self.status = text, status


def week_key(d):
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def week_bounds(key=None, today=None):
    """«2026-W38» → (понеділок, неділя). Без ключа — минулий повний тиждень."""
    today = today or timezone.localdate()
    if key:
        try:
            y, w = key.split("-W")
            mon = date.fromisocalendar(int(y), int(w), 1)
        except (ValueError, TypeError):
            raise ContestError("Тиждень у форматі РРРР-Wтт, напр. 2026-W38")
    else:
        mon = today - timedelta(days=today.weekday() + 7)
    return mon, mon + timedelta(days=6)


def participants():
    from .views import sales_managers
    return list(sales_managers().order_by("id"))


def _conversions(since, until, uids):
    from .rules import collect
    out = {}
    for e in collect(since, until, user_ids=uids):
        if e["kind"] == "test_main":
            out[e["manager_id"]] = out.get(e["manager_id"], 0) + 1
    return out


def _tests_paid(since, until, uids):
    from apps.crm.models import Deal
    from apps.finance.models import Transaction
    pol = engine.policy()
    firsts = (Transaction.objects.filter(direction="in", transfer_account__isnull=True, deal__isnull=False,
                                         deal__funnel_id__in=pol["funnels"]["test"], deal__owner_id__in=uids)
              .values("deal_id", "deal__owner_id").annotate(first=Min("date")))
    out = {}
    for r in firsts:
        if since <= r["first"] <= until:
            out[r["deal__owner_id"]] = out.get(r["deal__owner_id"], 0) + 1
    return out


def results(mon, sun=None):
    """Цифри всіх учасників за тиждень + переможець кожної категорії (None — немає / нічия). Лише читання."""
    from .views import quality_qs
    sun = sun or mon + timedelta(days=6)
    people = participants()
    uids = [u.id for u in people]
    conv = _conversions(mon, sun, uids)
    base = _conversions(mon - timedelta(days=28), mon - timedelta(days=1), uids)
    tests = _tests_paid(sun - timedelta(days=29), sun, uids)
    def _q(a, b):
        return {r["manager_id"]: (r["a"], r["n"]) for r in quality_qs(None, a, b).filter(manager_id__in=uids)
                .values("manager_id").annotate(a=Avg("overall_score"), n=Count("id"))}
    qual, qbase = _q(mon, sun), _q(mon - timedelta(days=28), mon - timedelta(days=1))
    rows = []
    for u in people:
        c = conv.get(u.id, 0)
        avg4 = round(base.get(u.id, 0) / 4, 1)
        t = tests.get(u.id, 0)
        qa, qn = qual.get(u.id, (None, 0))
        qb, qbn = qbase.get(u.id, (None, 0))
        qg = round(qa - qb, 1) if (qa is not None and qb is not None) else None
        rows.append({
            "id": u.id, "name": u.get_full_name() or u.username,
            "growth": {"value": round(c - avg4, 1), "ok": (c - avg4) >= 1,
                       "text": f"{c} за тиждень − {avg4:g} (ваш середній тиждень) = {round(c - avg4, 1):+g}"},
            "conversion": {"value": round(c / t * 100) if t else None, "ok": t >= MIN_TESTS and c >= 1,
                           "text": (f"{c} основних ÷ {t} тест-наборів × 100 = {round(c / t * 100)}%" if t
                                    else "тест-наборів за 30 днів немає")
                                   + ("" if t >= MIN_TESTS else f" (для участі потрібно від {MIN_TESTS})")},
            "quality": {"value": qg, "ok": qn >= MIN_CALLS and qbn >= MIN_CALLS and qg is not None and qg >= QUALITY_MIN_GROWTH,
                        "text": (f"бал тижня {round(qa)} ({qn} розборів) − ваш звичайний {round(qb)} = {qg:+g}" if qg is not None
                                 else (f"бал тижня {round(qa)} ({qn} розборів); за 4 тижні до нього розборів немає" if qa is not None
                                       else "розборів цього тижня немає"))
                                + ("" if (qn >= MIN_CALLS and qbn >= MIN_CALLS) else f" (для участі — від {MIN_CALLS} розборів у тижні і до нього)")
                                + ("" if qg is None or qg >= QUALITY_MIN_GROWTH else f"; приз — від +{QUALITY_MIN_GROWTH}")},
        })
    winners = {}
    for c in CONTESTS:
        ok = [r for r in rows if r[c["code"]]["ok"] and r[c["code"]]["value"] is not None]
        if not ok:
            winners[c["code"]] = {"user_id": None, "note": "ніхто не виконав умову участі"}
            continue
        top = max(r[c["code"]]["value"] for r in ok)
        best = [r for r in ok if r[c["code"]]["value"] == top]
        winners[c["code"]] = ({"user_id": best[0]["id"], "name": best[0]["name"], "value": top} if len(best) == 1
                              else {"user_id": None, "tie": [r["id"] for r in best],
                                    "note": "нічия: " + ", ".join(r["name"] for r in best) + " — рішення за власником"})
    return {"week": week_key(mon), "from": mon.isoformat(), "to": sun.isoformat(),
            "finished": sun < timezone.localdate(), "rows": rows, "winners": winners}


def state():
    """Які змагання заведено й увімкнено (GamSettings.contests) + дані задачі біржі (назва, приз)."""
    from apps.bounty.models import TaskOffer
    from .models import GamSettings
    cfg = GamSettings.get().contests or {}
    offers = {o.id: o for o in TaskOffer.objects.filter(id__in=[(v or {}).get("offer_id") for v in cfg.values()]
                                                        ).select_related("category")}
    out = []
    for c in CONTESTS:
        v = cfg.get(c["code"]) or {}
        o = offers.get(v.get("offer_id"))
        out.append({"code": c["code"], "title": o.title if o else c["title"], "rule": c["rule"], "unit": c["unit"],
                    "prize": float(o.price) if o else float(c["prize"]), "offer_id": o.id if o else None,
                    "seeded": bool(o and not o.archived), "enabled": bool(o and not o.archived and v.get("enabled"))})
    return out


def awarded(code, week):
    from apps.bounty.models import TaskClaim
    st = next((s for s in state() if s["code"] == code), None)
    if not st or not st["offer_id"]:
        return None
    return (TaskClaim.objects.filter(offer_id=st["offer_id"], proof_text__startswith=f"[contest:{code}:{week}]")
            .exclude(status="cancelled").select_related("user").first())


def for_user(uid, today=None):
    """Картка учасника: лише ввімкнені змагання і лише СВОЇ цифри за поточний і минулий тиждень."""
    on = [s for s in state() if s["enabled"]]
    if not on or uid not in {u.id for u in participants()}:
        return None
    today = today or timezone.localdate()
    cur_mon = today - timedelta(days=today.weekday())
    cur = results(cur_mon, cur_mon + timedelta(days=6))
    last_mon = cur_mon - timedelta(days=7)
    last = results(last_mon)
    me_c = next((r for r in cur["rows"] if r["id"] == uid), None)
    me_l = next((r for r in last["rows"] if r["id"] == uid), None)
    out = []
    for s in on:
        won = awarded(s["code"], last["week"])
        out.append({**s, "now": me_c[s["code"]] if me_c else None, "last": me_l[s["code"]] if me_l else None,
                    "won_last": bool(won and won.user_id == uid)})
    return {"week": cur["week"], "from": cur["from"], "to": cur["to"], "last_week": last["week"], "items": out}


@transaction.atomic
def award(code, week, by_user, user_id=None):
    """Нарахувати приз переможцю тижня через Біржу задач. user_id — лише при нічиї (з тих, хто в нічиї)."""
    from apps.bounty import services as bs
    from apps.bounty.models import TaskClaim, TaskOffer
    if code not in BY_CODE:
        raise ContestError("Невідоме змагання")
    st = next(s for s in state() if s["code"] == code)
    if not st["seeded"]:
        raise ContestError("Змагання ще не заведено (команда rozvytok_contests_seed --live)", 409)
    if not st["enabled"]:
        raise ContestError("Змагання вимкнено — спершу увімкніть його", 409)
    mon, sun = week_bounds(week)
    if sun >= timezone.localdate():
        raise ContestError("Тиждень ще не закінчився — приз нараховується після неділі", 409)
    wk = week_key(mon)
    if awarded(code, wk):
        raise ContestError("Приз за цей тиждень уже нараховано", 409)
    res = results(mon, sun)
    w = res["winners"][code]
    uid = w.get("user_id")
    if uid is None and user_id and int(user_id) in (w.get("tie") or []):
        uid = int(user_id)
    if uid is None:
        raise ContestError("Переможця немає: " + (w.get("note") or "умову не виконано"), 409)
    row = next(r for r in res["rows"] if r["id"] == uid)
    o = TaskOffer.objects.select_for_update().get(pk=st["offer_id"])
    from apps.accounts.models import User
    winner = User.objects.get(pk=uid)
    now = timezone.now()
    text = f"[contest:{code}:{wk}] {BY_CODE[code]['title']} · {res['from']}–{res['to']}: {row[code]['text']}"
    c = TaskClaim.objects.create(offer=o, user=winner, qty=1, price=o.price, unit=o.unit, status="submitted",
                                 taken_at=now, submitted_at=now, proof_text=text[:2000], subtasks=[], subtasks_done=[],
                                 history=[bs._ev(by_user, "submit", f"переможець змагання тижня {wk} (визначила CRM)")])
    try:
        return bs.accept(c.id, by_user, comment=f"Приз: {BY_CODE[code]['title']} ({wk})")
    except bs.BountyError as e:
        raise ContestError(getattr(e, "detail", None) or str(e), getattr(e, "status", 409) or 409)
