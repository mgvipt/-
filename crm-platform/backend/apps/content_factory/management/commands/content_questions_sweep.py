"""Нічний розбір питань клієнтів у теми (контент-завод, етап 1). Крон 03:40.
Вимкнено в налаштуваннях → нічого платного не робить. --dry-run — лише порахувати без ШІ."""
import json

from django.core.management.base import BaseCommand

from apps.content_factory.questions import run


class Command(BaseCommand):
    help = "Розібрати нові питання клієнтів у теми контенту"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        self.stdout.write(json.dumps(run(dry_run=opts["dry_run"]), ensure_ascii=False, default=str))
