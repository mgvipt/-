# -*- coding: utf-8 -*-
"""Нарахувати відсотки по всіх активних кредитах. Крон раз на добу.
Ідемпотентна: нараховує лише те, чого ще немає (дивиться last_accrual)."""
from django.core.management.base import BaseCommand

from apps.finance.loans import accrue, pull_payments, sync_planned
from apps.finance.models import Loan


class Command(BaseCommand):
    help = "Нарахування відсотків по кредитах і позиках"

    def add_arguments(self, parser):
        parser.add_argument("--dry", action="store_true", help="лише показати, нічого не писати")
        parser.add_argument("--id", type=int, default=0, help="лише один кредит")

    def handle(self, *a, **o):
        qs = Loan.objects.filter(is_active=True)
        if o.get("id"):
            qs = qs.filter(id=o["id"])
        total = 0
        for ln in qs:
            made = accrue(ln, dry=o.get("dry"))
            if made:
                total += len(made)
                for m in made:
                    amt = m["amount"] if isinstance(m, dict) else m.amount
                    d = m["date"] if isinstance(m, dict) else m.date
                    self.stdout.write("  %s · %s: +%s %s" % (ln.name, d, amt, ln.currency))
            paid = pull_payments(ln, dry=o.get("dry"))
            for m in paid:
                amt = m["amount"] if isinstance(m, dict) else m.amount
                d = m["date"] if isinstance(m, dict) else m.date
                self.stdout.write("  %s · %s: платіж %s %s" % (ln.name, d, amt, ln.currency))
            if not o.get("dry"):
                sync_planned(ln)
        self.stdout.write(self.style.SUCCESS("нарахувань: %s%s" % (total, " (DRY)" if o.get("dry") else "")))
