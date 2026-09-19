"""Щоденна перевірка: приходи без сделки, схожі на оплату клієнта → сповіщення (19.09.2026).

    python manage.py unlinked_income_check --dry     # лише показати
    python manage.py unlinked_income_check           # надіслати сповіщення (кожен прихід — один раз)
"""
from django.core.management.base import BaseCommand

from apps.finance.unlinked import find, notify


class Command(BaseCommand):
    help = "Приходи без сделки, схожі на оплату клієнта → сповіщення відповідальному і власнику"

    def add_arguments(self, p):
        p.add_argument("--dry", action="store_true")
        p.add_argument("--days", type=int, default=14)

    def handle(self, *a, **o):
        rows = find(days=o["days"])
        self.stdout.write("Приходів без сделки, схожих на оплату клієнта: %d" % len(rows))
        for r in rows:
            self.stdout.write("  журнал #%s %s грн → сделка #%s (%s)" % (r["tx"].id, r["tx"].amount_uah, r["deal"].id, r["why"]))
        n = notify(rows, dry=o["dry"])
        self.stdout.write("Сповіщень надіслано: %d" % n)
