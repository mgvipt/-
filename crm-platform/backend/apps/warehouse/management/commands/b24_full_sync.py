# -*- coding: utf-8 -*-
"""
ПОЛНАЯ синхронизация каталога товаров из Bitrix24 → Wallcov-CRM.

Тянет напрямую из REST (вебхук), без промежуточных JSON:
  1. Пользователи Б24 (id → имя) — для «кто создал / кто изменил»
  2. Все разделы (70) → ProductCategory (по bitrix_id, идемпотентно, с деревом parent)
  3. Все товары (1678) → Product (по bitrix_id): название, описание, раздел,
     активность, цена, валюта, ед.изм., кто создал/изменил, даты Б24
  4. Закупочные цены (purchasingPrice) — только если в Б24 задана (не затирает нулём)
  5. Картинки товаров (catalog.productImage.list батчами) → ProductImage (скачивает файлы)

Запуск (в web-контейнере):
    python manage.py b24_full_sync                  # DRY-RUN — только отчёт
    python manage.py b24_full_sync --commit          # применить
    python manage.py b24_full_sync --commit --images # применить + скачать картинки

Идемпотентно: повторный запуск обновляет, не дублирует. НИЧЕГО не удаляет —
товары, которых больше нет в Б24, помечаются is_active=False (скрыты, история цела).
"""
import os
import time
import json
import urllib.request
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.dateparse import parse_datetime
from apps.warehouse.models import Product, ProductCategory, ProductImage

WEBHOOK = os.environ.get("B24_WEBHOOK", "https://b24-gmideas.com.ua/rest/4/njz4qn7s9ifg4bm4")
IBLOCK = 24
STD_MEASURE = {"6": "м", "163": "г", "166": "кг", "796": "шт", "55": "м²", "112": "л", "113": "л",
               "5": "м", "9": "шт"}


def b24(method, payload=None, retries=3):
    """Один вызов REST Б24 (urllib) с повтором при сетевой ошибке/лимите."""
    body = json.dumps(payload or {}).encode()
    for att in range(retries):
        try:
            req = urllib.request.Request(f"{WEBHOOK}/{method}", data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read().decode())
            if d.get("error") == "QUERY_LIMIT_EXCEEDED":
                time.sleep(2); continue
            return d
        except Exception:
            if att == retries - 1:
                raise
            time.sleep(2)
    return {}


def http_get(url, timeout=60):
    """Скачать файл (картинку) по URL. Возвращает (bytes, content_type) или (None, "")."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read(), r.headers.get("Content-Type", "")
    except Exception:
        return None, ""


def b24_pages(method, payload, result_key=None):
    """Постраничная выгрузка (по 50). result_key: ключ внутри result (products/sections)."""
    out, start = [], 0
    while True:
        p = dict(payload); p["start"] = start
        d = b24(method, p)
        res = d.get("result") or []
        if result_key and isinstance(res, dict):
            res = res.get(result_key) or []
        out.extend(res)
        nxt = d.get("next")
        if not nxt:
            break
        start = nxt
    return out


class Command(BaseCommand):
    help = "Полная синхронизация каталога из Bitrix24 (разделы, товары, описания, закупки, картинки)"

    def add_arguments(self, parser):
        parser.add_argument("--commit", action="store_true", help="Применить (иначе DRY-RUN)")
        parser.add_argument("--images", action="store_true", help="Скачивать картинки товаров")

    def handle(self, *args, **opts):
        commit = opts["commit"]
        mode = "LIVE" if commit else "DRY-RUN"
        log = self.stdout.write

        # ── 1. Пользователи (id → имя) ─────────────────────────────────────
        users = {}
        for u in b24_pages("user.get", {"FILTER": {}}):
            users[str(u["ID"])] = (f"{u.get('NAME','')} {u.get('LAST_NAME','')}").strip() or f"user#{u['ID']}"
        log(f"[{mode}] пользователей Б24: {len(users)}")

        # ── 2. Разделы ─────────────────────────────────────────────────────
        sections = b24_pages("catalog.section.list",
                             {"filter": {"iblockId": IBLOCK}, "select": ["id", "name", "iblockSectionId"]},
                             "sections")
        log(f"[{mode}] разделов в Б24: {len(sections)}")

        # ── 3. Товары (основное через crm.product.list) ────────────────────
        prods = b24_pages("crm.product.list", {
            "filter": {},
            "select": ["ID", "NAME", "DESCRIPTION", "SECTION_ID", "ACTIVE", "PRICE",
                        "CURRENCY_ID", "MEASURE", "CREATED_BY", "MODIFIED_BY",
                        "DATE_CREATE", "TIMESTAMP_X"],
        })
        log(f"[{mode}] товаров в Б24: {len(prods)}")

        # ── 4. Закупочные цены (catalog.product.list) ──────────────────────
        cost_map = {}
        for cp in b24_pages("catalog.product.list",
                            {"filter": {"iblockId": IBLOCK},
                             "select": ["id", "iblockId", "purchasingPrice"]},
                            "products"):
            pp = cp.get("purchasingPrice")
            if pp:
                cost_map[int(cp["id"])] = round(float(pp), 2)
        log(f"[{mode}] закупочных цен в Б24: {len(cost_map)}")

        if not commit:
            b24_ids = {int(p["ID"]) for p in prods}
            have = set(Product.objects.exclude(bitrix_id=None).values_list("bitrix_id", flat=True))
            missing = b24_ids - have
            gone = have - b24_ids
            with_desc = sum(1 for p in prods if (p.get("DESCRIPTION") or "").strip())
            log(f"[DRY-RUN] новых товаров будет создано: {len(missing)}")
            log(f"[DRY-RUN] есть у нас, но нет в Б24 (→ скроем is_active=False): {len(gone)}")
            log(f"[DRY-RUN] товаров с описанием: {with_desc}")
            log("Добавь --commit чтобы применить.")
            return

        # ═══ LIVE ═══
        with transaction.atomic():
            # категории
            cat_by_bx, cre_c = {}, 0
            for s in sections:
                bx = int(s["id"])
                obj, created = ProductCategory.objects.get_or_create(bitrix_id=bx, defaults={"name": s["name"]})
                if not created and obj.name != s["name"]:
                    obj.name = s["name"]; obj.save(update_fields=["name"])
                cre_c += int(created)
                cat_by_bx[bx] = obj
            for s in sections:  # родители вторым проходом
                parent_bx = s.get("iblockSectionId")
                obj = cat_by_bx[int(s["id"])]
                new_parent = cat_by_bx.get(int(parent_bx)) if parent_bx else None
                if obj.parent_id != (new_parent.id if new_parent else None):
                    obj.parent = new_parent; obj.save(update_fields=["parent"])
            log(f"категории: создано {cre_c}, всего {len(cat_by_bx)}")

            # товары
            existing = {p.bitrix_id: p for p in Product.objects.exclude(bitrix_id=None)}
            cre_p = upd_p = 0
            b24_ids = set()
            for p in prods:
                bx = int(p["ID"]); b24_ids.add(bx)
                sec = p.get("SECTION_ID")
                cat = cat_by_bx.get(int(sec)) if sec else None
                vals = {
                    "name": (p.get("NAME") or "")[:255],
                    "description": (p.get("DESCRIPTION") or "").strip(),
                    "price": round(float(p.get("PRICE") or 0), 2),
                    "currency": (p.get("CURRENCY_ID") or "UAH")[:8],
                    "unit": STD_MEASURE.get(str(p.get("MEASURE")), "шт")[:16],
                    "is_active": (p.get("ACTIVE") == "Y"),
                    "category": cat,
                    "b24_created_by": users.get(str(p.get("CREATED_BY")), "")[:120],
                    "b24_modified_by": users.get(str(p.get("MODIFIED_BY")), "")[:120],
                    "b24_created_at": parse_datetime(p.get("DATE_CREATE") or "") or None,
                    "b24_modified_at": parse_datetime(p.get("TIMESTAMP_X") or "") or None,
                }
                if bx in cost_map:
                    vals["cost"] = cost_map[bx]  # только если в Б24 есть закупка
                obj0 = existing.get(bx)
                if obj0 is not None and obj0.components.exists():
                    vals.pop("cost", None)  # набір: cost авто із компонентів
                obj = existing.get(bx)
                if obj is None:
                    vals["sku"] = f"B24-{bx}"
                    Product.objects.create(bitrix_id=bx, **vals)
                    cre_p += 1
                else:
                    changed = []
                    for f, v in vals.items():
                        cur = getattr(obj, f)
                        if f == "category":
                            cur = obj.category
                        if f in ("price", "cost") and cur is not None and v is not None:
                            if float(cur) != float(v):
                                changed.append(f)
                        elif cur != v:
                            changed.append(f)
                    if changed:
                        for f in changed:
                            setattr(obj, f, vals[f])
                        obj.save()
                        upd_p += 1
            # исчезнувшие из Б24 → скрыть (НЕ удалять)
            gone = [pid for pid in existing if pid not in b24_ids]
            hidden = Product.objects.filter(bitrix_id__in=gone, is_active=True).update(is_active=False)
            log(f"товары: создано {cre_p}, обновлено {upd_p}, скрыто (нет в Б24) {hidden}")

        # ── 5. Картинки (вне транзакции — сеть) ────────────────────────────
        if opts["images"]:
            img_dir = "warehouse_photos/products"
            os.makedirs(img_dir, exist_ok=True)
            have_imgs = set(ProductImage.objects.values_list("b24_file_id", flat=True))
            dl = skip = 0
            pmap = {p.bitrix_id: p for p in Product.objects.exclude(bitrix_id=None)}
            all_ids = sorted(pmap.keys())
            # батчами по 50 через batch API
            for i in range(0, len(all_ids), 50):
                chunk = all_ids[i:i + 50]
                cmd = {f"i{pid}": f"catalog.productImage.list?productId={pid}" for pid in chunk}
                d = b24("batch", {"halt": 0, "cmd": cmd})
                res = (d.get("result") or {}).get("result") or {}
                for key, val in res.items():
                    pid = int(key[1:])
                    for img in (val or {}).get("productImages", []):
                        fid = int(img["id"])
                        if fid in have_imgs:
                            skip += 1; continue
                        url = img.get("detailUrl") or img.get("downloadUrl")
                        if not url:
                            continue
                        content, ct = http_get(url)
                        if not content:
                            continue
                        ext = "jpg"
                        if "png" in ct: ext = "png"
                        elif "webp" in ct: ext = "webp"
                        fname = f"{img_dir}/{pid}_{fid}.{ext}"
                        with open(fname, "wb") as fh:
                            fh.write(content)
                        ProductImage.objects.create(product=pmap[pid], file_path=fname, b24_file_id=fid)
                        dl += 1
                if i % 500 == 0:
                    log(f"  картинки: обработано товаров {i + len(chunk)}/{len(all_ids)}, скачано {dl}")
            log(f"картинки: скачано {dl}, уже были {skip}")

        log(self.style.SUCCESS("SYNC DONE"))
