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
                      "consumption": cons, "is_material": i == 0})
    total = sum((l["total"] for l in lines), Decimal("0"))
    mat = next((l for l in lines if l["is_material"]), None)
    colors = COLORS_BY_ID.get(material_id, COLORS.get(base, ""))
    return {"area": area, "material_id": material_id, "lines": lines, "missing": missing, "total": total,
            "material": mat, "ok": bool(mat), "colors": colors}


def short_name(name):
    s = re.split(r"[.,]\s|\s\(|,\d|\s\d+\s?кг", name or "")[0].strip()
    return (s or name or "")[:40]


def prompt_block(calc):
    """Текст для продавця: точні цифри, які він називає клієнту (сам не рахує)."""
    if not calc or not calc.get("ok"):
        return ""
    rows = ["• %s (%s) — %s %s × %s грн = %s грн" % (l["short"], l.get("role", ""), _g(l["qty"]), l["unit"],
                                                     _g(l["price"]), _g(l["total"]))
            for l in calc["lines"]]
    mat = calc["material"]
    out = ("РОЗРАХУНОК CRM на %s м² (рахувала CRM з карток каталогу — цифри точні, сам нічого не перераховуй):\n%s\n"
           "Разом: %s грн (≈ %s грн за 1 м² з усіма шарами). Лише декоративний матеріал: %s грн. "
           "Ґрунти й основа разом: %s грн.\n"
           "Жодних інших сум не складай і не рахуй — називай лише цифри з цього блоку.\n"
           "Тонування в колір клієнта сюди НЕ входить — його додає менеджер після вибору кольору. "
           "Захисного покриття в розрахунку НЕМАЄ — не називай ґрунти «захистом»."
           % (_g(calc["area"]), "\n".join(rows), _g(calc["total"]), _g(calc["total"] / Decimal(str(calc["area"]))),
              _g(mat["total"]), _g(calc["total"] - mat["total"])))
    if calc.get("colors"):
        out += "\nСторінка кольорів САМЕ цього матеріалу: %s (іншу не давай)." % calc["colors"]
    if calc["missing"]:
        out += "\nНе пораховано (у картці немає витрати): %s — скажи, що це менеджер додасть окремо." % (
            "; ".join(short_name(n) for n in calc["missing"]))
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
    return estimate(mat[0], mat[1], area)
