"""Каруселі (25.09.2026): тема → слайди в тематиці блогу → PNG 1080×1350 у CRM → «Надіслати мені» в Telegram.

Текст пише Claude за майстер-промтом і базою знань блогу. Картинки:
- library — реальні фото з бібліотеки CRM (для Wallcov: фактура лише справжня);
- ai — згенеровані Gemini (платно, ≈$0.04, для Wallcov з позначкою «ШІ-візуалізація»);
- none — дизайнерський фон без фото.
Рендер — Pillow, шрифти ті самі, що в рилсах (Montserrat / Inter з кирилицею).
"""
import io
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from . import aiimage, blogs
from .models import Carousel
from .reels import clean_text, _clean_caption
from .styles import font_file

SOURCE = "content_factory.carousels"
W, H = 1080, 1350
TEMPLATES = {"photo": "Фото на весь слайд", "plaster": "Світла штукатурка", "graphite": "Графіт"}

KINDS = {"single": "Одна тема по кроках", "list": "Добірка: кілька порад/тем"}
FUNNELS = {  # ціль каруселі → чого просимо в кінці (Instagram рахує збереження й пересилання як сильні сигнали)
    "save": "Зберегти: корисна інструкція/чекліст, до якого повернуться; заклик «збережіть, щоб не загубити»",
    "share": "Переслати: впізнавана ситуація чи «покажи тому, хто…»; заклик переслати конкретній людині",
    "comment": "Коментар: питання-вибір «А чи Б?» або «а як у вас?»; заклик відповісти в коментарях",
    "dm": "Заявка: кодове слово в Direct; заклик написати слово, щоб отримати розрахунок/добірку",
    "follow": "Підписка: частина серії; заклик підписатись, щоб не пропустити наступну частину",
}

TASK = """Ти редактор каруселей для Instagram. Зроби карусель на задану тему: {n} слайдів.
ТИП: {kind_rule}
ЦІЛЬ (воронка): {funnel_rule}
Слайд 1 — обкладинка: заголовок-гачок до 7 слів (питання, інтрига або обіцянка користі), body — 1 коротке речення.
Слайд 2 — другий вхід у тему: сильна думка, що тримає й сама по собі (кожен слайд має тягнути гортати далі).
Середні слайди — по одній думці: headline до 6 слів, body до 220 символів; можна переносити рядки (\n) для списків.
Останній слайд — підсумок і заклик за ЦІЛЛЮ та закликом блогу.
image_hint — що має бути на картинці слайда (коротко).
caption — підпис 2–5 речень: перший рядок — гачок із ключовими словами теми (пошук Instagram), далі суть, заклик за ціллю;
в кінці 3–5 доречних хештегів. Без емодзі.
alt — короткий опис каруселі для людей з вадами зору (1 речення).
checks — факти з тексту, які людина має звірити (цифри, ціни, властивості).
promise — якщо карусель обіцяє продовження — що саме (одним реченням), інакше порожньо. answers_promise_id — id відкритої обіцянки, на яку відповідає ця карусель, або null.
Відповідай ЛИШЕ JSON: {{"title":"...","caption":"...","alt":"...","slides":[{{"headline":"...","body":"...","image_hint":"..."}}],"checks":["..."],"promise":"","answers_promise_id":null}}"""
KIND_RULES = {
    "single": "одна тема: слайд 1 обіцяє конкретний результат, далі розкриття по кроках (кожен слайд — наступний крок/деталь тієї ж теми), без стрибків на інші теми.",
    "list": "добірка з кількох порад/тем: слайд 1 — гачок + ЩО ВСЕРЕДИНІ (перелік тем у body через \n, коротко), далі по одній темі на слайд у тому ж порядку.",
}

KEEP_AUTHOR = ("Поточний текст слайдів — ГОЛОВНИЙ: автор міг правити його вручну. Бери його за основу, зберігай зміст, намір і "
               "ТИП ДІЇ в заклику (коментарі лишаються коментарями, збереження — збереженням). Не додавай телефонів, посилань, цін і "
               "контактів, яких немає в поточному тексті. Заклик блогу за замовчуванням тут НЕ підставляй.")

REWRITE_ONE = """Перепиши ТЕКСТ одного слайда каруселі (заголовок і текст), не змінюючи його місце в історії та тему. Картинка лишається.
""" + KEEP_AUTHOR + """
Врахуй сусідні слайди, щоб не повторюватись. Заголовок до 7 слів, текст до 220 символів, можна переноси рядків.
{wish}
Відповідай ЛИШЕ JSON: {{"headline":"...","body":"..."}}"""

REWRITE_ALL = """Перепиши ТЕКСТИ всіх слайдів каруселі (кількість слайдів і порядок не змінюй — картинки лишаються на своїх місцях).
""" + KEEP_AUTHOR + """
Дотримуйся типу каруселі. {wish}
Відповідай ЛИШЕ JSON: {{"slides":[{{"headline":"...","body":"..."}}],"caption":"..."}}"""

ADVICE = """Ти SMM-продюсер. Подивись карусель і дай ДО 5 порад, як краще досягти ЦІЛІ каруселі й мети блогу (збереження, пересилання,
коментарі, заявки, підписки). Кожна порада — дія з переліку (поле action):
- {{"type":"text","slide":N,"headline":"...","body":"..."}} — новий текст слайда N (N з 0);
- {{"type":"image","slide":N,"value":"що намалювати ШІ"}} — нова ШІ-картинка слайда N (лише якщо блог дозволяє ШІ-картинки для цього змісту);
- {{"type":"caption","value":"новий підпис"}};
- {{"type":"pos","slide":N,"value":"top|center|bottom"}} — де розмістити текст.
Якщо порада не наближає до цілі — не пиши її. Не пропонуй вигаданих фактів. У title не пиши номер слайда.
Відповідай ЛИШЕ JSON: {{"advice":[{{"title":"до 8 слів","why":"як це працює на ціль","action":{{...}}}}]}}"""


def _lines(text, n):
    """Прибрати емодзі, але зберегти переноси рядків (структуру тексту)."""
    return "\n".join(clean_text(ln) for ln in str(text or "").splitlines()).strip()[:n]


def spent_month():
    from .questions import month_spent
    return month_spent(SOURCE)


def generate(blog, topic, n=6, template="photo", images="auto", material="", call=None, into=None, kind="single", funnel="save"):
    """Згенерувати текст каруселі й підібрати картинки. images: auto|library|ai|none.
    into — заготовка Carousel (створена одразу, щоб Олег бачив «готую…»), інакше створюється нова."""
    blogs.require_ready(blog)
    n = max(3, min(int(n or 6), 10))
    facts_text, fact_titles = blogs.facts_block(blog, f"{topic} {material}")
    kind = kind if kind in KINDS else "single"
    funnel = funnel if funnel in FUNNELS else "save"
    system = blogs.system_for(blog, TASK.format(n=n, kind_rule=KIND_RULES[kind], funnel_rule=FUNNELS[funnel]))
    if call is None:
        from apps.crm.ai import claude_json
        call = lambda p: claude_json(p, model="claude-sonnet-4-6", max_tokens=2500, system=system, source=SOURCE)
    ask = (f"Тема: {topic}\nМатеріал: {material or '—'}\n\nБаза знань:\n{facts_text or '(немає)'}\n\n"
           + blogs.memory_block(blog))
    try:
        r = call(ask) or {}
    except TimeoutError:  # таймаут спільного claude_json (45 с) — ще одна спроба
        r = call(ask) or {}
    slides = []
    for s in (r.get("slides") or [])[:n]:
        if isinstance(s, dict) and (s.get("headline") or s.get("body")):
            slides.append({"headline": _lines(s.get("headline"), 90),
                           "body": _lines(s.get("body"), 400),
                           "hint": clean_text(str(s.get("image_hint") or ""))[:200], "image": {"kind": "none"}})
    if len(slides) < 3:
        raise ValueError("ШІ не склав слайди — спробуйте іншу тему.")
    c = into or Carousel(blog=blog, topic=topic)
    c.title = clean_text(str(r.get("title") or topic))[:200]
    c.caption = _clean_caption(str(r.get("caption") or ""))
    c.template, c.slides, c.kind, c.funnel = template, slides, kind, funnel
    c.facts = fact_titles + [f"Перевірити: {clean_text(str(x))}" for x in (r.get("checks") or [])][:12]
    c.save()
    blogs.remember(blog, "carousel", c.id, c.title, " / ".join(x["headline"] for x in slides)[:600],
                   promise=str(r.get("promise") or ""), answers_id=r.get("answers_promise_id"))
    if r.get("alt"):
        c.facts = [f"Alt-текст: {clean_text(str(r['alt']))[:300]}"] + c.facts
        c.save(update_fields=["facts"])
    mode = images
    if mode == "auto":
        mode = "library" if blog.use_crm_kb else "none"
    if mode == "library":
        _library_images(c, material)
    elif mode == "ai":
        for i in range(len(c.slides)):
            try:
                set_ai_image(c, i, c.slides[i]["hint"] or c.slides[i]["headline"], save=False)
            except aiimage.ImageError:
                break
    render(c)
    return c


def _library_images(c, material):
    """Реальні фото матеріалу з бібліотеки CRM — по одному на слайд, без повторів."""
    from .telegram import pick_photos
    used = []
    for s in c.slides:
        ids = pick_photos(material, exclude=used) if material else []
        if ids:
            used.append(ids[0])
            s["image"] = {"kind": "library", "lib_id": ids[0]}


def set_library_image(c, idx, lib_id, save=True):
    c.slides[idx]["image"] = {"kind": "library", "lib_id": int(lib_id)}
    if save:
        render(c)


def set_ai_image(c, idx, prompt, save=True):
    data, mime = aiimage.regenerate(prompt, c.blog, aspect="4:5")
    link = aiimage.save(data, mime, f"carousel-{c.id}-{idx}")
    c.slides[idx]["image"] = {"kind": "ai", "link_id": link.id, "prompt": prompt[:500]}
    if save:
        render(c)


def improve_image(c, idx):
    got = _image_bytes(c.slides[idx].get("image") or {})
    if not got:
        raise ValueError("На цьому слайді немає картинки, яку можна покращити.")
    data, mime = aiimage.improve(got[0], got[1], c.blog, aspect="4:5")
    link = aiimage.save(data, mime, f"carousel-{c.id}-{idx}-better")
    prev = c.slides[idx]["image"]
    c.slides[idx]["image"] = {"kind": "ai", "link_id": link.id, "prompt": "покращено ШІ", "from": prev}
    render(c)


def _image_bytes(img):
    from apps.inbox.models import MediaLibraryItem, SharedLink
    if img.get("kind") == "library" and img.get("lib_id"):
        m = MediaLibraryItem.objects.filter(pk=img["lib_id"]).select_related("file").first()
        if m and m.file_id and m.file.data:
            return bytes(m.file.data), m.file.content_type
    if img.get("kind") == "ai" and img.get("link_id"):
        link = SharedLink.objects.filter(pk=img["link_id"]).first()
        if link:
            return bytes(link.data), link.content_type
    return None


# ── Рендер ─────────────────────────────────────────────────────────────────────────────────────────

def _font(family, weight, size):
    return ImageFont.truetype(font_file(family, weight), size)


def _wrap(draw, text, font, width):
    lines, line = [], ""
    for word in (text or "").split():
        test = (line + " " + word).strip()
        if draw.textlength(test, font=font) <= width or not line:
            line = test
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _plaster(base=(233, 226, 214), seed=0):
    """Фон «світла штукатурка»: мʼякі плями + дрібне зерно (детерміновано від seed)."""
    rnd = random.Random(seed)
    img = Image.new("RGB", (W // 4, H // 4), base)
    d = ImageDraw.Draw(img)
    for _ in range(90):
        x, y, r = rnd.randint(-40, W // 4), rnd.randint(-40, H // 4), rnd.randint(10, 60)
        t = rnd.randint(-14, 10)
        d.ellipse([x, y, x + r * 2, y + r], fill=tuple(max(0, min(255, c + t)) for c in base))
    img = img.filter(ImageFilter.GaussianBlur(9)).resize((W, H), Image.BICUBIC)
    grain = Image.effect_noise((W, H), 18).convert("RGB")
    return Image.blend(img, grain, 0.06)


def _cover(img, box):
    return ImageOps.fit(img.convert("RGB"), box, method=Image.LANCZOS, centering=(0.5, 0.45))


def _hex(c):
    c = (c or "#e3b85f").lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def render_slide(c, idx):
    s = c.slides[idx]
    n = len(c.slides)
    blog = c.blog
    accent = _hex(blog.color if blog else "#e3b85f")
    got = _image_bytes(s.get("image") or {})
    photo = Image.open(io.BytesIO(got[0])) if got else None
    tpl = c.template if c.template in TEMPLATES else "photo"
    if tpl == "photo" and not photo:
        tpl = "graphite"
    cover = idx == 0
    last = idx == n - 1
    if tpl == "photo":
        canvas = _cover(photo, (W, H))
        shade = Image.new("L", (1, H))
        for y in range(H):
            shade.putpixel((0, y), int(max(0, (y - H * 0.28) / (H * 0.72)) ** 1.3 * 235))
        canvas.paste(Image.new("RGB", (W, H), (12, 13, 15)), (0, 0), shade.resize((W, H)))
        ink, sub = (255, 255, 255), (228, 228, 228)
        text_top = None
    else:
        dark = tpl == "graphite"
        canvas = Image.new("RGB", (W, H), (20, 24, 27)) if dark else _plaster(seed=c.id or 1)
        ink, sub = ((240, 240, 238), (190, 196, 199)) if dark else ((28, 26, 23), (70, 64, 57))
        text_top = -1  # без фото — текст по центру слайда
        if photo:
            ph = _cover(photo, (W - 160, 620))
            mask = Image.new("L", ph.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, ph.size[0], ph.size[1]], radius=28, fill=255)
            canvas.paste(ph, (80, 110), mask)
            text_top = 790
    d = ImageDraw.Draw(canvas)
    h_font = _font("Montserrat", "ExtraBold", 92 if cover else 70)
    b_font = _font("Inter", "Medium", 38)
    small = _font("Inter", "Bold", 26)
    head = s.get("headline") or ""
    body = s.get("body") or ""
    hl = [ln for para in head.split("\n") for ln in (_wrap(d, para, h_font, W - 160) or [""])]
    bl = [ln for para in body.split("\n") for ln in (_wrap(d, para, b_font, W - 160) or [""])] if body else []
    lh_h, lh_b = int(h_font.size * 1.12), int(b_font.size * 1.38)
    block = len(hl) * lh_h + (24 + len(bl) * lh_b if bl else 0)
    pos = s.get("pos") or "auto"
    if pos == "top" and text_top is None:
        text_top = 170
    elif pos == "center" and text_top is None:
        text_top = -1
    elif pos == "bottom" and text_top == -1:
        text_top = None
    y = (H - 150 - block) if text_top is None else ((H - block) // 2 - 20 if text_top == -1 else text_top)
    d.rectangle([80, y - 30, 80 + 90, y - 22], fill=accent)
    for line in hl:
        d.text((80, y), line, font=h_font, fill=ink)
        y += lh_h
    if bl:
        y += 24
        for line in bl:
            d.text((80, y), line, font=b_font, fill=sub)
            y += lh_b
    # номер слайда й підпис блогу
    pill = f"{idx + 1}/{n}"
    pw = d.textlength(pill, font=small) + 36
    d.rounded_rectangle([W - 80 - pw, 60, W - 80, 108], radius=24, fill=(0, 0, 0) if tpl == "photo" else accent)
    d.text((W - 80 - pw + 18, 70), pill, font=small, fill=(255, 255, 255) if tpl == "photo" else (20, 20, 20))
    who = blogs.handle(blog) if blog else ""
    if who:
        d.text((80, H - 84), who, font=small, fill=sub)
    if not last and n > 1:
        d.text((W - 80 - d.textlength("гортай →", font=small), H - 84), "гортай →", font=small, fill=sub)
    if (s.get("image") or {}).get("kind") == "ai" and blog and blog.label_ai:
        lab = "ШІ-візуалізація"
        lw = d.textlength(lab, font=small) + 30
        d.rounded_rectangle([80, 60, 80 + lw, 108], radius=10, fill=(0, 0, 0))
        d.text((95, 70), lab, font=small, fill=(255, 255, 255))
    out = io.BytesIO()
    canvas.convert("RGB").save(out, "JPEG", quality=90, optimize=True, progressive=True)  # ~4× легше за PNG
    return out.getvalue()


def render(c):
    """Перемалювати всі слайди; PNG зберігаються в CRM (старі версії замінюються)."""
    from apps.inbox.models import SharedLink
    old = [s.get("rendered_id") for s in c.slides if s.get("rendered_id")]
    for i in range(len(c.slides)):
        img = render_slide(c, i)
        c.slides[i]["rendered_id"] = aiimage.save(img, "image/jpeg", f"carousel-{c.id}-{i + 1}").id
    c.error = ""
    c.save()
    SharedLink.objects.filter(id__in=old).delete()
    return c


def send_test(c):
    """Надіслати слайди Олегу в Telegram альбомом (як виглядатиме)."""
    import json as _json
    from apps.inbox.models import SharedLink
    from .telegram import PublishError, _tg, tg_config
    owner = tg_config()[2]
    if not owner:
        raise PublishError("Не вказано чат власника (TG_CONTENT_OWNER_CHAT_ID).")
    links = {l.id: l for l in SharedLink.objects.filter(id__in=[s.get("rendered_id") for s in c.slides])}
    files, media = {}, []
    for i, s in enumerate(c.slides[:10]):
        l = links.get(s.get("rendered_id"))
        if not l:
            continue
        files[f"f{i}"] = (l.filename, bytes(l.data), l.content_type)
        media.append({"type": "photo", "media": f"attach://f{i}"})
    if not media:
        raise PublishError("Слайди ще не намальовані.")
    media[0]["caption"] = (c.caption or c.title)[:1024]
    _tg("sendMediaGroup", {"chat_id": owner, "media": _json.dumps(media, ensure_ascii=False)}, files)



# ── 25.09 v2: перегенерувати лише текст, поради під ціль ──────────────────────────────────────────

def _ctx(c):
    return "\n".join(f"[{i}] {x.get('headline', '')} — {x.get('body', '')}".replace("\n", " ") for i, x in enumerate(c.slides))


def _call(system, prompt, max_tokens, call=None):
    if call is not None:
        return call(prompt) or {}
    from apps.crm.ai import claude_json
    try:
        return claude_json(prompt, model="claude-sonnet-4-6", max_tokens=max_tokens, system=system, source=SOURCE) or {}
    except TimeoutError:
        return claude_json(prompt, model="claude-sonnet-4-6", max_tokens=max_tokens, system=system, source=SOURCE) or {}


def _head(c):
    return (f"Тема: {c.topic}\nТип: {KINDS.get(c.kind, '')}\nЦіль: {FUNNELS.get(c.funnel, '')}\n"
            f"Кількість слайдів: {len(c.slides)}\n\nСлайди:\n{_ctx(c)}")


def rewrite_slide(c, idx, wish="", call=None):
    """Нова версія тексту одного слайда (картинка, позиція й дизайн лишаються)."""
    blogs.require_ready(c.blog)
    facts_text, _t = blogs.facts_block(c.blog, f"{c.topic} {c.slides[idx].get('headline', '')}")
    system = blogs.system_for(c.blog, REWRITE_ONE.format(wish=f"Побажання: {wish}" if wish else ""))
    r = _call(system, _head(c) + f"\n\nПерепиши слайд [{idx}].\n\nБаза знань:\n{facts_text or '(немає)'}", 500, call)
    if not (r.get("headline") or r.get("body")):
        raise ValueError("ШІ не повернув текст — спробуйте ще раз.")
    _keep_prev(c.slides[idx])
    c.slides[idx]["headline"] = _lines(r.get("headline"), 90)
    c.slides[idx]["body"] = _lines(r.get("body"), 400)
    render(c)
    return c


def _keep_prev(slide):
    """Попередня версія тексту — щоб «↶ Повернути попередній» після невдалої перегенерації."""
    slide["prev"] = {"headline": slide.get("headline", ""), "body": slide.get("body", "")}


def undo_slide(c, idx):
    prev = c.slides[idx].get("prev")
    if not prev:
        raise ValueError("Попередньої версії тексту немає.")
    cur = {"headline": c.slides[idx].get("headline", ""), "body": c.slides[idx].get("body", "")}
    c.slides[idx].update(prev)
    c.slides[idx]["prev"] = cur  # повторне натискання — назад до нової версії
    render(c)
    return c


def rewrite_all(c, wish="", call=None):
    """Нові тексти всіх слайдів і підпису; картинки на місцях."""
    blogs.require_ready(c.blog)
    facts_text, _t = blogs.facts_block(c.blog, c.topic)
    system = blogs.system_for(c.blog, REWRITE_ALL.format(wish=f"Побажання: {wish}" if wish else ""))
    r = _call(system, _head(c) + f"\n\nБаза знань:\n{facts_text or '(немає)'}", 1800, call)
    new = [x for x in (r.get("slides") or []) if isinstance(x, dict)]
    if len(new) != len(c.slides):
        raise ValueError("ШІ змінив кількість слайдів — спробуйте ще раз.")
    for s, x in zip(c.slides, new):
        _keep_prev(s)
        s["headline"], s["body"] = _lines(x.get("headline"), 90), _lines(x.get("body"), 400)
    if r.get("caption"):
        c.caption = _clean_caption(str(r["caption"]))
    render(c)
    return c


def advice(c, call=None):
    blog = c.blog
    if not (blog and blog.goal.strip()):
        raise ValueError("Вкажіть мету блогу в «Блогах» — без неї поради будуть навмання.")
    system = blogs.system_for(blog, ADVICE)
    r = _call(system, _head(c) + f"\n\nПідпис:\n{c.caption[:800]}", 1400, call)
    out = []
    for a in (r.get("advice") or [])[:5]:
        act = a.get("action") if isinstance(a, dict) else None
        if not isinstance(act, dict):
            continue
        t = act.get("type")
        if t in ("text", "image", "pos"):
            try:
                sl = int(act.get("slide"))
            except (TypeError, ValueError):
                continue
            if not 0 <= sl < len(c.slides):
                continue
            act["slide"] = sl
        if t == "pos" and act.get("value") not in ("top", "center", "bottom"):
            continue
        if t == "image" and blog.label_ai and c.slides[act["slide"]].get("image", {}).get("kind") == "library":
            continue  # Wallcov: справжнє фото фактури не замінюємо ШІ
        if t not in ("text", "image", "caption", "pos"):
            continue
        out.append({"title": clean_text(str(a.get("title") or ""))[:80], "why": clean_text(str(a.get("why") or ""))[:240], "action": act})
    return out
