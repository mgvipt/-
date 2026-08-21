from django.core.management.base import BaseCommand, CommandError

from apps.crm.meta_conversions import capi_config, process_event
from apps.crm.models import MetaConversionEvent


class Command(BaseCommand):
    help = "Preview or explicitly send queued CRM conversion events to Meta"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument("--send", action="store_true", help="Actually call Meta; without this flag it is dry-run")
        parser.add_argument("--test-event-code", default="", help="Meta Events Manager test code")

    def handle(self, *args, **options):
        limit = max(1, min(options["limit"], 500))
        rows = list(
            MetaConversionEvent.objects.filter(status__in=["pending", "failed"], attempts__lt=5)
            .order_by("created_at", "id")[:limit]
        )
        if not options["send"]:
            self.stdout.write(f"DRY_RUN: {len(rows)} event(s); nothing was sent")
            for event in rows:
                self.stdout.write(
                    f"would send {event.event_name} | {event.source_type}#{event.source_id} | {event.event_id}"
                )
            return
        config = capi_config()
        if not config["enabled"]:
            raise CommandError("Sending is disabled. Set META_CAPI_ENABLED=1 only after Test Events validation.")
        test_code = (options["test_event_code"] or config["test_event_code"]).strip()
        sent = failed = 0
        for event in rows:
            updated, ok = process_event(event.pk, test_event_code=test_code)
            if ok:
                sent += 1
                self.stdout.write(self.style.SUCCESS(f"sent {updated.event_id}"))
            else:
                failed += 1
                self.stderr.write(f"failed {updated.event_id}: {updated.last_error}")
        self.stdout.write(f"DONE: sent={sent}, failed={failed}, test_mode={'yes' if test_code else 'no'}")
