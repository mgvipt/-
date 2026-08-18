"""Бухгалтерские проводки: оплата сделки -> доход, отгрузка -> расход (себестоимость)."""
from .models import Account, Category, Transaction


def liqpay_account():
    """Рахунок «LiqPay еквайринг»: валовий дохід клієнта → сюди; комісія — звідси;
    зарахування банку = переказ LiqPay → ФОП. Баланс ≈ гроші «в дорозі»."""
    a = Account.objects.filter(name__icontains="liqpay").first()
    if a is None:
        a = Account.objects.create(name="LiqPay еквайринг", kind="bank")
    if not a.is_active:
        a.is_active = True
        a.save(update_fields=["is_active"])
    return a


def novapay_account():
    """Рахунок «НоваПей (накладені)»: дохід наложок (номінал) → сюди; комісія — звідси;
    виплата банку = переказ НоваПей → ФОП. Баланс ≈ наложки «в дорозі»."""
    a = Account.objects.filter(name__icontains="новапей").first()
    if a is None:
        a = Account.objects.create(name="НоваПей (накладені)", kind="bank")
    if not a.is_active:
        a.is_active = True
        a.save(update_fields=["is_active"])
    return a


def default_account():
    return (Account.objects.filter(is_active=True).first()
            or Account.objects.create(name="Каса", kind="cash"))


def _category(name, direction):
    return Category.objects.get_or_create(name=name, direction=direction)[0]


def _default_direction():
    """Напрямок для доходів зі сделок: продажі = «ДЕКОР_Товары(Оффл./Онлайн)» (НЕ Маркетинг)."""
    from .models import FinDirection
    return (FinDirection.objects.filter(active=True, name__icontains="ДЕКОР").first()
            or FinDirection.objects.filter(active=True).order_by("id").first())


def record_income(amount, *, deal=None, account=None, payment=None, category="Продаж товару", channel=None):
    """Єдина точка створення доходу. Народжується ОДРАЗУ повною:
    канал/контрагент/напрямок зі сделки → одразу видно в журналі, напрямках, P&L, ЗП.
    channel: явний канал (напр. «Салон» для готівки) — має пріоритет над deal.source."""
    ch = (channel or "").strip()
    counterparty = ""
    if deal is not None:
        if not ch:
            ch = (getattr(deal, "source", "") or "")[:24]
        c = getattr(deal, "contact", None)
        if c is not None:
            counterparty = (" ".join(filter(None, [getattr(c, "first_name", ""), getattr(c, "last_name", "")])).strip()
                            or getattr(c, "nickname", "") or "")[:160]
    from django.utils import timezone as _tz
    cat = _category(category, "in")
    # напрямок: звʼязка категорія→напрямок з довідника має пріоритет над дефолтом
    fdir = (getattr(cat, "fin_direction", None) if cat else None) or _default_direction()
    return Transaction.objects.create(
        direction="in", amount=amount, amount_uah=amount, account=account or default_account(),
        category=cat, deal=deal, payment=payment, op_time=_tz.localtime().time(),
        channel=ch[:24], counterparty=counterparty, fin_direction=fdir,
        contact=(getattr(deal, "contact", None) if deal is not None else None))


def record_expense(amount, *, deal=None, account=None, category="Собівартість"):
    counterparty = ""
    if deal is not None:
        c = getattr(deal, "contact", None)
        if c is not None:
            counterparty = (" ".join(filter(None, [getattr(c, "first_name", ""), getattr(c, "last_name", "")])).strip() or "")[:160]
    from django.utils import timezone as _tz
    return Transaction.objects.create(
        direction="out", amount=amount, amount_uah=amount, account=account or default_account(),
        category=_category(category, "out"), deal=deal, counterparty=counterparty,
        op_time=_tz.localtime().time(),
        contact=(getattr(deal, "contact", None) if deal is not None else None))


# ── Финмодель: P&L (ATM) + точка безубыточности ──────────────────────────
from datetime import date as _date
from django.db.models import Sum as _Sum


def _fin_articles():
    from .models import FinModelArticle
    # лише верхній рівень: підфонди — це під-розподіл конвертів, не коефіцієнти P&L
    return list(FinModelArticle.objects.filter(active=True, parent__isnull=True))


def _revenue(d_from, d_to):
    """Выручка = реальні доходи-транзакції (direction=in) за період у гривні.
    Перекази (transfer) НЕ враховуються. Угоди = УНІКАЛЬНІ deal_id (не транзакції):
    передоплата+доплата по одній угоді = 1 угода."""
    from .models import Transaction
    qs = Transaction.objects.filter(direction="in",
                                    date__gte=d_from, date__lte=d_to)
    rev = float(qs.aggregate(s=_Sum("amount_uah"))["s"] or 0)
    with_deal = qs.exclude(deal__isnull=True).values("deal_id").distinct().count()
    no_deal = qs.filter(deal__isnull=True).count()
    return rev, with_deal + no_deal


def _margin_pct(arts):
    """ЄДИНА формула маржинальності (ATM): 100 − Σ(фонди виручки %) − Σ(комісії %).
    Використовується у P&L, ТБ і Каналах — щоб не розходились."""
    rev_fund = sum(float(a.value) for a in arts if a.category == "revenue_fund")
    pay = sum(float(a.value) for a in arts if a.category == "payment_fee" and a.value_type == "percent")
    return max(0.0, 100.0 - rev_fund - pay)


def compute_pnl(d_from, d_to):
    """P&L по структуре Cashflow: Виручка − Прямі(% з виручки + комісії% + AI/угода)
    = Маржа − Операційні(постійні+змінні грн/міс за період) = Чистий прибуток."""
    arts = _fin_articles()
    revenue, deals = _revenue(d_from, d_to)
    days = (d_to - d_from).days + 1
    direct_pct_total = 100.0 - _margin_pct(arts)  # ЄДИНА формула з ТБ
    ai_per_deal = sum(float(a.value) for a in arts if a.category == "payment_fee" and a.value_type == "fixed_per_deal")
    direct = revenue * direct_pct_total / 100 + ai_per_deal * deals
    margin = revenue - direct
    # операційні: змінні + постійні + УПР(обидві) + СКД (₴/міс) — повний котел ATM
    operating = sum(float(a.value) for a in arts
                    if a.category in ("variable", "fixed", "upr_cat2", "upr_cat3", "skd") and a.value_type in ("fixed_sum_per_month", "auto_meta_ads")) * days / 30.0
    net = margin - operating
    return {
        "revenue": round(revenue), "deals": deals,
        "direct": round(direct), "direct_pct": round(direct_pct_total, 2),
        "ai_total": round(ai_per_deal * deals),
        "margin": round(margin), "margin_pct": round(margin / revenue * 100, 1) if revenue else round(_margin_pct(arts), 2),
        "operating": round(operating),
        "net": round(net), "net_pct": round(net / revenue * 100, 1) if revenue else 0,
    }


def compute_breakeven(d_from, d_to):
    """Точка безубыточности — формула 1:1 из Cashflow admin_router.breakeven:
    margin% = 100 − Σ(revenue_fund); monthly = Σ(variable+fixed грн/міс);
    fees = Σ(payment_fee грн/угода)×100; ТБ = monthly×(дні/30) / (margin%/100)."""
    arts = _fin_articles()
    revenue, deals = _revenue(d_from, d_to)
    margin_pct = _margin_pct(arts)  # та ж формула, що у P&L (ATM)
    # у ТБ входять: змінні + постійні + УПР обовʼязкові + СКД-мінімум (₴/міс). УПР відмовні (upr_cat3) — НІ.
    monthly_costs = sum(float(a.value) for a in arts
                        if a.category in ("variable", "fixed", "upr_cat2", "skd") and a.value_type in ("fixed_sum_per_month", "auto_meta_ads"))
    # ₴/угода × ФАКТИЧНІ угоди періоду, приведені до місяця (раніше був хардкод ×100)
    days_f = (d_to - d_from).days + 1
    deals_month = deals / days_f * 30.0 if days_f else 0
    per_deal_fees = sum(float(a.value) for a in arts
                        if a.category == "payment_fee" and a.value_type == "fixed_per_deal") * deals_month
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
        "rev_funds_pct": round(100.0 - margin_pct, 2),
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
    # ЗП рахуємо від РЕАЛЬНИХ грошей (рішення Олега 01.07): income-транзакції, привʼязані до
    # сделок ЦЬОГО менеджера, у гривні (amount_uah). Раніше брали Deal.amount(won) → розбіжність ×17.
    from .models import Transaction
    _inc = Transaction.objects.filter(direction="in", deal__owner=user, date__year=y, date__month=mo)
    rev = float(_inc.aggregate(s=_Sum("amount_uah"))["s"] or 0)
    deals = _inc.values("deal_id").distinct().count()
    avg_check = rev / deals if deals else 0
    # маржа періоду — від ФІНМОДЕЛІ (єдина _margin_pct), а не хардкод:
    # зміниш % фондів у фінмоделі → бонус менеджера перерахується
    margin_amt = rev * _margin_pct(_fin_articles()) / 100.0

    plan = ManagerPlan.objects.filter(user=user, period=period).first()
    target = float(plan.target_revenue) if plan and plan.target_revenue else None
    plan_pct = round(rev / target * 100, 1) if target else None
    mult = tier_multiplier(plan_pct)
    margin_kpi = margin_tier_pct(plan_pct, p)

    # --- табель робочого часу: пропорційний оклад + перевиконання ---
    from .models import WorkDay
    base_salary = p.get("salary_base", 4000)
    norm = int(p.get("salary_norm_days", 22)) or 22
    wd = WorkDay.objects.filter(user=user, date__year=y, date__month=mo)
    has_ts = wd.exists()
    worked = wd.filter(status__in=["worked", "overtime"]).count()
    overtime_days = wd.filter(status="overtime").count()
    daily_rate = base_salary / norm
    if has_ts:
        part_base = base_salary * min(worked, norm) / norm
        overtime_bonus = overtime_days * daily_rate
    else:
        part_base = base_salary
        worked = norm
        overtime_bonus = 0.0
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

    total = part_base + part_revenue + part_margin + bonus_kpi + overtime_bonus
    # ЗНИЖКИ менеджера за період (несогласовані знижки) — ТІЛЬКИ показуємо, ЗП НЕ зачіпаємо (рішення Олега).
    # Знижка по сделці = повна ціна (Σ price×qty) − фактична сума сделки.
    _disc_total = 0.0
    _disc_list = []
    _dids = list(_inc.values_list("deal_id", flat=True).distinct())
    if _dids:
        for _d in Deal.objects.filter(id__in=_dids).prefetch_related("items"):
            _full = 0.0
            for _i in _d.items.all():
                try:
                    _full += float(_i.price or 0) * float(_i.quantity or 0)
                except Exception:
                    pass
            _ds = _full - float(_d.amount or 0)
            if _ds > 0.5:
                _disc_total += _ds
                _disc_list.append({"deal": _d.id, "title": (_d.title or ("#%s" % _d.id))[:60], "discount": round(_ds)})
    _disc_list.sort(key=lambda x: -x["discount"])
    return {
        "user_id": user.id, "user_name": user.get_full_name() or user.username, "period": period,
        "revenue": round(rev), "deals": deals, "avg_check": round(avg_check),
        "plan_target": round(target) if target else None, "plan_pct": plan_pct,
        "tier_mult": mult, "margin_kpi_pct": margin_kpi,
        "part_base": round(part_base), "part_revenue": round(part_revenue), "part_margin": round(part_margin),
        "worked_days": worked, "norm_days": norm, "overtime_days": overtime_days, "overtime_bonus": round(overtime_bonus),
        "kpi": kpi, "kpi_hits": kpi_hits, "kpi_premium": premium, "bonus_kpi": round(bonus_kpi),
        "total": round(total),
        "discount_total": round(_disc_total), "discount_deals": len(_disc_list), "discount_list": _disc_list[:50],
        "min_revenue": round(float(plan.min_revenue)) if plan else None,
        "ambition_revenue": round(float(plan.ambition_revenue)) if plan else None,
    }


def canonical_counterparty(name):
    """Одна сутність — одне написання. Нормалізує пробіли/телефони і шукає
    вже наявне написання (без урахування регістру), щоб не плодити дублі."""
    import re
    from .models import Transaction
    s = " ".join((name or "").split())
    if not s:
        return s
    digits = re.sub(r"\D", "", s)
    if re.fullmatch(r"\+?380\d{9}", s.replace(" ", "")) or (digits.startswith("380") and len(digits) == 12 and len(s) <= 14):
        return "+" + digits
    ex = (Transaction.objects.exclude(counterparty="")
          .filter(counterparty__iexact=s).values_list("counterparty", flat=True).first())
    return ex or s


def internal_contact_for_direction(fd):
    """Внутрішній контрагент підрозділу (напрямку) — створюється і привʼязується при першій потребі."""
    if not fd:
        return None
    if getattr(fd, "internal_contact_id", None):
        return fd.internal_contact
    from apps.crm.models import Contact
    c = Contact.objects.create(first_name=((fd.name or "Підрозділ")[:120] + " · підрозділ"))
    fd.internal_contact = c
    fd.save(update_fields=["internal_contact"])
    return c


def sync_internal_debts(tx):
    """Перегенерувати внутрішні борги між підрозділами з розподілу (splits) операції.
    Борг виникає, коли частка НЕ платника сплачена з каси платника (payer_direction).
    Борг = PlannedPayment(is_internal): у боржника — кредиторка, у платника — дебіторка (через counterparty_contact)."""
    from .models import PlannedPayment
    PlannedPayment.objects.filter(source_transaction=tx, is_internal=True).delete()
    payer = getattr(tx, "payer_direction", None)
    if not payer or getattr(tx, "direction", "") == "transfer":
        return
    payer_c = internal_contact_for_direction(payer)
    pname = (" ".join(filter(None, [payer_c.first_name or "", payer_c.last_name or ""])).strip() if payer_c else "")[:160]
    for sp in tx.splits.all():
        if not sp.fin_direction_id or sp.fin_direction_id == payer.id:
            continue
        if not sp.amount or sp.amount <= 0:
            continue
        debtor_c = internal_contact_for_direction(sp.fin_direction)
        PlannedPayment.objects.create(
            kind="payable", amount=sp.amount, due_date=(tx.date or __import__("datetime").date.today()),
            contact=debtor_c, counterparty=pname, counterparty_contact=payer_c,
            fin_direction=sp.fin_direction, category=sp.category,
            is_internal=True, source_transaction=tx, status="planned",
        )
