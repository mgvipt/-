"""«Що буде, якщо» у «Моя ЗП» (Розвиток v2, 16.09.2026) — калькулятор за ТІЄЮ САМОЮ формулою, що й ЗП.

GET /api/payroll/my/whatif/?pay=X&tests=N&avg_order=Y — лише свої дані, лише поточний місяць, лише читання.

Як рахуємо (без жодного запису в БД):
- база — engine.calc(людина, місяць): ті самі рядки, що в «Моя ЗП»;
- «% з маржі» перераховуємо формулою engine._c_margin: маржа × (1 − частка понад план) × ставка до плану +
  маржа × частка понад план × (ставка понад план, якщо стандарт ≥ поріг), де частка понад план = (оплати − план) ÷ оплати.
  Оплати й маржа — ті самі, що бере engine (журнал «in» по ваших угодах у воронках ставки, engine.margin_map);
  тести перевіряють, що база дає рівно рядок engine.calc, а «ще X ₴» — рівно те, що дасть engine.calc після такої оплати;
- «% з оплат» (basis own_payments) — X × %; бонус «тест → основне» — ступінь зі СВОЄЇ ставки (як engine._c_event);
- гарантія новачку: доплата = max(0, гарантія − сума інших рядків), як в engine.calc (лише коли умови підтверджено).
Маржа: хто не має права «маржа угоди» (deal.margin.view), не бачить ні маржі, ні її % — лише свій заробіток (16.09.2026, Олег: без округлення).
(Округлення не ховає середню маржу повністю: з великої суми X її можна оцінити приблизно — див. README.)
"""
from datetime import timedelta

from django.db.models import Min, Sum
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import engine
from .my_views import NO_PLAN_TEXT, _can, _fmt, _has_plan, _n, _tiers

ROUND_TO = 10
MAX_PAY = 10_000_000
MAX_TESTS = 200


def _num(v, default, lo, hi):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, x))


def margin_state(user, comp, period, pol, std_score):
    """Оплати, маржа і параметри ставки — рівно як їх бере engine._c_margin."""
    p = comp.params or {}
    funnels = engine.online_funnels(p, pol)
    d1, d2 = engine.period_bounds(period)
    txs = list(engine._income(d1, d2, deal__owner=user, deal__funnel_id__in=funnels))
    # якщо в engine вже є повернення клієнтам (пакет returns, 16.09: engine._refunds) — мінусуємо рівно як _c_margin
    _refunds = getattr(engine, "_refunds", None)
    rf = list(_refunds(d1, d2, deal__owner=user, deal__funnel_id__in=funnels)) if _refunds else []
    mm = engine.margin_map([t.deal_id for t in txs + rf], pol)
    rev = margin = 0.0
    for t, sign in [(x, 1) for x in txs] + [(x, -1) for x in rf]:
        r, _e = mm.get(t.deal_id, (0.5, True))
        amt = sign * float(t.amount_uah or 0)
        rev += amt
        margin += amt * r
    to_pct = float(p.get("pct_to_plan", 10))
    over_pct = float(p.get("pct_over_plan", to_pct))
    _site = set(pol["funnels"].get("site") or [])  # 17.09: воронки сайтів не міняють норматив (оцінка — як у 21/22)
    est = [float(pol["margin_estimate_pct"].get(str(f), 50)) / 100.0 for f in funnels if f not in _site or not (set(funnels) - _site)]
    return {"rev": rev, "margin": margin, "to": to_pct, "over": over_pct, "plan": engine._plan(user, period),
            "gate": std_score >= float(p.get("gate_standard_min", 0.75)), "funnels": list(funnels),
            "ratio": (margin / rev) if rev > 0 else (sum(est) / len(est) if est else 0.5), "ratio_est": rev <= 0}


def margin_amount(st, rev, margin):
    """Формула engine._c_margin (рядок «% з маржі»), округлення — як engine._line."""
    plan = st["plan"]
    over_share = max(0.0, rev - plan) / rev if (plan and rev) else 0.0
    a = margin * (1 - over_share) * st["to"] / 100 + margin * over_share * (st["over"] if st["gate"] else st["to"]) / 100
    return round(float(a or 0))


def _guarantee(sc, period, pol):
    """(ціль гарантії за місяць, умови підтверджено?) — як в engine.calc; None — гарантія цього місяця не діє."""
    d1, d2 = engine.period_bounds(period)
    for c in sc.components.filter(active=True, kind="guarantee"):
        s, e = engine.guarantee_window(c)
        if not s or d2 < s or d1 > e:
            continue
        g_amt = float((c.params or {}).get("amount") or pol["guarantee"]["amount"])
        k = engine.workdays(max(d1, s), min(d2, e)) / (engine.workdays(d1, d2) or 1)
        ok = bool((((c.params or {}).get("checks") or {}).get(period) or {}).get("ok"))
        return g_amt * k, ok
    return None


def _avg_main_order(user, pol, today):
    from apps.finance.models import Transaction
    rows = (Transaction.objects.filter(direction="in", transfer_account__isnull=True, deal__owner=user,
                                       ).filter(engine.kind_q("main", pol, "deal__"))
            .values("deal_id").annotate(first=Min("date"), total=Sum("amount_uah")))
    vals = [float(r["total"] or 0) for r in rows if r["first"] >= today - timedelta(days=90) and r["total"]]
    return (sum(vals) / len(vals)) if vals else None


OPEN_DAYS = 90   # «відкриті» — створені за останні 90 днів (старі завислі угоди не обіцяємо)


def _open_discounts(user, pol):
    """Мої основні угоди за останні 90 днів, ще не оплачені повністю і не програні, зі знижкою на позиціях."""
    from apps.crm.models import Deal
    out = []
    since = timezone.now() - timedelta(days=OPEN_DAYS)
    for d in (Deal.objects.filter(engine.kind_q("main", pol), owner=user, stage__is_lost=False, stage__is_won=False,
                                  created_at__gte=since)
              .prefetch_related("items__product").order_by("-id")[:300]):
        disc = sum(float(i.discount_sum or 0) for i in d.items.all())
        if disc <= 0.5:
            continue
        paid = _n(d.payments.filter(is_paid=True).aggregate(s=Sum("amount"))["s"])
        if paid + 0.5 >= _n(d.amount):
            continue
        out.append({"deal_id": d.id, "title": (d.title or "")[:80], "discount": round(disc)})
    out.sort(key=lambda x: -x["discount"])
    return out


class MyWhatIfView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        u = request.user
        q = request.query_params
        other = q.get("user") or q.get("user_id")
        if other not in (None, "") and str(other) != str(u.id):
            return Response({"detail": "Тут видно лише ваші власні дані"}, status=403)
        today = timezone.localdate()
        period = today.strftime("%Y-%m")
        pol = engine.policy()
        sc = engine.active_scheme(u, engine.period_bounds(period)[1])
        if not sc:
            return Response({"available": False, "message": "Для вас ще не задано ставку — калькулятору нема з чого рахувати."})
        comps = list(sc.components.filter(active=True))
        mc = next((c for c in comps if c.kind == "margin_share"), None)
        ev = next((c for c in comps if c.kind == "event_bonus"), None)
        if not mc and not ev:
            return Response({"available": False, "message": "Калькулятор — для ставок з відсотком від продажів."})
        can_margin = _can(u, "deal.margin.view")
        rnd = lambda x: int(round(float(x)))  # 16.09.2026 (Олег): без округлення — людина бачить точну суму
        base = engine.calc(u, period)
        lines = base["lines"]
        subtotal = sum(l["amount"] for l in lines if l.get("kind") not in ("guarantee", "insurance", "bounty"))
        g = _guarantee(sc, period, pol)
        std_c = next((c for c in comps if c.kind == "standard"), None)
        sv = ((std_c.params or {}).get("scores") or {}).get(period) if std_c else None
        std_score = float(sv) if sv is not None else 1.0
        st = margin_state(u, mc, period, pol, std_score) if mc else None
        rs_pct = sum(float((c.params or {}).get("pct") or 0) for c in comps
                     if c.kind == "revenue_share" and (c.params or {}).get("basis") == "own_payments")
        has_plan = _has_plan(u, period)
        notes = []
        if not has_plan and mc:
            notes.append(f"{NO_PLAN_TEXT} — усе рахується за ставкою {st['to']:g}%, без «понад план».")
        if any(l.get("kind") == "insurance" for l in lines):
            notes.append("Цього місяця діє «страховочний місяць» (платимо більшу з двох схем) — прибавка може бути меншою.")
        if not can_margin:
            notes.append("Маржу угод бачить лише керівник — тут видно ваш заробіток.")

        def delta_total(d_lines):
            """Прибавка до «разом» з урахуванням гарантії (як engine.calc)."""
            if g and g[1]:
                old = subtotal + max(0.0, g[0] - subtotal)
                new_sub = subtotal + d_lines
                return (new_sub + max(0.0, g[0] - new_sub)) - old
            return d_lines

        def extra_pay(x, margin_add=None):
            if not st:
                return 0, 0
            m_add = x * st["ratio"] if margin_add is None else margin_add
            d_m = margin_amount(st, st["rev"] + x, st["margin"] + m_add) - margin_amount(st, st["rev"], st["margin"])
            d_r = round(x * rs_pct / 100) if rs_pct else 0
            return d_m, d_r

        scen = []
        # 1. ще оплат на X ₴
        pay = _num(q.get("pay"), 10000, 0, MAX_PAY)
        d_m, d_r = extra_pay(pay)
        dt = delta_total(d_m + d_r)
        if st:
            if can_margin:
                how = (f"Оплати цього місяця {_fmt(st['rev'])} ₴, маржа {_fmt(st['margin'])} ₴ "
                       f"({round(st['ratio'] * 100)}%{' — оцінка за нормативом воронки' if st['ratio_est'] else ''}). "
                       f"Ще {_fmt(pay)} ₴ → маржа +{_fmt(pay * st['ratio'])} ₴ × ставка → +{_fmt(d_m)} ₴")
            else:
                how = (f"Ще {_fmt(pay)} ₴ оплат по ваших угодах → за вашою ставкою ({st['to']:g}% з маржі"
                       + (f", понад план {st['over']:g}%" if has_plan and st['over'] != st['to'] else "") + f") ≈ +{_fmt(rnd(d_m))} ₴")
            if d_r:
                how += f"; + {rs_pct:g}% з оплат = +{_fmt(rnd(d_r))} ₴"
            if g and g[1] and dt != d_m + d_r:
                how += f". Діє гарантія: доплата до неї зменшиться, тому до «разом» лише +{_fmt(rnd(dt))} ₴"
            elif g and not g[1]:
                how += ". Доплата до гарантії (коли керівник підтвердить умови) від цього зменшиться."
            scen.append({"code": "pay", "input": pay, "delta": rnd(dt), "lines_delta": rnd(d_m + d_r),
                         "new_total": rnd(base["total"] + dt), "explain": how + "."})
        # 2. конвертую N тест-наборів в основне вчасно
        if ev:
            t = _tiers(ev.params)
            n = int(_num(q.get("tests"), 3, 0, MAX_TESTS))
            avg = _num(q.get("avg_order"), 0, 0, MAX_PAY) or (_avg_main_order(u, pol, today) or float(t["min_order"]) * 2)
            per = float(t["fast"]) if avg >= float(t["min_order"]) else float(t["small"])
            bonus = n * per
            d_m2, d_r2 = extra_pay(n * avg)
            dt2 = delta_total(bonus + d_m2 + d_r2)
            parts = [{"label": f"бонус «тест → основне»: {n} × {_fmt(per)} ₴", "amount": rnd(bonus)}]
            if st:
                parts.append({"label": f"% з оплат цих основних ({n} × {_fmt(avg)} ₴)", "amount": rnd(d_m2 + d_r2)})
            scen.append({"code": "tests", "input": n, "avg_order": round(avg), "delta": rnd(dt2), "parts": parts,
                         "new_total": rnd(base["total"] + dt2),
                         "explain": (f"Якщо {n} клієнтів із тест-набором оплатять основне замовлення до строку "
                                     f"({t['fast_days']} днів) цього місяця: бонус {n} × {_fmt(per)} ₴"
                                     + (f" + ваш % з їхніх оплат (у середньому {_fmt(avg)} ₴ на замовлення)" if st else "")
                                     + f" = +{_fmt(rnd(dt2))} ₴.")})
        # 3. без знижки на відкритих угодах
        if st:
            deals = _open_discounts(u, pol)
            disc = float(sum(d["discount"] for d in deals))
            d_m3, d_r3 = extra_pay(disc, margin_add=disc) if disc else (0, 0)
            dt3 = delta_total(d_m3 + d_r3)
            scen.append({"code": "discount", "input": round(disc), "delta": rnd(dt3), "deals": deals[:5],
                         "n_deals": len(deals), "new_total": rnd(base["total"] + dt3),
                         "explain": (f"На {len(deals)} ваших відкритих угодах (за {OPEN_DAYS} днів) знижки {_fmt(disc)} ₴. Знижка зменшує лише маржу "
                                     f"(собівартість та сама), тож без неї ваш заробіток був би більшим на {_fmt(rnd(dt3))} ₴ — "
                                     "якщо ці угоди оплатять цього місяця." if deals else
                                     "На ваших відкритих основних угодах знижок немає — так тримати.")})
        return Response({"available": True, "period": period, "has_plan": has_plan, "can_margin": can_margin,
                         "rounded": False, "total": rnd(base["total"]), "scenarios": scen, "notes": notes,
                         "formula": "Та сама формула, що ЗП: engine.calc. Це прогноз; остаточна сума — у ЗП за місяць."})
