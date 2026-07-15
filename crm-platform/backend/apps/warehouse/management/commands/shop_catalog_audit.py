from collections import Counter

from django.core.management.base import BaseCommand

from apps.warehouse.models import Product
from apps.warehouse.shop_sync import (
    SAMPLE_CATEGORY_ID, catalog_validation_errors, prepare_product_for_shop, queue_product_sync,
)


class Command(BaseCommand):
    help = "Безпечний аудит каталогу магазину; без --commit нічого не змінює."

    def add_arguments(self, parser):
        parser.add_argument("--category", type=int, default=SAMPLE_CATEGORY_ID)
        parser.add_argument("--product-id", type=int)
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--commit", action="store_true")

    def handle(self, *args, **opts):
        qs = Product.objects.filter(category_id=opts["category"], is_active=True).order_by("id")
        if opts["product_id"]:
            qs = qs.filter(pk=opts["product_id"])
        if opts["limit"]:
            qs = qs[:opts["limit"]]
        rows = list(qs)
        groups = Counter()
        incomplete = 0
        queued = 0
        for product in rows:
            inferred = prepare_product_for_shop(product, save=opts["commit"])
            errors = catalog_validation_errors(inferred)
            groups[inferred.shop_group_key or "(не визначена)"] += 1
            incomplete += bool(errors)
            self.stdout.write(f"#{product.id} {product.sku} | {inferred.shop_parent_name} | "
                              f"варіант={inferred.shop_variant_order or '-'} | "
                              f"{'ГОТОВО' if not errors else '; '.join(errors)}")
            if opts["commit"]:
                queue_product_sync(inferred)
                queued += 1
        wrong_groups = {key: count for key, count in groups.items() if count != 4}
        mode = "COMMIT" if opts["commit"] else "DRY_RUN"
        self.stdout.write(self.style.SUCCESS(
            f"{mode}: товарів={len(rows)}, груп={len(groups)}, неповних={incomplete}, "
            f"груп не по 4={len(wrong_groups)}, у черзі={queued}"
        ))
        if wrong_groups:
            self.stdout.write("Групи не по 4: " + ", ".join(f"{k}={v}" for k, v in wrong_groups.items()))
