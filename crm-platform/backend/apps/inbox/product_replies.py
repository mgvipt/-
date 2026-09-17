"""Швидкі відповіді з номенклатури (17.09.2026, Олег).

«Описи тест-наборів з цінами, привʼязані до номенклатури: додали позицію в папку — і в швидких відповідях
зʼявився опис». Як працює:
  • QuickReplyFolder — папка номенклатури → розділ швидких відповідей (тест-набори / викраски / товари).
  • Сімʼя = варіанти одного товару (група магазину shop_group_key; без групи — сам товар). Одна сімʼя — одна відповідь.
  • sync_folder(): нова сімʼя → нова відповідь (текст-заготовка, розділ, «коли»); нові варіанти → додаються до
    привʼязаних позицій; у сімʼї не лишилось активних позицій → відповідь ховається (auto_hidden), зʼявились — повертається.
    Текст, назву й «коли», які вже є, синхронізація НЕ переписує — їх редагують у Налаштуваннях.
  • {ціни} у тексті → актуальні ціни привʼязаних позицій у момент показу чи відправки (render_text).
    Змінили ціну в номенклатурі — відповідь уже з новою ціною, нічого переписувати не треба.
  • Синхронізація запускається сама, коли менеджер відкриває швидкі відповіді (не частіше ніж раз на 2 хв),
    після змін привʼязок у Налаштуваннях і командою manage.py sync_product_replies.
"""
import re
from decimal import Decimal

from django.core.cache import cache
from django.db import IntegrityError, transaction

PRICES_TAG = "{ціни}"
SYNC_EVERY_SEC = 120


def _money(x):
    x = Decimal(str(x or 0))
    s = "{:,.2f}".format(x).replace(",", " ").replace(".", ",")
    return s[:-3] if s.endswith(",00") else s


def family_key(p):
    return (p.shop_group_key or "").strip()[:80] or "p%s" % p.id


def family_title(products, kind):
    """Назва відповіді для нової сімʼї (далі її можна змінити в Налаштуваннях)."""
    p = sorted(products, key=lambda x: (x.shop_variant_order or 0, x.id))[0]
    name = (p.shop_parent_name or p.name or "").strip() if kind == "test_set" else (p.name or "").strip()
    name = re.sub(r"\([^)]*\)\s*$", "", name)                       # «(без дощечки для нанесення …)»
    name = re.sub(r"^Викраска\s*10\s*[×x]\s*30\s*см\s*·\s*", "", name, flags=re.I)
    name = re.sub(r"[\"“”«»]?\s*тестов\w*\s+набі?о?р\w*\s*", " ", name, flags=re.I)
    name = re.sub(r"\s{2,}", " ", name).strip(" —-\"“”")
    return name[:120] or "Товар #%s" % p.id


def _variant_label(p):
    board, tint = p.shop_has_board, p.shop_is_tinted
    if board is None and tint is None:
        return None
    parts = ["з дощечкою 40×40 см" if board else "без дощечки", "з тонуванням у колір з каталогу" if tint else "без тонування"]
    return ", ".join(parts)


def price_block(products, kind):
    """Рядки цін для {ціни}. Лише активні позиції; ціни — з номенклатури, доплати за колір — з «Ставки співробітників»."""
    from apps.crm import kit_tint
    active = [p for p in products if p.is_active]
    if not active:
        return "(позиції вимкнені в номенклатурі — ціну уточніть)"
    try:
        pr = kit_tint.prices()
    except Exception:
        pr = {"ind": Decimal("0"), "rich": Decimal("0"), "s_ind": Decimal("0")}
    if kind == "sample":
        p = sorted(active, key=lambda x: x.id)[0]
        base = Decimal(str(p.price or 0))
        lines = ["• викраска у колір з каталогу — %s ₴" % _money(base)]
        if pr.get("s_ind"):
            lines.append("• викраска під Ваш зразок кольору — %s ₴" % _money(base + pr["s_ind"]))
        return "\n".join(lines)
    if kind == "test_set":
        rows = sorted(active, key=lambda x: (bool(x.shop_is_tinted), bool(x.shop_has_board), x.shop_variant_order or 0, x.id))
        lines, plain = [], None
        for p in rows:
            label = _variant_label(p) or p.name
            lines.append("• %s — %s ₴" % (label, _money(p.price)))
            if p.shop_has_board is False and p.shop_is_tinted is False:
                plain = Decimal(str(p.price or 0))
        if plain is not None and pr.get("ind"):
            lines.append("• колір під Ваш зразок — +%s ₴ до набору без тонування (від %s ₴)" % (_money(pr["ind"]), _money(plain + pr["ind"])))
        if plain is not None and pr.get("rich"):
            lines.append("• насичений колір (темний або яскравий) — від +%s ₴" % _money(pr["rich"]))
        return "\n".join(lines)
    return "\n".join("• %s — %s ₴" % (p.name, _money(p.price)) for p in sorted(active, key=lambda x: (x.name, x.id)))


def price_range(products):
    vals = [Decimal(str(p.price or 0)) for p in products if p.is_active and p.price]
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    return "%s ₴" % _money(lo) if lo == hi else "%s–%s ₴" % (_money(lo), _money(hi))


def reply_kind(q, links=None):
    if not q.product_folder_id:
        return ""
    link = (links or {}).get(q.product_folder_id)
    if link is None:
        from .models import QuickReplyFolder
        link = QuickReplyFolder.objects.filter(folder_id=q.product_folder_id).first()
    return link.kind if link else "product"


def render_text(q, products=None, kind=None):
    """Текст відповіді з актуальними цінами. Без {ціни} або без позицій — текст як є."""
    text = q.text or ""
    if PRICES_TAG not in text:
        return text
    products = list(products if products is not None else q.products.all())
    if not products:
        return text.replace(PRICES_TAG, "").strip()
    return text.replace(PRICES_TAG, price_block(products, kind or reply_kind(q) or "product"))


def default_text(title, kind):
    if kind == "sample":
        return ("Викраска 10×30 см · %s — готовий зразок, який ми наносимо вручну у Вашому кольорі. Прикладете до стіни, "
                "меблів чи текстилю і побачите колір і фактуру у своєму світлі.\n\n%s\n\nВикраску готуємо під Вас, оплата наперед. "
                "Надішліть номер кольору з каталогу або фото зразка — і ми її підготуємо." % (title, PRICES_TAG))
    if kind == "test_set":
        return ("Тест-набір %s — щоб побачити колір і фактуру у своїй кімнаті ще до покупки на всю стіну.\n\n"
                "У наборі: матеріал, основа під нього, тара і відео-інструкція з нанесення.\n%s\n\n"
                "Який варіант підготувати?" % (title, PRICES_TAG))
    return "%s\n\n%s" % (title, PRICES_TAG)


def sync_folder(link, dry=False, texts=None):
    """Одна папка → відповіді. texts: {product_key: {"title","text","when_to_use","sort"}} — для першого наповнення.
    Повертає список дій (для DRY і журналу)."""
    from apps.warehouse.models import Product
    from .models import QuickReply
    texts = texts or {}
    fams = {}
    for p in Product.objects.filter(category_id=link.folder_id).order_by("id"):
        fams.setdefault(family_key(p), []).append(p)
    actions = []
    for key, ps in fams.items():
        active = [p for p in ps if p.is_active]
        q = QuickReply.objects.filter(product_folder_id=link.folder_id, product_key=key).first()
        if q is None:
            if not active:
                continue
            t = texts.get(key) or {}
            title = (t.get("title") or family_title(active, link.kind))[:120]
            actions.append(("create", key, title, [p.id for p in active]))
            if dry:
                continue
            try:
                with transaction.atomic():
                    q = QuickReply.objects.create(
                        title=title, text=t.get("text") or default_text(title, link.kind), category=link.category[:60],
                        when_to_use=t.get("when_to_use") or link.when_to_use, product_folder_id=link.folder_id,
                        product_key=key, sort=t.get("sort") or 0)
                    q.products.set(active)
            except IntegrityError:  # інший процес щойно створив цю ж відповідь
                continue
            continue
        have = set(q.products.values_list("id", flat=True))
        want = {p.id for p in active}
        if have != want:
            actions.append(("products", key, q.title, sorted(want - have), sorted(have - want)))
            if not dry:
                q.products.set(active)
        if not active and q.is_active:
            actions.append(("hide", key, q.title))
            if not dry:
                QuickReply.objects.filter(id=q.id).update(is_active=False, auto_hidden=True)
        elif active and not q.is_active and q.auto_hidden:
            actions.append(("show", key, q.title))
            if not dry:
                QuickReply.objects.filter(id=q.id).update(is_active=True, auto_hidden=False)
    # відповіді, чия сімʼя зникла з папки (позиції перенесли в іншу папку)
    gone = QuickReply.objects.filter(product_folder_id=link.folder_id, is_active=True).exclude(product_key__in=list(fams.keys()))
    for q in gone:
        actions.append(("hide", q.product_key, q.title))
        if not dry:
            QuickReply.objects.filter(id=q.id).update(is_active=False, auto_hidden=True)
            q.products.clear()
    return actions


def sync_all(dry=False, force=False):
    """Усі активні привʼязки. Без force — не частіше ніж раз на SYNC_EVERY_SEC (на процес)."""
    from .models import QuickReplyFolder
    if not force and not dry and not cache.add("qr_product_sync", 1, SYNC_EVERY_SEC):
        return []
    out = []
    for link in QuickReplyFolder.objects.filter(is_active=True).select_related("folder"):
        try:
            out.extend((link.folder.name,) + a for a in sync_folder(link, dry=dry))
        except Exception:
            continue
    return out
