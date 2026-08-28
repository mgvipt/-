from django.core.management.base import BaseCommand

from apps.crm.ga4_sync import sync_ga4


class Command(BaseCommand):
    help = "Sync Google Analytics 4 daily stats for Wallcov sites"

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30)

    def handle(self, *args, **options):
        result = sync_ga4(days=options["days"])
        if result.get("errors") or result.get("error"):
            self.stderr.write(self.style.WARNING("GA4 sync: %s" % result))
        else:
            self.stdout.write(self.style.SUCCESS("GA4 sync: %s" % result))
