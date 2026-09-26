# -*- coding: utf-8 -*-
"""Розрахунок матеріалу на обʼєм для продавця CRM (22.09.2026, Олег).

«Всі дані для прорахунку завжди тягнути з картки каталогу — так ми не будемо щоразу переобучати ШІ-агента.»
«Щоб ШІ сам рахував усі обʼєми — вчимо його працювати автономно.» «Фондо потрібне — сума з усім пирогом.»

Рахує КОД, не ШІ: кількість = площа × «Витрата на 1 м²» з картки товару, ціна — з картки.
Позиція без витрати в картці в розрахунок не йде (і про це видно в missing) — нічого не вигадуємо.
Склад «пирога» (який ґрунт під який матеріал) — як у реальних сделках менеджерів за вересень 2026.
Тонування в колір для обʼєму ціни в каталозі не має — додає менеджер."""
import math
import re
from decimal import ROUND_CEILING, Decimal

PRIMER_DEEP = 1927        # Primer Deep 1 (UPr XZ 1001_100) — ґрунт-концентрат, пакет 100 г
QUARTZ = 1582             # Quartz Primer 2 — ґрунт з кварцом під фактурні
FONDO = 1572              # Fondo Decoro — грунт-фарба під Velvet Luna
SECOND_LAYER = 1583       # Second Layer — основа під тонкошарові

# як називати позицію клієнту (щоб ШІ не назвав ґрунт «захистом»)
ROLE = {PRIMER_DEEP: "ґрунт глибокого проникнення", QUARTZ: "ґрунт з кварцом",
        FONDO: "ґрунт-фарба під вельвет", SECOND_LAYER: "основа під тонкошарове покриття"}
# сторінка кольорів — кодом, а не «з памʼяті» ШІ
COLORS = {"facture": "https://wallcov.com.ua/p/pattera/", "velvet_luna": "https://wallcov.com.ua/p/velvet-luna/"}
COLORS_BY_ID = {1623: "https://wallcov.com.ua/p/pisochky/", 1617: "https://wallcov.com.ua/p/pisochky/",
                1618: "https://wallcov.com.ua/p/pisochky/", 1619: "https://wallcov.com.ua/p/pisochky/",
                1620: "https://wallcov.com.ua/p/pisochky/", 1610: "https://wallcov.com.ua/p/mokryi-shovk/",
                1611: "https://wallcov.com.ua/p/mokryi-shovk/", 1642: "https://wallcov.com.ua/p/mokryi-shovk/",
                1643: "https://wallcov.com.ua/p/mokryi-shovk/", 1630: "https://wallcov.com.ua/p/mokryi-shovk/",
                1631: "https://wallcov.com.ua/p/mokryi-shovk/", 1650: ""}

# матеріал → ґрунти під нього
BASE = {
    "facture": (PRIMER_DEEP, QUARTZ),
    "velvet_luna": (PRIMER_DEEP, FONDO),
    "thin": (PRIMER_DEEP, SECOND_LAYER),
}

# (регулярка, картка товару, «пиріг») — перевіряються по черзі, конкретніші вище
_M = [
    (r"velvet\s*lux|вельвет\s*л[юу]кс|велвет\s*л[юу]кс", 1650, "facture"),
    (r"(?:velvet\s*luna|вельвет|велвет|луна)[^.\n]{0,25}(?:gold|голд|золот)|(?:gold|золот)\w*\s+(?:velvet|вельвет)", 1648, "velvet_luna"),
    (r"(?:velvet\s*luna|вельвет|велвет|луна)[^.\n]{0,25}(?:bianco|б[іи]ан|б[іе]л)", 1647, "velvet_luna"),
    (r"velvet\s*luna|вельвет|велвет|\bлун[аиі]\b", 1649, "velvet_luna"),
    (r"pattera\s*grose|грос[еє]|gros[es]", 1640, "facture"),
    (r"pattera\s*micro|патер\w*\s*м[іи]кро|гротто|грото|м[іи]кро\s*патер", 1641, "facture"),
    (r"pattera|патер|травертин|марморин|арт.?бетон", 1639, "facture"),
    (r"галате|galate|galathe|галатэ", 1623, "thin"),
    (r"mermi\w*\s*mat|мерм\w*\s*мат", 1631, "thin"),
    (r"mermi|мерм[іи]", 1630, "thin"),
    (r"celestial\s*mat|селест\w*\s*мат|целест\w*\s*мат", 1615, "thin"),
    (r"celestial|селест|целест", 1614, "thin"),
    (r"eleganti[^.\n]{0,15}(?:gold|золот)", 1618, "thin"),
    (r"eleganti[^.\n]{0,15}(?:pearl|перл)", 1617, "thin"),
    (r"eleganti[^.\n]{0,15}(?:bianco|б[іе]л)", 1619, "thin"),
    (r"eleganti|елеганті|элеганти|елеганти", 1620, "thin"),
    (r"(?:sirena|сирен|шовк|шелк)[^.\n]{0,20}(?:gold|золот)", 1643, "thin"),
    (r"(?:sirena|сирен|шовк|шелк)[^.\n]{0,20}(?:pearl|перл)", 1642, "thin"),
    (r"(?:sirena|сирен|шовк|шелк)[^.\n]{0,20}(?:bianco|б[іе]л)", 1611, "thin"),
    (r"sirena|сирен|мокр\w*\s*(?:шовк|шелк)|шовк|шелк", 1610, "thin"),
]
MATERIALS = [(re.compile(rx, re.I), pid, base) for rx, pid, base in _M]

AREA_RX = re.compile(
    r"(\d{1,4}(?:[.,]\d{1,2})?)\s*(?:м2|м²|м\.?\s?кв|кв\.?\s?м|квадрат\w*|кв\b|кв\.|метр\w*|м\b|m2|m²|sqm)", re.I)
MIN_AREA, MAX_AREA = 1, 2000


def find_area(client_texts):
    """Площа з повідомлень КЛІЄНТА — від найсвіжішого. None, якщо не називав."""
    for t in reversed(client_texts or []):
        for m in AREA_RX.finditer(t or ""):
            v = float(m.group(1).replace(",", "."))
            if MIN_AREA <= v <= MAX_AREA:
                return v
    return None


def find_material(texts, extra=""):
    """(product_id, base) матеріалу, про який мова, — з найсвіжішого повідомлення, де він названий.
    extra — підказка «звідки прийшов» (напр. матеріал реклами), коли в розмові матеріал не звучав."""
    for t in list(reversed(texts or [])) + [extra or ""]:
        low = (t or "").lower()
        for rx, pid, base in MATERIALS:
            if rx.search(low):
                return pid, base
    return None


def _qty(area, cons, unit):
    q = Decimal(str(area)) * Decimal(cons)
    if (unit or "").strip(". ").lower() in ("шт", "уп", "компл", "набір", "набор", "пак"):
        return Decimal(math.ceil(q))
    return (q * 10).to_integral_value(rounding=ROUND_CEILING) / 10   # кг/л — вгору до 0,1


def _g(x):
    return ("%.2f" % float(x)).rstrip("0").rstrip(".")


def estimate(material_id, base, area):
    """Розрахунок «пирога» на площу — лише з карток каталогу."""
    from apps.warehouse.models import Product
    ids = [material_id] + list(BASE.get(base) or ())
    prods = {p.id: p for p in Product.objects.filter(id__in=ids, is_active=True)}
    lines, missing = [], []
    for i, pid in enumerate(ids):
        p = prods.get(pid)
        if p is None:
            continue
        cons = p.consumption_per_m2
        if not cons or cons <= 0 or not p.price or p.price <= 0:
            missing.append(p.name)
            continue
        q = _qty(area, cons, p.unit)
        lines.append({"product_id": p.id, "name": p.name, "short": short_name(p.name), "qty": q, "unit": p.unit,
                      "role": "декоративний матеріал" if i == 0 else ROLE.get(p.id, "ґрунт"),
                      "price": Decimal(p.price), "total": (q * Decimal(p.price)).quantize(Decimal("0.01")),
                      "consumption": cons, "density": p.density_kg_l, "is_material": i == 0})
    taras = tara_lines(lines)
    total = sum((l["total"] for l in lines + taras), Decimal("0"))
    mat = next((l for l in lines if l["is_material"]), None)
    colors = COLORS_BY_ID.get(material_id, COLORS.get(base, ""))
    # base потрібен для тонування (фактурні рахуються інакше, ніж тонкошарові)
    return {"area": area, "material_id": material_id, "base": base, "lines": lines, "missing": missing,
            "tara_lines": taras, "total": total, "material": mat, "ok": bool(mat), "colors": colors}


def short_name(name):
    s = re.split(r"[.,]\s|\s\(|,\d|\s\d+\s?кг", name or "")[0].strip()
    return (s or name or "")[:40]


def prompt_block(calc):
    """Текст для продавця: точні цифри, які він називає клієнту (сам не рахує)."""
    if not calc or not calc.get("ok"):
        return ""
    taras = calc.get("tara_lines") or []
    rows = ["• %s (%s) — %s %s × %s грн = %s грн" % (l["short"], l.get("role", ""), _g(l["qty"]), l["unit"],
                                                     _g(l["price"]), _g(l["total"]))
            for l in list(calc["lines"]) + list(taras)]
    mat = calc["material"]
    tara_total = sum((l["total"] for l in taras), Decimal("0"))
    out = ("РОЗРАХУНОК CRM на %s м² (рахувала CRM з карток каталогу — цифри точні, сам нічого не перераховуй):\n%s\n"
           "Разом: %s грн (≈ %s грн за 1 м² з усіма шарами). Лише декоративний матеріал: %s грн. "
           "Ґрунти й основа разом: %s грн. Тара під розлив: %s грн.\n"
           "Жодних інших сум не складай і не рахуй — називай лише цифри з цього блоку.\n"
           "Захисного покриття в розрахунку НЕМАЄ — не називай ґрунти «захистом»."
           % (_g(calc["area"]), "\n".join(rows), _g(calc["total"]), _g(calc["total"] / Decimal(str(calc["area"]))),
              _g(mat["total"]), _g(calc["total"] - mat["total"] - tara_total), _g(tara_total)))
    t = calc.get("tint") or tint_estimate(calc, None)
    if t and not t["need_color"]:
        out += ("\nТОНУВАННЯ у колір %s%s (тонуємо %s — разом %s кг, тара: %s): послуга %s грн + колорант %s мл × 6 грн = %s грн. "
                "Разом з тонуванням: %s грн."
                % (calc.get("color") or "—", "" if calc.get("color_in_library") else " (цього коду немає в бібліотеці —"
                   " рахую за кодом, який назвав клієнт)", t["what"], _g(t["kg"]), t["tara_parts"],
                   _g(t["service"]), _g(t["ml"]),
                   _g(t["toner"]), _g(calc["total"] + t["total"])))
    elif t and calc.get("color"):
        out += ("\nТОНУВАННЯ у колір %s: послуга %s грн; у цього кольору формула на два шари, тому точну суму "
                "колоранта порахує менеджер — так і скажи клієнту, суму не вигадуй."
                % (calc["color"], _g(t["service"])))
    elif t:
        out += ("\nТОНУВАННЯ: послуга %s грн; колорант рахується ЗА КОДОМ КОЛЬОРУ з нашої палітри "
                "(друга частина коду — мл колоранта на 250 г, напр. FBK03-12), тому спитай код кольору — "
                "тоді назвеш точну суму. Свою цифру за колорант НЕ вигадуй." % _g(t["service"]))
    if calc.get("colors"):
        out += "\nСторінка кольорів САМЕ цього матеріалу: %s (іншу не давай)." % calc["colors"]
    if calc["missing"]:
        out += "\nНе пораховано (у картці немає витрати): %s — скажи, що це менеджер додасть окремо." % (
            "; ".join(short_name(n) for n in calc["missing"]))
    return out




# ───────── тонування: регламент Wallcov (Notion «Як розрахувати вартість тонування», 27.07.2025) ─────────
# Фактурні: <5 кг — 100 грн за тару; ≥5 кг — вага × 20 грн/кг.
# Тонкошарові й фарби: 100 грн за КОЖНУ тару. Тонер: 6 грн/мл у всіх випадках.
# Обʼєм тонера точно відомий лише після підбору кольору → беремо норму з прикладів регламенту
# (3 кг — 12 мл, 8 кг — 20 мл, 6,5 кг — 24 мл) ≈ 4 мл/кг; насичений колір — більше.
TINT_SERVICE_MIN = Decimal("100")     # мінімальна послуга за тару
TINT_PER_KG = Decimal("20")           # фактурні від 5 кг
TINT_MIN_KG = Decimal("5")
# Кількість колоранта — З КОДУ КОЛЬОРУ (Олег, 22.09.2026): у коді «03-1» друга цифра — мл колоранта
# на 250 г матеріалу. На 1 кг множимо на 4: «03-1» → 4 мл/кг, «03-20» → 80 мл/кг, «03-05» (це 0,5) → 2 мл/кг.
TONER_UAH_ML = Decimal("6")
ML_PER_250G_TO_KG = Decimal("4")
TARA_FALLBACK_DENSITY = Decimal("1.3")   # середня щільність наших матеріалів, поки в картці немає своєї
TARA_KG = Decimal("5")                # запасний варіант, якщо в картці немає щільності
TARA_RX = re.compile(r"тара\s*([\d.,]+)\s*(?:л\b|л\.|$|·)", re.I)   # «Тара 3.4л», «ТАРА 2,2»
TARA_SKIP_RX = re.compile(r"шприц|флакон|мите\s*відро", re.I)   # це не тара під розлив
TINT_PRODUCT = 1311                   # картка «Послуга тонування» (ціну ставить менеджер)

# Код кольору з бібліотеки CRM: «FBK16-1,5», «CSK 01-21», «MSK03-5», «SLK12-0,1» —
# друга частина = мл колоранта на 250 г матеріалу (Олег 22.09.2026). На 1 кг множимо на 4.
COLOR_RX = re.compile(r"(?<![\wА-Яа-яЇїІіЄєҐґ])([A-ZА-Я]{2,4})?\s?(\d{1,3})\s*[-–—]\s*(\d{1,3}(?:[.,]\d{1,3})?)(?!\s*\d)",
                      re.I)
_COLOR_WORDS = re.compile(r"колір|кольор|цвет|відтін|оттен|палітр|палитр|код", re.I)
# складений код на два шари: FBK20/08-0,15/2,5 — суму колоранта рахує менеджер
COMPOUND_RX = re.compile(r"([A-ZА-Я]{0,4}\s?\d{1,3}(?:/\d{1,3})+\s*[-–—]\s*[\d.,]+(?:/[\d.,]+)+)", re.I)
# матеріал у бібліотеці кольорів (розділ «Кольори») за «пирогом» і карткою товару
LIB_MATERIAL = {1639: "Патера", 1640: "Патера", 1641: "Патера", 1650: "Патера",
                1649: "Вельвет Луна", 1648: "Вельвет Луна", 1647: "Вельвет Луна",
                1623: "Перламутрові піщинки", 1617: "Перламутрові піщинки", 1618: "Перламутрові піщинки",
                1619: "Перламутрові піщинки", 1620: "Перламутрові піщинки",
                1610: "Мокрий шовк", 1611: "Мокрий шовк", 1642: "Мокрий шовк", 1643: "Мокрий шовк",
                1630: "Мокрий шовк", 1631: "Мокрий шовк", 1614: "Мокрий шовк", 1615: "Мокрий шовк"}


def color_dose(tail):
    """Друга частина коду → мл колоранта на 250 г. «1»→1 · «20»→20 · «1,5»→1,5 · «0,05»→0,05 · «05»→0,5."""
    t = str(tail or "").strip().replace(",", ".")
    try:
        if "." not in t and t.startswith("0") and len(t) > 1:
            t = "0." + t[1:]
        d = Decimal(t)
    except Exception:
        return None
    return d if 0 < d <= 100 else None


def lib_color(num, tail, material_id=None):
    """Звіряємо код з бібліотекою кольорів CRM: повертає (код з бібліотеки, доза) або None."""
    try:
        from apps.inbox.models import MediaLibraryItem
        rx = r"(^|[^0-9])0*%s[[:space:]]*-[[:space:]]*%s$" % (str(num).lstrip("0") or "0",
                                                             re.escape(str(tail)).replace(",", "[.,]"))
        qs = MediaLibraryItem.objects.filter(section="colors", is_active=True, color_code__iregex=rx)
        mat = LIB_MATERIAL.get(material_id)
        item = (qs.filter(material__iexact=mat).first() if mat else None) or qs.first()
        if item is None:
            return None
        code = item.color_code or ""
        if "/" in code:      # складений код на два шари (FBK20/08-0,15/2,5) — рахує менеджер
            return (code, None)
        d = color_dose(code.split("-")[-1])
        return (code, d) if d is not None else None
    except Exception:
        return None


def find_color(msgs, material_id=None):
    """Код кольору з повідомлень КЛІЄНТА (найсвіжіший) → (код, доза на 250 г, чи знайдено в бібліотеці)."""
    for m in reversed(msgs or []):
        if m.get("role") != "client":
            continue
        t = m.get("text") or ""
        mc = COMPOUND_RX.search(t)
        if mc:
            return mc.group(1).strip(), None, True
        for mt in COLOR_RX.finditer(t):
            if not (_COLOR_WORDS.search(t) or mt.group(1) or len(t.strip()) <= 24):
                continue
            dose = color_dose(mt.group(3))
            if dose is None:
                continue
            found = lib_color(mt.group(2), mt.group(3), material_id)
            if found:
                return found[0], found[1], True      # доза None = складений код (два шари)
            code = "%s%s-%s" % ((mt.group(1) or "").upper(), mt.group(2), mt.group(3))
            return code, dose, False
    return None


def tara_sizes():
    """Обʼєми тар з каталогу (Тара 1л, 2,2, 3.4л, 5,5л…) — у літрах, за зростанням."""
    from apps.warehouse.models import Product
    out = set()
    for name in Product.objects.filter(is_active=True, name__istartswith="тара").values_list("name", flat=True):
        m = TARA_RX.search(name or "")
        if m:
            try:
                v = Decimal(m.group(1).replace(",", "."))
            except Exception:
                continue
            if v > 0:
                out.add(v)
    return sorted(out)


def tara_products():
    """Картки тари з каталогу: {обʼєм у літрах: картка}. Лише нова тара — без шприців, флаконів
    і митих відер (менеджери у справжніх сделках ставлять саму тару: ТАРА 2,2, Тара 3.4л, 5,5л…)."""
    from apps.warehouse.models import Product
    out = {}
    for p in Product.objects.filter(is_active=True, name__istartswith="тара").order_by("id"):
        if TARA_SKIP_RX.search(p.name or "") or not p.price or p.price <= 0:
            continue
        m = TARA_RX.search(p.name or "")
        if not m:
            continue
        try:
            v = Decimal(m.group(1).replace(",", "."))
        except Exception:
            continue
        if v > 0:
            out.setdefault(v, p)
    return out


def tara_pick(kg, density, sizes=None):
    """(скільки тар, обʼєм однієї тари в літрах, чи рахували по щільності)."""
    kg = Decimal(str(kg))
    if not density or Decimal(str(density)) <= 0:
        return int(math.ceil(kg / TARA_KG)) or 1, None, False
    litres = (kg / Decimal(str(density))).quantize(Decimal("0.01"), rounding=ROUND_CEILING)
    sizes = sizes if sizes is not None else tara_sizes()
    if not sizes:
        return int(math.ceil(kg / TARA_KG)) or 1, None, False
    for v in sizes:
        if litres <= v:
            return 1, v, True
    big = sizes[-1]
    return int(math.ceil(litres / big)) or 1, big, True


def tara_for(kg, density, sizes=None):
    """Скільки тар і яких треба на цю вагу: літри = вага ÷ щільність, беремо найменшу тару, в яку влазить.
    Без щільності в картці рахуємо запасним способом — одна тара на кожні 5 кг."""
    n, litres, ok = tara_pick(kg, density, sizes)
    if not ok or litres is None:
        return n, "", False
    return n, ("%s л" % _g(litres)) if n == 1 else ("%s × %s л" % (n, _g(litres))), True


def tara_lines(lines):
    """Тара під розлив — окремі позиції в накладну (Олег 26.09.2026: «тару ти не додав»).
    На кожну позицію в кг/л беремо найменшу тару з каталогу, в яку влазить обʼєм."""
    prods = tara_products()
    if not prods:
        return []
    sizes = sorted(prods)
    agg = {}
    for l in tinted_lines({"lines": lines}):
        dens = l.get("density")
        if not dens or Decimal(str(dens)) <= 0:
            dens = TARA_FALLBACK_DENSITY   # щільності ще немає в картці — беремо середню по наших матеріалах
        n, litres, ok = tara_pick(l["qty"], dens, sizes)
        if not ok or litres not in prods:
            continue
        agg[litres] = agg.get(litres, 0) + n
    out = []
    for litres in sorted(agg):
        p = prods[litres]
        q = Decimal(agg[litres])
        out.append({"product_id": p.id, "name": p.name, "short": (p.name or "").strip(), "qty": q,
                    "unit": p.unit or "шт", "role": "тара під розлив", "price": Decimal(p.price),
                    "total": (q * Decimal(p.price)).quantize(Decimal("0.01")),
                    "consumption": None, "density": None, "is_material": False, "is_tara": True})
    return out


def tinted_lines(calc):
    """Що саме тонуємо (Олег 22.09.2026): декоративний матеріал І підкладка — Quartz Primer / Fondo Decoro /
    Second Layer. Primer Deep (ґрунт-концентрат глибокого проникнення) НЕ тонується."""
    out = []
    for l in (calc.get("lines") or []):
        if l.get("product_id") == PRIMER_DEEP:
            continue
        if (l.get("unit") or "").strip(". ").lower() not in ("кг", "л"):
            continue
        out.append(l)
    return out


def tint_estimate(calc, dose250=None):
    """Тонування обʼєму. Тонуємо матеріал + підкладку.
    Послуга: фактурні — до 5 кг 100 грн, від 5 кг вага × 20 грн/кг; тонкошарові — 100 грн за КОЖНУ тару (≈5 кг).
    Колорант: доза з коду кольору (мл на 250 г) × 4 × вага, ціна 6 грн/мл.
    Без коду кольору суму колоранта не рахуємо (need_color=True)."""
    if not calc or not calc.get("ok"):
        return None
    lines = tinted_lines(calc)
    if not lines:
        return None
    kg = sum((Decimal(str(l["qty"])) for l in lines), Decimal("0"))
    sizes = tara_sizes()
    tara, by_density, parts = 0, True, []
    for l in lines:
        n, label, ok = tara_for(l["qty"], l.get("density"), sizes)
        tara += n
        by_density = by_density and ok
        parts.append("%s — %s" % (l["short"], label or ("%s тар" % n)))
    if calc.get("base") == "facture":
        service = TINT_SERVICE_MIN if kg < TINT_MIN_KG else (kg * TINT_PER_KG)
    else:
        service = TINT_SERVICE_MIN * tara
    service = service.quantize(Decimal("0.01"))
    out = {"kg": kg, "service": service, "tara": tara, "need_color": dose250 is None,
           "ml": None, "toner": None, "total": None, "dose250": dose250,
           "what": ", ".join(l["short"] for l in lines),
           "tara_parts": "; ".join(parts), "tara_by_density": by_density}
    if dose250 is not None:
        ml = (kg * Decimal(dose250) * ML_PER_250G_TO_KG).quantize(Decimal("0.1"), rounding=ROUND_CEILING)
        out["ml"] = ml
        out["toner"] = (ml * TONER_UAH_ML).quantize(Decimal("0.01"))
        out["total"] = (service + out["toner"]).quantize(Decimal("0.01"))
    return out


_RU = re.compile(r"[ыэъё]|\b(что|сколько|нужно|давайте|сразу|цвет|хочу|мне|можно|спасибо|пожалуйста|как)\b", re.I)
_UA = re.compile(r"[іїєґ]", re.I)


def language_hint(client_text):
    """Клієнт пише російською → явна вказівка (Haiku інакше збивається на українську через укр. блоки)."""
    t = client_text or ""
    if _RU.search(t) and not _UA.search(t):
        return "МОВА: клієнт пише РОСІЙСЬКОЮ — відповідай повністю російською, без українських слів."
    return ""


def shown_to_client(msgs, calc):
    """Чи клієнт уже бачив цю суму (у нашій попередній відповіді) — лише тоді можна оформлювати обʼєм."""
    if not calc or not calc.get("ok"):
        return False
    tot = _g(calc["total"])
    variants = {tot, "{:,}".format(int(calc["total"])).replace(",", " "), "{:,}".format(int(calc["total"])).replace(",", "\u00a0")}
    return any(any(v in (m.get("text") or "") for v in variants) for m in msgs[:-1] if m.get("role") == "agent")


def for_dialog(msgs, extra=""):
    """msgs = [{"role": "client"|"agent", "text"}] → розрахунок або None (немає площі чи матеріалу)."""
    area = find_area([m["text"] for m in msgs if m.get("role") == "client"])
    if not area:
        return None
    mat = find_material([m["text"] for m in msgs], extra)
    if not mat:
        return None
    calc = estimate(mat[0], mat[1], area)
    col = find_color(msgs, mat[0])
    calc["color"], dose = (col[0], col[1]) if col else ("", None)
    calc["color_in_library"] = bool(col and col[2])
    calc["tint"] = tint_estimate(calc, dose)
    return calc
