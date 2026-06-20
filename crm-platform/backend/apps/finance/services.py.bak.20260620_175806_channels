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
