# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Читає пошту накладних (Gmail) і робить чернетки IncomingDoc"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=60)
        parser.add_argument("--backfill", action="store_true")

    def handle(self, *args, **opts):
        from apps.integrations.models import IntegrationSettings
        from apps.integrations.email_invoices import poll
        o = IntegrationSettings.objects.filter(provider="email_invoices").first()
        if not o or not o.is_active:
            self.stdout.write("email_invoices: вимкнено або не налаштовано")
            return
        res = poll(limit=opts["limit"], backfill=opts["backfill"], log=lambda m: self.stdout.write(str(m)))
        self.stdout.write("email_invoices: %s" % res)
