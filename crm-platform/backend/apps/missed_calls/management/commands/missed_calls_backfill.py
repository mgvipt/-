"""Сухий прогін (типово) черги пропущених по історії дзвінків.

  python manage.py missed_calls_backfill --days 30              # DRY: лише цифри, у БД нічого не пише
  python manage.py missed_calls_backfill --from-json data.json  # DRY з вивантаження (БД не потрібна)
  python manage.py missed_calls_backfill --days 30 --apply      # ЗАПИС (лише після «ок» Олега):
        створює пункти черги з позначкою backfilled, БЕЗ задач і БЕЗ сповіщень.
"""
import json
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.missed_calls import engine


def _settings_readonly():
    """Налаштування БЕЗ створення рядка (DRY нічого не пише)."""
    from apps.missed_calls.models import MissedCallSettings
    return MissedCallSettings.objects.order_by("id").first() or MissedCallSettings()


def build_dataset(days, cfg):
    """Набір даних з БД (лише SELECT)."""
    from apps.accounts.models import User
    from apps.crm.models import Contact, Deal, Lead
    from apps.finance.models import WorkSession
    from apps.telephony.models import Call, CallQueueMember
    from apps.missed_calls.services import eligible_ids, ignored_numbers
    now = timezone.now()
    since = now - timedelta(days=days)
    calls = []
    for c in (Call.objects.filter(started_at__gte=since - timedelta(days=1))
              .values("id", "direction", "disposition", "from_number", "to_number", "line", "started_at", "contact_id")):
        ts = c.pop("started_at") or now
        c["ts"] = ts.isoformat()
        calls.append(c)
    cids = {c["contact_id"] for c in calls if c["contact_id"]}
    contacts = {cid: {"owner": owner, "last": None}
                for cid, owner in Contact.objects.filter(id__in=cids).values_list("id", "owner_id")}
    for cid, owner in (Lead.objects.filter(contact_id__in=cids, owner__isnull=False)
                       .order_by("created_at").values_list("contact_id", "owner_id")):
        contacts.setdefault(cid, {"owner": None, "last": None})["last"] = owner
    for cid, owner in (Deal.objects.filter(contact_id__in=cids, owner__isnull=False)
                       .order_by("created_at").values_list("contact_id", "owner_id")):
        contacts.setdefault(cid, {"owner": None, "last": None})["last"] = owner   # угода важливіша за лід
    active = eligible_ids()
    return {
        "now": now.isoformat(), "since": since.isoformat(), "calls": calls,
        "contacts": {str(k): v for k, v in contacts.items()},
        "sessions": [[u, s.isoformat(), e.isoformat() if e else None]
                     for u, s, e in WorkSession.objects.filter(started_at__gte=since - timedelta(days=2))
                     .values_list("user_id", "started_at", "ended_at")],
        "queue": list(CallQueueMember.objects.filter(enabled=True).order_by("position", "id").values_list("user_id", flat=True)),
        "active_ids": sorted(active),
        "users": {str(u.id): (u.get_full_name() or u.username) for u in User.objects.filter(id__in=active)},
        "ignore": sorted(ignored_numbers(cfg)),
    }


class Command(BaseCommand):
    help = "Сухий прогін черги пропущених по історії (типово нічого не пише)"
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30)
        parser.add_argument("--from-json", dest="from_json", default="")
        parser.add_argument("--apply", action="store_true", help="ЗАПИСАТИ пункти (без задач і сповіщень)")
        parser.add_argument("--work-start", default="09:00", help="лише для --from-json")
        parser.add_argument("--work-end", default="18:00", help="лише для --from-json")

    def handle(self, *args, **o):
        if o["from_json"]:
            if o["apply"]:
                raise CommandError("--apply працює лише з БД, не з JSON")
            with open(o["from_json"], encoding="utf-8") as fh:
                ds = json.load(fh)
            cal = engine.WorkCalendar(start=datetime.strptime(o["work_start"], "%H:%M").time(),
                                      end=datetime.strptime(o["work_end"], "%H:%M").time())
            sla, esc = 15, 60
        else:
            from apps.missed_calls.services import calendar
            cfg = _settings_readonly()
            ds = build_dataset(o["days"], cfg)
            cal, sla, esc = calendar(cfg), cfg.sla_minutes, cfg.escalate_minutes
        items, rep = engine.run_dataset(ds, cal, sla, esc)
        rep["open_now"] = [{"number": it.number, "line": it.line, "since": it.first_missed_at.isoformat(),
                            "calls": it.calls_count} for it in items if it.status == "open"]
        self.stdout.write(json.dumps(rep, ensure_ascii=False, indent=1, default=str))
        if not o["apply"]:
            self.stdout.write("DRY_RUN: нічого не записано")
            return
        self._apply(items)

    def _apply(self, items):
        from apps.missed_calls.models import MissedCallItem
        now = timezone.now()
        seen = set()
        for ids in MissedCallItem.objects.values_list("call_ids", flat=True):
            seen.update(ids or [])
        made = 0
        with transaction.atomic():
            for it in items:
                if set(it.call_ids) & seen:
                    continue
                MissedCallItem.objects.create(
                    phone9=it.phone9, number=it.number[:32], line=it.line, line_key=it.line_key,
                    contact_id=it.contact_id, first_call_id=it.call_ids[0], call_ids=it.call_ids,
                    calls_count=it.calls_count, first_missed_at=it.first_missed_at, last_missed_at=it.last_missed_at,
                    assignee_id=it.assignee_id, assign_reason=it.assign_reason, due_at=it.due_at,
                    first_attempt_at=it.first_attempt_at, reaction_work_min=it.reaction_work_min,
                    status=it.status, closed_at=it.closed_at, close_reason=it.close_reason,
                    closing_call_id=it.closing_call_id, escalated_at=now, backfilled=True,
                    history=[{"at": now.isoformat(), "event": "backfill"}])
                made += 1
        self.stdout.write(f"APPLY: створено {made} пунктів (без задач і сповіщень)")
