"""
Импорт остатков товаров из Bitrix (catalog.storeproduct) в наш склад.
Создаёт приходный документ BITRIX-STOCK с движениями = остаток по каждому товару.
Идемпотентно: повторный запуск удаляет прежний документ BITRIX-STOCK и создаёт заново.

    python manage.py import_bitrix_stock --file /tmp/b24_stock.json            # DRY-RUN
    python manage.py import_bitrix_stock --file /tmp/b24_stock.json --commit    # применить
"""
import json
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.warehouse.models import Product, Warehouse, StockDocument, StockMovement


class Command(BaseCommand):
    help = "Импорт остатков товаров из Bitrix JSON"

    def add_arguments(self, parser):
        parser.add_argument("--file", default="/tmp/b24_stock.json")
        parser.add_argument("--commit", action="store_true")

    def handle(self, *args, **opts):
        data = json.load(open(opts["file"], encoding="utf-8"))
        stock = data["stock"]
        commit = opts["commit"]
        mode = "LIVE" if commit else "DRY-RUN"

        wh = Warehouse.objects.filter(is_default=True).first() or Warehouse.objects.first()
        if not wh:
            wh = Warehouse.objects.create(name="Основний склад", is_default=True)

        prods = {p.bitrix_id: p for p in Product.objects.exclude(bitrix_id=None)}
        matched = [(prods[int(pid)], float(amt)) for pid, amt in stock.items()
                   if int(pid) in prods and float(amt) > 0]
        self.stdout.write(f"[{mode}] остатков в файле: {len(stock)} | сматчено товаров: {len(matched)} | склад: {wh.name}")

        with transaction.atomic():
            StockDocument.objects.filter(number="BITRIX-STOCK").delete()  # идемпотентность
            doc = StockDocument.objects.create(
                kind="in", number="BITRIX-STOCK", warehouse=wh,
                comment="Імпорт залишків з Bitrix")
            StockMovement.objects.bulk_create([
                StockMovement(document=doc, product=p, quantity=amt, price=p.cost or 0)
                for p, amt in matched])
            total = sum(a for _, a in matched)
            self.stdout.write(self.style.SUCCESS(
                f"Создано движений: {len(matched)} | сумма остатков: {round(total, 1)} ед."))
            if not commit:
                self.stdout.write(self.style.WARNING("DRY-RUN — откат. Добавь --commit."))
                transaction.set_rollback(True)
