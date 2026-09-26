"""Майстер рилса «команда ШІ» (25.09.2026, запит Олега): 7 кроків від ідеї до готового ролика.

1 Ідея (Продюсер-стратег) → 2 Сценарій (Сценарист) → 3 Матеріал (Монтажер) → 4 Стиль (Монтажер) →
5 Чорновий монтаж → 6 Перевірка командою (SMM-редактор, Монтажер, Контролер бренду) → 7 Готово (SMM).
Крок зберігається в ReelDraft.stage, задум — у ReelDraft.brief, висновки перевірки — у ReelDraft.review.

Джерела ідей: ШІ сам (мета блогу + памʼять + що вистрілило у стрічці + питання клієнтів), наші кадри, база знань,
своя ідея, референс (ролик зі стрічки або посилання; YouTube Gemini дивиться сам за посиланням), пошук в інтернеті.
Пошук в інтернеті: пошуковик DuckDuckGo по Instagram, TikTok, Pinterest, Telegram, Facebook + Shorts на YouTube — безкоштовно.
Відео не-YouTube ШІ не переглядає — бере підпис/опис.
"""
import urllib.error
import json
import re
import urllib.parse
import urllib.request

from django.db.models import Count, Q

from . import blogs
from .reels import MARKUP_MODEL, ReelError, _clean_caption, _gemini, clean_text

SOURCE = "content_factory.studio"
STAGES = ("idea", "script", "material", "style", "draft", "review", "done")
GOALS = {"save": "зберегти", "share": "переслати", "comment": "написати коментар", "dm": "написати в Direct", "follow": "підписатися"}
FITS = ("ours", "ai", "shoot")

IDEA_TASK = """Ти продюсер-стратег коротких вертикальних роликів цього блогу. Запропонуй 5 ідей рилсів, які наближають до МЕТИ блогу.
ГОЛОВНЕ ПРАВИЛО: ролик відповідає на РЕАЛЬНИЙ біль, страх або запит людини з цільової аудиторії — так, як вона сама це
формулює в Direct чи коментарях («чи видно шви», «скільки піде на 20 м²», «боюсь, що не впораюсь сама», «як не прогадати з кольором»).
Назва матеріалу чи процес («Вельвет Луна: від відра до стіни») — НЕ гачок: це абстрактно й не чіпляє. Продукт — лише відповідь на біль.
Кожна ідея:
- pain — біль/запит клієнта його словами, 1 речення (з блоку питань клієнтів, коли він є);
- title — тема до 10 слів, сформульована через цей біль;
- hook — текст першого кадру до 7 слів: біль або результат для людини («Шви не видно навіть збоку»), без назви продукту,
  без штампів і риторичних питань-пустушок;
- goal — одна дія глядача: save|share|comment|dm|follow;
- why — 1 речення: чому спрацює для цієї аудиторії й мети, з опорою на дані нижче (що вистрілило, питання, памʼять);
- shots — які кадри потрібні, коротко через «;»;
- fit — "ours" (є в наших кадрах з каталогу), "ai" (малює ШІ), "shoot" (треба доснімати).
Не повторюй теми з памʼяті блогу. Факти й цифри — лише з бази знань. Без емодзі.
Відповідай ЛИШЕ JSON: {"ideas":[{"pain":"...","title":"...","hook":"...","goal":"save","why":"...","shots":"...","fit":"ours"}]}"""

REF_PROMPT = """Це ролик-референс з соцмережі. Розбери, ЧОМУ він чіпляє, щоб повторити будову (не текст і не кадри) у своєму ролику.
Відповідай ЛИШЕ JSON: {"summary":"про що ролик, 1 речення","hook":"що відбувається в перші 3 с і чому зупиняє",
"beats":[{"seconds":2.0,"purpose":"гачок|проблема|доказ|показ|заклик","what":"що в кадрі"}],"text_style":"як виглядає текст на екрані",
"why_works":"1–2 речення","total_seconds":15}
У beats.what опиши кадр так, щоб художник намалював НОВИЙ схожий за задумом: дія, крупність, ракурс, рух камери — без імен, логотипів і впізнаваних деталей."""

REVIEW_TASK = """Ти — команда перевірки рилса перед публікацією. Три ролі дивляться ролик кожна зі свого боку:
- smm (SMM-редактор): чи гачок називає біль/запит клієнта ЦА (а не назву продукту чи процес); чи зупиняє перший кадр за 1–3 с;
  одна дія в кінці й вона веде до мети блогу; підпис і перший рядок з ключовими
  словами; правила Instagram (оригінальність, до 5 хештегів, без накрутки); ШІ-штампи й емодзі;
- editor (Монтажер): ритм (кадр 1,5–3,5 с, гачок ≤2,5 с), загальна тривалість під мету, переходи, рух камери, повтори кадрів;
- brand (Контролер бренду): відповідність майстер-промту й тону блогу, факти лише з бази знань, для блогу з правилом
  «фактура справжня» — ШІ не малює покриття.
Кожна роль: score 1–10 і до 3 зауважень. Зауваження — з дією, яку CRM виконає сама (поле action), або без дії (action: null),
якщо це порада людині. Дії:
{"type":"transition","beat":N,"value":"fade|slide|zoom|cut"} · {"type":"motion","beat":N,"value":"zoomin|zoomout|none"} ·
{"type":"text","beat":N,"value":"новий текст до 7 слів"} · {"type":"seconds","beat":N,"value":2.0} ·
{"type":"edit_frame","beat":N,"value":"що домалювати"} · {"type":"regenerate","beat":N,"value":"опис нового кадру"} ·
{"type":"caption","beat":0,"value":"новий підпис повністю"}.
N — номер кадру з 0. Не повторюй однакові зауваження в різних ролях. Якщо все добре — порожній список і високий бал.
Відповідай ЛИШЕ JSON: {"smm":{"score":8,"notes":[{"title":"до 8 слів","why":"1 речення","action":{...}|null}]},
"editor":{...},"brand":{...},"verdict":"1 речення: чи можна публікувати"}"""

ROLES = {"smm": "SMM-редактор", "editor": "Монтажер", "brand": "Контролер бренду"}


def _call(system, max_tokens=1600, model="claude-sonnet-4-6"):
    from apps.crm.ai import claude_json

    def call(prompt):
        try:
            return claude_json(prompt, model=model, max_tokens=max_tokens, system=system, source=SOURCE) or {}
        except TimeoutError:  # спільний claude_json має таймаут 45 с — одна повторна спроба
            return claude_json(prompt, model=model, max_tokens=max_tokens, system=system, source=SOURCE) or {}
    return call


# ── Крок 1. Ідея ────────────────────────────────────────────────────────────────────────────────

def _feed_block(blog, limit=8):
    from .analyst import feed
    try:
        rows = feed(days=90, blog=blog, limit=limit)
    except Exception:
        return ""
    lines = [f"- ×{ratio:.1f} від звичного · {i.views or 0} переглядів · @{i.username}: {(i.caption or '')[:160]}"
             for i, ratio in rows if ratio]
    return "Що вистрілило у сторінок, які ми відстежуємо (90 днів):\n" + "\n".join(lines) if lines else ""


def _questions_block(blog, limit=8):
    if blog.slug != "wallcov":
        return ""
    from .models import QuestionTopic
    rows = (QuestionTopic.objects.exclude(status=QuestionTopic.Status.IGNORED).annotate(n=Count("mentions"))
            .filter(n__gt=0).order_by("-n")[:limit])
    return "Про що найчастіше питають клієнти:\n" + "\n".join(f"- {t.title} ({t.n})" for t in rows) if rows else ""


def _footage_block(blog, limit=40):
    from .models import SourceAsset, VideoScene
    if not blog.real_footage:
        return "Власних кадрів у блогу немає — кадри малює ШІ за стилем блогу."
    qs = VideoScene.objects.filter(quality__gte=3, asset__hidden=False).select_related("asset")
    if blog.slug != "wallcov":
        qs = qs.filter(asset__blog=blog)
    rows = list(qs.order_by("-quality", "-id")[:limit])
    mats = (SourceAsset.objects.filter(kind="video", hidden=False).exclude(material="").values_list("material")
            .annotate(n=Count("id")).order_by("-n")[:12])
    return ("Наші матеріали з відео: " + ", ".join(f"{m} ({n})" for m, n in mats) + "\nКаталог наших кадрів (приклади):\n"
            + "\n".join(f"- {s.asset.material}: {s.what}" for s in rows))


def youtube_id(url):
    m = re.search(r"(?:youtube\.com/(?:shorts/|watch\?v=|embed/)|youtu\.be/)([\w-]{11})", url or "")
    return m.group(1) if m else ""


def _ref_frames(video_path, beats, limit=8):
    """Кадри з референсу в середині кожного плану → SharedLink id (для ремейку: ракурс і крупність)."""
    import os
    from .reels import _run
    from . import aiimage
    ids, t = [], 0.0
    folder = os.path.dirname(video_path)
    for n, b in enumerate((beats or [])[:limit]):
        try:
            sec = float(b.get("seconds") or 2)
        except (TypeError, ValueError):
            sec = 2.0
        out = os.path.join(folder, f"rf{n}.jpg")
        try:
            _run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t + sec / 2:.2f}", "-i", video_path, "-frames:v", "1",
                  "-vf", "scale=720:-2", "-q:v", "3", out])
            with open(out, "rb") as f:
                ids.append(aiimage.save(f.read(), "image/jpeg", "ref-frame").id)
        except Exception:
            ids.append(None)
        t += sec
    return ids


def _watch_bytes(data):
    import base64
    import os
    import shutil
    import tempfile
    from .reels import WORK, _light_copy
    os.makedirs(WORK, exist_ok=True)
    folder = tempfile.mkdtemp(dir=WORK)
    try:
        src = os.path.join(folder, "ref.mp4")
        with open(src, "wb") as f:
            f.write(data)
        with open(_light_copy(src, folder), "rb") as f:
            part = {"inlineData": {"mimeType": "video/mp4", "data": base64.b64encode(f.read()).decode()}}
        r = _gemini([part, {"text": REF_PROMPT}], max_tokens=2500)
        r = r if isinstance(r, dict) else {}
        r["frames"] = _ref_frames(src, r.get("beats"))
        return r
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def _watch_instagram(url, username):
    """Офіційно: Business Discovery нашого IG-акаунта → пряме посилання на відео бізнес/автор-акаунта → Gemini."""
    from . import freeai
    m = freeai.ig_media(url, username)
    if not m or not m.get("media_url") or m.get("media_type") not in ("VIDEO", "REELS"):
        return None
    with urllib.request.urlopen(urllib.request.Request(m["media_url"], headers={"User-Agent": UA}), timeout=60) as r:
        data = r.read(80 * 1024 * 1024)
    out = _watch_bytes(data)
    if m.get("caption"):
        out["caption"] = m["caption"][:500]
    out["likes"] = m.get("like_count")
    return out


def analyze_ref(url="", feed_item=None, thumb="", title="", author=""):
    """Розбір референсу: YouTube — Gemini дивиться сам за посиланням (≈$0.01–0.04); інше — лише підпис/опис сторінки."""
    if feed_item is not None:
        url = url or feed_item.url
    yid = youtube_id(url)
    if yid:
        try:
            r = _gemini([{"fileData": {"fileUri": f"https://www.youtube.com/watch?v={yid}"}}, {"text": REF_PROMPT}], max_tokens=2500)
            r = r if isinstance(r, dict) else {}
            r["url"], r["watched"] = url, True
            try:  # кадри для ремейку (ракурси) — з завантаженого відео
                r["frames"] = _download_frames(url, r.get("beats"))
            except Exception:
                pass
            return r
        except ReelError as e:
            note = f"Gemini не зміг переглянути ({str(e)[:80]}) — беру лише опис."
    else:
        ig_user = author or (feed_item.username if feed_item is not None and "instagram.com" in (url or "") else "")
        if "instagram.com" in (url or "") and ig_user:
            try:
                r = _watch_instagram(url, ig_user.lstrip("@"))
                if r:
                    r["url"], r["watched"] = url, True
                    return r
            except Exception:
                pass
        try:
            r = _watch_download(url)
            r["url"], r["watched"] = url, True
            return r
        except Exception as e:
            note = f"Відео не віддали ({str(e)[:60]})."
            if thumb:  # хоча б обкладинка: композиція, фон, предмети
                try:
                    req = urllib.request.Request(thumb, headers={"User-Agent": UA})
                    with urllib.request.urlopen(req, timeout=15) as rr:
                        img, mime = rr.read(), rr.headers.get_content_type() or "image/jpeg"
                    import base64
                    r = _gemini([{"inlineData": {"mimeType": mime, "data": base64.b64encode(img).decode()}},
                                 {"text": REF_PROMPT + "\nЦе лише обкладинка ролика — опиши, що можна зрозуміти з неї; beats — за здогадом про будову."}], max_tokens=1500)
                    r = r if isinstance(r, dict) else {}
                    r.update({"url": url, "watched": False, "note": note + " ШІ подивився обкладинку."})
                    if title:
                        r["summary"] = f"{r.get('summary', '')} Підпис: {title[:200]}".strip()
                    return r
                except Exception:
                    pass
            note += " Беру лише підпис."
    text = ""
    if feed_item is not None:
        text = f"Підпис: {feed_item.caption[:600]}\nПереглядів: {feed_item.views}, лайків: {feed_item.likes}, коментарів: {feed_item.comments}"
    elif title:
        text = title
    elif url:
        try:
            from .learn import text_from_url
            text = text_from_url(url)[:1500]
        except Exception:
            text = ""
    return {"url": url, "watched": False, "summary": text[:600], "note": note}


def _download_frames(url, beats):
    import os
    import shutil
    import tempfile
    import yt_dlp
    from .reels import WORK
    os.makedirs(WORK, exist_ok=True)
    folder = tempfile.mkdtemp(dir=WORK)
    try:
        with yt_dlp.YoutubeDL({"outtmpl": os.path.join(folder, "ref.%(ext)s"), "format": "mp4/best", "quiet": True, "no_warnings": True,
                               "noprogress": True, "noplaylist": True, "max_filesize": 80 * 1024 * 1024}) as y:
            y.download([url])
        files = [f for f in os.listdir(folder) if f.startswith("ref.")]
        return _ref_frames(os.path.join(folder, files[0]), beats) if files else []
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def _watch_download(url, max_mb=80, max_sec=240):
    """Завантажити ролик Instagram/TikTok/Pinterest/Facebook (yt-dlp) і дати Gemini переглянути (≈$0.01–0.03). Файл — лише тимчасово."""
    import base64
    import os
    import shutil
    import tempfile
    from .reels import WORK, _light_copy
    import yt_dlp
    os.makedirs(WORK, exist_ok=True)
    folder = tempfile.mkdtemp(dir=WORK)
    try:
        opts = {"outtmpl": os.path.join(folder, "ref.%(ext)s"), "format": "mp4/best[ext=mp4]/best", "quiet": True, "no_warnings": True, "noprogress": True,
                "noplaylist": True, "max_filesize": max_mb * 1024 * 1024, "socket_timeout": 30,
                "match_filter": yt_dlp.utils.match_filter_func(f"duration < {max_sec}")}
        with yt_dlp.YoutubeDL(opts) as y:
            y.download([url])
        files = [f for f in os.listdir(folder) if f.startswith("ref.")]
        if not files:
            raise ReelError("мережа не віддала відео")
        with open(_light_copy(os.path.join(folder, files[0]), folder), "rb") as f:
            part = {"inlineData": {"mimeType": "video/mp4", "data": base64.b64encode(f.read()).decode()}}
        r = _gemini([part, {"text": REF_PROMPT}], max_tokens=2500)
        r = r if isinstance(r, dict) else {}
        r["frames"] = _ref_frames(os.path.join(folder, files[0]), r.get("beats"))
        return r
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def ideas(blog, source="ai", text="", url="", feed_ids=None, call=None, urls=None, remake=False):
    """5 ідей під мету блогу з вибраного джерела. Повертає {"ideas": [...], "refs": [...]}."""
    from .models import FeedItem
    blogs.require_ready(blog)
    if not (blog.goal or "").strip():
        raise ValueError(f"Вкажіть мету блогу «{blog.name}» у «Блогах» — продюсер підбирає ідеї під неї.")
    refs = []
    ctx = [blogs.memory_block(blog)]
    query = f"{blog.goal} {text}"
    if source == "ai":
        ctx += [_feed_block(blog), _questions_block(blog), _footage_block(blog, 20)]
    elif source == "ours":
        ctx.append(_footage_block(blog, 60))
        ctx.append("Завдання: ідеї, які можна змонтувати з НАШИХ наявних кадрів (fit=ours).")
    elif source == "base":
        ctx.append("Завдання: ідеї з бази знань блогу — корисне, що варто розповісти аудиторії.")
    elif source == "mine":
        if len((text or "").strip()) < 5:
            raise ValueError("Опишіть свою ідею хоча б кількома словами.")
        ctx.append(f"Ідея власника (зроби 5 варіантів подачі цієї ідеї, не міняючи суті):\n{text.strip()[:1500]}")
        ctx.append(_footage_block(blog, 20))
    elif source == "ref":
        items = list(FeedItem.objects.filter(id__in=feed_ids or [])[:3])
        refs = [analyze_ref(feed_item=i) for i in items]
        for u in ([{"url": url}] if url else []) + [u if isinstance(u, dict) else {"url": u} for u in (urls or [])]:
            if len(refs) >= 3 or not u.get("url") or any(r.get("url") == u["url"] for r in refs):
                continue
            refs.append(analyze_ref(url=u["url"], thumb=u.get("thumb", ""), title=u.get("title", ""), author=u.get("ig_user", "")))
        if not refs:
            raise ValueError("Виберіть ролик зі стрічки або вставте посилання.")
        if remake:
            ctx.append("РЕЖИМ РЕМЕЙКУ: кожна ідея — новий ролик за будовою референсів, де ВСЕ в кадрі інше (приміщення, фон, руки, предмети, "
                       "світло, ракурси) і показано НАШ продукт/тему блогу. Нічого впізнаваного з оригіналу; fit=ai.")
        ctx.append("Референси (повтори будову й прийом гачка, але НАША тема, наші факти, свої слова):\n"
                   + json.dumps(refs, ensure_ascii=False)[:5000])
        ctx.append(_footage_block(blog, 20))
    else:
        raise ValueError("Невідоме джерело ідей.")
    facts_text, _ = blogs.facts_block(blog, query)
    prompt = "\n\n".join(c for c in ctx if c) + f"\n\nБаза знань:\n{facts_text or '(немає)'}"
    if text and source != "mine":
        prompt += f"\n\nПобажання власника: {text[:500]}"
    call = call or _call(blogs.system_for(blog, IDEA_TASK), max_tokens=1800)
    r = call(prompt)
    out = []
    for i in (r.get("ideas") or [])[:5]:
        if not isinstance(i, dict) or not i.get("title"):
            continue
        out.append({"title": clean_text(str(i["title"]))[:120], "hook": clean_text(str(i.get("hook") or ""))[:80],
                    "pain": clean_text(str(i.get("pain") or ""))[:200],
                    "goal": i.get("goal") if i.get("goal") in GOALS else "save",
                    "why": clean_text(str(i.get("why") or ""))[:300], "shots": clean_text(str(i.get("shots") or ""))[:300],
                    "fit": i.get("fit") if i.get("fit") in FITS else ("ours" if blog.real_footage else "ai")})
    if not out:
        raise ValueError("Продюсер не повернув ідей — спробуйте ще раз.")
    return {"ideas": out, "refs": refs}


def search_youtube(q, limit=20, lang="uk"):
    """Пошук Shorts: офіційний YouTube Data API (YOUTUBE_API_KEY, ≈100 пошуків/добу), інакше сторінка результатів. Безкоштовно."""
    q = (q or "").strip()
    if len(q) < 2:
        raise ValueError("Введіть слово для пошуку.")
    from . import freeai
    api = freeai.youtube_search(q, lang=lang, limit=limit)
    if api:
        return api
    url = "https://www.youtube.com/results?" + urllib.parse.urlencode({"search_query": q + " #shorts", "hl": lang})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                                                             "(KHTML, like Gecko) Chrome/126 Safari/537.36", "Accept-Language": "uk,ru;q=0.8"})
    with urllib.request.urlopen(req, timeout=20) as r:
        html = r.read().decode("utf8", "ignore")
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", html)
    if not m:
        return []
    data = json.loads(m.group(1))
    out, seen = [], set()

    def walk(x):
        if len(out) >= limit:
            return
        if isinstance(x, dict):
            v = x.get("videoRenderer")
            s = x.get("shortsLockupViewModel") or x.get("reelItemRenderer")
            if v and v.get("videoId") not in seen:
                seen.add(v["videoId"])
                out.append({"url": f"https://www.youtube.com/watch?v={v['videoId']}",
                            "title": "".join(t.get("text", "") for t in (v.get("title") or {}).get("runs", []))[:160],
                            "views": ((v.get("viewCountText") or {}).get("simpleText") or "")[:40],
                            "author": "".join(t.get("text", "") for t in (v.get("ownerText") or {}).get("runs", []))[:80],
                            "thumb": f"https://i.ytimg.com/vi/{v['videoId']}/hqdefault.jpg"})
            elif s:
                ent = str(s.get("entityId") or "")
                vid = ent.rsplit("-", 1)[-1] if ent.startswith("shorts-shelf-item-") else ""
                if not re.fullmatch(r"[\w-]{11}", vid or ""):
                    vid = (re.search(r'"videoId":\s*"([\w-]{11})"', json.dumps(s)) or [None, None])[1]
                if vid and vid not in seen:
                    seen.add(vid)
                    acc = str(s.get("accessibilityText") or "")
                    title, _, rest = acc.partition(", ")
                    views = rest.split(" – ")[0] if "перегляд" in rest or "view" in rest else ""
                    out.append({"url": f"https://www.youtube.com/shorts/{vid}", "title": (title or acc)[:160], "views": views[:40],
                                "author": "", "thumb": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"})
            for val in x.values():
                walk(val)
        elif isinstance(x, list):
            for val in x:
                walk(val)
    walk(data)
    return out


# ── Крок 2. Сценарій ───────────────────────────────────────────────────────────────────────────

def topic_of(brief):
    goal = GOALS.get(brief.get("goal") or "", "")
    return ((f"Біль/запит клієнта: {brief['pain']}. " if brief.get("pain") else "")
            + f"{brief.get('title', '')}. Перший кадр (гачок): «{brief.get('hook', '')}»."
            + (f" Мета ролика — щоб глядач захотів {goal}." if goal else "")
            + (f" Потрібні кадри: {brief['shots']}." if brief.get("shots") else ""))[:900]


def build_script(reel, material="", asset_ids=None):
    """Сценарій під задум: з нашими кадрами (розмітка → план) або ШІ-кадри (описи без картинок — малюються на кроці 3)."""
    from .models import ReelDraft, SourceAsset, VideoScene
    from . import reels as R
    blog, brief = reel.blog, reel.brief or {}
    structure = brief.get("structure") or None
    if blog is not None and (brief.get("all_ai") or not blog.real_footage) and not asset_ids:
        blogs.require_ready(blog)
        facts_text, titles = blogs.facts_block(blog, brief.get("title", ""))
        call = _call(blogs.system_for(blog, R.AI_PLAN_TASK), max_tokens=1400)
        prompt = f"Тема: {topic_of(brief)}\n\nБаза знань:\n{facts_text or '(немає)'}\n\n" + blogs.memory_block(blog)
        ref_beats = []
        for ref in (structure or []) if isinstance(structure, list) else []:
            for k, rb in enumerate(ref.get("beats") or []):
                fr = (ref.get("frames") or [None] * 99)[k] if k < len(ref.get("frames") or []) else None
                ref_beats.append({"seconds": rb.get("seconds"), "purpose": rb.get("purpose"), "what": rb.get("what"), "frame": fr})
            break  # ремейк — за першим референсом
        if material:
            from .material_specs import apply_stages_text
            st = apply_stages_text(material)
            if st:
                prompt += "\n\n" + st + "\nУ image_prompt кадру з роботою вкажи етап словами (напр. «другий шар, свіжий, мокрий»)."
        if brief.get("all_ai"):
            prompt += ("\n\nЦе РЕМЕЙК за референсом: кадрів стільки ж, скільки в референсі (до 6), КАДР ЗА КАДРОМ у тому ж порядку, "
                       "з тією ж тривалістю, ракурсом, крупністю й дією (у beats додай \"ref\": номер кадру референсу з 0). "
                       "Але все в кадрі нове: інше приміщення, фон, руки, предмети, світло; нічого впізнаваного з оригіналу."
                       + (f" Покриття в кадрі — {material}." if material else "")
                       + ("\nКадри референсу:\n" + "\n".join(f"[{k}] {rb['seconds']} с · {rb['purpose']} · {rb['what']}" for k, rb in enumerate(ref_beats[:6]))
                          if ref_beats else ""))
        if structure:
            prompt += "\n\nПовтори БУДОВУ й ТЕМП референсу (не текст):\n" + json.dumps(structure, ensure_ascii=False)[:3000]
        r = call(prompt)
        beats = []
        for b in (r.get("beats") or [])[:6]:
            ip = str(b.get("image_prompt") or "").strip()
            if not ip:
                continue
            try:
                secs = max(1.5, min(float(b.get("seconds") or 3), 5.0))
            except (TypeError, ValueError):
                secs = 3.0
            row = {"text": clean_text(str(b.get("text") or ""))[:80], "seconds": round(secs, 2), "prompt": ip[:600]}
            try:
                k = int(b.get("ref")) if b.get("ref") is not None else len(beats)
            except (TypeError, ValueError):
                k = len(beats)
            if brief.get("all_ai") and 0 <= k < len(ref_beats) and ref_beats[k].get("frame"):
                row["ref_frame"] = ref_beats[k]["frame"]  # кадр референсу → ракурс і крупність для художника
            beats.append(row)
        if len(beats) < 3:
            raise ReelError("Сценарист не склав кадри — спробуйте іншу ідею.")
        if material:
            reel.material = material
        reel.title = clean_text(str(r.get("title") or brief.get("title") or ""))[:200] or reel.title
        reel.caption = _clean_caption(str(r.get("caption") or ""))
        reel.facts = titles + [f"Перевірити: {clean_text(str(c))}" for c in (r.get("checks") or [])][:10]
    else:
        chosen = list(SourceAsset.objects.filter(id__in=asset_ids or [], kind="video")) if asset_ids else None
        import os
        import shutil
        import tempfile
        os.makedirs(R.WORK, exist_ok=True)
        folder = tempfile.mkdtemp(dir=R.WORK)
        try:
            for a in (chosen if chosen is not None else R.candidates(material, limit=15)):
                if a.markup_at:
                    continue
                try:
                    R.markup(a, folder)
                except Exception:
                    continue
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        if chosen is not None:
            scenes = list(VideoScene.objects.filter(asset__in=chosen, quality__gte=2).select_related("asset").order_by("-quality")[:80])
            material = material or (chosen[0].material if chosen else "")
        else:
            scenes = list(VideoScene.objects.filter(asset__material=material, quality__gte=3, asset__hidden=False)
                          .select_related("asset").order_by("-quality")[:80])
        p = R.plan(topic_of(brief), material, scenes, structure=structure, blog=blog)
        beats = p["beats"]
        reel.title, reel.caption = p["title"], p["caption"]
        reel.facts = p["facts"] + [f"Перевірити: {clean_text(str(c))}" for c in p["checks"]][:10]
        reel.material = material
        if blog is not None and p.get("promise"):
            brief["promise"] = p["promise"]
    reel.beats, reel.brief = beats, brief
    reel.stage, reel.busy, reel.error = "script", False, ""
    reel.save()
    return reel


def rewrite_texts(reel, call=None):
    """«Переписати тексти» на кроці 2: ті самі кадри, нові тексти на екрані й підпис під задум і мету. ≈$0.01."""
    blog = reel.blog or blogs.default_blog()
    task = ("Перепиши ТЕКСТИ ролика під задум. Кадри й тривалість не міняй. Кадр 1 — гачок до 7 слів, останній — одна дія до мети. "
            "До 7 слів на кадр, без штампів і емодзі; факти лише з бази знань. "
            'Відповідай ЛИШЕ JSON: {"texts":["текст кадру 1","..."],"caption":"підпис 2–4 речення"}')
    facts_text, _ = blogs.facts_block(blog, reel.title)
    lines = "\n".join(f"[{i}] {b.get('seconds')} с · у кадрі: {b.get('prompt') or b.get('what') or ''} · зараз: «{b.get('text', '')}»"
                      for i, b in enumerate(reel.beats))
    call = call or _call(blogs.system_for(blog, task), max_tokens=900)
    r = call(f"Задум: {topic_of(reel.brief or {'title': reel.title})}\n\nКадри:\n{lines}\n\nБаза знань:\n{facts_text or '(немає)'}")
    texts = [clean_text(str(t))[:80] for t in (r.get("texts") or [])]
    if len(texts) != len(reel.beats) or not all(texts):
        raise ValueError("Сценарист повернув не всі тексти — спробуйте ще раз.")
    prev = [b.get("text", "") for b in reel.beats]
    reel.beats = [dict(b, text=t) for b, t in zip(reel.beats, texts)]
    brief = dict(reel.brief or {}, prev_texts=prev, prev_caption=reel.caption)
    reel.brief = brief
    if r.get("caption"):
        reel.caption = _clean_caption(str(r["caption"]))
    reel.save(update_fields=["beats", "brief", "caption"])
    return reel


def undo_texts(reel):
    brief = dict(reel.brief or {})
    prev = brief.pop("prev_texts", None)
    if not prev or len(prev) != len(reel.beats):
        raise ValueError("Немає попередньої версії текстів.")
    reel.beats = [dict(b, text=t) for b, t in zip(reel.beats, prev)]
    reel.caption = brief.pop("prev_caption", reel.caption)
    reel.brief = brief
    reel.save(update_fields=["beats", "brief", "caption"])
    return reel


# ── Крок 3–4. Матеріал і стиль ─────────────────────────────────────────────────────────────────

def missing(reel):
    """Кадри без картинки (ШІ-опис є, але ще не намальовано)."""
    return [i for i, b in enumerate(reel.beats) if not b.get("image_id") and not b.get("scene_id")]


def editor_notes(reel):
    """Що бачить монтажер на кроці «Матеріал» (без ШІ, безкоштовно): відсутні кадри, слабкі кадри, повтори, довжина."""
    from .models import VideoScene
    notes = []
    q = {s.id: s for s in VideoScene.objects.filter(id__in=[b.get("scene_id") for b in reel.beats if b.get("scene_id")])}
    used = {}
    for i, b in enumerate(reel.beats):
        if not b.get("image_id") and not b.get("scene_id"):
            notes.append({"beat": i, "kind": "missing", "text": "Кадру ще немає — намалюйте ШІ або виберіть наш."})
            continue
        sc = q.get(b.get("scene_id"))
        if sc and sc.quality and sc.quality < 3:
            notes.append({"beat": i, "kind": "weak", "text": f"Слабкий кадр (якість {sc.quality}/5) — краще замінити."})
        if sc:
            if sc.id in used:
                notes.append({"beat": i, "kind": "repeat", "text": f"Той самий кадр, що й №{used[sc.id] + 1}."})
            used.setdefault(sc.id, i)
    total = sum(float(b.get("seconds") or 0) for b in reel.beats)
    if reel.beats and float(reel.beats[0].get("seconds") or 0) > 2.5:
        notes.append({"beat": 0, "kind": "hook", "text": "Гачок довший за 2,5 с — глядач може прогорнути."})
    if total > 45:
        notes.append({"beat": len(reel.beats) - 1, "kind": "long", "text": f"Ролик {total:.0f} с — для охоплення краще до 30 с."})
    return notes


def auto_fx(beats):
    """Монтажер за замовчуванням: гачок — різкий вхід, далі мʼякі розчинення; ШІ-фото — повільне наближення."""
    out = []
    for i, b in enumerate(beats):
        fx = {"transition": "cut" if i == 0 else ("zoom" if i == len(beats) - 1 else "fade"),
              "motion": "zoomin" if b.get("image_id") or not b.get("scene_id") else "none"}
        out.append(dict(b, fx=fx))
    return out


def _link_bytes(link_id):
    if not link_id:
        return None
    from apps.inbox.models import SharedLink
    link = SharedLink.objects.filter(pk=link_id).first()
    return (bytes(link.data), link.content_type or "image/jpeg") if link else None


def _texture(reel):
    """Для блогу з правилом «фактура справжня»: найкраще реальне фото матеріалу ролика (bytes, mime) і назва матеріалу."""
    if not (reel.blog and reel.blog.label_ai):
        return None, ""
    from apps.inbox.models import MediaLibraryItem
    from .carousels import best_photos
    from .material_specs import find_material
    material = find_material(f"{reel.material} {reel.title}") or reel.material
    for lib in best_photos(material, limit=1) if material else []:
        m = MediaLibraryItem.objects.filter(pk=lib).select_related("file").first()
        if m and m.file_id:
            return (bytes(m.file.data), m.file.content_type), material
    return None, material


def fill_missing(reel, limit=6, draft=False):
    """Намалювати всі відсутні кадри (≈$0.04 за кадр) — лише для кадрів з описом, без монтажу."""
    from . import aiimage, freeai
    beats = list(reel.beats)
    done = 0
    texture, material = _texture(reel)
    for i in missing(reel)[:limit]:
        b = dict(beats[i])
        prompt = b.get("prompt") or b.get("text") or reel.title
        comp = _link_bytes(b.get("ref_frame"))
        free = freeai.cf_image(prompt, "9:16") if draft and not texture else None  # чернетка: FLUX безкоштовно (не фактура Wallcov)
        if free:
            data, mime = free
        elif texture:  # Wallcov: стіну малюємо лише за реальним фото фактури
            data, mime = aiimage.regenerate(prompt, reel.blog, texture=texture, material=material, composition=comp,
                                            model=None if draft else aiimage.MODEL_PRO)
        else:
            data, mime = aiimage.regenerate(prompt, reel.blog, composition=comp, model=None if draft else aiimage.MODEL_PRO)
        link = aiimage.save(data, mime, f"reel-{reel.id}-{i}")
        b.update({"image_id": link.id, "ai": "draft" if free else "generated"})
        beats[i] = b
        done += 1
        reel.beats = beats
        reel.save(update_fields=["beats"])
    return done


# ── Крок 6. Перевірка командою ─────────────────────────────────────────────────────────────────

ACTIONS = {"transition": {"fade", "slide", "zoom", "cut"}, "motion": {"zoomin", "zoomout", "none"}}


def _valid_action(act, reel, blog):
    if not isinstance(act, dict):
        return None
    t, val = act.get("type"), act.get("value")
    try:
        beat = int(act.get("beat") or 0)
    except (TypeError, ValueError):
        return None
    if not 0 <= beat < len(reel.beats):
        return None
    if t in ACTIONS:
        if val not in ACTIONS[t]:
            return None
    elif t == "seconds":
        try:
            val = max(0.8, min(float(val), 8.0))
        except (TypeError, ValueError):
            return None
    elif t in ("text", "edit_frame", "regenerate", "caption"):
        val = (_clean_caption(str(val or ""))[:2200] if t == "caption" else clean_text(str(val or ""))[:300 if t != "text" else 80])
        if not val:
            return None
        if t in ("edit_frame", "regenerate") and blog.label_ai and not reel.beats[beat].get("image_id"):
            return None  # Wallcov: справжню фактуру не перемальовуємо
    else:
        return None
    return {"type": t, "beat": beat, "value": val}


def rule_checks(reel):
    """Перевірки без ШІ: хештеги, емодзі, тривалість, гачок, мітка ШІ."""
    out = []
    tags = re.findall(r"#\w+", reel.caption or "")
    if len(tags) > 5:
        out.append({"role": "smm", "title": f"Хештегів {len(tags)} — Instagram дозволяє до 5", "why": "Правило Instagram з 2025 року.", "action": None})
    if re.search("[\U0001F000-\U0001FAFF☀-➿]", reel.caption or ""):
        out.append({"role": "smm", "title": "У підписі є емодзі", "why": "Правило блогу: без смайлів.", "action": None})
    if not (reel.caption or "").strip():
        out.append({"role": "smm", "title": "Немає підпису", "why": "Підпис з ключовими словами допомагає пошуку Instagram.", "action": None})
    for n in editor_notes(reel):
        if n["kind"] in ("missing", "hook", "long", "repeat"):
            out.append({"role": "editor", "title": n["text"], "why": f"Кадр {n['beat'] + 1}.", "action": None})
    return out


def team_review(reel, call=None):
    blog = reel.blog or blogs.default_blog()
    lines = []
    for i, b in enumerate(reel.beats):
        fx = b.get("fx") or {}
        lines.append(f"[{i}] {b.get('seconds')} с · {'ШІ-кадр' if b.get('image_id') else 'справжній кадр'} · текст: «{b.get('text', '')}» · "
                     f"перехід: {fx.get('transition', 'cut')} · рух: {fx.get('motion', 'none')}"
                     + (f" · у кадрі: {b.get('prompt')}" if b.get("prompt") else ""))
    brief = reel.brief or {}
    prompt = (f"Задум: {topic_of(brief) if brief.get('title') else reel.title}\nТривалість: {reel.duration} с\n"
              f"Правило фактури: {'так — ШІ не малює покриття' if blog.label_ai else 'ні'}\n"
              f"Підпис:\n{(reel.caption or '')[:1200]}\n\nКадри:\n" + "\n".join(lines))
    call = call or _call(blogs.system_for(blog, REVIEW_TASK), max_tokens=2000)
    r = call(prompt)
    out = {"roles": {}, "verdict": clean_text(str(r.get("verdict") or ""))[:300], "rules": rule_checks(reel)}
    for key, name in ROLES.items():
        x = r.get(key) if isinstance(r.get(key), dict) else {}
        try:
            score = max(1, min(10, int(x.get("score") or 0))) if x.get("score") else None
        except (TypeError, ValueError):
            score = None
        notes = []
        for n in (x.get("notes") or [])[:3]:
            if not isinstance(n, dict) or not n.get("title"):
                continue
            notes.append({"title": clean_text(str(n["title"]))[:80], "why": clean_text(str(n.get("why") or ""))[:240],
                          "action": _valid_action(n.get("action"), reel, blog)})
        out["roles"][key] = {"name": name, "score": score, "notes": notes}
    reel.review = out
    reel.stage = "review"
    reel.save(update_fields=["review", "stage"])
    return out


# ── Пошук референсів по всьому інтернету (25.09: Олег — «пошук має працювати по всьому інтернету») ─────────
# Gemini з Google Search перевірено: для Instagram/TikTok не шукає й вигадує посилання — тому НЕ використовуємо.
# Працює звичайний пошуковик: DuckDuckGo (без ключа, безкоштовно) по кожній мережі через site:, + пошук Shorts на YouTube.
WEB_SITES = {"instagram": "instagram.com", "tiktok": "tiktok.com", "pinterest": "pinterest.com", "telegram": "t.me",
             "facebook": "facebook.com"}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
POST_RX = {"instagram": r"instagram\.com/(reel|p|tv)/", "tiktok": r"tiktok\.com/@[^/]+/(video|photo)/", "pinterest": r"pinterest\.[a-z.]+/pin/",
           "telegram": r"t\.me/[\w_]+/\d+", "facebook": r"facebook\.com/(reel|watch|[^/]+/videos)"}


def _platform(url):
    for k, rx in (("instagram", "instagram.com"), ("tiktok", "tiktok.com"), ("youtube", "youtube.com|youtu.be"),
                  ("pinterest", "pinterest."), ("telegram", "t.me/"), ("facebook", "facebook.com|fb.watch")):
        if re.search(rx, url):
            return k
    return "other"


LANGS = {"uk": ("ua", "uk"), "ru": ("ua", "ru"), "en": ("us", "en")}


def translate_query(q, langs):
    """Той самий запит різними мовами (Haiku, ≈$0.0005): {"uk": "...", "ru": "...", "en": "..."}; кеш на тиждень."""
    import hashlib
    from django.core.cache import cache
    langs = [l for l in langs if l in LANGS]
    key = "cf-tr:" + hashlib.md5(f"{q.lower()}|{','.join(sorted(langs))}".encode()).hexdigest()
    hit = cache.get(key)
    if hit:
        return hit
    out = {l: q for l in langs}
    if len(langs) > 1 or langs != ["uk"]:
        try:
            from apps.crm.ai import claude_json
            r = claude_json(f"Запит для пошуку коротких відео: «{q}». Переклади природно, як шукали б люди, мовами: {', '.join(langs)}. "
                            'Відповідай ЛИШЕ JSON: {"uk":"...","ru":"...","en":"..."} (лише потрібні мови).',
                            model="claude-haiku-4-5", max_tokens=200, source=SOURCE) or {}
            out.update({l: clean_text(str(r[l]))[:120] for l in langs if r.get(l)})
        except Exception:
            pass
    cache.set(key, out, 7 * 24 * 3600)
    return out


def _serper(ep, body):
    import os
    req = urllib.request.Request(f"https://google.serper.dev/{ep}", data=json.dumps(body).encode(),
                                 headers={"X-API-KEY": os.environ["SERPER_API_KEY"], "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


class SearchBlocked(Exception):
    pass


def search_ddg(q, limit=10):
    """Запасний шлях без ключа: DuckDuckGo. Часті запити він приймає за бота — тоді SearchBlocked."""
    import html as _html
    data = urllib.parse.urlencode({"q": q, "kl": "ua-uk"}).encode()
    req = urllib.request.Request("https://html.duckduckgo.com/html/", data=data, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        page = r.read().decode("utf8", "ignore")
    if "anomaly" in page and "result__a" not in page:
        raise SearchBlocked()
    out = []
    for href, title, snippet in re.findall(r'class="result__a" href="([^"]+)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</a>', page, re.S):
        m = re.search(r"uddg=([^&]+)", href)
        url = urllib.parse.unquote(m.group(1)) if m else href
        strip = lambda t: clean_text(re.sub(r"<[^>]+>", "", _html.unescape(t)))
        out.append({"url": url, "title": strip(title), "why": strip(snippet), "thumb": ""})
        if len(out) >= limit:
            break
    return out


def search_site(q, site, lang="uk", page=1):
    """Один пошук по мережі однією мовою: кеш на добу; Serper (розділ «Відео» — з превʼю, далі звичайний), інакше DuckDuckGo."""
    import hashlib
    import os
    from django.core.cache import cache
    key = "cf-web2:" + hashlib.md5(f"{q.lower()}|{site}|{lang}|{page}".encode()).hexdigest()
    hit = cache.get(key)
    if hit is not None:
        return hit
    gl, hl = LANGS.get(lang, LANGS["uk"])
    from . import freeai
    rows = None
    if os.environ.get("SERPER_API_KEY"):
        try:
            body = {"q": f"{q} site:{site}", "gl": gl, "hl": hl, "page": page}
            rows = [{"url": x.get("link", ""), "title": x.get("title", ""), "why": x.get("snippet", ""), "thumb": x.get("imageUrl", ""),
                     "date": x.get("date", ""), "author": x.get("channel", "")} for x in _serper("videos", body).get("videos") or []]
            if len(rows) < 5:
                rows += [{"url": x.get("link", ""), "title": x.get("title", ""), "why": x.get("snippet", ""), "thumb": x.get("imageUrl", ""),
                          "date": x.get("date", "")} for x in _serper("search", dict(body, q=f"site:{site} {q}")).get("organic") or []]
        except Exception:
            rows = None  # ліміт Serper вичерпано / збій — нижче Tavily
    if rows is None and page == 1:
        rows = freeai.tavily_search(f"{q} site:{site}") or None
    if rows is None:
        rows = search_ddg(f"site:{site} {q}") if page == 1 else []
    for x in rows:  # Instagram: нік автора з опису («… comments - nick on …») — для офіційного Business Discovery
        if "instagram.com" in x.get("url", ""):
            x["ig_user"] = freeai.ig_username_from_snippet(x.get("why", ""))
    rows = [{**x, "title": clean_text(x["title"])[:160], "why": clean_text(x["why"])[:240]} for x in rows if x.get("url", "").startswith("http")]
    cache.set(key, rows, 24 * 3600)
    return rows


def search_all(q, where="web", langs=None, nets=None, page=1):
    """Пошук референсів по мережах і мовах. langs — uk/ru/en (запит перекладається); nets — instagram, tiktok, youtube,
    pinterest, telegram, facebook; page — «показати ще». Повертає {"items": [...], "note": "...", "queries": N}."""
    import time
    q = (q or "").strip()
    if len(q) < 2:
        raise ValueError("Введіть слово для пошуку.")
    langs = [l for l in (langs or ["uk", "ru"]) if l in LANGS] or ["uk"]
    nets = [n for n in (nets or ["youtube", *WEB_SITES]) if n == "youtube" or n in WEB_SITES]
    if where == "youtube":
        nets = ["youtube"]
    words = translate_query(q, langs)
    out, blocked, failed, queries = [], False, [], 0
    for lang in langs:
        word = words.get(lang) or q
        if "youtube" in nets and page <= 2:
            try:
                yt = search_youtube(word, limit=20, lang=lang)
                yt = yt[:10] if page == 1 else yt[10:20]
                out += [dict(x, platform="youtube", why=x.get("author") or "", lang=lang) for x in yt]
            except Exception:
                failed.append("YouTube")
        for n in nets:
            if n == "youtube" or blocked:
                continue
            try:
                rows = search_site(word, WEB_SITES[n], lang=lang, page=page)
                queries += 1
            except SearchBlocked:
                blocked = True
                continue
            except Exception:
                failed.append(n)
                continue
            out += [dict(x, platform=n, views="", author=x.get("author", ""), lang=lang) for x in rows if re.search(POST_RX[n], x["url"])]
            if not __import__("os").environ.get("SERPER_API_KEY"):
                time.sleep(0.8)  # пошуковик без ключа не любить запити підряд
    seen, by = set(), {}
    for x in out:
        k = youtube_id(x["url"]) or x["url"].split("?")[0].rstrip("/")
        if k not in seen:
            seen.add(k)
            by.setdefault(x["platform"], []).append(x)
    mixed = []
    while any(by.values()):  # чергуємо мережі, щоб одна не займала весь список
        for k in list(by):
            if by[k]:
                mixed.append(by[k].pop(0))
    note = ""
    if blocked:
        note = "Instagram, TikTok, Pinterest, Telegram і Facebook зараз не шукаються: пошуковик без ключа блокує сервер. Показую YouTube."
    elif failed:
        note = "Не відповіли: " + ", ".join(sorted(set(failed))) + "."
    return {"items": mixed[:120], "note": note, "queries": queries, "words": words}



# ── Озвучка: виправити наголос/вимову словами (безкоштовно, Groq) ──────────────────────────────────

SPEECH_FIX = """Ти готуєш текст для синтезу мовлення ElevenLabs (українська). Тобі дають репліку і вказівку власника, що звучить неправильно
(наголос, вимова, пауза, темп). Перепиши ЛИШЕ так, щоб синтезатор вимовив правильно:
- наголос позначай знаком наголосу (комбінований гострий акцент U+0301) одразу ПІСЛЯ наголошеної голосної, напр. «шо́вк», «фарбува́ти»;
- якщо слово все одно читається неправильно — перепиши його фонетично (як чується), без зміни сенсу;
- паузу — комою або «...»;
- не змінюй інших слів, не додавай пояснень. Поверни ЛИШЕ готовий текст репліки."""


def fix_speech(reel, idx, instruction):
    """Власник пише, що виправити у вимові → Groq переписує текст для синтезу (say_tts); екранний текст не змінюється.
    Перезвучується лише ця репліка (символи ElevenLabs), перемонтаж без ШІ-картинок."""
    from . import freeai
    b = dict(reel.beats[idx])
    base = (b.get("say_tts") or b.get("say") or b.get("text") or "").strip()
    instruction = (instruction or "").strip()
    if not base or len(instruction) < 3:
        raise ValueError("Напишіть, що саме звучить неправильно.")
    out = freeai.groq_chat(SPEECH_FIX, f"Репліка: {base}\nЩо виправити: {instruction}")
    if not out:
        raise ValueError("Безкоштовний ШІ зараз не відповів — спробуйте ще раз за хвилину.")
    out = out.strip().strip("«»\"'")[:400]
    b["say_tts"] = out
    b.setdefault("fixes", []).append(instruction[:200])
    beats = list(reel.beats)
    beats[idx] = b
    reel.beats = beats
    reel.save(update_fields=["beats"])
    return out
