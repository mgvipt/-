"""Автознімок платежів дня — страховка, якщо відповідальний не закрив день сам.

Час — з налаштувань (Фінанси → Знімки дня → ⚙, за замовчуванням 19:00 за Києвом).
Крон на хості кожні 15 хв (хост живе за Берліном, тому час перевіряємо тут, за Києвом).
Ідемпотентно: якщо на сьогодні знімок уже є (вручну, авто або день відкрили назад) — нічого не робить.
Надолуження: якщо сервер лежав і вчора знімка немає — закриє вчора (лише коли функція вже працювала).
  python manage.py day_close_snapshot [--dry-run] [--date YYYY-MM-DD] [--at HH:MM]
"""
from datetime import date as _date, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.finance.day_close import close_day, settings_get
from apps.finance.models import DaySnapshot, Transaction


class Command(BaseCommand):
    help = "Автознімок платежів дня (час — з налаштувань, за Києвом)"

    def add_arguments(self, parser):
        parser.add_argument("--date", help="Закрити конкретний день (YYYY-MM-DD)")
        parser.add_argument("--dry-run", action="store_true", help="Лише показати, що буде зроблено")
        parser.add_argument("--at", default="", help="Час автознімка за Києвом (HH:MM); порожньо — з налаштувань")

    def handle(self, *args, **opts):
        cfg = settings_get()
        now = timezone.localtime()
        today = now.date()
        targets = []
        if opts.get("date"):
            targets = [_date.fromisoformat(opts["date"])]
        else:
            yesterday = today - timedelta(days=1)
            if (DaySnapshot.objects.filter(date__lt=yesterday).exists()
                    and not DaySnapshot.objects.filter(date=yesterday).exists()):
                targets.append(yesterday)
            at = opts.get("at") or cfg.get("auto_time") or "19:00"
            hh, mm = (int(x) for x in at.split(":"))
            weekend_ok = cfg.get("auto_weekends", True) or today.weekday() < 5
            if weekend_ok and (now.hour, now.minute) >= (hh, mm) and not DaySnapshot.objects.filter(date=today).exists():
                targets.append(today)
        for d in targets:
            n = Transaction.objects.filter(date=d).count()
            if opts["dry_run"]:
                self.stdout.write("DRY: закрив би %s (%d операцій)" % (d, n))
                continue
            s, created = close_day(d, None, "auto")
            self.stdout.write("%s %s v%s (%d операцій)" % ("закрито" if created else "вже є", d, s.version, n))
        if not targets:
            self.stdout.write("нічого робити (%s)" % now.strftime("%d.%m %H:%M"))
