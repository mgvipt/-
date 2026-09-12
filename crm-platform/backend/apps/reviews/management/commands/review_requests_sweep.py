"""Відгуки: знайти посилки «Отримано», перевірити правила, записати в журнал.

Поки ReviewSettings.send_enabled=False (тексти не затверджені) — жодних повідомлень і задач, лише журнал
«відправили б». --dry-run — не надсилати навіть коли відправку увімкнуть (журнал усе одно пишеться).
За розкладом НЕ запускається — додати в crontab хоста лише разом із увімкненням відправки.
"""
from django.core.management.base import BaseCommand

from apps.reviews.services import run_sweep


class Command(BaseCommand):
    help = "Відгуки: прогін просьб (поки відправка вимкнена — лише журнал «кому б відправили»)"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Нічого не надсилати навіть при увімкненій відправці")

    def handle(self, *args, **opts):
        stats = run_sweep(force_dry=opts["dry_run"])
        self.stdout.write("reviews sweep: " + (", ".join("%s=%s" % kv for kv in sorted(stats.items())) or "нічого"))
