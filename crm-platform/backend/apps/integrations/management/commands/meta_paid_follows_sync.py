import time

from django.core.management.base import BaseCommand, CommandError

from apps.integrations.meta_paid_follows import (
    import_csv_file,
    import_reports,
    import_share_report,
    share_report_url,
)


class Command(BaseCommand):
    help = "Import paid Instagram follows (share-link report by default, e-mail XLSX as fallback)"

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--interval", type=int, default=600)
        parser.add_argument("--backfill", action="store_true")
        parser.add_argument("--dry-run", action="store_true")
        # [claude:analytics 26.08] share = анонімне посилання звіту (без пошти/Selenium),
        # email = шлях Codex через листи; auto = share, якщо налаштований URL.
        parser.add_argument("--source", choices=["auto", "share", "email"], default="auto")
        parser.add_argument("--csv-file", default="", help="одноразовий бекфіл історії з CSV-експорту звіту")

    def handle(self, *args, **options):
        if options["interval"] < 60:
            raise CommandError("--interval must be at least 60 seconds")
        if options["csv_file"]:
            result = import_csv_file(options["csv_file"], dry_run=options["dry_run"])
            self.stdout.write(self.style.SUCCESS("Meta paid follows CSV: %s" % result))
            return
        source = options["source"]
        if source == "auto":
            source = "share" if share_report_url() else "email"
        while True:
            if source == "share":
                result = import_share_report(dry_run=options["dry_run"])
            else:
                result = import_reports(backfill=options["backfill"], dry_run=options["dry_run"])
            message = "Meta paid follows [%s]: %s" % (source, result)
            if result.get("errors") or result.get("error") or result.get("warning"):
                self.stderr.write(self.style.WARNING(message))
            else:
                self.stdout.write(self.style.SUCCESS(message))
            if not options["watch"]:
                return
            time.sleep(options["interval"])
