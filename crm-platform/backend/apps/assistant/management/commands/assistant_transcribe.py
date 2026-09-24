"""Розшифрувати нові голосові асистента (крон кожні 5 хв). Ліміт місяця — зупиняє."""
from django.core.management.base import BaseCommand

from apps.assistant.services import BudgetError, transcribe_pending


class Command(BaseCommand):
    def handle(self, *args, **opts):
        try:
            n = transcribe_pending()
        except BudgetError as e:
            self.stdout.write(str(e))
            return
        if n:
            self.stdout.write(f"розшифровано {n}")
