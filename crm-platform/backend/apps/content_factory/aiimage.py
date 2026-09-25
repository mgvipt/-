"""ШІ-зображення для контент-заводу (25.09.2026): генерація й покращення кадрів/слайдів через Gemini.

Модель gemini-3.1-flash-image (та сама, що в локальному конекторі Олега). Кожна картинка платна (≈$0.04 — ОЦІНКА),
облік у AiUsage (source=content_factory.images), місячна стеля MONTH_CAP. Результат — файл у CRM (SharedLink).
Для блогів з label_ai (Wallcov) кадр позначається «ШІ-візуалізація» під час монтажу/рендеру.
"""
import base64
import json
import os
import urllib.error
import urllib.request
from secrets import token_urlsafe

MODEL = "gemini-3.1-flash-image"
SOURCE = "content_factory.images"
PRICE = (0.50, 30.0)  # $/1M токенів вхід/вихід — ОЦІНКА (≈1290 токенів на картинку ≈ $0.04)
MONTH_CAP = 10.0
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class ImageError(Exception):
    pass


def spent_month():
    from .questions import month_spent
    return month_spent(SOURCE)


def generate(prompt, aspect="9:16", ref=None, extra_parts=None):
    """prompt → (bytes, mime). ref=(bytes, mime) — редагування/покращення наявного кадру; extra_parts — референси стилю."""
    if spent_month() >= MONTH_CAP:
        raise ImageError(f"Досягнуто місячної стелі ШІ-картинок ${MONTH_CAP:.0f}.")
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ImageError("Немає GEMINI_API_KEY.")
    parts = list(extra_parts or [])
    if ref:
        parts.append({"inlineData": {"mimeType": ref[1], "data": base64.b64encode(ref[0]).decode()}})
    parts.append({"text": prompt})
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"], "imageConfig": {"aspectRatio": aspect}}}
    req = urllib.request.Request(API.format(model=MODEL), data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            resp = json.load(r)
    except urllib.error.HTTPError as e:
        raise ImageError(f"Gemini HTTP {e.code}: {e.read().decode()[:200]}") from None
    u = resp.get("usageMetadata") or {}
    tin = int(u.get("promptTokenCount") or 0)
    tout = int(u.get("candidatesTokenCount") or 0) + int(u.get("thoughtsTokenCount") or 0)
    from apps.crm.models import AiUsage
    AiUsage.objects.create(source=SOURCE, model=MODEL, in_tok=tin, out_tok=tout,
                           cost_usd=(tin * PRICE[0] + tout * PRICE[1]) / 1_000_000)
    for part in ((resp.get("candidates") or [{}])[0].get("content") or {}).get("parts", []):
        if "inlineData" in part and not part.get("thought"):
            return base64.b64decode(part["inlineData"]["data"]), part["inlineData"].get("mimeType", "image/png")
    reason = (resp.get("candidates") or [{}])[0].get("finishReason") or resp.get("promptFeedback")
    raise ImageError(f"Модель не повернула картинку ({reason}).")


def save(data, mime, name="ai-image"):
    from apps.inbox.models import SharedLink
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(mime, "png")
    return SharedLink.objects.create(token=token_urlsafe(24), filename=f"{name}.{ext}", content_type=mime, data=data)


IMPROVE_REAL = ("Покращ цей кадр як фоторедактор: світло, баланс білого, різкість, прибери шум і сміття в кадрі. "
                "НЕ змінюй фактуру, колір, блиск і малюнок декоративного покриття, предмети, композицію й ракурс. "
                "Без тексту й логотипів. Вертикальний кадр.")
IMPROVE_FREE = ("Покращ цей кадр: світло, різкість, кольори, чистота, виразність. Збережи зміст, персонажів, композицію й стиль. "
                "Без тексту й логотипів. Вертикальний кадр.")


def improve(data, mime, blog, aspect="9:16"):
    return generate(IMPROVE_REAL if blog and blog.label_ai else IMPROVE_FREE, aspect=aspect, ref=(data, mime))


def texture_prompt(prompt, material, aspect="4:5"):
    """Кадр із декоративною стіною ЗА РЕАЛЬНИМ ЗРАЗКОМ: перше зображення — фото фактури, його не можна «спрощувати»."""
    from .material_specs import spec_for
    spec = spec_for(material)
    return (f"{prompt.strip()}. The decorative wall MUST reproduce the wall finish from the first reference photo exactly: "
            f"same pattern, trowel marks, relief, sparkle/sheen and colour at true scale — do NOT render a plain painted or smooth wall. "
            f"{spec} Photorealistic, real camera, no text, no letters, no logos.")


def regenerate(prompt, blog, aspect="9:16", texture=None, material=""):
    """Новий кадр з опису. texture=(bytes, mime) — реальне фото фактури: для Wallcov стіна малюється лише за ним."""
    if texture is not None:
        return generate(texture_prompt(prompt, material, aspect), aspect=aspect, ref=texture)
    """Для інших блогів — стиль і персонажі з візуального зразка блогу."""
    rules = ""
    if blog and blog.label_ai:
        rules = (" Це ВІЗУАЛІЗАЦІЯ інтерʼєру, не фото реального обʼєкта: сучасний житловий інтерʼєр, реалістичні масштаби, "
                 "мотивоване світло. Декоративну стіну показуй спокійно, без вигаданих візерунків.")
    style, refs = "", []
    if blog is not None:
        from .visual import ref_parts, visual_text
        bible = visual_text(blog)
        if bible:
            style = " Візуальна біблія блогу (дотримуйся точно, особливо зовнішності персонажів): " + bible[:1800]
        elif blog.master_prompt:
            vis = [ln for ln in blog.master_prompt.splitlines() if ln.lower().startswith(("візуал", "герої", "про що"))]
            style = " Контекст блогу: " + " ".join(vis)[:700]
        refs = ref_parts(blog)
        if refs:
            style += " Перші зображення — референси: повтори їхній стиль малювання і тих самих персонажів, але нову сцену."
    return generate(f"{prompt.strip()}.{rules}{style} Без тексту, літер і логотипів у кадрі.", aspect=aspect, extra_parts=refs)
