"""Перегляди й реакції опублікованих постів з публічного віджета каналу (крон щогодини)."""
from django.core.management.base import BaseCommand

from apps.content_factory.telegram import collect_stats


class Command(BaseCommand):
    help = "Оновити перегляди/реакції опублікованих з CRM постів"

    def handle(self, *args, **opts):
        n = collect_stats()
        if n:
            self.stdout.write(f"оновлено {n}")
