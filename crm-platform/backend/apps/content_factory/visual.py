"""Візуальний зразок блогу (25.09.2026): приклад мультика/ролика → стиль, персонажі, оточення, рух і темп.

Олег дає приклад (відео з «Джерел» або файл-картинку/відео). Gemini описує: стиль малювання, палітру, кожного
персонажа (зовнішність, одяг, риси — для однаковості), оточення, рух камери, темп і текст на екрані; для відео — секунди
найкращих кадрів з героями. Ці кадри вирізаються ffmpeg і зберігаються як референси (до 6): їх отримує ШІ-художник разом
з описом, тож персонажі й стиль повторюються від кадру до кадру. ≈$0.01–0.03 за приклад.
"""
import base64
import os
import shutil
import tempfile

from .models import Blog

MAX_REFS = 6
PROMPT = """Це приклад, у якому стилі має бути контент блогу. Опиши візуальну «біблію», щоб художник-ШІ повторював її.
Відповідай ЛИШЕ JSON:
{"style":"стиль малювання/зйомки (2D/3D, лінії, текстури, освітлення), 1–3 речення",
 "palette":"основні кольори",
 "characters":[{"name":"імʼя або роль","look":"зовнішність, вік, статура, одяг, кольори, характерні риси — детально, щоб намалювати однаково"}],
 "environment":"оточення/локації, 1–2 речення",
 "motion":"рух камери й персонажів, монтаж (крупність, зміни планів), 1–2 речення",
 "pacing":"темп: скільки кадрів, тривалість плану, як побудований гачок",
 "text_style":"як виглядає текст на екрані (якщо є)",
 "key_frames":[{"t":секунда,"who":"хто в кадрі"}]}
key_frames — до 4 найкращих кадрів, де чітко видно персонажів (для картинки — порожній список)."""


def analyze(blog, data, mime):
    from .reels import WORK, _gemini, _light_copy, _run
    is_video = mime.startswith("video/")
    os.makedirs(WORK, exist_ok=True)
    folder = tempfile.mkdtemp(dir=WORK)
    try:
        src = os.path.join(folder, "src")
        with open(src, "wb") as f:
            f.write(data)
        if is_video:
            with open(_light_copy(src, folder), "rb") as f:
                part = {"inlineData": {"mimeType": "video/mp4", "data": base64.b64encode(f.read()).decode()}}
        else:
            part = {"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode()}}
        r = _gemini([part, {"text": PROMPT}], max_tokens=3000)
        r = r if isinstance(r, dict) else (r[0] if isinstance(r, list) and r else {})
        refs = []
        if is_video:
            for n, k in enumerate((r.get("key_frames") or [])[:4]):
                try:
                    out = os.path.join(folder, f"k{n}.jpg")
                    _run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{float(k.get('t') or 0):.2f}", "-i", src,
                          "-frames:v", "1", "-vf", "scale='min(1080,iw)':-2", "-q:v", "3", out])
                    with open(out, "rb") as f:
                        refs.append((f.read(), "image/jpeg", str(k.get("who") or "")[:80]))
                except Exception:
                    continue
        else:
            refs.append((data, mime, "зразок"))
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return r, refs


def apply(blog, r, refs):
    """Зберегти біблію в блог: опис замінюється новим, референси додаються (останні MAX_REFS)."""
    from . import aiimage
    vis = {k: r.get(k) for k in ("style", "palette", "characters", "environment", "motion", "pacing", "text_style") if r.get(k)}
    blog.visual = vis
    ids = list(blog.ref_images or [])
    for data, mime, who in refs:
        ids.append({"id": aiimage.save(data, mime, f"ref-{blog.slug}").id, "who": who})
    blog.ref_images = ids[-MAX_REFS:]
    blog.save(update_fields=["visual", "ref_images", "updated_at"])
    return blog


def visual_text(blog):
    v = blog.visual or {}
    if not v:
        return ""
    chars = "; ".join(f"{c.get('name', '')}: {c.get('look', '')}" for c in (v.get("characters") or []) if isinstance(c, dict))
    parts = [("Стиль", v.get("style")), ("Палітра", v.get("palette")), ("Персонажі", chars), ("Оточення", v.get("environment")),
             ("Рух і монтаж", v.get("motion")), ("Темп", v.get("pacing")), ("Текст на екрані", v.get("text_style"))]
    return "\n".join(f"{k}: {t}" for k, t in parts if t)


def ref_parts(blog, limit=3):
    """До трьох референс-кадрів блогу для ШІ-художника (inlineData)."""
    from apps.inbox.models import SharedLink
    out = []
    for r in (blog.ref_images or [])[-limit:]:
        link = SharedLink.objects.filter(pk=r.get("id")).first()
        if link:
            out.append({"inlineData": {"mimeType": link.content_type, "data": base64.b64encode(bytes(link.data)).decode()}})
    return out
