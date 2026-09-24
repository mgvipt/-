"""Щотижневий звіт аналітика (крон пн 08:30). Вимкнено в налаштуваннях → нічого платного не робить."""
from django.core.management.base import BaseCommand

from apps.content_factory.analyst import BudgetError, generate_report
from apps.content_factory.models import AnalystSettings


class Command(BaseCommand):
    help = "Звіт аналітика контенту за тиждень"

    def handle(self, *args, **opts):
        if not AnalystSettings.get().weekly_enabled:
            self.stdout.write("Вимкнено — нічого не робимо")
            return
        try:
            r = generate_report(days=7)
            self.stdout.write(f"Звіт #{r.id}")
        except (BudgetError, ValueError) as e:
            self.stdout.write(str(e))
