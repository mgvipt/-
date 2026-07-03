"""
Импорт закупочных цен (себестоимости) из приходных накладных Bitrix.
Источник — JSON {elementId: {cost, currency}} (b24_export_cost.py).
elementId == Product.bitrix_id.

    python manage.py import_bitrix_cost --file /tmp/b24_cost.json            # DRY-RUN
    python manage.py import_bitrix_cost --file /tmp/b24_cost.json --commit    # применить
"""
import json
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.warehouse.models import Product


class Command(BaseCommand):
    help = "Импорт закупочных цен из Bitrix (приходные накладные)"

    def add_arguments(self, parser):
        parser.add_argument("--file", default="/tmp/b24_cost.json")
        parser.add_argument("--commit", action="store_true")

    def handle(self, *args, **opts):
        data = json.load(open(opts["file"], encoding="utf-8"))
        commit = opts["commit"]
        mode = "LIVE" if commit else "DRY-RUN"
        prods = {p.bitrix_id: p for p in Product.objects.exclude(bitrix_id=None)}
        upd = 0
        skipped = 0
        with transaction.atomic():
            for eid, v in data.items():
                p = prods.get(int(eid))
                if not p:
                    skipped += 1
                    continue
                if p.components.exists():
                    continue  # набір: cost = Σ компонентів (авто), імпортом не чіпаємо
                cost = round(float(v["cost"]), 2)
                if float(p.cost or 0) != cost:
                    p.cost = cost
                    p.save(update_fields=["cost"])
                    upd += 1
            self.stdout.write(self.style.SUCCESS(
                f"[{mode}] закупок в файле: {len(data)} | обновлено: {upd} | "
                f"не сматчено (папка !!УДАЛИТЬ): {skipped}"))
            if not commit:
                self.stdout.write(self.style.WARNING("DRY-RUN — откат. Добавь --commit."))
                transaction.set_rollback(True)
