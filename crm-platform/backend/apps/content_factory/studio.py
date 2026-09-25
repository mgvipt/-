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
Кожна ідея:
- title — тема до 10 слів;
- hook — текст першого кадру до 7 слів: конкретика або неочікуваний факт, без штампів і риторичних питань-пустушок;
- goal — одна дія глядача: save|share|comment|dm|follow;
- why — 1 речення: чому спрацює для цієї аудиторії й мети, з опорою на дані нижче (що вистрілило, питання, памʼять);
- shots — які кадри потрібні, коротко через «;»;
- fit — "ours" (є в наших кадрах з каталогу), "ai" (малює ШІ), "shoot" (треба доснімати).
Не повторюй теми з памʼяті блогу. Факти й цифри — лише з бази знань. Без емодзі.
Відповідай ЛИШЕ JSON: {"ideas":[{"title":"...","hook":"...","goal":"save","why":"...","shots":"...","fit":"ours"}]}"""

REF_PROMPT = """Це ролик-референс з соцмережі. Розбери, ЧОМУ він чіпляє, щоб повторити будову (не текст і не кадри) у своєму ролику.
Відповідай ЛИШЕ JSON: {"summary":"про що ролик, 1 речення","hook":"що відбувається в перші 3 с і чому зупиняє",
"beats":[{"seconds":2.0,"purpose":"гачок|проблема|доказ|показ|заклик","what":"що в кадрі"}],"text_style":"як виглядає текст на екрані",
"why_works":"1–2 речення","total_seconds":15}"""

REVIEW_TASK = """Ти — команда перевірки рилса перед публікацією. Три ролі дивляться ролик кожна зі свого боку:
- smm (SMM-редактор): чи зупиняє перший кадр за 1–3 с; одна дія в кінці й вона веде до мети блогу; підпис і перший рядок з ключовими
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


def analyze_ref(url="", feed_item=None):
    """Розбір референсу: YouTube — Gemini дивиться сам за посиланням (≈$0.01–0.04); інше — лише підпис/опис сторінки."""
    if feed_item is not None:
        url = url or feed_item.url
    yid = youtube_id(url)
    if yid:
        try:
            r = _gemini([{"fileData": {"fileUri": f"https://www.youtube.com/watch?v={yid}"}}, {"text": REF_PROMPT}], max_tokens=2500)
            r = r if isinstance(r, dict) else {}
            r["url"], r["watched"] = url, True
            return r
        except ReelError as e:
            note = f"Gemini не зміг переглянути ({str(e)[:80]}) — беру лише опис."
    else:
        note = "Відео цієї мережі ШІ не переглядає за посиланням — беру підпис і показники."
    text = ""
    if feed_item is not None:
        text = f"Підпис: {feed_item.caption[:600]}\nПереглядів: {feed_item.views}, лайків: {feed_item.likes}, коментарів: {feed_item.comments}"
    elif url:
        try:
            from .learn import text_from_url
            text = text_from_url(url)[:1500]
        except Exception:
            text = ""
    return {"url": url, "watched": False, "summary": text[:600], "note": note}


def ideas(blog, source="ai", text="", url="", feed_ids=None, call=None):
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
        if url:
            refs.append(analyze_ref(url=url))
        if not refs:
            raise ValueError("Виберіть ролик зі стрічки або вставте посилання.")
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
                    "goal": i.get("goal") if i.get("goal") in GOALS else "save",
                    "why": clean_text(str(i.get("why") or ""))[:300], "shots": clean_text(str(i.get("shots") or ""))[:300],
                    "fit": i.get("fit") if i.get("fit") in FITS else ("ours" if blog.real_footage else "ai")})
    if not out:
        raise ValueError("Продюсер не повернув ідей — спробуйте ще раз.")
    return {"ideas": out, "refs": refs}


def search_youtube(q, limit=12):
    """Пошук Shorts на YouTube без ключа API: сторінка результатів → назва, посилання, перегляди. Безкоштовно."""
    q = (q or "").strip()
    if len(q) < 2:
        raise ValueError("Введіть слово для пошуку.")
    url = "https://www.youtube.com/results?" + urllib.parse.urlencode({"search_query": q + " #shorts", "hl": "uk"})
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
                vid = (re.search(r'"videoId":"([\w-]{11})"', json.dumps(s)) or [None, None])[1]
                if vid and vid not in seen:
                    seen.add(vid)
                    title = (s.get("accessibilityText") or (s.get("headline") or {}).get("simpleText") or "")[:160]
                    out.append({"url": f"https://www.youtube.com/shorts/{vid}", "title": title, "views": "", "author": "",
                                "thumb": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"})
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
    return (f"{brief.get('title', '')}. Перший кадр (гачок): «{brief.get('hook', '')}»."
            + (f" Мета ролика — щоб глядач захотів {goal}." if goal else "")
            + (f" Потрібні кадри: {brief['shots']}." if brief.get("shots") else ""))[:900]


def build_script(reel, material="", asset_ids=None):
    """Сценарій під задум: з нашими кадрами (розмітка → план) або ШІ-кадри (описи без картинок — малюються на кроці 3)."""
    from .models import ReelDraft, SourceAsset, VideoScene
    from . import reels as R
    blog, brief = reel.blog, reel.brief or {}
    structure = brief.get("structure") or None
    if blog is not None and not blog.real_footage and not asset_ids:
        blogs.require_ready(blog)
        facts_text, titles = blogs.facts_block(blog, brief.get("title", ""))
        call = _call(blogs.system_for(blog, R.AI_PLAN_TASK), max_tokens=1400)
        prompt = f"Тема: {topic_of(brief)}\n\nБаза знань:\n{facts_text or '(немає)'}\n\n" + blogs.memory_block(blog)
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
            beats.append({"text": clean_text(str(b.get("text") or ""))[:80], "seconds": round(secs, 2), "prompt": ip[:600]})
        if len(beats) < 3:
            raise ReelError("Сценарист не склав кадри — спробуйте іншу ідею.")
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


def fill_missing(reel, limit=6):
    """Намалювати всі відсутні кадри (≈$0.04 за кадр) — лише для кадрів з описом, без монтажу."""
    from . import aiimage
    beats = list(reel.beats)
    done = 0
    for i in missing(reel)[:limit]:
        b = dict(beats[i])
        data, mime = aiimage.regenerate(b.get("prompt") or b.get("text") or reel.title, reel.blog)
        link = aiimage.save(data, mime, f"reel-{reel.id}-{i}")
        b.update({"image_id": link.id, "ai": "generated"})
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


def _web_api(q, limit=10):
    """Пошукове API з ключем (стабільно): SERPER_API_KEY (Google, 2 500 запитів безкоштовно) або BRAVE_API_KEY (2 000/міс)."""
    import os
    if os.environ.get("SERPER_API_KEY"):
        req = urllib.request.Request("https://google.serper.dev/search", data=json.dumps({"q": q, "gl": "ua", "hl": "uk", "num": limit}).encode(),
                                     headers={"X-API-KEY": os.environ["SERPER_API_KEY"], "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return [{"url": x.get("link", ""), "title": x.get("title", ""), "why": x.get("snippet", "")} for x in json.load(r).get("organic") or []]
    if os.environ.get("BRAVE_API_KEY"):
        req = urllib.request.Request("https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode({"q": q, "count": limit}),
                                     headers={"X-Subscription-Token": os.environ["BRAVE_API_KEY"], "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return [{"url": x.get("url", ""), "title": x.get("title", ""), "why": re.sub(r"<[^>]+>", "", x.get("description", ""))}
                    for x in (json.load(r).get("web") or {}).get("results") or []]
    return None


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
        out.append({"url": url, "title": strip(title), "why": strip(snippet)})
        if len(out) >= limit:
            break
    return out


def search_site(q, site):
    """Один пошук по мережі: кеш на добу (щоб не смикати пошуковик повторно), спершу API з ключем, інакше DuckDuckGo."""
    from django.core.cache import cache
    import hashlib
    key = "cf-web:" + hashlib.md5(f"{q.lower()}|{site}".encode()).hexdigest()
    hit = cache.get(key)
    if hit is not None:
        return hit
    query = f"site:{site} {q}"
    rows = _web_api(query)
    if rows is None:
        rows = search_ddg(query)
    rows = [{"url": x["url"], "title": clean_text(x["title"])[:160], "why": clean_text(x["why"])[:240]} for x in rows if x.get("url", "").startswith("http")]
    cache.set(key, rows, 24 * 3600)
    return rows


def search_all(q, where="web", platforms=None):
    """Пошук референсів: where=web — Instagram, TikTok, Pinterest, Telegram, Facebook + YouTube Shorts; where=youtube — лише YouTube.
    Лише публікації (ролик/пост), не профілі. Повертає {"items": [...], "note": "..."}."""
    import time
    q = (q or "").strip()
    if len(q) < 2:
        raise ValueError("Введіть слово для пошуку.")
    out, blocked, failed = [], False, []
    try:
        out += [dict(x, platform="youtube", why=x.get("author") or "") for x in search_youtube(q, limit=8)]
    except Exception:
        failed.append("YouTube")
    if where != "youtube":
        for n, k in enumerate(k for k in (platforms or WEB_SITES) if k in WEB_SITES):
            if blocked:
                break
            try:
                rows = search_site(q, WEB_SITES[k])
            except SearchBlocked:
                blocked = True
                break
            except Exception:
                failed.append(k)
                continue
            out += [dict(x, platform=k, thumb="", views="", author="") for x in rows if re.search(POST_RX[k], x["url"])]
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
        note = ("Пошуковик тимчасово обмежив запити з сервера — показую, що встиг знайти. Для стабільного пошуку по всіх мережах "
                "потрібен безкоштовний ключ пошуку (Serper або Brave) — див. «Налаштування пошуку».")
    elif failed:
        note = "Не відповіли: " + ", ".join(failed) + "."
    return {"items": mixed[:30], "note": note}
