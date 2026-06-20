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
    return list(FinModelArticle.objects.filter(active=True))


def _revenue(d_from, d_to):
    """Выручка = сумма выигранных (won) сделок за период по created_at."""
    from apps.crm.models import Deal
    won = Deal.objects.filter(stage__is_won=True,
                              created_at__date__gte=d_from, created_at__date__lte=d_to)
    return float(won.aggregate(s=_Sum("amount"))["s"] or 0), won.count()


def compute_pnl(d_from, d_to):
    arts = _fin_articles()
    revenue, deals = _revenue(d_from, d_to)
    direct_pct = sum(float(a.value) for a in arts if a.category == "revenue_fund" and a.value_type == "percent")
    direct = revenue * direct_pct / 100
    margin = revenue - direct
    var_pct = sum(float(a.value) for a in arts if a.category == "variable" and a.value_type == "percent")
    variable = margin * var_pct / 100
    skd = margin - variable
    days = (d_to - d_from).days + 1
    upr_month = sum(float(a.value) for a in arts if a.value_type == "fixed_sum_per_month")
    upr = upr_month * days / 30.0
    net = skd - upr
    return {
        "revenue": round(revenue), "deals": deals,
        "direct": round(direct), "direct_pct": round(direct_pct, 2),
        "margin": round(margin), "margin_pct": round(100 - direct_pct, 2),
        "variable": round(variable), "variable_pct": round(var_pct, 2),
        "skd": round(skd), "upr": round(upr), "net": round(net),
        "net_pct": round(net / revenue * 100, 1) if revenue else 0,
    }


def compute_breakeven(d_from, d_to):
    arts = _fin_articles()
    revenue, deals = _revenue(d_from, d_to)
    rf_pct = sum(float(a.value) for a in arts if a.category == "revenue_fund" and a.value_type == "percent")
    margin_pct = max(1.0, 100 - rf_pct)
    fixed_month = sum(float(a.value) for a in arts if a.value_type == "fixed_sum_per_month")
    fee_deal = sum(float(a.value) for a in arts if a.value_type == "fixed_per_deal")
    deals_month = next((float(a.value) for a in arts if a.category == "config" and "угод" in a.name.lower()), 100)
    days = (d_to - d_from).days + 1
    period_costs = (fixed_month + fee_deal * deals_month) * days / 30.0
    breakeven = period_costs / (margin_pct / 100.0) if margin_pct else 0
    avg_check = revenue / deals if deals else 0
    today = _date.today()
    days_elapsed = max(1, (min(today, d_to) - d_from).days + 1)
    days_left = max(0, (d_to - today).days)
    daily_pace = revenue / days_elapsed
    projected = daily_pace * days
    required_daily = max(0, (breakeven - revenue) / days_left) if days_left else 0
    markup = next((float(a.value) for a in arts if a.category == "config" and "націнк" in a.name.lower()), 30)
    return {
        "breakeven": round(breakeven), "margin_pct": round(margin_pct, 2),
        "revenue": round(revenue), "period_costs": round(period_costs),
        "progress": round(revenue / breakeven * 100, 1) if breakeven else 0,
        "avg_check": round(avg_check), "deals": deals,
        "tb_deals": round(breakeven / avg_check, 1) if avg_check else 0,
        "daily_pace": round(daily_pace), "projected": round(projected),
        "required_daily": round(required_daily), "days_left": days_left,
        "company_target": round(breakeven * (1 + markup / 100)),
    }
