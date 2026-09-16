"""Тонування тест-наборів (16.09.2026, Олег).

Галочка на рядку тест-набору в угоді:
  порожньо  — колір з каталогу (він уже входить у ціну картки «з тонуванням»);
  ind       — індивідуальний колір, доплата клієнту KIT_TINT_PRICE_IND;
  rich      — насичений колір (довгий підбір), доплата KIT_TINT_PRICE_RICH.
Доплата стає ОКРЕМИМ рядком «Послуга тонування» в угоді (позначка tint_mode = auto_ind / auto_rich),
щоб гроші йшли звичним шляхом: сума угоди, маржа, реалізація. Цей рядок веде CRM — руками не чіпаємо.
Складу за таке тонування платимо фіксовану ставку за набір (wh_views), а не 20% від рядка.
"""
from decimal import Decimal

MODES = ("ind", "rich")
PRICE_CODE = {"ind": "KIT_TINT_PRICE_IND", "rich": "KIT_TINT_PRICE_RICH"}
LABEL = {"ind": "індивідуальний колір", "rich": "насичений колір"}


def price(mode):
    """Ціна доплати для клієнта — жива цифра з Налаштування → Ставки співробітників (Фінмодель)."""
    from apps.finance.models import FinModelArticle
    a = FinModelArticle.objects.filter(code=PRICE_CODE.get(mode, ""), active=True).order_by("id").first()
    try:
        return Decimal(str(a.value or 0)) if a else Decimal("0")
    except Exception:
        return Decimal("0")


def service_product():
    from apps.warehouse.models import Product
    return Product.objects.filter(name__istartswith="Послуга тонування").order_by("id").first()


def sync_lines(deal):
    """Привести рядки-доплати у відповідність до галочок на наборах. Повертає True, якщо щось змінилось."""
    from .models import DealItem
    svc = service_product()
    changed = False
    want = {}
    for it in deal.items.all():
        m = str(it.tint_mode or "")
        if m in MODES:
            want[m] = want.get(m, Decimal("0")) + (it.quantity or Decimal("0"))
    for mode in MODES:
        auto = "auto_" + mode
        line = deal.items.filter(tint_mode=auto).first()
        qty = want.get(mode, Decimal("0"))
        if qty <= 0 or svc is None:
            if line is not None:
                line.delete(); changed = True
            continue
        p = price(mode)
        if line is None:
            DealItem.objects.create(deal=deal, product=svc, quantity=qty, price=p, cost=Decimal("0"), tint_mode=auto)
            changed = True
        elif line.quantity != qty or line.price != p:
            line.quantity = qty; line.price = p
            line.save(update_fields=["quantity", "price"])
            changed = True
    return changed
