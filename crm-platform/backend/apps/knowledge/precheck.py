"""Попередня перевірка чернеток (14.09, ai-kb2) — щоб Олег затверджував стару базу швидко, темами.

Кожна чернетка отримує мітку:
    «готово до затвердження» / «потрібна правка: …» / «дубль #N» / «суперечить затвердженому або каталогу CRM».
Безкоштовно (кодом, $0): відомі помилки аудиту (⚠️) і дублі за схожістю питання в межах теми.
Claude Haiku — лише за кнопкою, з оцінкою вартості ДО запуску, пачками по 6 чернеток.
НІЧОГО не затверджує. Мітка — KnowledgeCheck (одна на запис); правка запису після перевірки → мітка «застаріла».
"""
import difflib
import re

from django.db.models import Q

from . import catalog
from .models import KnowledgeCheck, KnowledgeItem
from .topics import flags_for

MODEL = "claude-haiku-4-5"
BATCH = 6
SOURCE = "База знань: попередня перевірка чернеток"
LABELS = dict(KnowledgeCheck.LABELS)

SYSTEM = (
    "Ти — редактор бази знань Wallcov (декоративні покриття і фарби для стін). Перевіряєш ЧЕРНЕТКИ записів, "
    "які ШІ-агенти говоритимуть клієнтам. Для КОЖНОЇ чернетки дай одну мітку:\n"
    "ready — текст коректний, без вигаданих цифр, не суперечить затвердженому і каталогу — можна затверджувати;\n"
    "fix — потрібна правка: застарілі дані, ціни цифрами замість підстановки з каталогу, обіцянки знижок, "
    "«інструмент у наборі», персональні дані клієнта, незрозуміла або неповна відповідь; у reason — ЩО виправити (1 речення);\n"
    "dup — повторює інший запис; у ref — його номер;\n"
    "conflict — суперечить затвердженому запису або цінам каталогу CRM; у ref — номер запису (якщо це запис).\n"
    "Чернетка з позначкою «правка до #N» — навмисна заміна запису #N: з #N не порівнюй.\n"
    "Правила Wallcov: ціни лише з каталогу CRM; знижки — лише менеджер; інструмент у тест-набір не входить; дощечка 40×40 см; "
    "тест-набори — 100% передоплата; накладений платіж лише для нетонованих (20% до 5 000 грн, 15% до 15 000, 10% понад); "
    "дзвінки 096 419 18 90, месенджери 097 328 22 83. Не вигадуй фактів; сумніваєшся — fix з поясненням.\n"
    'Поверни СТРОГО JSON: {"results": [{"id": 123, "label": "ready|fix|dup|conflict", "reason": "коротко", "ref": null}]}'
)


def _nq(s):
    s = re.sub(r"[^\wʼ'’ ]+", " ", (s or "").lower())
    return " ".join(s.split())


def _similar(a, b):
    if a == b:
        return True
    if abs(len(a) - len(b)) > max(len(a), len(b)) * 0.25:
        return False
    sm = difflib.SequenceMatcher(None, a, b)
    return sm.real_quick_ratio() >= 0.9 and sm.quick_ratio() >= 0.9 and sm.ratio() >= 0.9


def check_of(item):
    try:
        return item.precheck
    except KnowledgeCheck.DoesNotExist:
        return None


def is_fresh(item):
    c = check_of(item)
    return bool(c and c.item_version == item.version)


def drafts(topic=None, recheck=False):
    qs = (KnowledgeItem.objects.filter(status="draft").select_related("precheck").prefetch_related("products")
          .order_by("id"))
    if topic:
        qs = qs.filter(topic=topic)
    items = list(qs)
    return items if recheck else [i for i in items if not is_fresh(i)]


def code_labels(items):
    """{id: (label, reason, ref)} — відомі помилки аудиту і дублі. Безкоштовно."""
    out = {}
    topics = {i.topic for i in items}
    idx_ap, idx_dr = {}, {}
    for a in KnowledgeItem.objects.filter(status="approved", topic__in=topics).only("id", "title", "topic"):
        idx_ap.setdefault(a.topic, []).append((a.id, _nq(a.title)))
    for d in KnowledgeItem.objects.filter(status="draft", topic__in=topics).only("id", "title", "topic").order_by("id"):
        idx_dr.setdefault(d.topic, []).append((d.id, _nq(d.title)))
    for i in items:
        flags = flags_for("%s\n%s" % (i.title, i.text))
        if flags:
            out[i.id] = ("fix", ("відома помилка: " + "; ".join(flags))[:300], None)
            continue
        n = _nq(i.title)
        if len(n) < 8:
            continue
        ref = None
        for aid, an in idx_ap.get(i.topic, []):
            if aid != i.replaces_id and _similar(n, an):
                ref = aid
                break
        if ref is None:
            for did, dn in idx_dr.get(i.topic, []):
                if did >= i.id:
                    break
                if _similar(n, dn):
                    ref = did
                    break
        if ref:
            out[i.id] = ("dup", "те саме питання, що й #%d" % ref, ref)
    return out


def _approved_ctx(topic):
    rows = (KnowledgeItem.objects.filter(status="approved").filter(Q(topic=topic) | Q(kind="rule"))
            .order_by("priority", "id")[:20])
    return ["#%d [%s] %s — %s" % (a.id, a.get_kind_display(), a.title[:120],
                                  re.sub(r"\s+", " ", catalog.render(a.text))[:300]) for a in rows]


def batch_prompt(batch, ctx_cache):
    topics = sorted({i.topic for i in batch})
    parts = []
    for t in topics:
        if t not in ctx_cache:
            ctx_cache[t] = (_approved_ctx(t), [
                "#%d %s" % (d.id, d.title[:90]) for d in
                KnowledgeItem.objects.filter(status="draft", topic=t).only("id", "title").order_by("id")[:40]])
        ap, titles = ctx_cache[t]
        parts.append("ТЕМА «%s». ЗАТВЕРДЖЕНЕ (для звірки):\n%s" % (
            dict(KnowledgeItem.TOPICS).get(t, t), "\n".join(ap) or "(ще нічого не затверджено)"))
        parts.append("ІНШІ ЧЕРНЕТКИ ТЕМИ (лише питання, для пошуку дублів):\n" + ("\n".join(titles) or "—"))
    prices = catalog.prices_block(batch, " ".join("%s %s" % (i.title, i.text) for i in batch), max_lines=20, per_family=6)
    if prices:
        parts.append(prices)
    rows = []
    for i in batch:
        mark = " (правка до #%d)" % i.replaces_id if i.replaces_id else ""
        rows.append("#%d [%s]%s\nПитання/назва: %s\nТекст: %s" % (
            i.id, i.get_kind_display(), mark, i.title[:300], catalog.render(i.text or "")[:900]))
    parts.append("ЧЕРНЕТКИ НА ПЕРЕВІРКУ:\n\n" + "\n\n".join(rows))
    return "\n\n".join(parts) + "\n\nПоверни JSON з міткою для кожної чернетки."


def save_check(item, label, reason, ref=None, source="ai", model="", run=None):
    KnowledgeCheck.objects.update_or_create(item=item, defaults=dict(
        label=label, reason=(reason or "")[:300], ref_item_id=ref, item_version=item.version, source=source,
        model=model, run=run))


def plan(topic=None, recheck=False):
    items = drafts(topic, recheck)
    code = code_labels(items)
    rest = [i for i in items if i.id not in code]
    batches = [rest[k:k + BATCH] for k in range(0, len(rest), BATCH)]
    return items, code, batches


def estimate(topic=None, recheck=False):
    from .answer import estimate_usd
    items, code, batches = plan(topic, recheck)
    cache, usd, chars = {}, 0.0, 0
    for b in batches:
        n = len(SYSTEM) + len(batch_prompt(b, cache))
        chars += n
        usd += estimate_usd(MODEL, n, 350)
    return {"drafts": len(items), "code_only": len(code), "ai_items": sum(len(b) for b in batches),
            "calls": len(batches), "est_usd": round(usd, 3), "model": MODEL, "prompt_chars": chars,
            "code_labels": {k: sum(1 for v in code.values() if v[0] == k) for k in LABELS}}


def run_precheck(run, topic=None, recheck=False, progress=None):
    """Виконується з runs.py (фоновий потік). Пише лише KnowledgeCheck; записи не змінює."""
    from . import answer as ans
    items, code, batches = plan(topic, recheck)
    by_id = {i.id: i for i in items}
    for iid, (label, reason, ref) in code.items():
        save_check(by_id[iid], label, reason, ref, "code", "", run)
    total, cost, errors, cache = len(batches), 0.0, [], {}
    counts = {k: 0 for k in LABELS}
    for v in code.values():
        counts[v[0]] += 1
    if progress:
        progress(done=0, total=total)
    for n, b in enumerate(batches, 1):
        try:
            resp = ans.call_claude(SYSTEM, batch_prompt(b, cache), MODEL, max_tokens=900, source=SOURCE, cache=False)
            cost += ans.cost_usd(MODEL, (resp or {}).get("usage"))
            data = ans.parse_json(ans.resp_text(resp))
            ids = {i.id: i for i in b}
            for r in data.get("results") or []:
                try:
                    it = ids.get(int(r.get("id")))
                except (TypeError, ValueError):
                    it = None
                label = str(r.get("label") or "")
                if not it or label not in LABELS:
                    continue
                try:
                    ref = int(r.get("ref")) if r.get("ref") not in (None, "", "null") else None
                except (TypeError, ValueError):
                    ref = None
                save_check(it, label, str(r.get("reason") or ""), ref, "ai", MODEL, run)
                counts[label] += 1
        except Exception as e:  # мережа / ключ — фіксуємо, йдемо далі
            errors.append(str(e)[:200])
        if progress:
            progress(done=n, total=total, cost=cost)
    return {"drafts": len(items), "code_only": len(code), "calls": total, "counts": counts,
            "unlabeled": len(items) - sum(counts.values()), "errors": errors[:20], "cost_usd": round(cost, 4)}


def summary(topic=None):
    qs = KnowledgeItem.objects.filter(status="draft")
    if topic:
        qs = qs.filter(topic=topic)
    rows = list(qs.select_related("precheck").only("id", "topic", "version", "precheck__label",
                                                   "precheck__item_version"))
    counts = {k: 0 for k in LABELS}
    stale = none = 0
    by_topic = {}
    for i in rows:
        c = check_of(i)
        t = by_topic.setdefault(i.topic, {"drafts": 0, "ready": 0})
        t["drafts"] += 1
        if not c:
            none += 1
        elif c.item_version != i.version:
            stale += 1
        else:
            counts[c.label] += 1
            if c.label == "ready":
                t["ready"] += 1
    return {"drafts": len(rows), "counts": counts, "stale": stale, "unchecked": none, "by_topic": by_topic}
