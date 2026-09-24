"""Контент-завод, етап 1 (24.09.2026): нічний розбір питань клієнтів у теми.

Економія (вимога Олега «щоб аналіз не зʼїдав багато впусту»):
1. Фільтр БЕЗ ШІ: лише вхідні повідомлення клієнтів, схожі на питання; «дякую/ок», фото й дублікати відсіюються.
2. Кожне повідомлення розбирається ОДИН раз (last_message_id) — повторно нічого не оплачується.
3. Менше min_new нових питань — ШІ не викликаємо.
4. Місячний ліміт monthly_budget_usd: перед кожним викликом рахуємо витрати місяця з AiUsage.
5. Звʼязок теми з базою знань — пошук за словами, без ШІ.
6. Кожен виклик записується в AiUsage (source=SOURCE) → видно в «AI ЦЕНТР».
"""
import re
from datetime import timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import QuestionMention, QuestionSettings, QuestionTopic

SOURCE = "content_factory.questions"
BATCH = 120            # питань за один виклик ШІ
TOPICS_IN_PROMPT = 150  # скільки існуючих тем показуємо моделі (найсвіжіші)
PRICE = {"claude-sonnet-4-6": (3.0, 15.0), "claude-haiku-4-5": (1.0, 5.0)}  # $/1M in/out, для оцінки

_Q_RX = re.compile(
    r"\?|^\s*(а\s+)?(як|скільки|чи|де|коли|який|яка|яке|які|чому|навіщо|можна|є\s+у|а\s+є|"
    r"как|сколько|можно|какой|какая|какое|какие|где|когда|почему|есть\s+ли|а\s+есть|подскажіть|підкажіть|подскажите)\b",
    re.I)
_JUNK_RX = re.compile(r"^\W*(ок|окей|ok|дякую|спасибо|добре|хорошо|так|да|ні|нет|привіт|привет|вітаю|"
                      r"здравствуйте|добрий день|добрый день|\+|👍)\W*$", re.I)
_PHONE_RX = re.compile(r"\+?\d[\d\s\-()]{7,}\d")
_EMAIL_RX = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_URL_RX = re.compile(r"https?://\S+")


def is_question(text):
    t = (text or "").strip()
    return 12 <= len(t) <= 400 and not _JUNK_RX.match(t) and bool(_Q_RX.search(t))


def clean(text):
    """Прибираємо телефони, пошту й посилання — у приклади теми потрапляє лише суть питання."""
    t = _URL_RX.sub("", _EMAIL_RX.sub("[пошта]", _PHONE_RX.sub("[телефон]", text or "")))
    return re.sub(r"\s+", " ", t).strip()[:200]


def _norm(text):
    return re.sub(r"\W+", " ", (text or "").lower()).strip()


def month_spent(source=SOURCE):
    from apps.crm.models import AiUsage
    start = timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return float(AiUsage.objects.filter(source=source, created_at__gte=start).aggregate(s=Sum("cost_usd"))["s"] or 0)


def candidates(settings_obj):
    """Нові вхідні повідомлення → (max_id, {нормалізований текст: [(msg_id, текст, канал, коли), ...]})."""
    from apps.inbox.models import Message
    qs = Message.objects.filter(direction="in", internal=False)
    if settings_obj.last_message_id:
        qs = qs.filter(id__gt=settings_obj.last_message_id)
    else:
        qs = qs.filter(created_at__gte=timezone.now() - timedelta(days=settings_obj.backfill_days))
    rows = list(qs.order_by("id").values_list("id", "text", "conversation__channel__kind", "created_at"))
    max_id = rows[-1][0] if rows else settings_obj.last_message_id
    seen = set(QuestionMention.objects.filter(message_id__gte=rows[0][0]).values_list("message_id", flat=True)) if rows else set()
    groups = {}
    for mid, text, ch, at in rows:
        if mid not in seen and is_question(text):
            groups.setdefault(_norm(text), []).append((mid, clean(text), ch or "", at))
    return max_id, groups


def estimate_usd(model, n_questions, n_topics):
    """Груба оцінка до виклику: ~2,5 символа на токен кирилиці."""
    pin, pout = PRICE.get(model, (3.0, 15.0))
    tokens_in = (len(SYSTEM) + n_topics * 45 + n_questions * 70) / 2.5
    tokens_out = n_questions * 9 + max(8, n_questions // 4) * 25
    return round((tokens_in * pin + tokens_out * pout) / 1_000_000, 4)


def kb_match(title):
    """Найближчий затверджений запис бази знань за спільними основами слів (без ШІ). Мінімум 2 спільні основи."""
    from apps.knowledge.models import KnowledgeItem
    from apps.knowledge.reader import _stems
    q = _stems(title)
    if len(q) < 2:
        return None
    best, best_score = None, 1
    for item in KnowledgeItem.objects.filter(status="approved").exclude(kind="rule").only("id", "title", "text"):
        s = len(q & _stems(item.title + " " + (item.text or "")[:600]))
        if s > best_score:
            best, best_score = item, s
    return best


SYSTEM = """Ти групуєш питання клієнтів магазину декоративних штукатурок і фарб Wallcov (Україна) у теми для контенту.
Матеріали Wallcov: Галатея, Елеганті, Мокрий шовк, Вельвет Луна, Патера, Перламутрові піщинки, мікроцемент TOPCIMENT та інші.

Отримаєш: список існуючих тем (id|назва) і нумерований список нових повідомлень клієнтів.
Для кожного повідомлення, яке є справжнім питанням про товар, ціну, розрахунок, нанесення, догляд, доставку чи оплату,
віднеси його до ОДНІЄЇ теми: існуючої (за id), якщо зміст той самий, або до нової.
Пропусти повідомлення, які не мають сенсу без контексту розмови («А це?», «Фото чого вислати?») або не є питанням.

Нова тема: коротке питання словами клієнта, українською, до 70 символів, без імен і цифр конкретного клієнта
(«Скільки коштує Галатея на кімнату», а не «Скільки коштує Галатея на 12 м²»). Не дублюй існуючі теми.
material — назва матеріалу, якщо тема про конкретний, інакше "".

Відповідай ЛИШЕ JSON:
{"a": [[номер, id_або_ключ_нової], ...], "new": [{"key": "n1", "title": "...", "material": "..."}]}"""


def _prompt(topics, items):
    lines = ["Існуючі теми:"] + ([f"{t.id}|{t.title}" for t in topics] or ["(поки немає)"])
    lines += ["", "Нові повідомлення:"] + [f"{i}. {text}" for i, (text, _rows) in enumerate(items, 1)]
    return "\n".join(lines)


def _apply(result, items):
    """Застосовуємо відповідь моделі. Невідомі id/ключі ігноруються. Повертає (тем створено, питань віднесено)."""
    new_topics = {}
    for nt in (result.get("new") or [])[:60]:
        key, title = str(nt.get("key") or "").strip(), str(nt.get("title") or "").strip()[:200]
        if key and title:
            new_topics[key] = (title, str(nt.get("material") or "").strip()[:80])
    created, assigned = {}, 0
    for pair in (result.get("a") or []):
        try:
            idx, target = int(pair[0]), str(pair[1]).strip()
        except (TypeError, ValueError, IndexError):
            continue
        if not 1 <= idx <= len(items):
            continue
        text, rows = items[idx - 1]
        if target.isdigit():
            topic = QuestionTopic.objects.filter(pk=int(target)).first()
        elif target in new_topics:
            if target not in created:
                title, material = new_topics[target]
                kb = kb_match(title)
                created[target] = QuestionTopic.objects.create(
                    title=title, material=material, kb_item_id=kb.id if kb else None,
                    kb_item_title=(kb.title[:200] if kb else ""))
            topic = created[target]
        else:
            topic = None
        if not topic:
            continue
        for mid, _t, ch, at in rows:
            _, made = QuestionMention.objects.get_or_create(message_id=mid, defaults={"topic": topic, "channel": ch, "asked_at": at})
            assigned += int(made)
        ex = [e for e in (topic.examples or []) if e != text]
        topic.examples = ([text] + ex)[:5]
        last = max(r[3] for r in rows)
        first = min(r[3] for r in rows)
        topic.last_seen = max(topic.last_seen or last, last)
        topic.first_seen = min(topic.first_seen or first, first)
        topic.save(update_fields=["examples", "last_seen", "first_seen"])
    return len(created), assigned


def run(dry_run=False, force=False, max_batches=None, call=None):
    """Один прохід. dry_run — лише порахувати без ШІ. force — ігнорувати «вимкнено» і min_new (кнопка власника).
    call — підміна виклику ШІ (для тестів)."""
    s = QuestionSettings.get()
    max_id, groups = candidates(s)
    items = [(rows[-1][1], rows) for rows in groups.values()]
    n_topics = min(QuestionTopic.objects.count(), TOPICS_IN_PROMPT)
    budget, spent = float(s.monthly_budget_usd), month_spent()
    report = {"new_messages_scanned": max_id - s.last_message_id if s.last_message_id else None,
              "questions": len(items), "estimate_usd": estimate_usd(s.model, len(items), n_topics),
              "spent_month_usd": round(spent, 4), "budget_usd": budget, "model": s.model,
              "enabled": s.enabled, "batches": 0, "topics_created": 0, "assigned": 0}
    if dry_run:
        return report
    note = None
    if not s.enabled and not force:
        note = "Вимкнено — ШІ не викликався"
    elif not items or (len(items) < s.min_new and not force):
        note = f"Нових питань {len(items)} (менше {s.min_new}) — ШІ не викликався"
    if note:
        # Нічого платного не було. Покажчик не рухаємо, якщо вимкнено (питання дочекаються вмикання).
        if s.enabled and not items:
            s.last_message_id = max_id
        s.last_run_at, s.last_run_note = timezone.now(), note
        s.save(update_fields=["last_message_id", "last_run_at", "last_run_note"])
        report["note"] = note
        return report

    if call is None:
        from apps.crm.ai import claude_json
        call = lambda prompt: claude_json(prompt, model=s.model, max_tokens=4000, system=SYSTEM, source=SOURCE)
    stop, stop_at = None, None
    for start in range(0, len(items), BATCH):
        stop_at = start
        if max_batches is not None and report["batches"] >= max_batches:
            stop = "Частину відкладено на наступний запуск"
            break
        chunk = items[start:start + BATCH]
        est = estimate_usd(s.model, len(chunk), n_topics)
        if month_spent() + est > budget:
            stop = f"Досягнуто місячного ліміту ${budget:.2f} — решту розберемо з 1-го числа"
            break
        topics = list(QuestionTopic.objects.order_by("-last_seen")[:TOPICS_IN_PROMPT])
        try:
            result = call(_prompt(topics, chunk))
        except Exception as e:  # мережа / ключ / ліміт Anthropic — не рухаємо покажчик
            stop = f"Помилка ШІ: {str(e)[:120]}"
            break
        with transaction.atomic():
            c, a = _apply(result if isinstance(result, dict) else {}, chunk)
        report["batches"] += 1
        report["topics_created"] += c
        report["assigned"] += a
    if stop is None:
        done_upto = max_id  # усе розібрано, включно з повідомленнями-не-питаннями
    else:
        # Покажчик — перед першим НЕрозібраним питанням; вже розібрані наступного разу відсіє QuestionMention.
        first_left = min(r[0] for _t, rows in items[stop_at:] for r in rows)
        done_upto = max(s.last_message_id, first_left - 1)
    s.last_message_id = done_upto
    s.last_run_at = timezone.now()
    s.last_run_note = (stop or "Готово") + f": {report['assigned']} питань, нових тем {report['topics_created']}"
    s.save(update_fields=["last_message_id", "last_run_at", "last_run_note"])
    report["note"] = s.last_run_note
    report["spent_month_usd"] = round(month_spent(), 4)
    return report
