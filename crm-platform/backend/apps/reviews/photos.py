"""Фото відгуків: перевірка і пересохранення без EXIF/геолокації (Pillow)."""
import hashlib
import io

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 2_000_000
MAX_PIXELS = 12_000_000
FORMATS = {"JPEG", "MPO", "PNG", "WEBP"}


def _jpeg(image, quality):
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=quality, optimize=True)  # без exif= → жодних метаданих
    return out.getvalue()


def process_photo(raw: bytes) -> dict:
    """Повертає {data, thumb, width, height, sha256}. ValueError — зрозумілий текст для клієнта."""
    if not raw:
        raise ValueError("Порожнє фото")
    if len(raw) > MAX_BYTES:
        raise ValueError("Фото завелике (до 2 МБ після стиснення)")
    try:
        with Image.open(io.BytesIO(raw)) as check:
            if check.format not in FORMATS:
                raise ValueError("Підтримуються фото JPG, PNG або WebP")
            if check.width * check.height > MAX_PIXELS:
                raise ValueError("Фото більше 12 Мп")
            check.verify()
        with Image.open(io.BytesIO(raw)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError):
        raise ValueError("Не вдалося прочитати фото. Оберіть JPG, PNG або WebP")
    full = image.copy()
    full.thumbnail((1600, 1600))
    thumb = image.copy()
    thumb.thumbnail((480, 480))
    return {"data": _jpeg(full, 84), "thumb": _jpeg(thumb, 80), "width": full.width, "height": full.height,
            "sha256": hashlib.sha256(raw).hexdigest()}
