"""Агент заводу (26.09.2026, запит Олега): чат, у якому власник дає завдання ШІ як маркетологу, SMM-спеціалісту,
аналітику чи продюсеру. Агент бачить дані заводу (блог, рилси, каруселі, Telegram, питання клієнтів, звіт аналітика,
стрічку ніші) і записи баз знань «Маркетинг» та «Бізнес і найм», відповідає документом, таблицею або дашбордом.

Модель вибирається в чаті: Claude (Anthropic), Gemini (Google), GPT (відкрита модель OpenAI gpt-oss через Groq —
безкоштовно; платний GPT-5 потребує ключа OpenAI, його на сервері немає). Кожен виклик пишеться в AiUsage.
Нічого не публікує і нічого не змінює в заводі — лише відповідає.
"""
import json
import os
import re
import urllib.request
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

SOURCE = "content_factory.agent"
MONTH_CAP_USD = 15.0  # стеля агента на місяць; видно в чаті

# id → (назва в чаті, постачальник, $ за 1M вхід, $ за 1M вихід, підказка)
MODELS = {
    "claude-sonnet-4-6": ("Claude Sonnet 4.6", "anthropic", 3.0, 15.0, "збалансовано: стратегія, тексти, розбори"),
    "claude-opus-5": ("Claude Opus 5", "anthropic", 5.0, 25.0, "найглибший аналіз, дорожче"),
    "claude-haiku-4-5": ("Claude Haiku 4.5", "anthropic", 1.0, 5.0, "швидко й дешево"),
    "gemini-3.1-pro-preview": ("Gemini 3.1 Pro", "google", 2.0, 12.0, "Google: довгі документи, орієнтовна ціна"),
    "gemini-3.8-flash": ("Gemini 3.8 Flash", "google", 0.3, 2.5, "Google: швидко й дешево, орієнтовна ціна"),
    "openai/gpt-oss-120b": ("GPT (gpt-oss 120B)", "groq", 0.0, 0.0, "відкрита модель OpenAI через Groq — безкоштовно"),
}
DEFAULT_MODEL = "claude-sonnet-4-6"

ROLES = {
    "marketer": ("Маркетолог", "Ти — маркетолог-стратег Wallcov. Мислиш позиціонуванням, офером, воронкою, болями аудиторії й "
                 "цифрами. Спираєшся на прийоми з бази «Маркетинг» (Уланов, Морозов, ОАЗИС, КНБ, ATM) і називаєш, який прийом береш."),
    "smm": ("SMM-спеціаліст", "Ти — SMM-спеціаліст, що веде кілька блогів Wallcov. Думаєш рубриками, частотою, форматами "
            "(рилси, каруселі, Telegram), гачками перших секунд, обкладинками, найкращим часом, залученням і контент-планом."),
    "analyst": ("Аналітик", "Ти — аналітик контенту. Рахуєш на цифрах заводу: що вийшло, перегляди, реакції, що спрацювало "
                "в ніші. Даєш висновки з числами й дашборд. Не вигадуєш цифр — якщо даних немає, так і кажеш."),
    "producer": ("Продюсер відео", "Ти — продюсер і сценарист коротких відео. Пишеш сценарії рилсів по кадрах: гачок до 1,5 с, "
                 "план кадрів, текст на екрані, озвучка, заклик. Фактура Wallcov у кадрі — лише справжня."),
}

RULES = """ПРАВИЛА ВІДПОВІДІ
- Мова: українська (якщо власник пише російською — відповідай російською). Прямо, по-людськи, без води.
- Заборонено ШІ-штампи («Плануєш… і не знаєш», «Хочеш…, але боїшся», «Мрієш про…») і емодзі-прикраси.
- Цифри, ціни й факти — лише з блоку ДАНІ ЗАВОДУ або записів бази. Якщо даних немає — скажи, яких саме не вистачає.
- Коли береш прийом із бази знань, познач його: «Методика: <назва запису>».
- Формат — Markdown: заголовки ##, списки, таблиці | a | b |. Документ — структурований, з висновком і кроками.
- Якщо просять дашборд або цифри — додай рівно один блок:
```dashboard
{"title": "...", "kpis": [{"label": "...", "value": "...", "note": "..."}], "bars": [{"title": "...", "items": [{"label": "...", "value": 12}]}]}
```
  (value в bars — число; kpis — до 6; bars — до 3 графіків по до 10 рядків).
- Ти лише радиш: нічого не публікуєш і не змінюєш у заводі. Наприкінці — 1–3 конкретні кроки, де саме в заводі їх зробити.
"""


def month_spent():
    from apps.crm.models import AiUsage
    start = timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return float(sum(AiUsage.objects.filter(source=SOURCE, created_at__gte=start).values_list("cost_usd", flat=True)) or 0)


# ── Контекст: дані заводу ────────────────────────────────────────────────────────────────────────

def snapshot(blog):
    """Короткий зріз заводу для промпта (без ШІ, лише БД)."""
    from .models import AnalystReport, Carousel, FeedItem, QuestionTopic, ReelDraft, TgPost
    now = timezone.now()
    week, month = now - timedelta(days=7), now - timedelta(days=30)
    L = []
    if blog:
        L.append(f"БЛОГ: «{blog.name}» (тип: {blog.get_kind_display()}). Про що: {blog.about or '—'}")
        L.append(f"Мета: {blog.goal or '(не вказана)'}. Заклик: {blog.cta or '(немає)'}")
        L.append("Майстер-промт блогу:\n" + (blog.master_prompt or "(порожній)")[:1800])
        accs = ", ".join(f"{c.platform}:@{c.handle}" for c in blog.channels.filter(role="own")[:8])
        L.append(f"Акаунти: {accs or 'не привʼязані'}")
    reels = ReelDraft.objects.filter(blog=blog) if blog else ReelDraft.objects.all()
    L.append(f"\nРИЛСИ: усього {reels.count()}, чернеток {reels.filter(status=ReelDraft.Status.DRAFT).count()}, "
             f"за 30 днів створено {reels.filter(created_at__gte=month).count()}.")
    for r in reels.order_by("-created_at")[:8]:
        pub = ", ".join(k for k, v in (r.published or {}).items() if v) or "не опубліковано"
        L.append(f"- «{r.title}» · {r.get_status_display()} · {r.material or '—'} · {pub}")
    cars = Carousel.objects.filter(blog=blog) if blog else Carousel.objects.all()
    L.append(f"\nКАРУСЕЛІ: усього {cars.count()}.")
    for c in cars.order_by("-created_at")[:5]:
        L.append(f"- «{c.title or c.topic}» · {c.get_status_display()}")
    if not blog or blog.slug == "wallcov":
        pub = TgPost.objects.filter(status=TgPost.Status.PUBLISHED, published_at__gte=month).order_by("-published_at")
        L.append(f"\nTELEGRAM @wallcovpro за 30 днів: {pub.count()} постів, переглядів {sum(p.views or 0 for p in pub)}.")
        for p in pub[:10]:
            L.append(f"- {timezone.localtime(p.published_at):%d.%m} «{p.title}» · перегляди {p.views or 0} · реакції {p.reactions or 0}")
        topics = (QuestionTopic.objects.exclude(status=QuestionTopic.Status.IGNORED)
                  .annotate(n7=Count("mentions", filter=Q(mentions__asked_at__gte=week))).filter(n7__gt=0).order_by("-n7")[:10])
        L.append("\nПИТАННЯ КЛІЄНТІВ за 7 днів (тема · скільки разів):")
        L += [f"- {t.title} · {t.n7}" for t in topics] or ["- немає даних"]
    rep = AnalystReport.objects.filter(blog=blog).first() if blog else AnalystReport.objects.first()
    if rep:
        L.append(f"\nОСТАННІЙ ЗВІТ АНАЛІТИКА ({timezone.localtime(rep.created_at):%d.%m}): {rep.summary[:1200]}")
    if blog:  # 27.09: СВІЖІ ролики власних акаунтів (TikTok API / Virale) — важливіші за майстер-промт, він може бути застарілим
        own = {h.lower().lstrip(".") for h in blog.channels.filter(role="own").values_list("handle", flat=True)}
        mine = FeedItem.objects.filter(username__in=own).exclude(published_at=None).order_by("-published_at")[:15]
        if mine:
            L.append("\nНАШІ ОСТАННІ РОЛИКИ (живі дані акаунтів; якщо суперечать майстер-промту — довіряй роликам і скажи про розбіжність):")
            L += [f"- {timezone.localtime(i.published_at):%d.%m} {i.platform} @{i.username} · {i.views or 0} переглядів · {i.likes or 0} лайків · "
                  f"{(i.caption or '')[:100]}" for i in mine]
        else:
            L.append("\nНАШІ РОЛИКИ: даних з акаунтів ще немає — висновки лише з CRM, скажи про це власнику.")
    handles = [h.lower().lstrip(".") for h in blog.channels.exclude(role="own").values_list("handle", flat=True)] if blog else []
    feed = FeedItem.objects.filter(username__in=handles) if handles else FeedItem.objects.none()
    top = feed.exclude(views=None).order_by("-views")[:6]
    if top:
        L.append("\nСТРІЧКА НІШІ (найбільше переглядів):")
        L += [f"- @{i.username} · {i.views} переглядів · {(i.caption or '')[:90]}" for i in top]
    return "\n".join(L)


_W = re.compile(r"[A-Za-zА-Яа-яІіЇїЄєҐґ']{5,}")


def kb_hits(text, limit=10):
    """Записи баз «Маркетинг» і «Бізнес і найм», що містять слова із запиту (пошук по основі слова, без ШІ)."""
    from .models import BlogFact
    stems = sorted({w.lower()[:6] for w in _W.findall(text or "")}, key=len, reverse=True)[:8]
    if not stems:
        return []
    q = Q()
    for s in stems:
        q |= Q(title__icontains=s) | Q(text__icontains=s)
    rows = list(BlogFact.objects.filter(blog__slug__in=["marketing", "business"], active=True).filter(q)
                .select_related("blog").only("title", "text", "blog__slug")[:400])
    rows.sort(key=lambda f: -sum(s in (f.title + " " + f.text).lower() for s in stems))
    return rows[:limit]


# ── Виклики моделей ──────────────────────────────────────────────────────────────────────────────

def _post(url, body, headers, timeout=120):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json",
                                                                               "User-Agent": "wallcov-crm/1.0", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _call(model, system, messages, max_tokens=3000):
    """messages — [{"role": "user"|"assistant", "content": str}]. Повертає (текст, вхідні токени, вихідні токени)."""
    prov = MODELS[model][1]
    if prov == "anthropic":
        r = _post("https://api.anthropic.com/v1/messages",
                  {"model": model, "max_tokens": max_tokens, "system": system, "messages": messages},
                  {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
        text = "".join(b.get("text", "") for b in r.get("content") or [] if b.get("type") == "text")
        u = r.get("usage") or {}
        return text, int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0)
    if prov == "google":
        contents = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]} for m in messages]
        r = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                  {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents,
                   "generationConfig": {"maxOutputTokens": max_tokens * 2}},
                  {"x-goog-api-key": os.environ["GEMINI_API_KEY"]}, timeout=180)
        parts = ((r.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        u = r.get("usageMetadata") or {}
        return text, int(u.get("promptTokenCount") or 0), int(u.get("candidatesTokenCount") or 0) + int(u.get("thoughtsTokenCount") or 0)
    r = _post("https://api.groq.com/openai/v1/chat/completions",
              {"model": model, "max_tokens": max_tokens, "temperature": 0.4,
               "messages": [{"role": "system", "content": system}] + messages},
              {"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"})
    u = r.get("usage") or {}
    return (r["choices"][0]["message"].get("content") or ""), int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)


class AgentError(Exception):
    pass


def reply(chat, text, role, model, blog):
    """Додає повідомлення власника в чат, питає модель, зберігає відповідь. Повертає повідомлення агента."""
    from apps.crm.models import AiUsage
    if model not in MODELS:
        raise AgentError("Невідома модель.")
    if role not in ROLES:
        raise AgentError("Невідома роль.")
    if MODELS[model][2] and month_spent() >= MONTH_CAP_USD:
        raise AgentError(f"Досягнуто стелі агента ${MONTH_CAP_USD:.0f} на місяць. Виберіть GPT (безкоштовно) або почекайте до 1-го числа.")
    hits = kb_hits(text + " " + " ".join(m["text"] for m in chat.messages[-4:] if m.get("who") == "me"))
    kb = "\n".join(f"[{'Маркетинг' if f.blog.slug == 'marketing' else 'Бізнес і найм'}] {f.title}: {f.text[:500]}" for f in hits)
    system = (f"{ROLES[role][1]}\n\n{RULES}\n\nДАНІ ЗАВОДУ (станом на {timezone.localtime():%d.%m.%Y %H:%M}):\n{snapshot(blog)}"
              f"\n\nЗАПИСИ БАЗ ЗНАНЬ, схожі на запит (бери лише доречні):\n{kb or '— нічого схожого не знайдено'}")
    hist = [{"role": "assistant" if m["who"] == "agent" else "user", "content": m["text"]} for m in chat.messages[-12:] if m.get("text")]
    hist.append({"role": "user", "content": text})
    try:
        out, tin, tout = _call(model, system, hist)
    except urllib.error.HTTPError as e:
        raise AgentError(f"Модель відповіла помилкою {e.code}: {e.read()[:200].decode('utf8', 'ignore')}") from None
    except Exception as e:  # мережа, таймаут, немає ключа
        raise AgentError(f"Не вдалося звернутися до моделі: {str(e)[:200]}") from None
    if not out.strip():
        raise AgentError("Модель повернула порожню відповідь — спробуйте ще раз або іншу модель.")
    cost = (tin * MODELS[model][2] + tout * MODELS[model][3]) / 1_000_000
    AiUsage.objects.create(source=SOURCE, model=model, in_tok=tin, out_tok=tout, cost_usd=cost)
    now = timezone.now().isoformat()
    chat.messages = (chat.messages or []) + [
        {"who": "me", "text": text, "at": now, "role": role, "model": model},
        {"who": "agent", "text": out.strip(), "at": now, "role": role, "model": model, "cost": round(cost, 4),
         "kb": [f.title for f in hits][:10]},
    ]
    if not chat.title:
        chat.title = text.strip().split("\n")[0][:80]
    chat.role, chat.model, chat.blog = role, model, blog
    chat.cost_usd = float(chat.cost_usd or 0) + cost
    chat.save()
    return chat.messages[-1]
