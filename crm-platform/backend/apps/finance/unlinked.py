"""Приходи без сделки, схожі на оплату клієнта (19.09.2026, Олег: «щоб дані брались з одного джерела»).

Кейс #66537: клієнтка оплатила 2 261,50 грн за реквізитами, банк привіз гроші, а CRM не привʼязала
їх до сделки. У Фінансах гроші були, у сделці, KPI менеджера, складі й маркетингу — ні.

Автопривʼязка банку лишається обережною (номер замовлення або телефон/прізвище + точна сума + ОДНА
відкрита сделка). Все, що вона не привʼязала, але СХОЖЕ на оплату клієнта, ця перевірка показує людям:
  • номер сделки в призначенні (навіть якщо сделка в «Игнор»);
  • хвіст телефону клієнта або його прізвище + сума ≈ сума сделки (±5 грн), будь-яка стадія.
Сповіщення — відповідальному за знайдену сделку і власнику, один раз на кожен прихід.
Нічого не привʼязує сама: рішення за людиною (гроші).
"""
import re
from datetime import timedelta

from django.utils import timezone

DAYS = 14
NUM_RX = re.compile(r"(?<!\d)(\d{5,6})(?!\d)")


def _candidates(tx):
    from apps.crm.models import Deal
    text = tx.comment or ""
    low = text.lower()
    amt = float(tx.amount_uah or tx.amount or 0)
    since = timezone.now() - timedelta(days=180)
    found = {}
    for num in set(NUM_RX.findall(text)):
        if int(num) == int(round(amt)):
            continue
        d = Deal.objects.filter(id=int(num), created_at__gte=since).select_related("stage", "contact").first()
        if d and d.amount and amt <= float(d.amount) * 1.05 + 100:
            found[d.id] = (d, "номер сделки в призначенні")
    if found:
        return list(found.values())
    digits = re.sub(r"\D", "", text)
    for d in (Deal.objects.filter(created_at__gte=since, amount__gte=amt - 5, amount__lte=amt + 5)
              .exclude(stage__is_won=True).select_related("stage", "contact")):
        c = d.contact
        if not c:
            continue
        if sum(float(p.amount) for p in d.payments.all() if p.is_paid) >= float(d.amount) - 5:
            continue
        tail = re.sub(r"\D", "", c.phone or "")[-9:]
        ln = (c.last_name or "").strip().lower()
        if tail and len(tail) == 9 and tail in digits:
            found[d.id] = (d, "телефон клієнта + сума")
        elif ln and len(ln) > 2 and ln in low:
            found[d.id] = (d, "прізвище клієнта + сума")
    return list(found.values())


def find(days=DAYS):
    """Приходи без сделки за `days` днів, для яких є ОДНА ймовірна сделка."""
    from apps.finance.models import Transaction
    since = (timezone.now() - timedelta(days=days)).date()
    out = []
    qs = (Transaction.objects.filter(direction="in", deal__isnull=True, transfer_account__isnull=True, date__gte=since)
          .select_related("account").order_by("date", "id"))
    for tx in qs:
        cands = _candidates(tx)
        if len(cands) == 1:
            d, why = cands[0]
            out.append({"tx": tx, "deal": d, "why": why})
    return out


def notify(rows, dry=False):
    """Сповіщення відповідальному за сделку і власнику. Повтор по тому самому приходу не шлемо."""
    from django.contrib.auth import get_user_model
    from apps.inbox.models import Notification
    owners = list(get_user_model().objects.filter(is_superuser=True, is_active=True).values_list("id", flat=True))
    sent = 0
    for r in rows:
        tx, d = r["tx"], r["deal"]
        mark = "журнал #%s" % tx.id
        if Notification.objects.filter(text__contains=mark).exists():
            continue
        text = ("💰 %s: прихід %s грн від %s без сделки — схоже на оплату по сделці #%s «%s» (%s, стадія «%s»). "
                "Привʼяжіть у Фінансах → Журнал." % (
                    mark, tx.amount_uah, tx.date.strftime("%d.%m"), d.id, str(d.contact)[:30], r["why"],
                    d.stage.name if d.stage_id else "—"))
        if dry:
            print("  [DRY]", text)
            continue
        for uid in dict.fromkeys([u for u in [d.owner_id] + owners if u]):
            Notification.objects.create(user_id=uid, kind="system", text=text[:300])
        sent += 1
    return sent
