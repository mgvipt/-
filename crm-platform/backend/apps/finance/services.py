"""Бухгалтерские проводки: оплата сделки -> доход, отгрузка -> расход (себестоимость)."""
from .models import Account, Category, Transaction


def default_account():
    return (Account.objects.filter(is_active=True).first()
            or Account.objects.create(name="Каса", kind="cash"))


def _category(name, direction):
    return Category.objects.get_or_create(name=name, direction=direction)[0]


def record_income(amount, *, deal=None, account=None, payment=None, category="Продаж товару"):
    return Transaction.objects.create(
        direction="in", amount=amount, account=account or default_account(),
        category=_category(category, "in"), deal=deal, payment=payment)


def record_expense(amount, *, deal=None, account=None, category="Собівартість"):
    return Transaction.objects.create(
        direction="out", amount=amount, account=account or default_account(),
        category=_category(category, "out"), deal=deal)


# ── Финмодель: P&L (ATM) + точка безубыточности ──────────────────────────
from datetime import date as _date
from django.db.models import Sum as _Sum


def _fin_articles():
    from .models import FinModelArticle
    # лише верхній рівень: підфонди — це під-розподіл конвертів, не коефіцієнти P&L
    return list(FinModelArticle.objects.filter(active=True, parent__isnull=True))


def _revenue(d_from, d_to):
    """Выручка = реальні доходи-транзакції (direction=in) за період у гривні.
    Перекази (transfer) НЕ враховуються. Дані перенесені з ФінМапа."""
    from .models import Transaction
    qs = Transaction.objects.filter(direction="in",
                                    created_at__date__gte=d_from, created_at__date__lte=d_to)
    rev = float(qs.aggregate(s=_Sum("amount_uah"))["s"] or 0)
    return rev, qs.count()


def compute_pnl(d_from, d_to):
    """P&L по структуре Cashflow: Виручка − Прямі(% з виручки + комісії% + AI/угода)
    = Маржа − Операційні(постійні+змінні грн/міс за період) = Чистий прибуток."""
    arts = _fin_articles()
    revenue, deals = _revenue(d_from, d_to)
    days = (d_to - d_from).days + 1
    rev_fund_pct = sum(float(a.value) for a in arts if a.category == "revenue_fund")
    pay_pct = sum(float(a.value) for a in arts if a.category == "payment_fee" and a.value_type == "percent")
    ai_per_deal = sum(float(a.value) for a in arts if a.category == "payment_fee" and a.value_type == "fixed_per_deal")
    direct = revenue * (rev_fund_pct + pay_pct) / 100 + ai_per_deal * deals
    margin = revenue - direct
    operating = sum(float(a.value) for a in arts
                    if a.category in ("variable", "fixed") and a.value_type == "fixed_sum_per_month") * days / 30.0
    net = margin - operating
    return {
        "revenue": round(revenue), "deals": deals,
        "direct": round(direct), "direct_pct": round(rev_fund_pct + pay_pct, 2),
        "ai_total": round(ai_per_deal * deals),
        "margin": round(margin), "margin_pct": round(margin / revenue * 100, 1) if revenue else round(100 - rev_fund_pct - pay_pct, 2),
        "operating": round(operating),
        "net": round(net), "net_pct": round(net / revenue * 100, 1) if revenue else 0,
    }


def compute_breakeven(d_from, d_to):
    """Точка безубыточности — формула 1:1 из Cashflow admin_router.breakeven:
    margin% = 100 − Σ(revenue_fund); monthly = Σ(variable+fixed грн/міс);
    fees = Σ(payment_fee грн/угода)×100; ТБ = monthly×(дні/30) / (margin%/100)."""
    arts = _fin_articles()
    revenue, deals = _revenue(d_from, d_to)
    rev_funds = sum(float(a.value) for a in arts if a.category == "revenue_fund")
    margin_pct = max(0.0, 100.0 - rev_funds)
    monthly_costs = sum(float(a.value) for a in arts
                        if a.category in ("variable", "fixed") and a.value_type == "fixed_sum_per_month")
    per_deal_fees = sum(float(a.value) for a in arts
                        if a.category == "payment_fee" and a.value_type == "fixed_per_deal") * 100
    total_monthly = monthly_costs + per_deal_fees
    days = (d_to - d_from).days + 1
    period_costs = total_monthly * days / 30.0
    breakeven = period_costs / (margin_pct / 100.0) if margin_pct > 0 else 0
    avg_check = revenue / deals if deals else 0
    today = _date.today()
    days_elapsed = max(1, (min(today, d_to) - d_from).days + 1)
    days_left = max(0, (d_to - today).days)
    daily_pace = revenue / days_elapsed
    projected = daily_pace * days
    required_daily = max(0, (breakeven - revenue) / days_left) if days_left else 0
    return {
        "breakeven": round(breakeven), "margin_pct": round(margin_pct, 2),
        "revenue": round(revenue), "monthly_costs": round(total_monthly),
        "period_costs": round(period_costs),
        "progress": round(revenue / breakeven * 100, 1) if breakeven else 0,
        "avg_check": round(avg_check), "deals": deals,
        "tb_deals": round(breakeven / avg_check, 1) if avg_check else 0,
        "daily_pace": round(daily_pace), "projected": round(projected),
        "required_daily": round(required_daily), "days_left": days_left,
        "days_elapsed": days_elapsed, "days_total": days,
        "rev_funds_pct": round(rev_funds, 2),
        "projected_progress": round(projected / breakeven * 100, 1) if breakeven else 0,
        "to_breakeven": round(max(0, breakeven - revenue)),
    }


def compute_channels(d_from, d_to):
    """Доход по каналах (Deal.source): виручка/угод/сер.чек/маржа/spend/ROAS/частка."""
    from apps.crm.models import Deal, Lead
    from .models import ChannelSpend
    from django.db.models import Sum, Count
    arts = _fin_articles()
    margin_pct = max(0.0, 100.0 - sum(float(a.value) for a in arts if a.category == "revenue_fund"))
    won = Deal.objects.filter(stage__is_won=True,
                              created_at__date__gte=d_from, created_at__date__lte=d_to)
    rows = list(won.values("source").annotate(revenue=Sum("amount"), deals=Count("id")).order_by("-revenue"))
    total = sum(float(r["revenue"] or 0) for r in rows) or 1
    period = d_from.strftime("%Y-%m")
    spend_map = {c.channel: float(c.spend) for c in ChannelSpend.objects.filter(period=period)}
    labels = dict(Lead.SOURCES)
    out = []
    for r in rows:
        rev = float(r["revenue"] or 0)
        n = r["deals"]
        spend = spend_map.get(r["source"], 0)
        margin = rev * margin_pct / 100
        out.append({
            "source": r["source"], "label": labels.get(r["source"], r["source"]),
            "revenue": round(rev), "deals": n,
            "avg_check": round(rev / n) if n else 0,
            "spend": round(spend), "roas": round(rev / spend, 1) if spend else None,
            "margin": round(margin), "net": round(margin - spend),
            "share": round(rev / total * 100, 1),
        })
    return {"rows": out, "margin_pct": round(margin_pct, 2), "total_revenue": round(total if rows else 0)}


# ============================================================================
#  ЗП / KPI МЕНЕДЖЕРІВ — рушій на базі редагованих ставок (стратегія РОП+психолог)
#  Параметри-ставки живуть у FinModelArticle (category="salary", по code) —
#  власник міняє їх у Фінмоделі → бонус у картці сделки та ЗП оновлюються синхронно.
# ============================================================================

SALARY_DEFAULTS = {
    "salary_base": 4000, "salary_revenue_pct": 3, "salary_margin_pct": 14,
    "salary_kpi_premium": 1300, "salary_zero_error": 200,
    "kpi_avg_check": 3500, "kpi_test_kits": 40, "kpi_conv_lt": 10, "kpi_conv_tm": 30,
}


def salary_params():
    """Ставки ЗП/KPI з FinModelArticle (code). Якщо немає — дефолти стратегії."""
    from .models import FinModelArticle
    p = dict(SALARY_DEFAULTS)
    for a in FinModelArticle.objects.filter(category="salary"):
        if a.code:
            p[a.code] = float(a.value)
    return p


def tier_multiplier(plan_pct):
    """Тірований множник премій замість жорсткого GATE «100% або 0»."""
    if plan_pct is None:
        return 0.0
    if plan_pct < 70:  return 0.3
    if plan_pct < 90:  return 0.5
    if plan_pct < 100: return 0.8
    if plan_pct < 120: return 1.0
    return 1.3


def margin_tier_pct(plan_pct, p):
    base = p.get("salary_margin_pct", 14)
    if plan_pct is None or plan_pct < 100: return base
    if plan_pct < 120: return base + 2
    if plan_pct < 150: return base + 4
    return base + 6


def deal_manager_bonus(amount, margin):
    """Скільки менеджер заробляє з ОДНІЄЇ угоди (для картки сделки). Синхронно зі ставками."""
    p = salary_params()
    rev_pct = p.get("salary_revenue_pct", 3)
    mar_pct = p.get("salary_margin_pct", 14)
    from_rev = float(amount) * rev_pct / 100
    from_mar = float(margin or 0) * mar_pct / 100
    return {
        "total": round(from_rev + from_mar, 2),
        "from_revenue": round(from_rev, 2), "from_margin": round(from_mar, 2),
        "revenue_pct": rev_pct, "margin_pct": mar_pct,
    }


def compute_manager_salary(user, period):
    """Повна ЗП менеджера за місяць (period=YYYY-MM) за стратегією РОП+психолог."""
    from apps.crm.models import Deal
    from .models import ManagerPlan
    p = salary_params()
    y, mo = int(period[:4]), int(period[5:7])
    won = Deal.objects.filter(owner=user, stage__is_won=True, created_at__year=y, created_at__month=mo)
    rev = float(won.aggregate(s=_Sum("amount"))["s"] or 0)
    deals = won.count()
    avg_check = rev / deals if deals else 0
    # маржа período — приблизно через ставку маржі компанії (38.22% валова)
    margin_amt = rev * 0.3822

    plan = ManagerPlan.objects.filter(user=user, period=period).first()
    target = float(plan.target_revenue) if plan and plan.target_revenue else None
    plan_pct = round(rev / target * 100, 1) if target else None
    mult = tier_multiplier(plan_pct)
    margin_kpi = margin_tier_pct(plan_pct, p)

    part_base = p.get("salary_base", 4000)
    part_revenue = rev * p.get("salary_revenue_pct", 3) / 100
    part_margin = margin_amt * margin_kpi / 100

    # 5 KPI (кожна незалежно × mult). Конверсії поки немає даних → NA (не в оплату).
    kpi = []
    kpi.append({"name": "Виконання плану", "ok": plan_pct is not None and plan_pct >= 100, "na": plan_pct is None,
                "detail": (f"{plan_pct}% / 100%" if plan_pct is not None else "план не встановлено")})
    kpi.append({"name": "Середній чек", "ok": avg_check >= p.get("kpi_avg_check", 3500), "na": deals == 0,
                "detail": f"{round(avg_check)} / {round(p.get('kpi_avg_check',3500))} ₴"})
    kpi.append({"name": "Конв. Лід→Пробник", "ok": False, "na": True, "detail": "дані конверсій ще не підключені"})
    kpi.append({"name": "Конв. Пробник→Осн", "ok": False, "na": True, "detail": "дані конверсій ще не підключені"})
    kpi.append({"name": "К-сть пробників", "ok": False, "na": True, "detail": f"ціль {round(p.get('kpi_test_kits',40))}/міс"})
    premium = p.get("salary_kpi_premium", 1300)
    kpi_hits = sum(1 for k in kpi if k["ok"])
    bonus_kpi = kpi_hits * premium * mult

    total = part_base + part_revenue + part_margin + bonus_kpi
    return {
        "user_id": user.id, "user_name": user.get_full_name() or user.username, "period": period,
        "revenue": round(rev), "deals": deals, "avg_check": round(avg_check),
        "plan_target": round(target) if target else None, "plan_pct": plan_pct,
        "tier_mult": mult, "margin_kpi_pct": margin_kpi,
        "part_base": round(part_base), "part_revenue": round(part_revenue), "part_margin": round(part_margin),
        "kpi": kpi, "kpi_hits": kpi_hits, "kpi_premium": premium, "bonus_kpi": round(bonus_kpi),
        "total": round(total),
        "min_revenue": round(float(plan.min_revenue)) if plan else None,
        "ambition_revenue": round(float(plan.ambition_revenue)) if plan else None,
    }
