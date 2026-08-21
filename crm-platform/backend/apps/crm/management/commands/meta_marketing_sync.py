import time
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_date

from apps.crm.meta_marketing import MetaGraphError, sync_account, sync_ads, sync_content


class Command(BaseCommand):
    help = "Read-only sync Meta Ads Insights and own Instagram content metrics"

    def add_arguments(self, parser):
        parser.add_argument("--since", default="2026-06-16")
        parser.add_argument("--until", default="")
        parser.add_argument("--ads-only", action="store_true")
        parser.add_argument("--content-only", action="store_true")
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--interval", type=int, default=21600)
        parser.add_argument("--recent-days", type=int, default=7)

    def handle(self, *args, **options):
        since = parse_date(options["since"])
        until = parse_date(options["until"]) if options["until"] else date.today()
        if not since or not until:
            raise CommandError("Dates must use YYYY-MM-DD")
        if since > until:
            since, until = until, since
        if options["ads_only"] and options["content_only"]:
            raise CommandError("Choose either --ads-only or --content-only")

        while True:
            current_until = date.today() if options["watch"] else until
            ads_since = since
            if options["watch"]:
                ads_since = max(since, current_until - timedelta(days=max(1, options["recent_days"]) - 1))
            result = {}
            failures = []
            if not options["content_only"]:
                try:
                    result["ads"] = sync_ads(ads_since, current_until)
                except MetaGraphError as exc:
                    failures.append(("ads", exc))
            if not options["ads_only"]:
                try:
                    result["account"] = sync_account(since, current_until)
                except MetaGraphError as exc:
                    failures.append(("account", exc))
                try:
                    result["content"] = sync_content(since)
                except MetaGraphError as exc:
                    failures.append(("content", exc))

            if result:
                self.stdout.write(self.style.SUCCESS(f"Meta sync OK: {result}"))
            for section, exc in failures:
                self.stderr.write(self.style.ERROR(
                    f"Meta {section} sync failed: code={exc.code or '-'} "
                    f"subcode={exc.subcode or '-'} {exc}"
                ))
            if failures and not options["watch"]:
                raise CommandError("Meta sync partially failed") from failures[0][1]
            if not options["watch"]:
                break
            time.sleep(max(300, options["interval"]))
