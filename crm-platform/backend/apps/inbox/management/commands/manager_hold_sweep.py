# -*- coding: utf-8 -*-
"""Крон раз на хвилину: чи є діалоги, де клієнт чекає, а менеджер ще не відповів (apps/inbox/manager_hold.py)."""
from django.core.management.base import BaseCommand

from apps.inbox import manager_hold


class Command(BaseCommand):
    help = "Повідомлення клієнту «менеджер узяв ваш запит у роботу»"

    def add_arguments(self, parser):
        parser.add_argument("--dry", action="store_true", help="лише показати, кому і що надіслали б")

    def handle(self, *args, **o):
        rows = manager_hold.sweep(dry=o["dry"])
        for cid, kind, info in rows:
            self.stdout.write("чат %s · %s · %s" % (cid, kind, info))
        self.stdout.write("усього: %d%s" % (len(rows), " (ПОКАЗ)" if o["dry"] else ""))
