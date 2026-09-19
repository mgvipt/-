"""ОДНЕ джерело «отриманих грошей» для всіх звітів CRM (19.09.2026, Олег: «при аналізі статистики
перевіряй, щоб дані брались з одного джерела всюди, де вони використовуються»).

До цього різні екрани рахували «виручку» по-різному:
  • Аналітика / Воронка / Канали — суму сделок на стадії «Успішна угода» (а не отримані гроші;
    оплачені сделки «в роботі» туди не потрапляли, «Топ менеджерів» узагалі сумував і програні);
  • Маркетинг — оплати сделки за датою натискання «оплачено»;
  • Фінанси — усі приходи журналу, навіть без сделки;
  • ЗП (payroll) — приходи журналу по сделках мінус повернення.

Правило (як у ЗП — «гроші, що лишились у компанії»):
  гроші сделки = приходи фінансового журналу, привʼязані до сделки (не перекази між рахунками),
                 за ДАТОЮ ПРИХОДУ, мінус повернення клієнтам по цій сделці.
Визначення приходів і повернень — ті самі функції, що рахують ЗП (apps.payroll.engine._income/_refunds),
тому будь-яка зміна правила одразу діє і на ЗП, і на звіти.
"""
from datetime import date, timedelta

# Перший прихід по сделці у фінансовому журналі. Раніше журналу продажів не було (архів Бітрікс) —
# там єдине, що є, це суми успішних сделок. Тому для періодів ДО цієї дати виручка = суми успішних
# сделок, ПІСЛЯ — гроші з журналу. Одна функція revenue_by_deal() для всіх звітів.
JOURNAL_SINCE = date(2026, 5, 5)


def _range(d1, d2):
    return d1 or date(2000, 1, 1), d2 or date(2100, 1, 1)


def deal_money(d1=None, d2=None, deal_ids=None):
    """{deal_id: гроші сделки} за період (прихід − повернення). deal_ids=None — усі сделки."""
    from apps.payroll.engine import _income, _refunds
    a, b = _range(d1, d2)
    flt = {"deal__isnull": False}
    if deal_ids is not None:
        if isinstance(deal_ids, (list, tuple, set)) and not deal_ids:
            return {}
        flt["deal_id__in"] = list(deal_ids) if isinstance(deal_ids, (set, tuple)) else deal_ids
    out = {}
    for did, amt in _income(a, b, **flt).values_list("deal_id", "amount_uah"):
        out[did] = out.get(did, 0.0) + float(amt or 0)
    rflt = dict(flt)
    rflt.pop("deal__isnull", None)
    for did, amt in _refunds(a, b, **rflt).values_list("deal_id", "amount_uah"):
        out[did] = out.get(did, 0.0) - float(amt or 0)
    return out


def paid_deal_ids(money, eps=0.5):
    """Сделки, по яких гроші реально лишились у компанії (> 0)."""
    return {k for k, v in money.items() if v > eps}


def revenue_by_deal(d1=None, d2=None, deal_ids=None):
    """ЄДИНЕ правило виручки сделок за період (для Аналітики, Каналів, Маркетингу, Воронок):
      • з JOURNAL_SINCE — гроші журналу по сделці за датою приходу, мінус повернення (як ЗП);
      • до JOURNAL_SINCE — сума успішної сделки за датою закриття (архів Бітрікс, журналу тоді не було).
    Повертає {deal_id: гроші}."""
    from django.db.models import Q
    from apps.crm.models import Deal
    a, b = _range(d1, d2)
    out = deal_money(max(a, JOURNAL_SINCE), b, deal_ids) if b >= JOURNAL_SINCE else {}
    if a < JOURNAL_SINCE:
        lb = min(b, JOURNAL_SINCE - timedelta(days=1))
        qs = Deal.objects.filter(stage__is_won=True).filter(
            Q(closed_at__date__gte=a, closed_at__date__lte=lb) |
            Q(closed_at__isnull=True, created_at__date__gte=a, created_at__date__lte=lb))
        if deal_ids is not None:
            qs = qs.filter(id__in=list(deal_ids) if isinstance(deal_ids, (set, tuple)) else deal_ids)
        for did, amt in qs.values_list("id", "amount"):
            if did not in out:
                out[did] = float(amt or 0)
    return out


NOTE = ("Виручка = отримані гроші з фінансового журналу (з 05.05.2026, мінус повернення, за датою приходу); "
        "раніше — суми успішних сделок (архів Бітрікс).")
