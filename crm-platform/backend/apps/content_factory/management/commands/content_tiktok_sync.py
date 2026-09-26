"""Раз на добу: ролики власних TikTok-акаунтів блогів напряму з TikTok API (27.09.2026). Безкоштовно."""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Оновити ролики власних TikTok-акаунтів блогів (TikTok API for Business)"

    def handle(self, *args, **opts):
        from apps.content_factory.tiktok_stats import sync_all
        self.stdout.write(str(sync_all()))
