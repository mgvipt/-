"""Тонування тест-наборів і викрасок (16.09.2026, оновлено 17.09.2026 — Олег).

Вибір на рядку ТЕСТ-НАБОРУ в угоді:
  порожньо  — колір з каталогу (він уже входить у ціну картки «з тонуванням»);
  ind       — індивідуальний колір, доплата клієнту KIT_TINT_PRICE_IND (150 ₴);
  rich      — індивідуальний НАСИЧЕНИЙ колір, доплата KIT_TINT_PRICE_RICH (від 200 ₴).
Вибір на рядку ВИКРАСКИ (викраски готуються вручну під клієнта завжди):
  порожньо  — колір з каталогу, ціна картки (150 ₴);
  s_ind     — індивідуальний колір, доплата SAMPLE_TINT_PRICE_IND (100 ₴ → разом 250 ₴).
Доплата стає ОКРЕМИМ рядком «Послуга тонування» (tint_mode = auto_ind / auto_rich / auto_s_ind),
щоб гроші йшли звичним шляхом: сума угоди, маржа, реалізація. Кількість рядка CRM веде сама; ціну рядка
менеджер може підняти вручну (насичений колір «від 200 ₴») — CRM її більше не перезаписує.
Складу за тонування набору платимо фіксовану ставку за набір (wh_views), а не 20% від рядка.

НАСИЧЕНИЙ КОЛІР (для менеджерів): рецепт колеровки від 20 мл колоранту на 250 г матеріалу — темні й яскраві
кольори (графіт, шоколад, темно-синій, смарагдовий, бордо, насичений теракотовий) або колір, який підбирають
кількома колорантами «в око» за зразком клієнта в кілька підходів. Сумніваєтесь — питайте склад: там видно рецепт.
"""
from decimal import Decimal

KIT_MODES = ("ind", "rich")
SAMPLE_MODES = ("s_ind",)
MODES = KIT_MODES + SAMPLE_MODES
PRICE_CODE = {"ind": "KIT_TINT_PRICE_IND", "rich": "KIT_TINT_PRICE_RICH", "s_ind": "SAMPLE_TINT_PRICE_IND"}
LABEL = {"ind": "індивідуальний колір", "rich": "індивідуальний насичений колір", "s_ind": "індивідуальний колір викраски"}
RICH_HINT = ("Насичений — від 20 мл колоранту на 250 г матеріалу: темні й яскраві кольори (графіт, шоколад, темно-синій, "
             "смарагд, бордо) або підбір кількома колорантами за зразком клієнта.")


def is_kit_product(product):
    low = ((product.name if product else "") or "").lower()
    return bool(product) and ("тестов" in low or "набір" in low or "набор" in low)


def is_sample_product(product):
    low = ((product.name if product else "") or "").lower()
    return bool(product) and ("викраск" in low or "выкраск" in low)


def in_test_folder(product):
    """Товар у папці тест-наборів — у самій «Тестові набори та викраски» або в її підпапці («Викраски», 17.09.2026).
    Потрібно, щоб угода лише з викрасок, як і раніше, вважалась тест-набором (воронка 22, допродаж, ЗП сайтів)."""
    cat = getattr(product, "category", None) if product is not None else None
    for _ in range(3):
        if cat is None:
            return False
        if "тестов" in (cat.name or "").lower():
            return True
        cat = cat.parent if cat.parent_id else None
    return False


def prices():
    """Ціни доплат для клієнта — живі цифри з Налаштування → Ставки співробітників (Фінмодель), одним запитом."""
    from apps.finance.models import FinModelArticle
    out = {m: Decimal("0") for m in MODES}
    for a in FinModelArticle.objects.filter(code__in=list(PRICE_CODE.values()), active=True).order_by("-id"):
        for m, code in PRICE_CODE.items():
            if a.code == code:
                try:
                    out[m] = Decimal(str(a.value or 0))
                except Exception:
                    pass
    return out


def price(mode):
    return prices().get(mode, Decimal("0"))


def options(item, pr=None):
    """Варіанти для випадайки на рядку угоди: [{"mode", "label"}] або [] (не набір і не викраска)."""
    p = item.product if item.product_id else None
    if p is None or str(item.tint_mode or "").startswith("auto"):
        return []
    pr = pr if pr is not None else prices()
    f = lambda x: ("%g" % float(x or 0))
    if is_sample_product(p):
        base = Decimal(item.price or p.price or 0)
        return [{"mode": "", "label": "колір за каталогом (%s ₴)" % f(base)},
                {"mode": "s_ind", "label": "індивідуальний колір (+%s ₴, разом %s ₴)" % (f(pr["s_ind"]), f(base + pr["s_ind"]))}]
    if is_kit_product(p):
        cat = bool(getattr(p, "shop_is_tinted", False))
        return [{"mode": "", "label": "за каталогом (у ціні набору)" if cat else "без тонування / за каталогом"},
                {"mode": "ind", "label": "індивідуальний (+%s ₴)" % f(pr["ind"])},
                {"mode": "rich", "label": "індивідуальний насичений (від %s ₴)" % f(pr["rich"]), "hint": RICH_HINT}]
    return []


def service_product():
    from apps.warehouse.models import Product
    return Product.objects.filter(name__istartswith="Послуга тонування").order_by("id").first()


def sync_lines(deal):
    """Привести рядки-доплати у відповідність до вибору на наборах/викрасках. Повертає True, якщо щось змінилось."""
    from .models import DealItem
    svc = service_product()
    changed = False
    want = {}
    for it in deal.items.all():
        m = str(it.tint_mode or "")
        if m in MODES:
            want[m] = want.get(m, Decimal("0")) + (it.quantity or Decimal("0"))
    pr = None
    for mode in MODES:
        auto = "auto_" + mode
        line = deal.items.filter(tint_mode=auto).first()
        qty = want.get(mode, Decimal("0"))
        if qty <= 0 or svc is None:
            if line is not None:
                line.delete(); changed = True
            continue
        if line is None:
            pr = pr or prices()
            DealItem.objects.create(deal=deal, product=svc, quantity=qty, price=pr[mode], cost=Decimal("0"), tint_mode=auto)
            changed = True
        elif line.quantity != qty:
            # 17.09.2026: ціну не перезаписуємо — менеджер міг поставити більшу (насичений «від 200 ₴»),
            # а нова ставка в налаштуваннях не має міняти вже озвучену клієнту суму
            line.quantity = qty
            line.save(update_fields=["quantity"])
            changed = True
    return changed
