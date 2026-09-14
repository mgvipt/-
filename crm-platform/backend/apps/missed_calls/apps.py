from django.apps import AppConfig


class MissedCallsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.missed_calls"
    verbose_name = "Пропущені дзвінки"

    def ready(self):
        # Слухаємо появу нового дзвінка (його створює CallWebhookView з CDR-синку).
        # Код телефонії при цьому не змінюється.
        from django.db.models.signals import post_save
        from apps.telephony.models import Call
        from .signals import on_call_saved
        post_save.connect(on_call_saved, sender=Call, dispatch_uid="missed_calls_on_call_saved")
