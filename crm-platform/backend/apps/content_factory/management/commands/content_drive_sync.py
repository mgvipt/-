"""Обхід папок Google Drive для «Джерел контенту» (крон 04:30). Лише посилання й назви — файли не копіюються."""
from django.core.management.base import BaseCommand

from apps.content_factory.drive import sync_all


class Command(BaseCommand):
    help = "Оновити список фото й відео з підключених папок Google Drive"

    def handle(self, *args, **opts):
        self.stdout.write(str(sync_all()))
