"""Крон кожні 5 хв: підібрати пропущені, звірити з журналом, призначити черговому, ескалація.
Нічого не надсилає клієнтам."""
import json

from django.core.management.base import BaseCommand

from apps.missed_calls.services import sweep


class Command(BaseCommand):
    help = "Черга пропущених: звірка / призначення / ескалація (лише у CRM)"

    def handle(self, *args, **opts):
        res = sweep()
        self.stdout.write(json.dumps(res, ensure_ascii=False))
