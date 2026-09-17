"""Скільки чатів / лідів співробітник «узяв у роботу» — БЕЗ ПОВТОРІВ (17.09.2026).

Повторне «Закріпити» того самого клієнта тим самим співробітником протягом 30 днів — не нова робота
(напр. чати забрали при помилковому «Звільнити», а людина повернула їх собі). Раніше кожне натискання
рахувалось як нове «взяв», і в аналітиці ті самі клієнти зʼявлялись удруге.
Одне місце для всіх звітів: «Дії менеджерів», тижневий розбір, KPI по днях у «Моїй ЗП»."""
from datetime import timedelta

from django.utils import timezone

TAKE_ACTIONS = ("Взяв чат", "Призначено відповідального")
REPEAT_DAYS = 30


def take_events(d_from, d_to, user_ids=None):
    """[(user_id, дата)] — перші взяття в період [d_from; d_to] (дати включно)."""
    from apps.crm.models import ActivityLog
    qs = ActivityLog.objects.filter(user__isnull=False, action__in=TAKE_ACTIONS,
                                    created_at__date__gte=d_from - timedelta(days=REPEAT_DAYS),
                                    created_at__date__lte=d_to)
    if user_ids is not None:
        qs = qs.filter(user_id__in=list(user_ids))
    last, out = {}, []
    for uid, kind, oid, at in qs.order_by("created_at", "id").values_list("user_id", "kind", "object_id", "created_at"):
        key = (uid, kind, oid) if oid else None  # без клієнта (object_id=0) — кожне окремо
        repeat = key is not None and key in last and at - last[key] <= timedelta(days=REPEAT_DAYS)
        if key is not None:
            last[key] = at
        day = timezone.localtime(at).date()
        if repeat or day < d_from:
            continue
        out.append((uid, day))
    return out


def taken_by_user(d_from, d_to, user_ids=None):
    """{user_id: к-сть узятих у роботу без повторів}."""
    res = {}
    for uid, _d in take_events(d_from, d_to, user_ids):
        res[uid] = res.get(uid, 0) + 1
    return res
