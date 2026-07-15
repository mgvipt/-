import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from .models import Product, ShopSyncEvent


SAMPLE_CATEGORY_ID = int(os.environ.get("SHOP_SAMPLE_CATEGORY_ID", "59"))
SHOP_CATALOG_URL = os.environ.get(
    "SHOP_CATALOG_URL", "https://wallcov.com.ua/new/api/crm/catalog-products"
).rstrip("/")
CRM_PUBLIC_URL = os.environ.get("CRM_PUBLIC_URL", "https://crm.wallcovdec.com.ua").rstrip("/")


def _normal(value):
    return re.sub(r"\s+", " ", (value or "").strip())


def infer_sample_metadata(name):
    """Консервативно розбирає лише 4 ознаки комплектації; результат завжди лишається чернеткою."""
    text = _normal(name)
    low = text.lower().replace("ё", "е")
    without_board = any(x in low for x in ("без дощ", "без плаш", "без доски"))
    with_board = not without_board and any(x in low for x in ("з дощ", "с дощ", "з плаш", "с плаш", "с дос"))
    without_tint = any(x in low for x in ("без тонув", "без тонир"))
    with_tint = not without_tint and any(x in low for x in ("з тонув", "із тонув", "с тонув", "с тонир", "та тонув"))

    base = re.sub(r"\([^)]*(?:дощ|плаш|доск|тонув|тонир)[^)]*\)", "", text, flags=re.I)
    base = re.sub(r"\bтестов(?:ий|ый)\s+набір\b", "", base, flags=re.I)
    base = re.sub(r"\bтест(?:овый)?\s+набор\b", "", base, flags=re.I)
    base = _normal(base.strip(" —-–")) or text
    digest = hashlib.sha1(base.lower().encode("utf-8")).hexdigest()[:12]
    group_key = "sample-" + digest
    order = 0
    if without_board and without_tint:
        order = 1
    elif without_board and with_tint:
        order = 2
    elif with_board and without_tint:
        order = 3
    elif with_board and with_tint:
        order = 4
    variant_name = {
        1: "Без дощечки · без тонування",
        2: "Без дощечки · з тонуванням",
        3: "З дощечкою · без тонування",
        4: "З дощечкою · з тонуванням",
    }.get(order, "")
    return {
        "shop_group_key": group_key,
        "shop_parent_name": base[:255],
        "shop_slug": group_key,
        "shop_has_board": with_board if (with_board or without_board) else None,
        "shop_is_tinted": with_tint if (with_tint or without_tint) else None,
        "shop_variant_order": order,
        "shop_variant_name": variant_name,
    }


def prepare_product_for_shop(product, save=True):
    if product.category_id != SAMPLE_CATEGORY_ID:
        return product
    inferred = infer_sample_metadata(product.name)
    changed = []
    if not product.shop_managed:
        product.shop_managed = True
        changed.append("shop_managed")
    initial_variant = not product.shop_group_key and not product.shop_variant_order
    for field, value in inferred.items():
        # Автовизначення працює лише під час першого підключення товару.
        # Подальший ручний вибір менеджера (у тому числі False) не перезаписуємо.
        if initial_variant and getattr(product, field) in ("", None, 0) and value not in ("", None):
            setattr(product, field, value)
            changed.append(field)
    if not product.shop_variant_type:
        product.shop_variant_type = "sample"
        changed.append("shop_variant_type")
    if changed and save:
        product.save(update_fields=changed + ["updated_at"])
    return product


def catalog_validation_errors(product):
    errors = []
    if not product.sku.strip():
        errors.append("Немає SKU")
    if product.price <= 0:
        errors.append("Ціна повинна бути більшою за 0")
    if not product.is_active:
        errors.append("Товар вимкнений у номенклатурі")
    if not product.shop_group_key.strip():
        errors.append("Не вказана група товару")
    if not product.shop_parent_name.strip():
        errors.append("Не вказана назва покриття для покупця")
    if not product.shop_slug.strip():
        errors.append("Не вказана URL-адреса")
    if product.shop_variant_type == "sample":
        if product.shop_has_board is None or product.shop_is_tinted is None or not product.shop_variant_order:
            errors.append("Не визначена комплектація пробника")
        if not product.shop_variant_name.strip():
            errors.append("Не вказана назва комплектації")
    if not product.images.filter(is_approved=True).exists():
        errors.append("Немає затвердженого фото")
    return errors


def product_payload(product, action=None):
    product = prepare_product_for_shop(product)
    hidden = action == "hide" or not product.is_active or (
        product.shop_managed and product.category_id != SAMPLE_CATEGORY_ID
    )
    errors = catalog_validation_errors(product)
    publish = bool(product.shop_enabled and not hidden and not errors)
    images = []
    for image in product.images.filter(is_approved=True).order_by("order", "id"):
        images.append({
            "id": image.id,
            "url": f"{CRM_PUBLIC_URL}/api/products/{product.id}/image/{image.id}/",
            "alt": image.alt_text,
            "is_primary": image.is_primary,
            "variant_key": image.variant_key,
        })
    return {
        "action": "hide" if hidden else "upsert",
        "product": {
            "crm_id": product.id,
            "sku": product.sku,
            "internal_name": product.name,
            "price": str(product.price),
            "currency": product.currency,
            "unit": product.unit,
            "stock": str(product.stock()),
            "availability": "order" if product.is_drop else ("in_stock" if product.stock() > 0 else "out_of_stock"),
            "group_key": product.shop_group_key,
            "parent_name": product.shop_parent_name,
            "slug": product.shop_slug,
            "short_description": product.shop_short_description,
            "full_description": product.shop_full_description,
            "benefits": product.shop_benefits,
            "effect": product.shop_effect,
            "rooms": product.shop_rooms,
            "beginner": product.shop_beginner,
            "video_url": product.shop_video_url,
            "instruction_url": product.shop_instruction_url,
            "sort": product.shop_sort,
            "badges": product.shop_badges,
            "variant": {
                "type": product.shop_variant_type,
                "has_board": product.shop_has_board,
                "is_tinted": product.shop_is_tinted,
                "order": product.shop_variant_order,
                "name": product.shop_variant_name,
                "contents": product.shop_contents,
            },
            "seo": {
                "title": product.seo_title,
                "description": product.seo_description,
                "h1": product.seo_h1,
                "categories": product.seo_categories,
                "faqs": product.seo_faqs,
                "index": product.seo_index,
            },
            "images": images,
            "publish_requested": product.shop_enabled,
            "publishable": not errors,
            "validation_errors": errors,
            "updated_at": product.updated_at.isoformat() if product.updated_at else None,
        },
    }


@transaction.atomic
def queue_product_sync(product, action=None):
    payload = product_payload(product, action=action)
    # Стара невдала подія теж стає неактуальною: інакше після відновлення зв'язку
    # вона могла б прийти пізніше й перезаписати свіжішу версію картки.
    ShopSyncEvent.objects.filter(product=product, status__in=["pending", "failed"]).update(status="superseded")
    event = ShopSyncEvent.objects.create(product=product, action=payload["action"], payload=payload)
    desired = "hidden" if payload["action"] == "hide" else (
        "ready" if payload["product"]["publish_requested"] and payload["product"]["publishable"] else "draft"
    )
    Product.objects.filter(pk=product.pk).update(shop_status=desired, shop_sync_error="")
    return event


def deliver_event(event):
    secret = settings.SHOP_WEBHOOK_SECRET
    if not secret:
        raise RuntimeError("SHOP_WEBHOOK_SECRET не налаштований")
    envelope = {"event_uuid": str(event.event_uuid), **event.payload}
    raw = json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    timestamp = str(int(time.time()))
    signature = hmac.new(secret.encode("utf-8"), timestamp.encode("utf-8") + b"." + raw, hashlib.sha256).hexdigest()
    request = urllib.request.Request(
        f"{SHOP_CATALOG_URL}/{event.product_id}", data=raw, method="POST",
        headers={
            "Content-Type": "application/json", "Accept": "application/json",
            "X-Wallcov-Timestamp": timestamp, "X-Wallcov-Signature": signature,
        },
    )
    event.status = "processing"
    event.attempts += 1
    event.save(update_fields=["status", "attempts", "updated_at"])
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"Магазин повернув HTTP {exc.code}: {detail}") from exc
    event.status = "processed"
    event.processed_at = timezone.now()
    event.next_retry_at = None
    event.last_error = ""
    event.save(update_fields=["status", "processed_at", "next_retry_at", "last_error", "updated_at"])
    Product.objects.filter(pk=event.product_id).update(
        shop_status=body.get("status", "draft"),
        shop_last_sync_at=timezone.now(), shop_sync_error="",
        shop_remote_url=body.get("url", ""),
    )
    return body


def mark_event_failed(event, error):
    delay = min(3600, 30 * (2 ** min(event.attempts, 7)))
    event.status = "failed"
    event.last_error = str(error)[:1000]
    event.next_retry_at = timezone.now() + timedelta(seconds=delay)
    event.save(update_fields=["status", "last_error", "next_retry_at", "updated_at"])
    Product.objects.filter(pk=event.product_id).update(shop_status="error", shop_sync_error=event.last_error)


def process_pending(limit=20):
    now = timezone.now()
    events = ShopSyncEvent.objects.filter(
        status__in=["pending", "failed"],
    ).filter(next_retry_at__isnull=True).order_by("created_at", "id")[:limit]
    retry = ShopSyncEvent.objects.filter(status="failed", next_retry_at__lte=now).order_by("next_retry_at", "id")[:limit]
    merged = list(events)
    known = {event.id for event in merged}
    merged.extend(event for event in retry if event.id not in known)
    result = {"processed": 0, "failed": 0}
    for event in merged[:limit]:
        try:
            deliver_event(event)
            result["processed"] += 1
        except Exception as exc:
            mark_event_failed(event, exc)
            result["failed"] += 1
    return result


def products_needing_reconcile():
    return Product.objects.filter(shop_managed=True).filter(
        Q(shop_last_sync_at__isnull=True) | Q(shop_last_sync_at__lt=F("updated_at"))
    )
