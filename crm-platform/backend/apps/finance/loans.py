# -*- coding: utf-8 -*-
"""Кредити і позики: нарахування відсотків за правилом кожного кредитора.

У кожного кредитора свій період (місяць / день / рік) і свій день нарахування.
Приводимо все до одного: скільки набігло з останнього нарахування по сьогодні.
Валютний борг тримаємо у валюті, а гривневий еквівалент рахуємо за курсом НБУ —
щоб цифра в гривні не застарівала разом із курсом.
"""
import json
import urllib.request
from datetime import date, timedelta
from decimal import Decimal as D

from django.db import transaction as db_tx
from django.utils import timezone

from .models import Loan, LoanEntry, PlannedPayment

NBU = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode={}&json"
_rate_cache = {}


def fx_rate(ccy: str, on: date = None) -> D:
    """Курс НБУ: скільки гривень за 1 одиницю валюти. UAH = 1."""
    ccy = (ccy or "UAH").upper()
    if ccy == "UAH":
        return D("1")
    key = (ccy, on.isoformat() if on else "today")
    if key in _rate_cache:
        return _rate_cache[key]
    url = NBU.format(ccy)
    if on:
        url += "&date=" + on.strftime("%Y%m%d")
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            rows = json.load(r)
        rate = D(str(rows[0]["rate"])) if rows else D("0")
    except Exception:
        rate = D("0")
    if rate > 0:
        _rate_cache[key] = rate
    return rate


def _months_due(loan: Loan, today: date):
    """Дати місячних нарахувань, які ще не зробили (день = accrual_day)."""
    out = []
    start = loan.last_accrual or loan.started_at
    d = start
    day = max(1, min(28, int(loan.accrual_day or 1)))
    # наступна дата нарахування після start
    y, m = d.year, d.month
    while True:
        m += 1
        if m > 12:
            m = 1
            y += 1
        nxt = date(y, m, day)
        if nxt > today:
            break
        if nxt > start:
            out.append(nxt)
        if len(out) > 240:      # запобіжник від нескінченного циклу
            break
    return out


def accrue(loan: Loan, today: date = None, dry: bool = False):
    """Нарахувати відсотки, яких бракує. Повертає список створених рухів."""
    today = today or timezone.localdate()
    made = []
    if not loan.is_active or loan.rate_period == "none" or (loan.rate_pct or 0) <= 0:
        return made

    if loan.rate_period == "day":
        start = loan.last_accrual or loan.started_at
        days = (today - start).days
        if days <= 0:
            return made
        bal = D(loan.balance or 0)
        total = D("0")
        daily = D(str(loan.rate_pct)) / D("100")
        for _ in range(days):
            add = (bal * daily).quantize(D("0.01"))
            total += add
            if loan.capitalize:
                bal += add
        if total <= 0:
            return made
        made.append(_entry(loan, "accrual", today, total, bal if loan.capitalize else D(loan.balance) ,
                           "Відсотки за %s дн. (%s%%/день)" % (days, loan.rate_pct), dry))
        if not dry:
            loan.balance = bal if loan.capitalize else loan.balance
            loan.last_accrual = today
            loan.save(update_fields=["balance", "last_accrual"])
        return made

    # місячна і річна ставка — нараховуємо по датах
    monthly = loan.monthly_rate() / D("100")
    for d in _months_due(loan, today):
        bal = D(loan.balance or 0)
        add = (bal * monthly).quantize(D("0.01"))
        if add <= 0:
            continue
        new_bal = bal + add if loan.capitalize else bal
        made.append(_entry(loan, "accrual", d, add, new_bal,
                           "Відсотки за місяць (%s%%)" % loan.monthly_rate().normalize(), dry))
        if not dry:
            loan.balance = new_bal
            loan.last_accrual = d
            loan.save(update_fields=["balance", "last_accrual"])
    return made


def _entry(loan, kind, d, amount, balance_after, comment, dry=False):
    rate = fx_rate(loan.currency, None)
    row = dict(loan=loan, kind=kind, date=d, amount=amount, rate_uah=rate or D("1"),
               amount_uah=(amount * (rate or D("1"))).quantize(D("0.01")),
               balance_after=balance_after, comment=comment[:255])
    if dry:
        return row
    return LoanEntry.objects.create(**row)


@db_tx.atomic
def pay(loan: Loan, amount_uah: D, on: date = None, comment: str = "", tx=None):
    """Платіж по кредиту: зменшує тіло. amount_uah — скільки реально заплатили гривень."""
    on = on or timezone.localdate()
    rate = fx_rate(loan.currency, None) or D("1")
    in_ccy = (D(amount_uah) / rate).quantize(D("0.01"))
    loan.balance = (D(loan.balance or 0) - in_ccy).quantize(D("0.01"))
    loan.save(update_fields=["balance"])
    e = LoanEntry.objects.create(loan=loan, kind="payment", date=on, amount=-in_ccy,
                                 rate_uah=rate, amount_uah=-D(amount_uah),
                                 balance_after=loan.balance, comment=comment[:255], transaction=tx)
    sync_planned(loan)
    return e


def sync_planned(loan: Loan):
    """Оновити дзеркало в Дт/Кт, щоб борг був видно там, де решта кредиторки."""
    pp = loan.planned_payment
    uah = balance_uah(loan)
    if pp is None:
        if not loan.is_active or uah <= 0:
            return None
        pp = PlannedPayment.objects.create(
            kind="payable", amount=uah, due_date=timezone.localdate(), status="planned",
            counterparty=(loan.creditor and str(loan.creditor)) or loan.name,
            counterparty_contact=loan.creditor, contact=loan.creditor, is_loan=True,
            comment=("%s · %s" % (loan.name, loan.comment or ""))[:255])
        loan.planned_payment = pp
        loan.save(update_fields=["planned_payment"])
        return pp
    pp.amount = uah
    pp.status = "planned" if (loan.is_active and uah > 0) else "paid"
    pp.save(update_fields=["amount", "status"])
    return pp


def balance_uah(loan: Loan) -> D:
    rate = fx_rate(loan.currency, None) or D("1")
    return (D(loan.balance or 0) * rate).quantize(D("0.01"))


def summary():
    """Зведення по всіх активних кредитах — для сторінки «Кредити»."""
    rows = []
    for ln in Loan.objects.filter(is_active=True).select_related("creditor"):
        uah = balance_uah(ln)
        mr = ln.monthly_rate()
        per_month = (D(ln.balance or 0) * mr / D("100")).quantize(D("0.01"))
        rows.append(dict(
            id=ln.id, name=ln.name, creditor=str(ln.creditor) if ln.creditor else "",
            creditor_id=ln.creditor_id, currency=ln.currency,
            balance=float(ln.balance or 0), balance_uah=float(uah),
            rate_pct=float(ln.rate_pct or 0), rate_period=ln.rate_period,
            monthly_rate=float(mr), yearly_rate=float(ln.yearly_rate()),
            interest_month=float(per_month),
            interest_month_uah=float((per_month * (fx_rate(ln.currency) or D("1"))).quantize(D("0.01"))),
            interest_year_uah=float((uah * ln.yearly_rate() / D("100")).quantize(D("0.01"))),
            last_accrual=ln.last_accrual, capitalize=ln.capitalize,
        ))
    rows.sort(key=lambda r: -r["yearly_rate"])      # найдорожчий — зверху
    tot_uah = sum(r["balance_uah"] for r in rows)
    tot_m = sum(r["interest_month_uah"] for r in rows)
    return dict(loans=rows, total_uah=round(tot_uah, 2), interest_month_uah=round(tot_m, 2),
                interest_year_uah=round(sum(r["interest_year_uah"] for r in rows), 2))


PAY_CATEGORIES = ("Кредиты — возврат тела", "Погашение кредита")
ACCRUAL_MARK = "Нарахування % за користування кредитним"
INTEREST_MARK = "Погашення вiдсоткiв за користування"


def pull_payments(loan: Loan, since: date = None, dry: bool = False):
    """Підтягнути з журналу платежі, які стосуються цього кредиту.

    Беремо витрати у «кредитних» категоріях, де контрагент — наш кредитор.
    Кожну операцію записуємо один раз: привʼязка через LoanEntry.transaction.
    01.10.2026 (Олег): «у кредитах немає сум, які я оплатив і провів останні».
    """
    from .models import Category, Transaction
    if not loan.creditor_id:
        return []
    cats = list(Category.objects.filter(name__in=PAY_CATEGORIES).values_list("id", flat=True))
    if not cats:
        return []
    qs = Transaction.objects.filter(direction="out", category_id__in=cats).exclude(
        id__in=LoanEntry.objects.filter(loan=loan).exclude(transaction=None).values_list("transaction_id", flat=True))
    since = since or loan.pull_from
    if since:
        qs = qs.filter(date__gte=since)
    # відсотки — це НЕ погашення тіла: їх підтягує pull_interest
    qs = qs.exclude(comment__icontains=ACCRUAL_MARK).exclude(comment__icontains=INTEREST_MARK)
    if loan.account_id:
        # у банку кілька кредитів на одного кредитора — розрізняємо за рахунком
        qs = qs.filter(account_id=loan.account_id)
    else:
        name = (str(loan.creditor) or "").strip()
        parts = [w for w in name.replace(",", " ").split() if len(w) > 3]
        from django.db.models import Q
        cond = Q(contact_id=loan.creditor_id)
        for w in parts:
            cond |= Q(counterparty__icontains=w)
        qs = qs.filter(cond)
    qs = qs.order_by("date", "id")

    made = []
    for t in qs:
        rate = fx_rate(loan.currency, None) or D("1")
        amt = (D(t.amount_uah or 0) / rate).quantize(D("0.01"))
        if amt <= 0:
            continue
        if dry:
            made.append(dict(date=t.date, amount=amt, uah=t.amount_uah, tx=t.id))
            continue
        loan.balance = (D(loan.balance or 0) - amt).quantize(D("0.01"))
        made.append(LoanEntry.objects.create(
            loan=loan, kind="payment", date=t.date, amount=-amt, rate_uah=rate,
            amount_uah=-D(t.amount_uah or 0), balance_after=loan.balance, transaction=t,
            comment=("Платіж %s ₴ з журналу%s" % (int(t.amount_uah or 0),
                     (" · " + t.comment[:60]) if t.comment else ""))[:255]))
    if made and not dry:
        loan.save(update_fields=["balance"])
        sync_planned(loan)
    return made


def pull_interest(loan: Loan, dry: bool = False):
    """Для кредитного ліміту: підтягнути з журналу нарахування і сплату відсотків.

    На ліміті відсотки списують окремим платежем, а тіло лишається тим самим —
    тому ці рухи тіло НЕ змінюють, вони лише показують, у що обходиться кредит.
    01.10.2026 (Олег): «перевір по журналу всі рухи і додай, щоб дзеркально
    відображалось в аналітиці».
    """
    from .models import Transaction
    done = set(LoanEntry.objects.filter(loan=loan).exclude(transaction=None)
               .values_list("transaction_id", flat=True))
    rows = []
    for mark, kind, sign, label in ((ACCRUAL_MARK, "accrual", 1, "Нараховано відсотки"),
                                    (INTEREST_MARK, "interest", -1, "Сплачено відсотки")):
        q = Transaction.objects.filter(comment__icontains=mark)
        if loan.pull_from:
            q = q.filter(date__gte=loan.pull_from)
        for t in q.order_by("date", "id"):
            if t.id in done:
                continue
            rows.append((kind, t, D(sign) * D(t.amount_uah or 0), label))
    rows.sort(key=lambda r: (r[1].date, r[1].id))
    made = []
    for kind, t, amt, label in rows:
        if dry:
            made.append(dict(date=t.date, kind=kind, amount=amt))
            continue
        made.append(LoanEntry.objects.create(
            loan=loan, kind=kind, date=t.date, amount=amt, rate_uah=D("1"), amount_uah=amt,
            balance_after=loan.balance, transaction=t,
            comment=("%s · %s" % (label, (t.comment or "")[:60]))[:255]))
    return made
