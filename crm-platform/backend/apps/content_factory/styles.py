"""Стиль тексту на рилсах (24.09.2026): пресети, стиль з референсу, «наш блог».

Референс-картинка (обкладинка ролика з «Натхнення» / наш ролик) → Gemini описує, ЯК зроблено текст: тип шрифту,
жирність, колір, обводка, плашка, де стоїть, великі літери. Ми підбираємо найближчий встановлений шрифт з кирилицею
(Montserrat, Inter, Roboto, Open Sans, DejaVu). Референс-відео (з TG-групи/Drive) — ще й темп і будова ролика
(скільки кадрів, довжина, який гачок), щоб наш ролик повторив структуру, але з нашими кадрами й фактами.
Чужий текст і кадри не копіюються — лише прийоми оформлення й ритм.
"""
import base64
import os
import subprocess
import urllib.request

from .models import FeedItem, ReelStyle

FONTS = {  # тип шрифту з аналізу → встановлена родина
    "geometric": "Montserrat", "grotesk": "Inter", "neutral": "Roboto", "humanist": "Open Sans", "default": "DejaVu Sans",
}
WEIGHTS = ["Regular", "Medium", "SemiBold", "Bold", "ExtraBold", "Black"]
PRESETS = [
    {"name": "Класичний: біла жирна з плашкою", "font": "DejaVu Sans", "weight": "Bold", "size": 68, "box": True,
     "box_color": "#000000", "box_opacity": 0.45, "position": 0.70},
    {"name": "Великий заголовок: Montserrat, обводка", "font": "Montserrat", "weight": "ExtraBold", "size": 84, "box": False,
     "stroke": 7, "stroke_color": "#000000", "upper": True, "position": 0.45},
    {"name": "Біла плашка: Inter, чорний текст", "font": "Inter", "weight": "Bold", "size": 62, "color": "#111111",
     "box": True, "box_color": "#FFFFFF", "box_opacity": 0.92, "position": 0.78},
    {"name": "Мінімал: Roboto знизу", "font": "Roboto", "weight": "Medium", "size": 58, "box": False, "stroke": 3,
     "stroke_color": "#000000", "position": 0.84},
]


def ensure_presets():
    for p in PRESETS:
        ReelStyle.objects.get_or_create(name=p["name"], origin=ReelStyle.Origin.PRESET, defaults=p)


def font_file(family, weight):
    """Шлях до файлу шрифту через fontconfig; якщо такої жирності немає — найближча."""
    for w in [weight] + [x for x in reversed(WEIGHTS) if x != weight]:
        try:
            r = subprocess.run(["fc-match", "-f", "%{file}|%{family}", f"{family}:style={w}"], capture_output=True, text=True)
        except FileNotFoundError:  # немає fontconfig — лишаємо DejaVu
            break
        path, _, fam = (r.stdout or "").partition("|")
        if path and family.split()[0].lower() in fam.lower():
            return path
    return "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _hex(c, alpha=None):
    c = (c or "#FFFFFF").lstrip("#")[:6] or "FFFFFF"
    return f"0x{c}" + (f"@{alpha:.2f}" if alpha is not None else "")


def drawtext(style, textfile):
    """Фільтр ffmpeg drawtext для стилю (без сторонніх залежностей)."""
    s = style or ReelStyle(**PRESETS[0])
    parts = [f"fontfile={font_file(s.font, s.weight)}", f"textfile={textfile}", f"fontcolor={_hex(s.color)}",
             f"fontsize={s.size}", "line_spacing=14", "x=(w-text_w)/2", f"y=h*{s.position:.2f}-text_h/2"]
    if s.stroke:
        parts += [f"borderw={s.stroke}", f"bordercolor={_hex(s.stroke_color)}"]
    if s.box:
        parts += ["box=1", f"boxcolor={_hex(s.box_color, s.box_opacity)}", "boxborderw=26"]
    if not s.box and not s.stroke:  # без плашки й обводки текст губиться на світлій стіні — мʼяка тінь
        parts += ["shadowcolor=0x000000@0.65", "shadowx=3", "shadowy=3"]
    return "drawtext=" + ":".join(parts)


STYLE_PROMPT = """Подивись, як оформлено ТЕКСТ на кадрі вертикального ролика (не сам зміст). Опиши стиль для відтворення.
Відповідай ЛИШЕ JSON: {"font_kind":"geometric|grotesk|neutral|humanist|default","weight":"Regular|Medium|SemiBold|Bold|ExtraBold|Black",
"color":"#RRGGBB","stroke":0-10,"stroke_color":"#RRGGBB","box":true/false,"box_color":"#RRGGBB","box_opacity":0-1,
"position":0-1 (де по вертикалі центр тексту),"upper":true/false,"size_rel":"small|medium|large|huge","notes":"коротко українською: що характерне"}.
Якщо тексту на кадрі немає — {"no_text":true}."""

STRUCTURE_PROMPT = """Це вертикальний ролик-референс. Опиши його будову, щоб зняти схожий ролик з ІНШИМИ кадрами й текстом.
Відповідай ЛИШЕ JSON: {"total_sec":число,"beats":[{"sec":тривалість,"purpose":"гачок|проблема|показ|доказ|заклик|інше","text_words":к-сть слів на екрані}],
"hook":"який прийом у перші 2 с (без переказу чужого тексту)","pace":"повільний|середній|швидкий","notes":"що робить ролик сильним, коротко"}.
Плюс поле "style" з описом оформлення тексту в такому ж форматі: """ + STYLE_PROMPT.split("Відповідай ЛИШЕ JSON: ")[1]

SIZES = {"small": 52, "medium": 64, "large": 78, "huge": 92}


def _gemini(parts):
    from .reels import _gemini as call
    return call(parts, max_tokens=2000)


def _to_style(d, name, origin, source_url=""):
    if not isinstance(d, dict) or d.get("no_text"):
        return None
    weight = d.get("weight") if d.get("weight") in WEIGHTS else "Bold"
    try:
        pos = max(0.1, min(0.9, float(d.get("position") or 0.7)))
        op = max(0.0, min(1.0, float(d.get("box_opacity") or 0.5)))
        stroke = max(0, min(10, int(d.get("stroke") or 0)))
    except (TypeError, ValueError):
        pos, op, stroke = 0.7, 0.5, 0
    return ReelStyle.objects.create(
        name=name[:120], origin=origin, source_url=source_url[:2000], font=FONTS.get(d.get("font_kind"), "Montserrat"),
        weight=weight, size=SIZES.get(d.get("size_rel"), 70), color=str(d.get("color") or "#FFFFFF")[:9],
        stroke=stroke, stroke_color=str(d.get("stroke_color") or "#000000")[:9], box=bool(d.get("box")),
        box_color=str(d.get("box_color") or "#000000")[:9], box_opacity=op, position=pos, upper=bool(d.get("upper")),
        notes=str(d.get("notes") or "")[:300])


def from_image_url(url, name, origin=ReelStyle.Origin.REFERENCE):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        img, ctype = r.read(), r.headers.get("Content-Type", "image/jpeg")
    d = _gemini([{"inlineData": {"mimeType": ctype.split(";")[0], "data": base64.b64encode(img).decode()}},
                 {"text": STYLE_PROMPT}])
    return _to_style(d, name, origin, url)


def from_feed_item(item):
    """Обкладинка ролика з «Натхнення» → стиль тексту."""
    if not item.preview_url:
        raise ValueError("У цього ролика немає обкладинки.")
    return from_image_url(item.preview_url, f"Як у @{item.username}")


def from_video_asset(asset):
    """Референс-відео з TG-групи/Drive → стиль тексту + будова ролика."""
    import shutil
    import tempfile
    from .reels import WORK, _light_copy, fetch_original
    os.makedirs(WORK, exist_ok=True)
    folder = tempfile.mkdtemp(dir=WORK)
    try:
        with open(_light_copy(fetch_original(asset, folder), folder), "rb") as f:
            light = f.read()
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    d = _gemini([{"inlineData": {"mimeType": "video/mp4", "data": base64.b64encode(light).decode()}},
                 {"text": STRUCTURE_PROMPT}])
    d = d if isinstance(d, dict) else {}
    st = _to_style(d.get("style") or {}, f"Референс: {asset.file_name or asset.caption[:40] or asset.id}",
                   ReelStyle.Origin.REFERENCE, asset.link) or ReelStyle.objects.create(
        name=f"Референс: {asset.file_name or asset.id}"[:120], origin=ReelStyle.Origin.REFERENCE, source_url=asset.link[:2000])
    st.structure = {k: d.get(k) for k in ("total_sec", "beats", "hook", "pace", "notes") if d.get(k) is not None}
    st.save(update_fields=["structure"])
    return st


def our_blog(limit=3):
    """«Наш блог»: обкладинки наших найпереглянутіших роликів → один стиль (перший, де знайдено текст)."""
    for item in FeedItem.objects.filter(is_own=True).exclude(preview_url="").order_by("-views")[:limit]:
        st = from_image_url(item.preview_url, "Наш блог", ReelStyle.Origin.BLOG)
        if st:
            ReelStyle.objects.filter(origin=ReelStyle.Origin.BLOG).exclude(pk=st.pk).delete()
            return st
    raise ValueError("Не знайшов тексту на обкладинках наших роликів.")
