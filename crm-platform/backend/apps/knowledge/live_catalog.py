"""Current commercial facts from Product/ProductComponent. No persistent price cache."""
import re
from decimal import Decimal
from django.db.models import Prefetch, Q

KIT_PATTERN = r"тестов|пробни"
GENERIC = {"wallcov", "тестовий", "тестов", "набір", "набор", "пробник", "купити", "купить", "ціна", "цена", "грн", "paint", "silver", "gold", "bianco", "pearl", "base", "фарба", "для", "что", "как", "яка", "скільки"}


def number(value):
    return format(Decimal(str(value)).normalize(), "f").replace(".", ",")


def price_text(p):
    if not p.is_active or not p.price or p.price <= 0 or (p.shop_specs or {}).get("price_status") == "quote_required":
        return "ціну уточнює менеджер"
    return number(p.price) + " " + ("грн" if p.currency == "UAH" else p.currency) + "/" + p.unit


def products():
    from apps.warehouse.models import Product, ProductComponent
    return Product.objects.filter(is_active=True).prefetch_related(Prefetch(
        "components", queryset=ProductComponent.objects.select_related("component").order_by("id")))


def selected(items=None, query=None, limit=24):
    """Known aliases plus any current name/SKU; re-read linked rows even with stale KB prefetch."""
    from .catalog import mentioned_families, placeholder_ids
    linked = set(placeholder_ids([s for i in items or [] for s in (i.title, i.text)]))
    for item in items or []:
        linked.update(item.products.values_list("id", flat=True))
    q = (query or "").casefold()
    words = {w for w in re.findall(r"[\w&-]+", q) if len(w) >= 3 and w not in GENERIC}
    terms = [term for _, term in mentioned_families(q)]
    conditions = Q(id__in=linked)
    for term in terms:
        conditions |= Q(name__icontains=term)
    for word in sorted(words):
        conditions |= Q(name__icontains=word) | Q(sku__iexact=word)
    candidates = list(products().filter(conditions))
    def score(p):
        name = p.name.casefold()
        sku = p.sku.casefold().strip()
        return (1000 if sku and sku in words else 0) + (500 if name in q else 0) + (100 if p.id in linked else 0) + sum(20 for term in terms if term in name) + sum(len(w) for w in words if w in name)
    return sorted(candidates, key=lambda p: (-score(p), p.id))[:limit]


def line(p):
    out = "• #%s %s — %s" % (p.id, p.name, price_text(p))
    if p.sku:
        out += " (артикул: " + p.sku + ")"
    if p.consumption_per_m2 and p.price > 0 and (p.shop_specs or {}).get("price_status") != "quote_required":
        out += "; витрата: %s %s/м²; матеріал: %s %s/м²" % (number(p.consumption_per_m2), p.unit, number(p.price * p.consumption_per_m2), "грн" if p.currency == "UAH" else p.currency)
    components = list(p.components.all())
    if components:
        out += "\n  Складські компоненти набору (дощечку/тонування звіряй із точною назвою варіанта): " + "; ".join("%s — %s %s%s" % (c.component.name, number(c.quantity), c.component.unit, " (неактивний: уточнити можливість продажу)" if not c.component.is_active else "") for c in components)
    elif re.search(KIT_PATTERN, p.name, re.I):
        out += "\n  Комплектацію в CRM не заповнено — не вигадуй склад, уточни у менеджера."
    return out


def prices_block(items=None, query=None, limit=24):
    rows = selected(items, query, limit)
    if not rows:
        return ""
    return "Ціни з каталогу CRM (актуальні зараз; точна позиція, валюта й одиниця обовʼязкові):\n" + "\n".join(line(p) for p in rows)


def kits_block(query=None):
    rows = list(products().filter(name__iregex=KIT_PATTERN).order_by("name", "id"))
    if query:
        relevant = {p.id for p in selected(query=query, limit=120)}
        rows = [p for p in rows if p.id in relevant]
        if not rows:
            return "Пробник: спочатку уточни матеріал. Не вигадуй ціну чи комплектацію невизначеного набору."
    # Keep exact current names available for the existing order contract. A bounded list
    # must say it is incomplete rather than imply missing kits do not exist.
    suffix = "\nСписок скорочено; інші набори уточнюй за назвою матеріалу." if len(rows) > 120 else ""
    return ("ТЕСТ-НАБОРИ В КАТАЛОЗІ (точні назви для поля order; склад з комплектації CRM):\n" + "\n".join(line(p) for p in rows[:120]) + suffix) if rows else ""
