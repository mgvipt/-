from django.apps import AppConfig


class PartnersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.partners"
    verbose_name = "Партнерська програма"

    def ready(self):
        from . import signals  # noqa: F401  — автопідвищення рівня після оплати
