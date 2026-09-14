"""Фонди Фінмоделі, звʼязані зі «Ставками співробітників» (fm-link, 14.09.2026).

Олег: «ставки впливають на точку беззбитковості, тому звісно треба у фонди їх»;
«деякі моменти в фінмодель щоб затягувались з того місця, де вони налаштовуються, а решта у фінмоделі».

Як працює:
- список звʼязаних фондів — PayPolicy(id=1).params["linked_funds"] (id статей Фінмоделі).
  За замовчуванням ПОРОЖНІЙ — нічого не звʼязано, доки власник сам не увімкне
  «Автоматично зі Ставок» у Фінанси → Точка беззбитковості (таблиця «Зарплати: у фонді і за ставками»);
- значення звʼязаного фонду = колонка «За ставками» тієї самої таблиці
  (engine.breakeven_atm()["fot"][…]["suggested"]) — рівно те число, яке Олег бачить на екрані;
- перерахунок: одразу при вмиканні звʼязку; після кожного створення / збереження / архівування ставки;
  раз на добу командою `payroll_sync_funds` (свіжий % продажників за квартал);
- пишемо ЛИШЕ якщо число змінилось, з історією PayRateLog(action="fund_sync", «авто зі Ставок»);
- у Фінмоделі звʼязане число лише для читання (API не дає змінити value — два місця не «бʼються»),
  назву, конверт, категорію статті можна міняти як раніше;
- помилка автоперерахунку НІКОЛИ не ламає збереження ставки (after_rates_change ловить усе й пише в лог).
"""
import logging
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

log = logging.getLogger(__name__)

POLICY_KEY = "linked_funds"
WHERE_RATES = "Налаштування → Ставки співробітників (автоматично)"
WHERE_HERE = "тут, у Фінмоделі"


def _can(u, code):
    return bool(u and u.is_authenticated and (u.is_superuser or (hasattr(u, "has_perm_code") and u.has_perm_code(code))))


def can_link(u):
    """Звʼязувати/розвʼязувати фонди — лише власник (як і кнопка «Підставити»)."""
    return _can(u, "payroll.rates.edit") and _can(u, "finance.model.edit")


def _clean_ids(raw):
    out = []
    for x in raw or []:
        try:
            i = int(x)
        except (TypeError, ValueError):
            continue
        if i > 0 and i not in out:
            out.append(i)
    return out


def linked_ids():
    """id статей Фінмоделі, які автоматично дорівнюють сумі за ставками. За замовчуванням — []."""
    from .models import PayPolicy
    p = PayPolicy.objects.filter(pk=1).first()
    return _clean_ids((p.params or {}).get(POLICY_KEY) if p else None)


def configured_in(a, linked=None):
    """Людський підпис «Де налаштовується» для статті Фінмоделі (одне правило для всіх екранів)."""
    if linked is None:
        linked = a.id in set(linked_ids())
    if linked:
        return WHERE_RATES
    if a.value_type == "auto_meta_ads":
        return "Автоматично з Meta Ads"
    if a.category == "warehouse_rate":
        return "Налаштування → Ставки співробітників → Склад — відрядно (ті самі ставки)"
    if a.category == "salary":
        return "застарілі ставки старої формули (не впливають на ЗП за ставками)"
    if a.category == "payment_fee" and a.value_type == "fixed_per_deal":
        return "тут, ₴ за угоду"
    return WHERE_HERE


def _q(v):
    return Decimal(str(v or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _fmt(v, unit):
    f = float(v)
    if unit == "%":
        return (f"{f:.2f}".rstrip("0").rstrip(".")) + "%"
    return f"{round(f):,}".replace(",", " ") + " ₴"


def fot_rows():
    """Рядки таблиці «Зарплати: у фонді і за ставками» — те саме, що бачить Олег (без змін у рушії)."""
    from . import engine
    return engine.breakeven_atm()["fot"]


def sync_linked(user=None, dry=False, only=None, rows=None):
    """Звʼязані фонди := «За ставками». Пише лише те, що змінилось. Повертає [{fund_id, name, unit, before, after}].
    dry=True — нічого не пише, лише показує. only — обмежити списком id (напр. щойно увімкнений фонд).
    Фонд без жодного рядка в таблиці (немає людей) або «не лише зарплати» (syncable=False) — не чіпаємо."""
    ids = linked_ids()
    if only is not None:
        keep = set(_clean_ids(only))
        ids = [i for i in ids if i in keep]
    if not ids:
        return []
    from apps.finance.models import FinModelArticle
    from .models import PayRateLog
    by_id = {r["fund_id"]: r for r in (rows if rows is not None else fot_rows())}
    who = user if (user is not None and getattr(user, "is_authenticated", False)) else None
    out = []
    for fid in ids:
        r = by_id.get(fid)
        if not r or not r.get("syncable"):
            continue
        after = _q(r.get("suggested"))
        unit = r.get("unit") or ""
        with transaction.atomic():
            qs = FinModelArticle.objects.filter(pk=fid)
            a = (qs if dry else qs.select_for_update()).first()
            if not a:
                continue
            before = _q(a.value)
            if before == after:
                continue
            if not dry:
                a.value = after
                a.save(update_fields=["value"])
                PayRateLog.objects.create(
                    action="fund_sync", user=who,
                    before={"fund": a.name, "value": float(before)}, after={"fund": a.name, "value": float(after)},
                    note=f"Фонд «{a.name}»: {_fmt(before, unit)} → {_fmt(after, unit)} (авто зі Ставок)"[:255])
            out.append({"fund_id": fid, "name": a.name, "unit": unit, "before": float(before), "after": float(after)})
    return out


def after_rates_change(user=None):
    """Хук після створення/збереження/архівування ставки. Ніколи не кидає помилку — збереження ставки важливіше."""
    try:
        if not linked_ids():
            return []
        with transaction.atomic():  # власна точка збереження: збій тут не зачепить інші записи
            return sync_linked(user=user)
    except Exception:
        log.exception("fund_link: автоперерахунок звʼязаних фондів після зміни ставок не вдався")
        return []


def set_linked(fund_id, on, user=None):
    """Увімкнути/вимкнути звʼязок фонду. Повертає (новий список id, чи змінилось)."""
    from .models import PayPolicy, PayRateLog
    fid = int(fund_id)
    with transaction.atomic():
        p, _ = PayPolicy.objects.select_for_update().get_or_create(pk=1)
        params = dict(p.params or {})
        old = _clean_ids(params.get(POLICY_KEY))
        new = sorted(set(old) | {fid}) if on else [i for i in old if i != fid]
        if new == old:
            return old, False
        params[POLICY_KEY] = new
        p.params = params
        who = user if (user is not None and getattr(user, "is_authenticated", False)) else None
        p.updated_by = who
        p.save()
        from apps.finance.models import FinModelArticle
        a = FinModelArticle.objects.filter(pk=fid).first()
        nm = a.name if a else f"#{fid}"
        PayRateLog.objects.create(action="fund_link", user=who, before={POLICY_KEY: old}, after={POLICY_KEY: new},
                                  note=(f"Фонд «{nm}»: автоматично зі Ставок — " + ("увімкнено" if on else "вимкнено"))[:255])
    return new, True


def _truthy(v):
    return str(v).strip().lower() in ("1", "true", "yes", "on", "так")


class FundLinksView(APIView):
    """GET /api/payroll/funds/links/ — які фонди звʼязані + прев'ю «у фонді / за ставками».
    POST {fund_id, linked: true|false} — увімкнути/вимкнути (лише власник). Увімкнення одразу підставляє суму
    і повертає було → стало. Вимкнення значення НЕ змінює — фонд знову редагується у Фінмоделі вручну."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _can(request.user, "payroll.rates.view"):
            return Response({"detail": "Немає доступу до ставок"}, status=403)
        ids = linked_ids()
        funds = []
        for r in fot_rows():
            funds.append({"fund_id": r["fund_id"], "name": r["name"], "unit": r["unit"], "value": r["value"],
                          "suggested": r["suggested"], "syncable": r["syncable"], "linked": r["fund_id"] in ids,
                          "would_change": abs(float(r["suggested"]) - float(r["value"])) >= (0.01 if r["unit"] == "%" else 1)})
        return Response({"linked": ids, "can_edit": can_link(request.user), "funds": funds})

    def post(self, request):
        if not can_link(request.user):
            return Response({"detail": "Звʼязувати фонди зі ставками може лише власник"}, status=403)
        try:
            fid = int(request.data.get("fund_id"))
        except (TypeError, ValueError):
            return Response({"detail": "fund_id"}, status=400)
        on = _truthy(request.data.get("linked"))
        rows = fot_rows()
        row = next((r for r in rows if r["fund_id"] == fid), None)
        if on:
            if not row:
                return Response({"detail": "Фонд не знайдено серед зарплатних фондів"}, status=404)
            if not row.get("syncable"):
                return Response({"detail": "У цьому фонді не лише зарплати — звʼязати не можна, змініть його у Фінмоделі вручну"},
                                status=400)
        ids, _changed = set_linked(fid, on, request.user)
        changed = sync_linked(user=request.user, only=[fid], rows=rows) if on else []
        return Response({"fund_id": fid, "linked": on, "linked_ids": ids, "changed": changed})
