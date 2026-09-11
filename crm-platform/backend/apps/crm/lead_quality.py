"""Якість звернення (ліда): Цільовий / Нецільовий (+ причина) / Коментар без запиту / Не відповів.

Одне поле на ліді. Ставиться в чаті (кнопками або при завершенні з причиною) і в картках
ліда, угоди та клієнта — завжди на ОСТАННІЙ лід контакту, тому видно однаково всюди.
У конверсію менеджера йдуть лише цільові (правило схеми ЗП v7, 11.09.2026).
"""
import logging

from django.utils import timezone

from .models import Lead, log_activity

QUALITY = Lead.QUALITY
NONTARGET_REASONS = [
    ("spam", "Спам / бот"),
    ("not_our", "Не наш товар"),
    ("supplier_job", "Постачальник / вакансія"),
    ("wrong", "Помилився адресою"),
    ("other", "Інше"),
]
Q_LABEL = dict(QUALITY)
R_LABEL = dict(NONTARGET_REASONS)

log = logging.getLogger(__name__)


def current_lead(contact_id):
    """Останній лід контакту — саме його якість показуємо в чаті та картках."""
    if not contact_id:
        return None
    return Lead.objects.filter(contact_id=contact_id).order_by("-created_at").first()


def _label(quality, reason):
    txt = Q_LABEL.get(quality, "не відмічено")
    return txt + (" · " + R_LABEL[reason] if reason in R_LABEL else "")


def state(lead):
    if not lead:
        return {"lead_id": None, "quality": "", "reason": ""}
    by = lead.quality_by
    return {
        "lead_id": lead.id,
        "quality": lead.quality,
        "quality_label": Q_LABEL.get(lead.quality, ""),
        "reason": lead.quality_reason,
        "reason_label": R_LABEL.get(lead.quality_reason, ""),
        "by": (by.get_full_name() or by.username) if by else "",
        "at": lead.quality_at.isoformat() if lead.quality_at else None,
    }


def set_quality(lead, quality, reason="", user=None, source="вручну"):
    """Поставити/зняти якість. Нецільовий без відомої причини → «Інше». Пише в історію ліда."""
    quality = (quality or "").strip()
    reason = (reason or "").strip()
    if quality and quality not in Q_LABEL:
        raise ValueError("unknown quality")
    if quality != "nontarget":
        reason = ""
    elif reason not in R_LABEL:
        reason = "other"
    old = _label(lead.quality, lead.quality_reason)
    real_user = user if (user is not None and getattr(user, "is_authenticated", False)) else None
    lead.quality = quality
    lead.quality_reason = reason
    lead.quality_by = real_user
    lead.quality_at = timezone.now() if quality else None
    lead.save(update_fields=["quality", "quality_reason", "quality_by", "quality_at"])
    who = (real_user.get_full_name() or real_user.username) if real_user else "Система"
    log_activity("lead", lead.id, "Якість звернення", "%s → %s (%s)" % (old, _label(quality, reason), source),
                 real_user, who)
    return lead


def from_close_reason(reason):
    """Причина завершення чату → (якість, причина нецільового) або None (без причини — не чіпаємо)."""
    low = (reason or "").lower().strip()
    if not low:
        return None
    if low.startswith("нецільов"):
        for key, code in (("спам", "spam"), ("бот", "spam"), ("не наш", "not_our"), ("постачальник", "supplier_job"),
                          ("ваканс", "supplier_job"), ("помилив", "wrong")):
            if key in low:
                return ("nontarget", code)
        return ("nontarget", "other")
    if "не звернення" in low:
        return ("comment", "")
    return ("target", "")


def mark_on_close(contact_id, reason, user=None):
    """Завершення чату з причиною → якість останнього ліда.
    Нецільовий і коментар ставимо завжди; «цільовий» — лише якщо лід ще не відмічений
    (ручну відмітку менеджера не перетираємо)."""
    q = from_close_reason(reason)
    lead = current_lead(contact_id)
    if not q or not lead:
        return None
    quality, r = q
    if quality == "target" and lead.quality:
        return lead
    if lead.quality == quality and lead.quality_reason == r:
        return lead
    return set_quality(lead, quality, r, user, source="завершення чату: %s" % reason)


def safe_mark_on_close(contact_id, reason, user=None):
    """Те саме, але помилка відмітки ніколи не ламає завершення чату."""
    try:
        return mark_on_close(contact_id, reason, user)
    except Exception:  # noqa: BLE001
        log.exception("lead quality on chat close failed (contact %s)", contact_id)
        return None


def api_state_or_set(request, contact_id):
    """GET — стан якості останнього ліда контакту; POST {quality, reason} — відмітити."""
    from rest_framework.response import Response
    lead = current_lead(contact_id)
    if request.method == "POST":
        if not lead:
            return Response({"detail": "У клієнта ще немає звернення (ліда)"}, status=404)
        try:
            set_quality(lead, request.data.get("quality"), request.data.get("reason"), request.user)
        except ValueError:
            return Response({"detail": "Невідома якість звернення"}, status=400)
    return Response({**state(lead), "choices": QUALITY, "reasons": NONTARGET_REASONS})
