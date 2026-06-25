"""
═══════════════════════════════════════════════════════════════════════════
  РУШІЙ АВТО-СТАДІЙ ВОРОНКИ
  Рухає клієнта по воронці автоматично за активністю — як сценарій ChatPlace/Бітрикс,
  але незалежно, всередині нашої CRM. Кожен авто-перехід пишеться в Історію змін.
═══════════════════════════════════════════════════════════════════════════
"""
from .models import AutomationRule, log_activity

# Ключові слова «готовності купити» (тригер ready_buy)
BUY_KEYWORDS = [
    "куплю", "беру", "оформ", "замов", "заказ", "хочу замов", "готов", "давайте оформ",
    "рахунок", "счет", "счёт", "оплач", "придба", "купи", "возьму", "бронь", "бронир",
]


_NEG = ["не ", "поки не", "ще не", "не хочу", "не буду", "нет", "ні,"]

def is_buy_intent(text: str) -> bool:
    t = (text or "").lower()
    if any(n in t for n in _NEG):  # BUG-5: «не готов», «поки не беру» — не вважати готовністю
        return False
    return any(k in t for k in BUY_KEYWORDS)


def _advance(entity, kind: str, trigger: str) -> bool:
    """Знайти правило для поточної стадії+тригера і просунути стадію (тільки вперед)."""
    if not entity or not entity.stage_id or not entity.funnel_id:
        return False
    rule = (AutomationRule.objects
            .filter(funnel_id=entity.funnel_id, from_stage_id=entity.stage_id, trigger=trigger, enabled=True)
            .select_related("to_stage", "from_stage").first())
    if not rule:
        return False
    if rule.to_stage.order <= entity.stage.order:   # рух тільки вперед, ніколи назад
        return False
    old = entity.stage.name
    entity.stage = rule.to_stage
    _flds = ["stage"]
    if hasattr(entity, "stage_changed_at"):
        from django.utils import timezone as _tz
        entity.stage_changed_at = _tz.now(); _flds.append("stage_changed_at")
    entity.save(update_fields=_flds)
    label = dict(AutomationRule.TRIGGERS).get(trigger, trigger)
    log_activity(kind, entity.id, "Авто-стадія", f"{old} → {rule.to_stage.name} (тригер: {label})", None, "Автоматизація")
    return True


def _lead_for(contact):
    if not contact:
        return None
    from .models import Lead
    return (Lead.objects.filter(contact=contact).exclude(stage__is_lost=True)
            .select_related("stage", "funnel").order_by("-created_at").first())


def on_incoming(contact, text: str = ""):
    """Клієнт написав → авто-просування (готовність купити має пріоритет)."""
    lead = _lead_for(contact)
    if not lead:
        return
    if is_buy_intent(text) and _advance(lead, "lead", "ready_buy"):
        return
    _advance(lead, "lead", "client_reply")


def on_outgoing(contact):
    """Менеджер/AI відповів → авто-просування (напр. Лід отриманий → Взято в роботу)."""
    lead = _lead_for(contact)
    if lead:
        _advance(lead, "lead", "manager_reply")
