"""Повернення сделки з програшної стадії («Игнор», «Не відповідає» тощо).

19.09.2026 (Олег, сделка #66537): «навіть якщо сделка і клієнт в ігнорі, буває, що клієнт повертається
і оплачує — треба повертати сделку після оплати в потрібний статус «Оплату отримано» і показувати
цей момент у статистиці».

Що було: менеджер завершив чат з причиною «Не відповідає (ігнор)» → сделку автоматично закрито в
«Игнор». Клієнтка через 40 хвилин написала «я буду замовляти», оплатила — а сделка лишилась в «Игнор»:
  • при поверненні в чат відкривався лише ДІАЛОГ, сделка — ні (знімок стадії _reached_stage_id
    зберігався, але ніхто його не використовував);
  • рух «після оплати» працював тільки ВПЕРЕД за номером стадії, а «Игнор» стоїть у кінці воронки;
  • банк не привʼязував оплату до програної сделки навіть із номером замовлення в призначенні.

Єдина точка повернення — revive(). Кожне повернення лишає слід для статистики:
  • запис в історії сделки «↩️ Повернуто з ігнору» (ActivityLog, kind="deal") — ОДНЕ джерело для звітів;
  • qualification["_revived"] — список {at, from, to, why} (видно в картці та експорті).
"""
from datetime import timedelta

from django.utils import timezone

REVIVE_ACTION = "↩️ Повернуто з ігнору"
RETURN_DAYS = 90          # сделки, закриті разом із чатом не давніше — повертаємо, коли клієнт знову пише


def revive(deal, target, why, actor="Автоматизація"):
    """Перевести сделку з програшної стадії на `target` (будь-яка стадія тієї ж воронки).
    Повертає True, якщо сделку повернуто."""
    from .models import log_activity
    if deal is None or target is None or not deal.stage_id:
        return False
    if not getattr(deal.stage, "is_lost", False) or target.funnel_id != deal.funnel_id:
        return False
    old = deal.stage.name
    now = timezone.now()
    q = dict(deal.qualification or {})
    trail = list(q.get("_revived") or [])
    trail.append({"at": now.isoformat(), "from": old, "to": target.name, "why": why[:200]})
    q["_revived"] = trail
    q.pop("close_reason", None)
    deal.qualification = q
    deal.stage = target
    deal.stage_changed_at = now
    flds = ["stage", "stage_changed_at", "qualification"]
    if deal.closed_at and not (target.is_won or target.is_lost):
        deal.closed_at = None
        flds.append("closed_at")
    deal.save(update_fields=flds)
    log_activity("deal", deal.id, REVIVE_ACTION, "%s → %s · %s" % (old, target.name, why), None, actor)
    return True


def revive_on_return(contact_id, why="клієнт знову написав"):
    """Клієнт написав після того, як чат завершили «в ігнор»: повертаємо сделки, які закрились РАЗОМ
    із чатом (є знімок _reached_stage_id), на ту саму стадію, де вони були. Оплачені й успішні не чіпаємо."""
    from .models import Deal, Stage
    if not contact_id:
        return 0
    since = timezone.now() - timedelta(days=RETURN_DAYS)
    done = 0
    for d in (Deal.objects.filter(contact_id=contact_id, stage__is_lost=True, stage_changed_at__gte=since)
              .select_related("stage")):
        q = d.qualification or {}
        sid = q.get("_reached_stage_id")
        if not sid or not q.get("close_reason"):
            continue                     # закрита вручну з іншої причини — рішення менеджера не перекреслюємо
        target = Stage.objects.filter(id=sid, funnel_id=d.funnel_id, is_lost=False, is_won=False).first()
        if target and revive(d, target, why):
            done += 1
    return done


def paid_stage_for(deal):
    """Стадія «Оплату отримано» (або «Заброньовано» для броні) — пошук за назвою, як _advance_after_payment."""
    is_bron = "брон" in (deal.pay_type or "").lower()
    names = ["заброньов"] if is_bron else ["оплату отримано", "оплата отримано", "оплата отримана", "оплата/предоплата"]
    for nm in names:
        st = deal.funnel.stages.filter(name__icontains=nm, is_lost=False).order_by("order").first()
        if st:
            return st
    return None
