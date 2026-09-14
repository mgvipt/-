"""Рядок «Задачі з біржі» для ЗП (apps.payroll.engine.calc).

Модулі моделей імпортуємо лише ПІСЛЯ перевірки, що застосунок увімкнено (INSTALLED_APPS): інакше Django падає
на імпорті моделі. Таблиць ще немає (міграцію не застосовано) — тихо повертаємо None у власному savepoint,
щоб не зламати транзакцію розрахунку ЗП.
"""
from django.apps import apps as django_apps
from django.db import DatabaseError, transaction

LINE_TITLE = "Задачі з біржі"


def payroll_line(user, period):
    """Прийняті задачі людини, у яких місяць ЗП = period. None — нічого немає / застосунок вимкнено."""
    if not user or not getattr(user, "pk", None) or not django_apps.is_installed("apps.bounty"):
        return None
    from .models import TaskClaim
    try:
        with transaction.atomic():
            rows = list(TaskClaim.objects.filter(user_id=user.pk, status="accepted", payroll_period=period)
                        .order_by("reviewed_at", "id").values_list("offer__title", "amount"))
    except DatabaseError:
        return None
    if not rows:
        return None
    total = sum(float(a or 0) for _t, a in rows)
    counts = {}
    for t, _a in rows:
        counts[t] = counts.get(t, 0) + 1
    parts = [f"{t} ×{n}" if n > 1 else t for t, n in counts.items()]
    detail = f"прийнято задач: {len(rows)} — " + "; ".join(parts[:6]) + ("; …" if len(parts) > 6 else "")
    return {"component": None, "kind": "bounty", "title": LINE_TITLE, "basis": len(rows), "rate": None,
            "amount": round(total), "detail": detail, "estimate": False, "warn": ""}
