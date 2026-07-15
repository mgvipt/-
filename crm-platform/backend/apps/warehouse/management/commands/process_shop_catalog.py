import time

from django.core.management.base import BaseCommand

from apps.warehouse.shop_sync import process_pending, products_needing_reconcile, queue_product_sync


class Command(BaseCommand):
    help = "Надсилає чергу каталогу в магазин і регулярно звіряє зміни."

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--interval", type=int, default=30)
        parser.add_argument("--reconcile-minutes", type=int, default=15)
        parser.add_argument("--limit", type=int, default=20)

    def handle(self, *args, **opts):
        last_reconcile = 0
        while True:
            now = time.monotonic()
            if now - last_reconcile >= opts["reconcile_minutes"] * 60:
                for product in products_needing_reconcile()[:opts["limit"]]:
                    queue_product_sync(product)
                last_reconcile = now
            result = process_pending(opts["limit"])
            if result["processed"] or result["failed"]:
                self.stdout.write(f"processed={result['processed']} failed={result['failed']}")
            if not opts["watch"]:
                break
            time.sleep(max(5, opts["interval"]))
