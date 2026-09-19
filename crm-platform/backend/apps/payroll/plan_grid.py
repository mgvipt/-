"""План продажів по тижнях і днях + «що потрібно для плану» + зведена по команді (19.09.2026).

Олег: «план продажників поділити на тижні (так рекомендує ATM), у Розвитку — тижневий і денний план і виконання
в одній таблиці; що потрібно продати, скільки тест-наборів, основних, діалогів; мені — зведена по всіх;
дані — з одного місця».

ОДНЕ джерело грошей — те саме, що рахує ЗП: engine._income − engine._refunds по угодах менеджера,
за датою приходу (= apps.finance.money). План — ManagerPlan (загальний; якщо розбитий — онлайн і офлайн окремо).
Денний план = місячний ÷ робочі дні (пн–пт, як engine.workdays). Тиждень = сума його днів у межах місяця.
«Що потрібно» — з модели продажів: основних = залишок ÷ середній чек основного; тест-наборів = основні ÷
конверсія тест→основне; діалогів = тест-набори ÷ конверсія діалог→тест. Конверсії — фактичні по менеджеру
за 90 днів, якщо даних достатньо, інакше — ставки моделі (Фінмодель → Зарплата: kpi_conv_tm, kpi_conv_lt, kpi_avg_check).
"""
from collections import defaultdict
from datetime import timedelta

from django.db.models import Min
from django.utils import timezone

from . import engine

WD = ["пн", "вт", "ср", "чт", "пт", "сб", "нд"]
MIN_SAMPLE_TESTS = 10     # щоб рахувати власну конверсію тест→основне
MIN_SAMPLE_TAKEN = 20     # щоб рахувати власну конверсію діалог→тест


def _f(x):
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def targets(user, period):
    from apps.finance.models import ManagerPlan
    p = ManagerPlan.objects.filter(user=user, period=period).first()
    if not p:
        return None
    t = {"total": _f(p.target_revenue), "min": _f(p.min_revenue), "ambition": _f(p.ambition_revenue), "split": p.is_split}
    if p.is_split:
        t.update({"online": _f(p.online_target), "offline": _f(p.offline_target)})
    return t


def money_rows(user, d1, d2, funnels=None):
    """[(дата, deal_id, сума)] — прихід (+) і повернення (−) по угодах менеджера. Те саме правило, що ЗП."""
    flt = {"deal__owner": user}
    if funnels:
        flt["deal__funnel_id__in"] = list(funnels)
    rows = [(r[0], r[1], _f(r[2])) for r in engine._income(d1, d2, **flt).values_list("date", "deal_id", "amount_uah")]
    rows += [(r[0], r[1], -_f(r[2])) for r in engine._refunds(d1, d2, **flt).values_list("date", "deal_id", "amount_uah")]
    return rows


def plan_fact(user, period, pol=None):
    """ЄДИНИЙ факт плану: загальний і (якщо план розбитий) онлайн / офлайн окремо."""
    pol = pol or engine.policy()
    t = targets(user, period)
    d1, d2 = engine.period_bounds(period)
    total = sum(r[2] for r in money_rows(user, d1, d2))
    out = {"total": {"plan": t["total"] if t else 0.0, "fact": round(total, 2)}}
    if t and t["split"]:
        online = sum(r[2] for r in money_rows(user, d1, d2, engine.online_funnels(None, pol)))
        out["online"] = {"plan": t["online"], "fact": round(online, 2)}
        out["offline"] = {"plan": t["offline"], "fact": round(total - online, 2)}
    for v in out.values():
        v["pct"] = round(v["fact"] / v["plan"] * 100) if v["plan"] else None
    return out


def model(user, pol, today):
    """Середній чек основного і конверсії: власні за 90 днів (якщо вистачає даних) або з моделі."""
    from apps.crm.models import Deal
    from apps.crm.take_stats import take_events
    from apps.finance.models import Transaction
    from apps.finance.services import salary_params
    from .whatif import _avg_main_order
    sp = salary_params()
    since = today - timedelta(days=90)
    avg = _avg_main_order(user, pol, today)
    firsts = dict(Transaction.objects.filter(direction="in", transfer_account__isnull=True, deal__owner=user)
                  .values("deal_id").annotate(f=Min("date")).values_list("deal_id", "f"))
    recent = {d for d, f in firsts.items() if f and f >= since}
    test_ids = set(Deal.objects.filter(id__in=list(recent)).filter(engine.kind_q("test", pol)).values_list("id", flat=True))
    test_contacts = set(Deal.objects.filter(id__in=list(test_ids)).values_list("contact_id", flat=True)) - {None}
    main_contacts = set(Deal.objects.filter(owner=user, id__in=[d for d in firsts if d not in test_ids])
                        .filter(engine.kind_q("main", pol)).values_list("contact_id", flat=True)) - {None}
    taken = len([1 for uid, _d in take_events(since, today, [user.id])])
    conv_tm = (len(test_contacts & main_contacts) / len(test_contacts)) if len(test_contacts) >= MIN_SAMPLE_TESTS else None
    conv_lt = (len(test_contacts) / taken) if taken >= MIN_SAMPLE_TAKEN else None
    # скільки основних продажів ПРИХОДИТЬ через тест-набір (у салоні купують основне одразу) і скільки
    # діалогів припадає на одну оплачену угоду — фактично по менеджеру за 90 днів
    recent_main_contacts = set(Deal.objects.filter(id__in=[d for d in recent if d not in test_ids])
                               .filter(engine.kind_q("main", pol)).values_list("contact_id", flat=True)) - {None}
    all_test_contacts = set(Deal.objects.filter(owner=user, id__in=list(firsts)).filter(engine.kind_q("test", pol))
                            .values_list("contact_id", flat=True)) - {None}
    via_test = (len(recent_main_contacts & all_test_contacts) / len(recent_main_contacts)
                if len(recent_main_contacts) >= MIN_SAMPLE_TESTS else None)
    per_sale = (taken / len(recent)) if (len(recent) >= MIN_SAMPLE_TAKEN and taken) else None
    return {
        "via_test": round(via_test * 100) if via_test is not None else 100,
        "via_test_src": "ваші основні продажі за 90 днів" if via_test is not None else "припущення: усі через тест-набір",
        "dialogs_per_sale": round(per_sale, 1) if per_sale is not None else None,
        "avg_check": round(avg) if avg else _f(sp.get("kpi_avg_check")),
        "avg_check_src": "ваші основні продажі за 90 днів" if avg else "модель (Фінмодель)",
        "conv_tm": round(conv_tm * 100, 1) if conv_tm is not None else _f(sp.get("kpi_conv_tm")),
        "conv_tm_src": "ваші клієнти за 90 днів" if conv_tm is not None else "модель (Фінмодель)",
        "conv_lt": round(conv_lt * 100, 1) if conv_lt is not None else _f(sp.get("kpi_conv_lt")),
        "conv_lt_src": "ваші діалоги за 90 днів" if conv_lt is not None else "модель (Фінмодель)",
    }


def plan_grid(user, period, today=None, pol=None):
    from apps.crm.models import Deal
    from apps.crm.take_stats import take_events
    from apps.finance.models import Transaction
    pol = pol or engine.policy()
    today = today or timezone.localdate()
    d1, d2 = engine.period_bounds(period)
    t = targets(user, period) or {"total": 0.0, "split": False}
    n_work = engine.workdays(d1, d2) or 1
    per_day = t["total"] / n_work
    rows = money_rows(user, d1, d2)
    money = defaultdict(float)
    for d, _did, a in rows:
        money[d] += a
    # продажі — за днем ПЕРШОЇ оплати угоди (тест-набір / основне)
    ids = {r[1] for r in rows}
    firsts = dict(Transaction.objects.filter(direction="in", transfer_account__isnull=True, deal_id__in=list(ids))
                  .values("deal_id").annotate(f=Min("date")).values_list("deal_id", "f"))
    tests = set(Deal.objects.filter(id__in=list(ids)).filter(engine.kind_q("test", pol)).values_list("id", flat=True))
    mains = set(Deal.objects.filter(id__in=list(ids)).filter(engine.kind_q("main", pol)).values_list("id", flat=True))
    n_tests, n_mains = defaultdict(int), defaultdict(int)
    for did, f in firsts.items():
        if f and d1 <= f <= d2:
            if did in tests:
                n_tests[f] += 1
            elif did in mains:
                n_mains[f] += 1
    taken = defaultdict(int)
    for _uid, day in take_events(d1, min(d2, today), [user.id]):
        taken[day] += 1

    weeks, cur = [], None
    d = d1
    while d <= d2:
        if cur is None or d.weekday() == 0:
            cur = {"from": d.isoformat(), "days": [], "plan": 0.0, "fact": 0.0, "tests": 0, "mains": 0, "taken": 0}
            weeks.append(cur)
        work = d.weekday() < 5
        day = {"date": d.isoformat(), "wd": WD[d.weekday()], "workday": work, "future": d > today,
               "plan": round(per_day, 2) if work else 0.0, "fact": round(money.get(d, 0.0), 2),
               "tests": n_tests.get(d, 0), "mains": n_mains.get(d, 0), "taken": taken.get(d, 0)}
        day["pct"] = round(day["fact"] / day["plan"] * 100) if day["plan"] and not day["future"] else None
        cur["days"].append(day)
        for k in ("plan", "fact"):
            cur[k] += day[k]
        for k in ("tests", "mains", "taken"):
            cur[k] += day[k]
        cur["to"] = d.isoformat()
        d += timedelta(days=1)
    for w in weeks:
        w["plan"], w["fact"] = round(w["plan"], 2), round(w["fact"], 2)
        w["label"] = "%s–%s" % (w["from"][8:10] + "." + w["from"][5:7], w["to"][8:10] + "." + w["to"][5:7])
        w["pct"] = round(w["fact"] / w["plan"] * 100) if w["plan"] else None
        w["current"] = w["from"] <= today.isoformat() <= w["to"]

    fact = round(sum(money.values()), 2)
    plan_to_date = round(per_day * engine.workdays(d1, min(today, d2)), 2) if today >= d1 else 0.0
    start = max(today, d1)
    rem_days = engine.workdays(start, d2) if start <= d2 else 0
    left = max(0.0, t["total"] - fact)
    m = model(user, pol, today)
    need = None
    if t["total"] and rem_days:
        mains_n = left / m["avg_check"] if m["avg_check"] else 0.0
        # тест-набори потрібні лише для тієї частки основних, що приходить через тест (у салоні — напряму)
        tests_n = (mains_n * m["via_test"] / 100) / (m["conv_tm"] / 100) if m["conv_tm"] else 0.0
        if m.get("dialogs_per_sale"):
            dialogs_n = (mains_n + tests_n) * m["dialogs_per_sale"]   # фактично: діалогів на одну оплату
        else:
            dialogs_n = tests_n / (m["conv_lt"] / 100) if m["conv_lt"] else 0.0
        need = {"left": round(left), "days": rem_days, "per_day": round(left / rem_days),
                "mains": round(mains_n, 1), "mains_per_day": round(mains_n / rem_days, 1),
                "tests": round(tests_n, 1), "tests_per_day": round(tests_n / rem_days, 1),
                "dialogs": round(dialogs_n), "dialogs_per_day": round(dialogs_n / rem_days, 1)}
    return {"period": period, "user": {"id": user.id, "name": user.get_full_name() or user.username},
            "plan": t, "per_day": round(per_day, 2), "workdays": n_work, "fact": fact,
            "pct": round(fact / t["total"] * 100) if t["total"] else None,
            "plan_to_date": plan_to_date, "pace_pct": round(fact / plan_to_date * 100) if plan_to_date else None,
            "by_part": plan_fact(user, period, pol), "weeks": weeks, "need": need, "model": m,
            "totals": {"tests": sum(n_tests.values()), "mains": sum(n_mains.values()), "taken": sum(taken.values())},
            "source": "Гроші — оплати по ваших угодах з фінансового журналу мінус повернення (як ЗП), за датою приходу."}


def team_summary(period, today=None):
    """Зведена для власника: усі, у кого є план на місяць."""
    from django.contrib.auth import get_user_model
    from apps.finance.models import ManagerPlan
    pol = engine.policy()
    today = today or timezone.localdate()
    out = []
    for uid in ManagerPlan.objects.filter(period=period).values_list("user_id", flat=True):
        u = get_user_model().objects.filter(id=uid, is_active=True).first()
        if not u:
            continue
        g = plan_grid(u, period, today, pol)
        cw = next((w for w in g["weeks"] if w["current"]), None)
        out.append({"user": g["user"], "plan": g["plan"]["total"], "fact": g["fact"], "pct": g["pct"],
                    "pace_pct": g["pace_pct"], "week": ({"label": cw["label"], "plan": cw["plan"], "fact": cw["fact"],
                                                         "pct": cw["pct"]} if cw else None),
                    "need": g["need"], "totals": g["totals"], "by_part": g["by_part"]})
    out.sort(key=lambda r: -(r["pct"] or 0))
    team = {"plan": sum(r["plan"] for r in out), "fact": sum(r["fact"] for r in out)}
    team["pct"] = round(team["fact"] / team["plan"] * 100) if team["plan"] else None
    return {"period": period, "rows": out, "team": team}


# ───────────────────────── API ─────────────────────────
from rest_framework.permissions import IsAuthenticated  # noqa: E402
from rest_framework.response import Response  # noqa: E402
from rest_framework.views import APIView  # noqa: E402


def _can_see_team(u):
    return bool(u.is_superuser or (hasattr(u, "has_perm_code") and u.has_perm_code("roles.manage")))


def _period(request):
    p = str(request.query_params.get("period") or "")
    return p if len(p) == 7 and p[4] == "-" else timezone.localdate().strftime("%Y-%m")


class PlanGridView(APIView):
    """/api/payroll/my/plan-grid/?period=YYYY-MM[&user=<id> — лише власник/керівник]"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.contrib.auth import get_user_model
        u = request.user
        uid = request.query_params.get("user")
        if uid and str(uid) != str(u.id):
            if not _can_see_team(u):
                return Response({"detail": "Немає доступу до плану іншого співробітника"}, status=403)
            u = get_user_model().objects.filter(id=uid).first()
            if u is None:
                return Response({"detail": "Співробітника не знайдено"}, status=404)
        return Response(plan_grid(u, _period(request)))


class PlanTeamView(APIView):
    """/api/payroll/plan-team/?period=YYYY-MM — зведена по всіх з планом (власник/керівник)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _can_see_team(request.user):
            return Response({"detail": "Зведена — лише для власника або керівника"}, status=403)
        return Response(team_summary(_period(request)))
