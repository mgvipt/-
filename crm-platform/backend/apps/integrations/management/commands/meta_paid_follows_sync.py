import time

from django.core.management.base import BaseCommand, CommandError

from apps.integrations.meta_paid_follows import import_reports


class Command(BaseCommand):
    help = "Import paid Instagram follows from the scheduled Meta Ads email report"

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--interval", type=int, default=600)
        parser.add_argument("--backfill", action="store_true")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        if options["interval"] < 60:
            raise CommandError("--interval must be at least 60 seconds")
        while True:
            result = import_reports(backfill=options["backfill"], dry_run=options["dry_run"])
            message = "Meta paid follows: %s" % result
            if result.get("errors"):
                self.stderr.write(self.style.WARNING(message))
            else:
                self.stdout.write(self.style.SUCCESS(message))
            if not options["watch"]:
                return
            time.sleep(options["interval"])
