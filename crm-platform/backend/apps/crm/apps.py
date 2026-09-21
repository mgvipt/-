from django.apps import AppConfig


class CrmConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.crm"

    def ready(self):
        from . import signals  # noqa: F401
        from . import pattera_masterclass  # noqa: F401
