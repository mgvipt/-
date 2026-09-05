"""Library assets reference warehouse products; never store a second selling price."""
import re
from decimal import Decimal
from django.utils import timezone

def product_id(item):
    match = re.search(r"(?:^|\s)product:(\d+)(?:\s|$)", item.tags or "")
    return int(match.group(1)) if match else None

def library_product(request, item):
    pk = product_id(item)
    if not pk:
        return None
    if not hasattr(request, "_library_products"):
        from .models import MediaLibraryItem
        from apps.warehouse.models import Product
        ids = set()
        for tags in MediaLibraryItem.objects.filter(is_active=True, tags__contains="product:").values_list("tags", flat=True):
            match = re.search(r"(?:^|\s)product:(\d+)(?:\s|$)", tags)
            if match:
                ids.add(int(match.group(1)))
        request._library_products = {
            p.id: p for p in Product.objects.filter(pk__in=ids).only("id", "name", "sku", "price", "currency", "is_active", "shop_specs", "description", "unit", "shop_parent_name", "updated_at")
        }
    p = request._library_products.get(pk)
    if not p or not p.is_active:
        return {"id": pk, "available": False}
    specs = (p.shop_specs or {}).get("cezar", {})
    return {"id": p.id, "name": p.name, "sku": p.sku, "price": str(p.price), "currency": p.currency,
            "available": p.price > 0, "price_source": "CRM", "checked": timezone.localtime(p.updated_at).strftime("%d.%m.%Y"),
            "description": p.description, "unit": p.unit, "display_name": p.shop_parent_name or p.name,
            "commercial": bool((p.shop_specs or {}).get("commercial")),
            "length": specs.get("length", 0), "height": specs.get("height", 0), "thickness": specs.get("thickness", 0)}

def cezar_message(request, items):
    """Validate the selection/price at send time, before any outbound side effect."""
    ids = {product_id(item) for item in items}
    if len(ids) != 1 or None in ids or not items:
        raise ValueError("Оберіть фото одного товару")
    info = library_product(request, items[0])
    if not info or not info.get("available") or not (info.get("length") or info.get("commercial")):
        raise ValueError("Товар або його ціна недоступні. Перевірте номенклатуру.")
    if Decimal(str(request.data.get("cezar_preview_price", "-1"))) != Decimal(info["price"]):
        raise ValueError("Ціна змінилася. Відкрийте товар знову й перевірте повідомлення.")
    if not request.data.get("cezar_include_price"):
        return ""
    def fmt(value):
        return format(Decimal(str(value)).quantize(Decimal("0.01")), "f").rstrip("0").rstrip(".").replace(".", ",")
    if info.get("commercial"):
        return f"{info['display_name']}\n{fmt(info['price'])} грн / {info['unit']}"
    length = Decimal(str(info["length"])) / 1000
    return (f"Плінтус Cezar {items[0].color_code}\nДюрополімер під фарбування\n"
            f"{fmt(info['height'])} × {fmt(info['thickness'])} мм · довжина {fmt(length)} м\n"
            f"{fmt(info['price'])} грн за планку ({fmt(Decimal(info['price']) / length)} грн/м)")
