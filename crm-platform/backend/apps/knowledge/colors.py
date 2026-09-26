# -*- coding: utf-8 -*-
"""25.09.2026 (Олег): «клієнти часто називають колір не за нашою формулою, а за RAL чи NCS —
треба, щоб менеджер і наші ШІ-продавці підбирали наші кольори за цими каталогами».

Як влаштовано:
  • RAL Classic (213) і NCS (1950) лежать у довіднику ColorRef разом із кольором (hex) і Lab.
  • RAL Design у таблиці НЕ зберігаємо — його код сам описує колір (відтінок, світлота, насиченість),
    тому рахуємо формулою: «RAL 270 30 25» → Lab(L=30, C=25, H=270).
  • Наші кольори — це середній колір образка з бібліотеки (SwatchColor), рахує команда colors_index.
  • Близькість рахуємо в Lab (ΔE). Чесно кажемо рівень збігу, а не «це той самий колір»:
    до 3 — дуже близько, до 6 — близько, до 12 — схоже, далі — віддалено.
"""
import math
import re

RAL_RX = re.compile(r"\bRAL\s*[-–]?\s*(\d{4})\b", re.I)
RAL_DESIGN_RX = re.compile(r"\bRAL\s*(?:design\s*)?(\d{3})\s+(\d{1,2})\s+(\d{1,2})\b", re.I)
NCS_RX = re.compile(r"\bNCS\s*S?\s*(\d{4})\s*-\s*([A-Z]\d{2}[A-Z]|N|[A-Z])\b", re.I)
NCS_SHORT_RX = re.compile(r"\bS\s*(\d{4})\s*-\s*([A-Z]\d{2}[A-Z]|N|[A-Z])\b", re.I)

LEVELS = ((3.0, "дуже близько"), (6.0, "близько"), (12.0, "схоже"), (1e9, "віддалено"))


def level(delta):
    for limit, name in LEVELS:
        if delta <= limit:
            return name
    return "віддалено"


# ── кольорова математика (sRGB D65) ──

def hex_to_rgb(value):
    v = (value or "").lstrip("#")
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#%02X%02X%02X" % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def _srgb_to_linear(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(c):
    c = 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055
    return max(0.0, min(1.0, c)) * 255.0


def rgb_to_lab(rgb):
    r, g, b = (_srgb_to_linear(c) for c in rgb)
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    y = (r * 0.2126 + g * 0.7152 + b * 0.0722) / 1.00000
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883
    f = lambda t: t ** (1 / 3.0) if t > 0.008856 else (7.787 * t + 16 / 116.0)
    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def lab_to_rgb(lab):
    L, a, b = lab
    fy = (L + 16) / 116.0
    fx = fy + a / 500.0
    fz = fy - b / 200.0
    g = lambda t: t ** 3 if t ** 3 > 0.008856 else (t - 16 / 116.0) / 7.787
    x, y, z = g(fx) * 0.95047, g(fy) * 1.0, g(fz) * 1.08883
    r = x * 3.2406 + y * -1.5372 + z * -0.4986
    gg = x * -0.9689 + y * 1.8758 + z * 0.0415
    bb = x * 0.0557 + y * -0.2040 + z * 1.0570
    return tuple(_linear_to_srgb(c) for c in (r, gg, bb))


def delta_e(a, b):
    """ΔE76 — для підбору покриттів цього досить, зайва точність тут нічого не дає."""
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def lch_to_lab(l, c, h):
    rad = math.radians(h)
    return (float(l), c * math.cos(rad), c * math.sin(rad))


# ── розпізнавання коду у тексті ──

def parse(text):
    """Знаходить у тексті коди RAL/NCS. Повертає список словників:
    {system, code, label, lab, hex, source} — source: 'ref' (з довідника) або 'formula' (RAL Design)."""
    from .models import ColorRef
    out, seen = [], set()
    t = text or ""

    for m in RAL_DESIGN_RX.finditer(t):
        h, l, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
        code = "RAL %03d %d %d" % (h, l, c)
        if code in seen:
            continue
        seen.add(code)
        lab = lch_to_lab(l, c, h)
        out.append({"system": "ral_design", "code": code, "label": "RAL Design " + code[4:],
                    "lab": lab, "hex": rgb_to_hex(lab_to_rgb(lab)), "name": "", "source": "formula"})

    for m in RAL_RX.finditer(t):
        code = "RAL %s" % m.group(1)
        if code in seen:
            continue
        ref = ColorRef.objects.filter(system="ral", code=code).first()
        if not ref:
            continue
        seen.add(code)
        out.append({"system": "ral", "code": code, "label": code, "lab": (ref.lab_l, ref.lab_a, ref.lab_b),
                    "hex": ref.hex, "name": ref.name_uk or ref.name_en, "source": "ref"})

    for rx in (NCS_RX, NCS_SHORT_RX):
        for m in rx.finditer(t):
            code = "S %s-%s" % (m.group(1), m.group(2).upper())
            if code in seen:
                continue
            ref = ColorRef.objects.filter(system="ncs", code=code).first()
            if not ref:
                continue
            seen.add(code)
            out.append({"system": "ncs", "code": code, "label": "NCS " + code, "lab": (ref.lab_l, ref.lab_a, ref.lab_b),
                        "hex": ref.hex, "name": "", "source": "ref"})
    return out


# ── підбір ──

# у підбір не беремо те, що не є декоративним покриттям: ліпнину, плінтуси, витратні матеріали
SKIP_MATERIALS = ("Orac Decor", "Плінтуси Cezar", "Підготовка та витратні матеріали", "Майстер-класи")


def ours_for(lab, limit=5, material=None, with_all=False):
    """Наші кольори, найближчі до заданого. Повертає список із рівнем збігу."""
    from .models import SwatchColor
    qs = SwatchColor.objects.all()
    if not with_all:
        qs = qs.exclude(material__in=SKIP_MATERIALS)
    if material:
        qs = qs.filter(material=material)
    rows = []
    for s in qs:
        d = delta_e(lab, (s.lab_l, s.lab_a, s.lab_b))
        rows.append({"item_id": s.item_id, "material": s.material, "code": s.color_code,
                     "hex": s.hex, "delta": round(d, 1), "level": level(d)})
    rows.sort(key=lambda x: x["delta"])
    return rows[:limit]


def refs_for(lab, limit=3, system=None):
    """Зворотний бік: який це приблизно RAL / NCS."""
    from .models import ColorRef
    qs = ColorRef.objects.all()
    if system:
        qs = qs.filter(system=system)
    rows = []
    for r in qs.only("system", "code", "name_uk", "name_en", "hex", "lab_l", "lab_a", "lab_b"):
        d = delta_e(lab, (r.lab_l, r.lab_a, r.lab_b))
        rows.append({"system": r.system, "code": r.code, "name": r.name_uk or r.name_en,
                     "hex": r.hex, "delta": round(d, 1), "level": level(d)})
    rows.sort(key=lambda x: x["delta"])
    return rows[:limit]


_FAMILY_RX = re.compile(r"^(.*?)-([\d.,]+)$")


def _dose(code):
    m = _FAMILY_RX.match((code or "").strip())
    if not m:
        return None
    try:
        return float(m.group(2).replace(",", "."))
    except Exception:
        return None


def family(code, material=None, limit=10):
    """Сходинки насиченості того самого кольору (Олег 26.09.2026: «мені здається колір світліше,
    там одиничка може бути»). Друга частина коду — мл колоранта на 250 г: той самий префікс = той самий
    відтінок, менша цифра = світліше. Фото завжди темніше за реальну стіну, тому менеджер має бачити
    весь рядок, а не одну відповідь."""
    from .models import SwatchColor
    m = _FAMILY_RX.match((code or "").strip())
    if not m:
        return []
    qs = SwatchColor.objects.filter(color_code__istartswith=m.group(1) + "-")
    if material:
        qs = qs.filter(material=material)
    rows = [{"item_id": s.item_id, "material": s.material, "code": s.color_code, "hex": s.hex,
             "lab_l": round(s.lab_l, 1), "dose": _dose(s.color_code)} for s in qs]
    rows.sort(key=lambda r: -(r["lab_l"] or 0))
    return rows[:limit]


def by_our_code(code):
    """Наш образок за кодом кольору (FBK16-1,5 тощо)."""
    from .models import SwatchColor
    c = (code or "").strip()
    if not c:
        return None
    s = SwatchColor.objects.filter(color_code__iexact=c).first() or \
        SwatchColor.objects.filter(color_code__istartswith=c).first()
    return s


DISCLAIMER = ("Колір на екрані завжди умовний, а наші покриття ще й міняються під світлом — "
              "для рішення краще надіслати клієнту викраску в цьому кольорі.")


def prompt_block(text, limit=3):
    """Готовий шматок для підказки агенту/ШІ-РОПу, якщо в тексті згаданий RAL або NCS."""
    found = parse(text)
    if not found:
        return ""
    lines = ["ПІДБІР ЗА КАТАЛОГОМ КОЛЬОРІВ (порахувала CRM, цифри не вигадувати):"]
    for f in found[:3]:
        name = (" · %s" % f["name"]) if f.get("name") else ""
        lines.append("%s%s — наші найближчі:" % (f["label"], name))
        rows = ours_for(f["lab"], limit=limit)
        if not rows:
            lines.append("  (наших образків ще немає в базі)")
        for r in rows:
            lines.append("  • %s %s — збіг %s" % (r["material"], r["code"], r["level"]))
        if rows:
            fam = [x for x in family(rows[0]["code"], rows[0]["material"]) if x["code"] != rows[0]["code"]]
            if fam:
                lines.append("  Той самий відтінок, інша насиченість (цифра після дефіса = мл колоранта "
                             "на 250 г, менша = світліше): %s"
                             % ", ".join("%s" % x["code"] for x in fam))
    lines.append(DISCLAIMER)
    return "\n".join(lines)
