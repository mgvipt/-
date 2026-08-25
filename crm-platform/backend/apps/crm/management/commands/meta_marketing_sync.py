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

        def run_source(name, current_until, recent_days):
            try:
                if name == "ads":
                    ads_since = max(since, current_until - timedelta(days=max(1, recent_days) - 1))
                    r = sync_ads(ads_since, current_until)
                elif name == "account":
                    r = sync_account(since, current_until)
                else:
                    r = sync_content(since)
                self.stdout.write(self.style.SUCCESS(f"Meta {name} OK: {r}"))
                return True
            except MetaGraphError as exc:
                self.stderr.write(self.style.ERROR(
                    f"Meta {name} sync failed: code={exc.code or '-'} "
                    f"subcode={exc.subcode or '-'} {exc}"))
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"Meta {name} sync error: {exc}"))
            return False

        # Разовый запуск (без --watch) — как раньше
        if not options["watch"]:
            ok = True
            if not options["content_only"]:
                ok = run_source("ads", until, options["recent_days"]) and ok
            if not options["ads_only"]:
                ok = run_source("account", until, options["recent_days"]) and ok
                ok = run_source("content", until, options["recent_days"]) and ok
            if not ok:
                raise CommandError("Meta sync partially failed")
            return

        # Фоновый режим: интервалы берём из настроек БД (меняются из UI без рестарта)
        from apps.crm.models import MetaSyncSettings
        last = {"ads": 0.0, "account": 0.0, "content": 0.0}
        while True:
            try:
                st = MetaSyncSettings.get()
            except Exception:
                st = None
            now = time.time()
            current_until = date.today()
            recent_days = (getattr(st, "recent_days", None) or options["recent_days"])
            plan = [
                ("ads", getattr(st, "ads_enabled", True), getattr(st, "ads_interval_min", 360)),
                ("account", getattr(st, "account_enabled", True), getattr(st, "account_interval_min", 360)),
                ("content", getattr(st, "content_enabled", True), getattr(st, "content_interval_min", 360)),
            ]
            for name, enabled, interval_min in plan:
                if not enabled:
                    continue
                if now - last[name] >= max(1, interval_min) * 60:
                    run_source(name, current_until, recent_days)
                    last[name] = time.time()
            time.sleep(60)
