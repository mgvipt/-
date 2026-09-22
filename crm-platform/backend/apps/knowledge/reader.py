"""ОДИН читач бази знань для всіх ІІ-агентів CRM.

    context_for(agent, query=None, limit=20)  → текст для промпта агента

Бере ТІЛЬКИ затверджені записи, у яких цей агент є в «Для яких агентів».
Спершу всі правила (тип «Правило»), далі записи, найближчі до розмови (query),
і наприкінці — ціни з каталогу CRM для товарів записів і матеріалів із розмови.
Порожній рядок = база для агента порожня → агент працює на старому вбудованому тексті.

    merge_with_fallback(agent, chunks, query) → вбудований текст, де кожна тема замінюється
    затвердженими записами цієї теми (якщо вони є). Тема без затверджених записів — старий текст.
"""
import re
import threading
from contextlib import contextmanager

from django.db import connection

from . import catalog
from .models import KnowledgeItem
from .topics import guess_topics

AGENT_CODES = [c for c, _ in KnowledgeItem.AGENTS]
TOPIC_ORDER = [c for c, _ in KnowledgeItem.TOPICS]
TOPIC_LABEL = dict(KnowledgeItem.TOPICS)
KIND_LABEL = dict(KnowledgeItem.KINDS)
_STOP = {"якщо", "який", "якій", "якої", "можна", "потрі", "тільк", "також", "будь-", "будьл", "дякую", "добри",
         "вітаю", "здрав", "будет", "будет", "можно", "тольк", "когда", "коли", "через", "після", "після",
         "wallc", "клієн", "мене", "вона", "воно", "вони", "цього", "цей", "така", "такий", "дуже", "треба"}
ITEM_CHARS = 1500


def _stems(text):
    words = re.findall(r"[a-zа-яіїєґʼ'’&]+", (text or "").lower())
    return {w[:5] for w in words if len(w) >= 4 and w[:5] not in _STOP}


_TEST = threading.local()


@contextmanager
def test_pool(items):
    """ЛИШЕ для «Тестового чату» (ai-kb2, 14.09): у межах ОДНОГО запиту (цей потік) читач бачить переданий
    набір записів — напр. «затверджене + чернетки» або одну тему, — щоб Олег перевірив чернетки ДО затвердження
    на тих самих промптах, що й справжні агенти. Інші запити (справжні агенти) цього не бачать."""
    prev = getattr(_TEST, "items", None)
    _TEST.items = list(items)
    try:
        yield
    finally:
        _TEST.items = prev


def approved_for(agent):
    """Затверджені записи для агента (з товарами), у порядку пріоритету."""
    if agent not in AGENT_CODES:
        return []
    pool = getattr(_TEST, "items", None)
    if pool is not None:
        return [i for i in pool if agent in (i.audience or [])]
    qs = KnowledgeItem.objects.filter(status="approved").prefetch_related("products")
    if connection.vendor == "postgresql":
        qs = qs.filter(audience__contains=[agent])
    return [i for i in qs.order_by("priority", "id") if agent in (i.audience or [])]


def select(agent, query=None, limit=20, items=None):
    """22.09.2026 (критичний фікс, Олег: ІІ-РОП сказав «інформації про адресу немає», хоча вона
    затверджена в базі знань). Причина: правила (kind="rule") ЗАВЖДИ йдуть першими, а результат
    обрізався до limit СПІЛЬНО з ними. У rop_hint/yulia_web рівно 15 правил — при limit=15 (типове
    значення по коду) під тематичні записи не лишалось МІСЦЯ ВЗАГАЛІ: жоден запит ніколи не бачив
    жодного тематичного запису бази знань (адресу, ціни, все) — тільки самі правила. Тепер правила
    завжди включені ПОВНІСТЮ (їх мало, це і є їхнє призначення — універсальні обмеження), а limit
    діє лише на тематичні/пошукові записи ДОДАТКОВО до них."""
    items = approved_for(agent) if items is None else items
    rules = [i for i in items if i.kind == "rule"]
    rest = [i for i in items if i.kind != "rule"]
    if query:
        q = _stems(query)
        topics = guess_topics(query)
        scored = []
        for i in rest:
            s = len(q & _stems(i.title + " " + i.text)) + (2 if i.topic in topics else 0)
            if s > 0:
                scored.append((-s, i.priority, -i.popularity, i.id, i))
        rest = [t[-1] for t in sorted(scored, key=lambda t: t[:4])]
    else:
        rest = sorted(rest, key=lambda i: (i.priority, -i.popularity, i.id))
    return rules + rest[:max(0, int(limit))]


def render_items(items, max_chars=6000):
    """Записи → текст, згрупований за темами; ціни підставляються з каталогу."""
    if not items:
        return ""
    products = catalog.load_products(catalog.placeholder_ids([i.text for i in items] + [i.title for i in items]))
    by_topic = {}
    for i in items:
        by_topic.setdefault(i.topic, []).append(i)
    out, total = [], 0
    for topic in TOPIC_ORDER:
        group = by_topic.get(topic)
        if not group:
            continue
        lines = ["### " + TOPIC_LABEL.get(topic, topic)]
        for i in group:
            text = catalog.render(i.text or "", products).strip()
            if len(text) > ITEM_CHARS:
                text = text[:ITEM_CHARS] + "…"
            title = catalog.render(i.title or "", products).strip()
            if i.kind == "qa":
                line = "• Питання: %s\n  Відповідь: %s" % (title, text)
            elif not title or text.startswith(title):
                line = "• [%s] %s" % (KIND_LABEL.get(i.kind, i.kind), text)
            else:
                line = "• [%s] %s: %s" % (KIND_LABEL.get(i.kind, i.kind), title, text)
            if total + len(line) > max_chars:
                break
            lines.append(line)
            total += len(line)
        if len(lines) > 1:
            out.append("\n".join(lines))
        if total >= max_chars:
            break
    return "\n\n".join(out)


def context_for(agent, query=None, limit=20, max_chars=6000, with_prices=True):
    """Затверджені знання для агента (+ ціни каталогу для згаданих товарів). Ніколи не падає."""
    try:
        items = select(agent, query, limit)
    except Exception:
        items = []
    parts = []
    if items:
        parts.append(render_items(items, max_chars))
    if with_prices:
        p = catalog.prices_block(items, query)
        if p:
            parts.append(p)
    return "\n\n".join(p for p in parts if p)


def covered_topics(agent):
    try:
        return {i.topic for i in approved_for(agent)}
    except Exception:
        return set()


def extra_for(agent, chunks, query=None, limit=12, max_chars=5000):
    """Затверджені записи тем, яких немає серед вбудованих блоків (правила — завжди, решта — за розмовою)."""
    try:
        approved = approved_for(agent)
        fallback_topics = {t for t, _ in chunks if t}
        extra = [i for i in select(agent, query, limit, items=approved) if i.topic not in fallback_topics]
    except Exception:
        return ""
    return render_items(extra, max_chars) if extra else ""


def merge_with_fallback(agent, chunks, query=None, limit=12, max_chars=7000, with_prices=True):
    """chunks = [(тема або None, вбудований текст), …].
    Тема, у якій для агента є хоч один затверджений запис, береться з бази; інакше — вбудований текст.
    Блоки з темою None (заборони, межі) — завжди."""
    try:
        approved = approved_for(agent)
    except Exception:
        approved = []
    covered = {i.topic for i in approved}
    fallback_topics = {t for t, _ in chunks if t}
    parts, done = [], set()
    for topic, chunk in chunks:
        if topic and topic in covered:
            if topic not in done:
                done.add(topic)
                # 22.09.2026 (критичний фікс, Олег: ІІ-РОП не знав адресу компанії, хоча вона
                # затверджена в базі знань): раніше тема з ROP_CHUNKS бралась перших 12 записів
                # ЗА ПРІОРИТЕТОМ/ID, БЕЗ УВАГИ до самого питання — у великих темах (contacts
                # під 50 записів) релевантний запис (адреса) програвав випадковим старим Q&A.
                # Тепер, якщо є запит, сортуємо ТАК САМО, як і решту — за релевантністю питанню.
                pool = [i for i in approved if i.topic == topic]
                group = select(agent, query, 12, items=pool) if query else pool[:12]
                parts.append("[З бази знань, затверджено Олегом]\n" + render_items(group, 3000))
        else:
            parts.append(catalog.render(chunk).strip())
    try:
        extra = [i for i in select(agent, query, limit, items=approved) if i.topic not in fallback_topics]
    except Exception:
        extra = []
    if extra:
        parts.append("[З бази знань — що стосується цієї розмови]\n" + render_items(extra, max_chars))
    if with_prices and query:
        p = catalog.prices_block(extra, query)
        if p:
            parts.append(p)
    return "\n\n".join(p for p in parts if p)
