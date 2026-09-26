"""ШІ-зображення для контент-заводу (25.09.2026): генерація й покращення кадрів/слайдів через Gemini.

Модель gemini-3.1-flash-image (та сама, що в локальному конекторі Олега). Кожна картинка платна (≈$0.067 за 1K — офіційна ціна 25.09),
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
PRICE = (0.50, 60.0)  # $/1M вхід/вихід — офіційно 25.09: картинка 1K ≈ $0.067 (ai.google.dev/gemini-api/docs/pricing)
MONTH_CAP = 10.0
# 27.09: «якісне» перемалювання інтерʼєрів — Gemini 3 Pro Image (Nano Banana Pro): гіперреалізм, точніша фактура. ≈$0.13–0.24 за кадр
MODEL_PRO = "gemini-3-pro-image"
PRICE_PRO = (2.0, 120.0)
PRICES = {MODEL: PRICE, MODEL_PRO: PRICE_PRO}
# Арт-дирекція кадру-інтерʼєру (Олег 27.09: «як дизайн інтерʼєру; якщо 3D — гіперреалістично»)
INTERIOR_ART = ("Art direction: hyperrealistic interior design visualization indistinguishable from a professional architectural photo "
                "(Corona/V-Ray quality, magazine level like AD or Elle Decoration): a finished, styled contemporary Ukrainian home interior "
                "(no construction site, no bare concrete floor, no cables, no clutter), designer furniture and decor chosen to suit the wall "
                "finish, realistic scale, straight verticals, 24–35 mm lens, soft natural daylight plus warm motivated accent lighting that "
                "reveals the sheen of the decorative wall, physically correct shadows and reflections, fine micro-detail, no CGI plastic look. "
                "If the described shot is a close-up of the wall, keep it a close-up with the same photographic quality.")
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class ImageError(Exception):
    pass


def spent_month():
    from .questions import month_spent
    return month_spent(SOURCE)


def generate(prompt, aspect="9:16", ref=None, extra_parts=None, model=None):
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
    req = urllib.request.Request(API.format(model=model or MODEL), data=json.dumps(body).encode(),
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
    AiUsage.objects.create(source=SOURCE, model=model or MODEL, in_tok=tin, out_tok=tout,
                           cost_usd=(tin * PRICES.get(model or MODEL, PRICE)[0] + tout * PRICES.get(model or MODEL, PRICE)[1]) / 1_000_000)
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


def texture_prompt(prompt, material, aspect="4:5", art=True):
    """Кадр із декоративною стіною ЗА РЕАЛЬНИМ ЗРАЗКОМ: перше зображення — фото фактури, його не можна «спрощувати»."""
    from .material_specs import apply_rules, spec_for
    spec = spec_for(material) + apply_rules(prompt, material)
    return (f"{prompt.strip()}. The decorative wall MUST reproduce the wall finish from the first reference photo exactly: "
            f"same pattern, trowel marks, relief, sparkle/sheen and colour at true scale — do NOT render a plain painted or smooth wall. "
            f"{spec} {INTERIOR_ART if art else ''} Photorealistic, real camera, no text, no letters, no logos.")


COMPOSITION = (" The LAST reference image is a shot from someone else's video: copy ONLY its camera angle, shot size/crop, subject placement "
               "and the action/pose timing. Everything else must be new and unrecognizable: different room, walls, furniture, props, hands, "
               "clothes, lighting and colours. Never copy faces, logos, text or watermarks from it.")


def _part(img):
    return {"inlineData": {"mimeType": img[1], "data": base64.b64encode(img[0]).decode()}}


def regenerate(prompt, blog, aspect="9:16", texture=None, material="", composition=None, model=None):
    """Новий кадр з опису. texture=(bytes, mime) — реальне фото фактури: для Wallcov стіна малюється лише за ним.
    composition=(bytes, mime) — кадр референсу (ремейк): беремо лише ракурс, крупність і дію, решта — нове."""
    label_txt, label_part = "", []
    if material:  # відро/банка в кадрі → справжня етикетка матеріалу з Canva
        from .material_specs import BUCKET_RX, label_for
        lab = label_for(material) if BUCKET_RX.search(prompt or "") else None
        if lab:
            label_part = [_part(lab)]
            label_txt = (" A reference image of the product LABEL is provided: any bucket/pail in the frame is a round white plastic bucket "
                         "with a white lid, and this label is printed around it EXACTLY (same design, colours, WALLCOV logo, text layout), "
                         "correctly curved around the cylinder.")
    if texture is not None:
        if composition is not None or label_part:  # порядок: фактура (перша) → етикетка → кадр референсу (остання)
            return generate(texture_prompt(prompt, material, aspect) + label_txt + (COMPOSITION if composition is not None else ""),
                            aspect=aspect, extra_parts=[_part(texture)] + label_part + ([_part(composition)] if composition is not None else []), model=model)
        return generate(texture_prompt(prompt, material, aspect), aspect=aspect, ref=texture, model=model)
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
    if composition is not None:
        refs = list(refs) + [_part(composition)]
        style += COMPOSITION
    return generate(f"{prompt.strip()}.{rules}{style} Без тексту, літер і логотипів у кадрі.", aspect=aspect, extra_parts=refs, model=model)
