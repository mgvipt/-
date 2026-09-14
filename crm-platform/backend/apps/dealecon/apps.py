from django.apps import AppConfig


class DealEconConfig(AppConfig):
    name = "apps.dealecon"
    verbose_name = "Економіка угоди"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # Перерахунок після оплати / банку / НП / складу / виплати майстру — сигнали лише цього застосунку,
        # чужі файли не чіпаємо. Усе ловиться try/except усередині: збій економіки НЕ ламає основну дію.
        from . import signals
        signals.connect()
