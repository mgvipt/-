"""Корекція кольору без ШІ (27.09.2026, рішення Олега: дві кнопки — «Корекція кольору» і «Повністю ШІ»).

Лише загальні налаштування всього кадру: баланс білого, рівні, яскравість, контраст, різкість. Пікселі фактури
не перемальовуються, тому фото лишається справжнім — мітка «ШІ-візуалізація» не потрібна. Безкоштовно.
"""
import io

from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageStat


def color_fix(data):
    """bytes фото → (bytes JPEG, "image/jpeg")."""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    # баланс білого «сірий світ» на 60%: прибирає жовтизну ламп і синяву тіні, не знебарвлюючи матеріал
    r, g, b = ImageStat.Stat(img).mean
    avg = (r + g + b) / 3
    k = [min(1.25, max(0.8, 1 + 0.6 * (avg / max(c, 1.0) - 1))) for c in (r, g, b)]
    img = Image.merge("RGB", [ch.point(lambda v, f=f: min(255, int(v * f))) for ch, f in zip(img.split(), k)])
    img = ImageOps.autocontrast(img, cutoff=(1.0, 0.1))  # тіні підтягуємо, світлі місця й бліки не вибиваємо
    lum = ImageStat.Stat(img.convert("L")).mean[0]
    if lum < 105:  # лише справді темні кадри з телефона — світліше
        img = ImageEnhance.Brightness(img).enhance(min(1.2, 115 / max(lum, 40)))
    img = ImageEnhance.Contrast(img).enhance(1.05)
    img = ImageEnhance.Color(img).enhance(1.05)
    img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=70, threshold=3))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=92)
    return out.getvalue(), "image/jpeg"


def small_jpeg(data, side=512):
    """Зменшена копія для перегляду ШІ-дизайнером (дешевше й швидше)."""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    img.thumbnail((side, side))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=80)
    return out.getvalue()
