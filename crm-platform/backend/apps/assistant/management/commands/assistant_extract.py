"""Щоночі (02:50) витягти знання з нових повідомлень у пропозиції. Вимкнено в налаштуваннях → нічого платного."""
from django.core.management.base import BaseCommand

from apps.assistant.models import AssistantSettings
from apps.assistant.services import BudgetError, extract


class Command(BaseCommand):
    def handle(self, *args, **opts):
        if not AssistantSettings.get().extraction_enabled:
            self.stdout.write("Вимкнено")
            return
        try:
            self.stdout.write(f"нових пропозицій {extract()}")
        except BudgetError as e:
            self.stdout.write(str(e))
