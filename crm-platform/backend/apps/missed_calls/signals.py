import logging

log = logging.getLogger(__name__)


def on_call_saved(sender, instance, created, raw=False, **kwargs):
    """Новий дзвінок → оновити чергу пропущених. Помилка тут НІКОЛИ не ламає прийом дзвінка
    (webhook відповідає як і раніше; пропущене підбере крон missed_calls_sweep)."""
    if raw or not created:
        return
    try:
        from .services import process_call
        process_call(instance)
    except Exception:  # noqa: BLE001
        log.exception("missed_calls: process_call failed for call %s", getattr(instance, "pk", None))
