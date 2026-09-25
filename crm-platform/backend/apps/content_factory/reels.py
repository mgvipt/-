"""Контент-завод, етапи 4–5 (24.09.2026): розмітка сцен відео і генератор рилсів з ВАШИХ нарізок.

1. Розмітка (markup): відео з «Джерел» тимчасово качається, ffmpeg робить легку копію 360p/2 кадри за секунду
   без звуку, Gemini повертає список сцен (з якої по яку секунду, що в кадрі, якість). Розмічається ОДИН раз,
   лише потрібний матеріал — у момент, коли робимо ролик. Облік: AiUsage source=content_factory.markup.
2. Сценарій (plan): Claude пише 12–16 с ролик — гачок ≤2,5 с, 3–5 кадрів, заклик; факти ЛИШЕ з бази знань;
   під кожну фразу обирає сцену з каталогу розмітки. Стіна в кадрі завжди справжня — ШІ-кадрів немає.
3. Монтаж (render): ffmpeg ріже сцени з оригіналів, 1080×1920, великі субтитри DejaVu, тиха звукова доріжка
   (музику додасте в Instagram/TikTok із їхньої ліцензованої бібліотеки). Результат — ReelDraft + файл у CRM.
Тимчасові файли — /tmp/cf_reels, видаляються після монтажу.
"""
import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import urllib.error
import urllib.request
import uuid

from django.utils import timezone

from . import questions
from .models import ReelDraft, SourceAsset, VideoScene
from .telegram import kb_facts

MARKUP_MODEL = "gemini-3.6-flash"  # 24.09: gemini-2.5-flash закрита для нових ключів
MARKUP_PRICE = (0.50, 3.00)  # $/1M вхід/вихід — ОЦІНКА з запасом (точна ціна 3.6-flash не перевірена)
MARKUP_SOURCE = "content_factory.markup"
PLAN_SOURCE = "content_factory.reels"
WORK = "/tmp/cf_reels"
MAX_SRC_BYTES = 250 * 1024 * 1024


class ReelError(Exception):
    pass


def _run(args):
    r = subprocess.run(args, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise ReelError("ffmpeg: " + (r.stderr or "")[-300:])
    return r


def fetch_original(asset, folder):
    """Оригінал у тимчасову папку (Drive — потоком, Telegram — через getFile; бот качає до 20 МБ)."""
    path = os.path.join(folder, f"src{asset.id}")
    if os.path.exists(path):
        return path
    if asset.origin == SourceAsset.Origin.DRIVE:
        from .drive import API, token
        url = f"{API}/{asset.file_id}?alt=media&supportsAllDrives=true"
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token()})
    else:
        from .telegram import _tg, tg_config
        fp = _tg("getFile", {"file_id": asset.file_id})["file_path"]
        req = urllib.request.Request(f"https://api.telegram.org/file/bot{tg_config()[0]}/{fp}")
    size = 0
    with urllib.request.urlopen(req, timeout=300) as r, open(path, "wb") as f:
        while chunk := r.read(1 << 20):
            size += len(chunk)
            if size > MAX_SRC_BYTES:
                raise ReelError(f"«{asset.file_name}» більший за 250 МБ — пропускаю.")
            f.write(chunk)
    return path


def _light_copy(src, folder):
    out = os.path.join(folder, f"light{uuid.uuid4().hex}.mp4")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-t", "90", "-an", "-vf", "scale=-2:360,fps=2",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "32", out])
    return out


def _thumb(src, second, folder):
    """Кадр із середини сцени, 240px по висоті → SharedLink (jpeg ~10–20 КБ)."""
    from secrets import token_urlsafe
    from apps.inbox.models import SharedLink
    out = os.path.join(folder, f"th{uuid.uuid4().hex}.jpg")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{second:.2f}", "-i", src, "-frames:v", "1",
          "-vf", "scale=-2:240", "-q:v", "5", out])
    with open(out, "rb") as f:
        return SharedLink.objects.create(token=token_urlsafe(24), filename="scene.jpg", content_type="image/jpeg", data=f.read())


MARKUP_PROMPT = """Це відео з обʼєкта/салону Wallcov (декоративні штукатурки). Розбий його на сцени по 1–6 секунд.
Для кожної сцени: start і end у секундах; shot — один з: "крупно", "загальний план", "процес", "результат", "людина", "інше";
what — що в кадрі українською до 15 слів (матеріал, поверхня, дія, світло, кімната); quality 1–5 (різкість, світло,
чи добре видно фактуру; 1 — розмито/темно/тремтить); tags — до 5 слів (блік, шпатель, спальня, до/після…).
Не вигадуй того, чого не видно. Відповідай ЛИШЕ JSON: {"scenes":[{"start":0,"end":3.5,"shot":"...","what":"...","quality":4,"tags":["..."]}]}"""


def _gemini(parts, max_tokens=4000):
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ReelError("Немає GEMINI_API_KEY на сервері.")
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": max_tokens,
                                 "thinkingConfig": {"thinkingLevel": "low"}}}
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MARKUP_MODEL}:generateContent",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            resp = json.load(r)
    except urllib.error.HTTPError as e:
        raise ReelError(f"Gemini HTTP {e.code}: {e.read().decode()[:200]}") from None
    usage = resp.get("usageMetadata") or {}
    tin = int(usage.get("promptTokenCount") or 0)
    tout = int(usage.get("candidatesTokenCount") or 0) + int(usage.get("thoughtsTokenCount") or 0)  # «думання» теж платне
    from apps.crm.models import AiUsage
    AiUsage.objects.create(source=MARKUP_SOURCE, model=MARKUP_MODEL, in_tok=tin, out_tok=tout,
                           cost_usd=(tin * MARKUP_PRICE[0] + tout * MARKUP_PRICE[1]) / 1_000_000)
    text = "".join(p.get("text", "") for p in ((resp.get("candidates") or [{}])[0].get("content") or {}).get("parts", []))
    return json.loads(text or "{}")


def markup(asset, folder):
    """Розмітити одне відео (один раз). Повертає кількість сцен."""
    if asset.markup_at:
        return asset.scenes.count()
    light_path = _light_copy(fetch_original(asset, folder), folder)
    with open(light_path, "rb") as f:
        light = f.read()
    data = _gemini([{"inlineData": {"mimeType": "video/mp4", "data": base64.b64encode(light).decode()}},
                    {"text": MARKUP_PROMPT}])
    VideoScene.objects.filter(asset=asset).delete()
    scenes = data if isinstance(data, list) else (data.get("scenes") or [])  # Gemini іноді віддає одразу список
    n = 0
    for s in scenes[:40]:
        if not isinstance(s, dict):
            continue
        try:
            start, end = float(s["start"]), float(s["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if end - start < 0.8:
            continue
        try:
            th = _thumb(light_path, (start + end) / 2, folder)
        except ReelError:
            th = None
        VideoScene.objects.create(asset=asset, start=start, end=end, shot=str(s.get("shot", ""))[:40],
                                  what=str(s.get("what", ""))[:300], quality=max(1, min(5, int(s.get("quality") or 3))),
                                  tags=[str(t)[:30] for t in (s.get("tags") or [])][:5], thumb=th)
        n += 1
    asset.markup_at = timezone.now()
    asset.save(update_fields=["markup_at"])
    return n


def candidates(material, limit=15, max_mb=60):
    """Відео матеріалу для розмітки: спершу вже розмічені, далі короткі (3–40 с) і не завеликі."""
    qs = SourceAsset.objects.filter(kind="video", material=material, hidden=False)
    done = list(qs.exclude(markup_at=None)[:limit])
    rest = list(qs.filter(markup_at=None, duration__gte=3, duration__lte=40, size__lte=max_mb * 1024 * 1024)
                .order_by("-duration")[:max(0, limit - len(done))])
    return done + rest


PLAN_SYSTEM = """Ти монтажер коротких вертикальних роликів Wallcov (декоративні штукатурки, Україна). Аудиторія — жінки, які роблять ремонт самі.
Зроби рилс 12–16 секунд на задану тему з ГОТОВИХ сцен (каталог нижче: id, секунди, що в кадрі, якість).
Структура: 1) гачок ≤2,5 с — найкрасивіший кадр фактури + текст-питання; 2) 3–4 кадри з відповіддю; 3) останній кадр — заклик.
Текст на екрані — українською, до 7 слів на кадр, просто, без жаргону. Пиши прямо й по-людськи, як говорить власник: факт → що робити. ЗАБОРОНЕНО шаблони на кшталт «Плануєш ремонт і не знаєш…», «Хочеш …, але боїшся/не знаєш…», «Мрієш про…», «А ти знала…», риторичні питання-пустушки й будь-які емодзі та смайли. Факти (цифри витрати, ціни, властивості) — ЛИШЕ з блоку
«База знань»; якщо точної цифри немає — не пиши її, а запропонуй написати в Direct. Бери сцени з quality ≥3, не повторюй одну сцену.
seconds кожного кадру не довше за довжину сцени. caption — підпис до рилса 2–4 речення без емодзі: конкретика про матеріал + заклик написати кодове слово в Direct.
checks — ЛИШЕ факти з тексту/підпису, які людина має звірити (цифри, властивості, ціни); технічні перевірки монтажу НЕ пиши.
Відповідай ЛИШЕ JSON: {"title":"...","caption":"...","beats":[{"text":"...","scene_id":123,"seconds":2.5}],"checks":["що перевірити людині"]}"""


def plan(topic, material, scenes, call=None, structure=None, blog=None):
    if blog is not None and blog.slug != "wallcov":  # інший блог: його майстер-промт і база знань
        from . import blogs
        facts_text, fact_titles = blogs.facts_block(blog, f"{topic} {material}")
        system = blogs.system_for(blog, PLAN_TASK_BLOG)
    else:
        facts_text, fact_titles = kb_facts(f"{topic} {material}")
        from .platform_rules import INSTAGRAM
        system = PLAN_SYSTEM + "\n\nПРАВИЛА INSTAGRAM (офіційні рекомендації Meta):\n" + INSTAGRAM
    catalog = "\n".join(f"{s.id} | {s.end - s.start:.1f}с | {s.shot} | {s.what} | q{s.quality}" for s in scenes)
    prompt = f"Тема: {topic}\nМатеріал: {material}\n\nКаталог сцен:\n{catalog}\n\nБаза знань:\n{facts_text or '(немає)'}"
    if blog is not None:
        from . import blogs as _b
        prompt += "\n\n" + _b.memory_block(blog) + MEMORY_JSON
    if structure:  # повторити будову й темп референсу — але наші кадри, наші факти, свої слова
        prompt += ("\n\nПовтори БУДОВУ й ТЕМП ролика-референсу (кількість кадрів, їх тривалість і призначення, прийом гачка), "
                   "не копіюючи його текст:\n" + json.dumps(structure, ensure_ascii=False))
    if call is None:
        from apps.crm.ai import claude_json
        call = lambda p: claude_json(p, model="claude-sonnet-4-6", max_tokens=1500, system=system, source=PLAN_SOURCE)
    r = call(prompt) or {}
    valid = {s.id: s for s in scenes}
    beats = []
    for b in r.get("beats") or []:
        try:
            sid = int(b.get("scene_id"))
        except (TypeError, ValueError):
            continue
        if sid in valid:
            sc = valid[sid]
            secs = max(1.0, min(float(b.get("seconds") or 2.5), sc.end - sc.start))
            beats.append({"text": clean_text(str(b.get("text") or ""))[:80], "scene_id": sid, "seconds": round(secs, 2)})
    if len(beats) < 3:
        raise ReelError("Замало придатних сцен для ролика — розмітьте більше відео цього матеріалу.")
    return {"title": clean_text(str(r.get("title") or topic))[:200], "caption": _clean_caption(str(r.get("caption") or "")),
            "beats": beats[:6], "checks": r.get("checks") or [], "facts": fact_titles,
            "promise": str(r.get("promise") or ""), "answers": r.get("answers_promise_id")}


PLAN_TASK_BLOG = """Ти монтажер коротких вертикальних роликів. Зроби рилс 12–25 секунд на задану тему з ГОТОВИХ сцен (каталог нижче).
Структура: гачок ≤2,5 с → 3–4 кадри по суті → фінал із закликом блогу. Текст на екрані до 7 слів на кадр.
seconds кожного кадру не довше за довжину сцени; бери сцени з quality ≥3, не повторюй.
checks — лише факти з тексту, які людина має звірити.
Відповідай ЛИШЕ JSON: {"title":"...","caption":"...","beats":[{"text":"...","scene_id":123,"seconds":2.5}],"checks":["..."]}"""

AI_PLAN_TASK = """Ти сценарист коротких вертикальних роликів. Власних відео немає — кожен кадр згенерує ШІ-художник за твоїм описом.
Зроби ролик 12–25 секунд на задану тему: 4–6 кадрів. Кадр 1 — гачок ≤2,5 с; останній — заклик блогу.
text — текст на екрані до 7 слів. seconds — 2–5. image_prompt — опис кадру для художника до 300 символів (хто/що в кадрі, дія,
ракурс, світло, стиль блогу; ті самі персонажі від кадру до кадру описуй однаково). Без тексту й літер у кадрі.
caption — підпис 2–4 речення + заклик блогу. checks — факти, які людина має звірити.
Відповідай ЛИШЕ JSON: {"title":"...","caption":"...","beats":[{"text":"...","seconds":3,"image_prompt":"..."}],"checks":["..."]}"""


_EMOJI_RX = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]")


def clean_text(text):
    """Прибрати емодзі (шрифт їх не малює — квадратик □) і зайві пробіли."""
    return " ".join(_EMOJI_RX.sub("", text or "").split())


def _clean_caption(text):
    """Підпис: без емодзі, зберігаючи абзаци."""
    return "\n".join(clean_text(line) for line in (text or "").splitlines()).strip()


def _wrap(text, width=18):
    return "\n".join(textwrap.wrap(text, width=width)) or " "


AI_LABEL = "ШІ-візуалізація"
MEMORY_JSON = ('\n\nДодатково в JSON: "promise" (що обіцяємо показати далі, одним реченням, або "") і '
               '"answers_promise_id" (id відкритої обіцянки, на яку відповідає ролик, або null).')
XFADE = {"fade": "fade", "slide": "slideleft", "zoom": "zoomin", "cut": None}
XFADE_SEC = 0.35
MOTIONS = ("zoomin", "zoomout", "none")


def _motion(kind, seconds):
    """Рух камери в кадрі (повільне наближення/віддалення) — фільтр ffmpeg з комою в кінці або порожньо."""
    frames = max(1, int(seconds * 30))
    if kind == "zoomin":
        z = f"min(1+0.10*on/{frames},1.10)"
    elif kind == "zoomout":
        z = f"max(1.10-0.10*on/{frames},1.0)"
    else:
        return ""
    return f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30,"


def render(p, folder, style=None, blog=None):
    """Змонтувати ролик за планом у заданому стилі тексту. Повертає (bytes mp4, тривалість).
    Кадр з image_id (ШІ-покращений або згенерований) — нерухоме фото з повільним наближенням; для блогів з label_ai
    на ньому пишеться «ШІ-візуалізація» (правило Wallcov: ШІ-картинку не видаємо за реальний обʼєкт)."""
    from apps.inbox.models import SharedLink
    from .styles import drawtext, font_file
    width = max(10, int(1000 / ((style.size if style else 68) * 0.56)))
    label = ""
    if blog is not None and blog.label_ai:
        lf = os.path.join(folder, "label.txt")
        with open(lf, "w") as f:
            f.write(AI_LABEL)
        label = (f",drawtext=fontfile={font_file('Inter', 'Bold')}:textfile={lf}:fontcolor=white:fontsize=34:"
                 "x=60:y=150:box=1:boxcolor=0x000000@0.55:boxborderw=14")
    segs = []
    for n, b in enumerate(p["beats"]):
        tf = os.path.join(folder, f"t{n}.txt")
        with open(tf, "w") as f:
            text = b["text"].upper() if style and style.upper else b["text"]
            f.write(_wrap(text, width))
        out = os.path.join(folder, f"seg{n}.mp4")
        secs = f"{float(b['seconds']):.2f}"
        fx = b.get("fx") or {}
        motion = _motion(fx.get("motion") or ("zoomin" if b.get("image_id") else "none"), float(b["seconds"]))
        if b.get("image_id"):
            link = SharedLink.objects.get(pk=b["image_id"])
            img = os.path.join(folder, f"img{n}")
            with open(img, "wb") as f:
                f.write(bytes(link.data))
            vf = ("scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,"
                  + motion + drawtext(style, tf) + label)
            _run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", "30", "-t", secs, "-i", img,
                  "-an", "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", out])
        else:
            sc = VideoScene.objects.select_related("asset").get(pk=b["scene_id"])
            src = fetch_original(sc.asset, folder)
            start = sc.start + float(b.get("offset") or 0)
            vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30," + motion + drawtext(style, tf)
            _run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-i", src, "-t", secs,
                  "-an", "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", out])
        segs.append(out)
    joined = os.path.join(folder, "joined.mp4")
    trans = [XFADE.get((b.get("fx") or {}).get("transition") or "cut") for b in p["beats"]]
    if any(trans[1:]):  # є переходи — склеюємо через xfade (перекодування)
        fc, prev, acc = [], "[0:v]", float(p["beats"][0]["seconds"])
        for i in range(1, len(segs)):
            d = float(p["beats"][i]["seconds"])
            if trans[i]:
                fc.append(f"{prev}[{i}:v]xfade=transition={trans[i]}:duration={XFADE_SEC}:offset={max(0.1, acc - XFADE_SEC):.3f}[v{i}]")
                acc += d - XFADE_SEC
            else:
                fc.append(f"{prev}[{i}:v]concat=n=2:v=1:a=0[v{i}]")
                acc += d
            prev = f"[v{i}]"
        args = ["ffmpeg", "-y", "-loglevel", "error"]
        for sg in segs:
            args += ["-i", sg]
        _run(args + ["-filter_complex", ";".join(fc), "-map", prev, "-c:v", "libx264", "-preset", "veryfast",
                     "-crf", "21", "-pix_fmt", "yuv420p", joined])
    else:
        lst = os.path.join(folder, "list.txt")
        with open(lst, "w") as f:
            f.write("".join(f"file '{s}'\n" for s in segs))
        _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined])
    final = os.path.join(folder, "reel.mp4")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", joined, "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
          "-shortest", "-c:v", "copy", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", final])
    dur = float(_run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", final]).stdout.strip())
    with open(final, "rb") as f:
        return f.read(), dur


def make_reel(topic, material, markup_limit=15, call=None, style=None, blog=None):
    """Повний цикл: розмітка (лише нове) → сценарій → монтаж → ReelDraft з файлом у CRM.
    Блог без власних нарізок (real_footage=False) → усі кадри генерує ШІ (make_ai_reel)."""
    from secrets import token_urlsafe
    from apps.inbox.models import SharedLink
    if blog is not None and not blog.real_footage:
        return make_ai_reel(topic, blog, call=call, style=style)
    os.makedirs(WORK, exist_ok=True)
    folder = tempfile.mkdtemp(dir=WORK)
    try:
        for a in candidates(material, limit=markup_limit):
            try:
                markup(a, folder)
            except Exception:  # одне «криве» відео не зупиняє ролик; не позначаємо як розмічене
                continue
        scenes = list(VideoScene.objects.filter(asset__material=material, quality__gte=3, asset__hidden=False)
                      .select_related("asset").order_by("-quality")[:80])
        p = plan(topic, material, scenes, call=call, structure=(style.structure if style else None) or None, blog=blog)
        data, dur = render(p, folder, style=style, blog=blog)
        link = SharedLink.objects.create(token=token_urlsafe(24), filename=f"reel-{material}.mp4",
                                         content_type="video/mp4", data=data)
        reel = ReelDraft.objects.create(title=p["title"], topic=topic, material=material, caption=p["caption"],
                                        beats=p["beats"], facts=p["facts"] + [f"Перевірити: {clean_text(str(c))}" for c in p["checks"]][:10],
                                        file=link, duration=round(dur, 1), style=style, blog=blog)
        if blog is not None:
            from . import blogs as _b
            _b.remember(blog, "reel", reel.id, reel.title, " / ".join(b["text"] for b in reel.beats)[:600],
                        promise=p.get("promise", ""), answers_id=p.get("answers"))
        return reel
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def make_ai_reel(topic, blog, call=None, style=None):
    """Рилс без власних відео: сценарій з описами кадрів → ШІ малює кожен кадр → монтаж. ≈$0.2–0.3 за ролик."""
    from secrets import token_urlsafe
    from apps.inbox.models import SharedLink
    from . import aiimage, blogs
    blogs.require_ready(blog)
    facts_text, fact_titles = blogs.facts_block(blog, topic)
    system = blogs.system_for(blog, AI_PLAN_TASK)
    if call is None:
        from apps.crm.ai import claude_json
        call = lambda p: claude_json(p, model="claude-sonnet-4-6", max_tokens=1400, system=system, source=PLAN_SOURCE)
    prompt = f"Тема: {topic}\n\nБаза знань:\n{facts_text or '(немає)'}\n\n" + blogs.memory_block(blog) + MEMORY_JSON
    if style and style.structure:
        prompt += "\n\nПовтори БУДОВУ й ТЕМП референсу (не текст):\n" + json.dumps(style.structure, ensure_ascii=False)
    try:
        r = call(prompt) or {}
    except TimeoutError:  # спільний claude_json має таймаут 45 с — одна повторна спроба
        r = call(prompt) or {}
    beats = []
    for b in (r.get("beats") or [])[:6]:
        ip = str(b.get("image_prompt") or "").strip()
        if not ip:
            continue
        data, mime = aiimage.regenerate(ip, blog)
        link = aiimage.save(data, mime, "reel-frame")
        try:
            secs = max(1.5, min(float(b.get("seconds") or 3), 5.0))
        except (TypeError, ValueError):
            secs = 3.0
        beats.append({"text": clean_text(str(b.get("text") or ""))[:80], "seconds": round(secs, 2),
                      "image_id": link.id, "ai": "generated", "prompt": ip[:600]})
    if len(beats) < 3:
        raise ReelError("ШІ не склав кадри — спробуйте іншу тему.")
    os.makedirs(WORK, exist_ok=True)
    folder = tempfile.mkdtemp(dir=WORK)
    try:
        data, dur = render({"beats": beats}, folder, style=style, blog=blog)
        link = SharedLink.objects.create(token=token_urlsafe(24), filename=f"reel-{blog.slug}.mp4", content_type="video/mp4", data=data)
        reel = ReelDraft.objects.create(title=clean_text(str(r.get("title") or topic))[:200], topic=topic, material="",
                                        caption=_clean_caption(str(r.get("caption") or "")), beats=beats,
                                        facts=fact_titles + [f"Перевірити: {clean_text(str(c))}" for c in (r.get("checks") or [])][:10],
                                        file=link, duration=round(dur, 1), style=style, blog=blog)
        blogs.remember(blog, "reel", reel.id, reel.title, " / ".join(b["text"] for b in beats)[:600],
                       promise=str(r.get("promise") or ""), answers_id=r.get("answers_promise_id"))
        return reel
    finally:
        shutil.rmtree(folder, ignore_errors=True)


# ── 25.09: кадр за кадром — покращити ШІ, перегенерувати, повернути оригінал ───────────────────────

def frame_bytes(reel, idx):
    """Поточний кадр ролика як картинка: ШІ-кадр — як є; кадр з відео — стоп-кадр 1080×1920 з оригіналу."""
    from apps.inbox.models import SharedLink
    b = reel.beats[idx]
    if b.get("image_id"):
        link = SharedLink.objects.get(pk=b["image_id"])
        return bytes(link.data), link.content_type
    sc = VideoScene.objects.select_related("asset").get(pk=b["scene_id"])
    os.makedirs(WORK, exist_ok=True)
    folder = tempfile.mkdtemp(dir=WORK)
    try:
        src = fetch_original(sc.asset, folder)
        out = os.path.join(folder, "frame.jpg")
        t = sc.start + min(float(b.get("seconds") or 1) / 2, max(0.1, sc.end - sc.start - 0.1))
        _run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", src, "-frames:v", "1",
              "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920", "-q:v", "2", out])
        with open(out, "rb") as f:
            return f.read(), "image/jpeg"
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def _set_frame(reel, idx, data, mime, kind, prompt=""):
    from . import aiimage
    link = aiimage.save(data, mime, f"reel-{reel.id}-{idx}")
    b = dict(reel.beats[idx])
    if not b.get("orig_scene_id") and b.get("scene_id"):
        b["orig_scene_id"] = b["scene_id"]  # щоб можна було повернути справжній кадр
    b.update({"image_id": link.id, "ai": kind, "prompt": prompt[:600]})
    beats = list(reel.beats)
    beats[idx] = b
    reel.beats = beats
    reel.save(update_fields=["beats"])
    return rerender(reel)


def improve_frame(reel, idx):
    from . import aiimage
    data, mime = frame_bytes(reel, idx)
    out, omime = aiimage.improve(data, mime, reel.blog)
    return _set_frame(reel, idx, out, omime, "improved", "покращено ШІ")


def regenerate_frame(reel, idx, prompt):
    from . import aiimage
    prompt = (prompt or "").strip() or (reel.beats[idx].get("prompt") or reel.beats[idx].get("text") or reel.title)
    data, mime = aiimage.regenerate(prompt, reel.blog)
    return _set_frame(reel, idx, data, mime, "generated", prompt)


def edit_frame(reel, idx, instruction):
    """Домалювати/змінити в кадрі за інструкцією (стрілка, акцент, предмет, персонаж) — решта кадру без змін."""
    from . import aiimage
    instruction = (instruction or "").strip()
    if not instruction:
        raise ReelError("Напишіть, що додати або змінити в кадрі.")
    data, mime = frame_bytes(reel, idx)
    keep = (" Фактуру, колір і малюнок декоративного покриття НЕ змінюй." if reel.blog and reel.blog.label_ai else "")
    out, omime = aiimage.generate(f"Відредагуй цей кадр: {instruction}. Усе інше в кадрі залиш як є — композицію, світло, "
                                  f"предмети.{keep} Без тексту й літер.", aspect="9:16", ref=(data, mime))
    return _set_frame(reel, idx, out, omime, "edited", instruction)


def revert_frame(reel, idx):
    b = dict(reel.beats[idx])
    if not b.get("orig_scene_id"):
        raise ReelError("У цього кадру немає справжнього оригіналу — його можна лише перегенерувати.")
    b["scene_id"] = b.pop("orig_scene_id")
    for k in ("image_id", "ai", "prompt"):
        b.pop(k, None)
    beats = list(reel.beats)
    beats[idx] = b
    reel.beats = beats
    reel.save(update_fields=["beats"])
    return rerender(reel)


def spent_month():
    return round(questions.month_spent(MARKUP_SOURCE) + questions.month_spent(PLAN_SOURCE), 4)


def backfill_thumbs(material, limit=200):
    """Превʼю для вже розмічених сцен без кадру (без ШІ, безкоштовно): качаємо оригінал, беремо кадр."""
    os.makedirs(WORK, exist_ok=True)
    folder = tempfile.mkdtemp(dir=WORK)
    done = 0
    try:
        for sc in VideoScene.objects.filter(asset__material=material, thumb=None).select_related("asset")[:limit]:
            try:
                sc.thumb = _thumb(fetch_original(sc.asset, folder), (sc.start + sc.end) / 2, folder)
                sc.save(update_fields=["thumb"])
                done += 1
            except Exception:
                continue
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return done


def rerender(reel):
    """Перемонтувати рилс за відредагованими кадрами (без нових викликів ШІ)."""
    from secrets import token_urlsafe
    from apps.inbox.models import SharedLink
    os.makedirs(WORK, exist_ok=True)
    folder = tempfile.mkdtemp(dir=WORK)
    try:
        data, dur = render({"beats": reel.beats}, folder, style=reel.style, blog=reel.blog)
        old = reel.file
        reel.file = SharedLink.objects.create(token=token_urlsafe(24), filename=f"reel-{reel.material}.mp4",
                                              content_type="video/mp4", data=data)
        reel.duration, reel.error = round(dur, 1), ""
        reel.status = ReelDraft.Status.DRAFT
        reel.save(update_fields=["file", "duration", "error", "status"])
        if old:
            old.delete()
        return reel
    finally:
        shutil.rmtree(folder, ignore_errors=True)
