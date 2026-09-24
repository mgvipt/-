"""Стрічка рекомендацій: оновити ролики сторінок з Virale (крон щодня 06:40). Безкоштовно — Virale вже оплачено."""
from django.core.management.base import BaseCommand

from apps.content_factory.analyst import sync_feed


class Command(BaseCommand):
    help = "Оновити стрічку рекомендацій з Virale"

    def handle(self, *args, **opts):
        self.stdout.write(str(sync_feed()))
