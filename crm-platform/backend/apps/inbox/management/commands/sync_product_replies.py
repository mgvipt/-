"""Швидкі відповіді з номенклатури: синхронізувати папки (17.09.2026).

    python manage.py sync_product_replies          # план (нічого не пише)
    python manage.py sync_product_replies --apply
"""
from django.core.management.base import BaseCommand

from apps.inbox import product_replies as PR


class Command(BaseCommand):
    help = "Нові позиції в привʼязаних папках номенклатури → нові швидкі відповіді (без --apply лише план)"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **o):
        acts = PR.sync_all(dry=not o["apply"], force=True)
        for a in acts:
            self.stdout.write("  %s" % (a,))
        self.stdout.write("%s: змін %s" % ("LIVE" if o["apply"] else "DRY", len(acts)))
