from django.apps import AppConfig


class InboxConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.inbox"

    def ready(self):
        # TikTok Direct: реєструє адаптер kind="tiktok" в adapters.ADAPTERS (див. apps/inbox/tiktok.py).
        # Імпорт тут, а не в adapters.py, щоб не чіпати спільний файл адаптерів.
        from . import tiktok  # noqa: F401
        from . import landing_signals  # noqa: F401
