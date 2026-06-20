"""
Импорт каталога товаров из Bitrix (b24-gmideas) в наш склад.
Источник — JSON, выгруженный через REST (scripts: b24_export_products.py).
Папка "!!УДАЛИТЬ" уже исключена на этапе выгрузки.

Запуск (внутри web-контейнера):
    python manage.py import_bitrix_catalog --file /tmp/b24_catalog.json            # DRY-RUN (только показать)
    python manage.py import_bitrix_catalog --file /tmp/b24_catalog.json --commit    # применить

Идемпотентно: товары/категории матчатся по bitrix_id (повторный запуск обновляет, не дублирует).
"""
import json
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.warehouse.models import Product, ProductCategory


class Command(BaseCommand):
    help = "Импорт каталога товаров из Bitrix JSON в склад"

    def add_arguments(self, parser):
        parser.add_argument("--file", default="/tmp/b24_catalog.json")
        parser.add_argument("--commit", action="store_true", help="Применить (иначе DRY-RUN)")

    def handle(self, *args, **opts):
        data = json.load(open(opts["file"], encoding="utf-8"))
        sections = {int(k): v for k, v in data["sections"].items()}
        products = data["products"]
        commit = opts["commit"]
        mode = "LIVE" if commit else "DRY-RUN"
        self.stdout.write(f"[{mode}] секций: {len(sections)}, товаров: {len(products)}")

        with transaction.atomic():
            # ── 1. Категории: создать/обновить по bitrix_id ──
            cat_by_bx = {}
            cre_c = upd_c = 0
            for bx, s in sections.items():
                obj, created = ProductCategory.objects.get_or_create(
                    bitrix_id=bx, defaults={"name": s["name"]})
                if not created and obj.name != s["name"]:
                    obj.name = s["name"]; obj.save(update_fields=["name"])
                    upd_c += 1
                cre_c += int(created)
                cat_by_bx[bx] = obj

            # ── 2. Родители категорий (второй проход) ──
            for bx, s in sections.items():
                parent_bx = s.get("parent")
                obj = cat_by_bx[bx]
                new_parent = cat_by_bx.get(parent_bx) if parent_bx else None
                if obj.parent_id != (new_parent.id if new_parent else None):
                    obj.parent = new_parent; obj.save(update_fields=["parent"])

            # ── 3. Товары: создать/обновить по bitrix_id ──
            cre_p = upd_p = 0
            for p in products:
                cat = cat_by_bx.get(p["section_id"]) if p.get("section_id") else None
                defaults = {
                    "name": p["name"][:255],
                    "price": round(p["price"], 2),
                    "currency": p.get("currency", "UAH"),
                    "unit": (p.get("measure") or "шт")[:16],
                    "is_active": p.get("active", True),
                    "category": cat,
                    "sku": f"B24-{p['bitrix_id']}",
                }
                obj, created = Product.objects.get_or_create(
                    bitrix_id=p["bitrix_id"], defaults=defaults)
                if created:
                    cre_p += 1
                else:
                    changed = [f for f, v in defaults.items() if getattr(obj, f) != v
                               and f not in ("category",)] or (obj.category_id != (cat.id if cat else None))
                    if changed:
                        for f, v in defaults.items():
                            setattr(obj, f, v)
                        obj.save()
                        upd_p += 1

            self.stdout.write(self.style.SUCCESS(
                f"Категории: +{cre_c} новых, ~{upd_c} обновлено | "
                f"Товары: +{cre_p} новых, ~{upd_p} обновлено"))

            if not commit:
                self.stdout.write(self.style.WARNING("DRY-RUN — откат транзакции. Добавь --commit для записи."))
                transaction.set_rollback(True)
