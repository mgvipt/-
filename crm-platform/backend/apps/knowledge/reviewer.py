"""Рецензент (команда агентів, фаза 1): щодня перевіряє вибірку закритих чатів.

1) Безкоштовна перевірка кодом (без ІІ): відомі заборонені фрази у НАШИХ повідомленнях.
2) Claude (Haiku, лише коли Олег увімкнув): суперечності із затвердженою базою, пропущені кроки продажу,
   питання клієнтів, яких немає в базі.
Результат — ЧЕРНЕТКИ в базі знань з посиланням на діалог. Затверджені записи рецензент НЕ змінює,
клієнтам нічого не пише.
"""
import random
import re
from datetime import timedelta

from django.utils import timezone

from .models import KnowledgeItem, KnowledgeReviewLog, KnowledgeSettings, log_version
from .topics import guess_topic

SOURCE_LABEL = "Рецензент бази знань"
AUDIENCE = ["yulia_ig", "yulia_tiktok", "rop_hint", "compose_assist", "analyst"]
TOPICS = {c for c, _ in KnowledgeItem.TOPICS}
MAX_FINDINGS = 3

# Помилки, які вже відомі (памʼять Олега / аудит 14.09). Перевіряються кодом, безкоштовно.
LINT_OUT = [
    (r"вже є все потрібне|вже є потрібний інструмент|інструмент\w*\s+(входить|у комплекті|є в наборі)|у наборі (вже )?є інструмент",
     "Написали, що інструмент входить у тест-набір", "test_sets",
     "Інструмент у тест-набір НЕ входить: у наборі матеріал, ґрунт-підкладка, тара, відео-інструкція (+ дощечка 40×40)."),
    (r"40\s*[×xх*]\s*60", "Назвали дощечку 40×60", "test_sets", "Дощечка в тест-наборі — 40×40 см."),
    (r"097\s*931\s*21\s*90|wallcovpidtrimka", "Дали старий контакт", "contacts",
     "Дзвінки — 096 419 18 90; Viber/Telegram/WhatsApp — 097 328 22 83 (t.me/wallcov_pidtrimka)."),
    (r"номер\w*\s+карт|на картку|скину карт", "Запропонували оплату на картку", "payment",
     "На картку фізособи не приймаємо: LiqPay, IBAN рахунку ФОП або накладений платіж (нетоновані)."),
    (r"знижк\w*\s*(до\s*)?(1[5-9]|[2-9]\d)\s*%|(1[5-9]|[2-9]\d)\s*%\s*знижк", "Пообіцяли знижку понад 10%", "discounts",
     "Знижки — тільки менеджер і в межах єдиного правила знижок."),
]
# 18.09.2026 (Олег: «щоб усі агенти перевіряли й навчали одне одного») — перевірки за МАЙСТЕР-ПРОМТОМ.
LINT_OUT += [
    (r"витрат\w*[^.]{0,20}грн\s*/?\s*м²", "Сплутали витрату і ціну (витрата — кг/м²)", "pricing",
     "ВИТРАТА — кілограми на 1 м². ЦІНА — гривні за кг, за набір або за м². Не змішувати в одному рядку."),
    (r"\[(палітр|посиланн|ссылк)", "Замість адреси написали «[палітра]»", "tone",
     "Посилання вставляти повною адресою: https://wallcov.com.ua/p/<матеріал>/"),
    (r"тест\W*набір\s*(чи|або)\s*(розрахун|прорахун)|(розрахун|прорахун)\w*\s*(чи|або)\s*тест",
     "Дали меню «тест чи розрахунок» — клієнт зупиняється", "tone",
     "Один наступний крок на повідомлення: назвати доречний варіант і спитати, чи готувати його."),
    (r"^\s*(розумію|понимаю)[,!. ]", "Порожній вступ «Розумію» без заперечення клієнта", "tone",
     "Починати з суті. «Розумію» доречне лише у відповідь на сумнів або заперечення."),
]

LINT_LAST = (r"(оформлюємо|надіслати|підходить|цікавить|хочете|зручно|підготувати)\?\s*\W*$",
             "Останнє наше повідомлення — закрите питання «так/ні», клієнт замовк", "tone",
             "Закінчувати відкритим питанням, що звужує вибір: «Яку кімнату рахуємо першою?»")

from .seller_prompt import MASTER as _MASTER

REVIEWER_SYSTEM = (
    "Ти — рецензент відділу продажів Wallcov (декоративні покриття для стін). Перевіряєш ЗАКРИТИЙ діалог з клієнтом.\n"
    "Знайди лише важливе для продажу:\n"
    "1) contradiction — відповідь НАШОЇ сторони (Юля-ІІ або менеджер) суперечить базі знань або цінам каталогу нижче;\n"
    "2) missed_step — пропущений крок продажу: на цінове питання не назвали ціну; не запропонували тест-набір; "
    "не спитали площу/кімнату; немає наступного кроку; наприкінці закрите питання «так/ні»;\n"
    "3) unknown_question — клієнт спитав те, чого немає в базі знань. Запропонуй коротку відповідь для бази; "
    "якщо фактів не знаєш — у suggested_text напиши «ПОТРІБНА ВІДПОВІДЬ ОЛЕГА». Цифр не вигадуй.\n"
    "Не вигадуй цін і фактів. Якщо все добре — поверни порожній список.\n"
    'Поверни СТРОГО JSON: {"findings": [{"type": "contradiction|missed_step|unknown_question", "who": "ai|manager", '
    '"quote": "точна цитата з діалогу", "problem": "1 речення", "topic": "payment|delivery|test_sets|pricing|materials|'
    'application|tinting|contacts|discounts|objections|company|tone|process|other", '
    '"suggested_title": "питання клієнта або назва правила", "suggested_text": "як правильно відповідати"}]}\n'
    "Максимум 3 знахідки. Додай поле \"score\" 0-100 — наскільки наші повідомлення відповідають стандарту нижче.\n\n"
    "СТАНДАРТ ПРОДАВЦЯ (за ним пише наш ІІ — суди саме за ним):\n" + _MASTER.replace("{канал}", "каналі")
)


def conv_link(conv_id):
    return "/inbox?c=%d" % conv_id


def dialog(conv, limit=40):
    rows = list(conv.messages.filter(internal=False).order_by("-id")
                .values("direction", "text", "sender_id")[:limit])[::-1]
    out = []
    for m in rows:
        txt = (m.get("text") or "").strip()
        if not txt:
            continue
        who = "Клієнт" if m["direction"] == "in" else ("Менеджер" if m.get("sender_id") else "Юля/автоматизація")
        out.append((who, txt[:600]))
    return out


def dialog_text(msgs):
    return "\n".join("%s: %s" % (w, t) for w, t in msgs)


def style_problems(text):
    """Структура повідомлення за майстер-промтом: без полотна і без двох питань підряд."""
    out = []
    body = text.strip()
    lines = [l for l in body.splitlines() if l.strip()]
    if len(body) > 700 or (len(lines) <= 2 and len(body) > 450):
        out.append(("Повідомлення полотном, без коротких рядків", "tone",
                    "До 5–6 коротких рядків: суть, варіанти через «• », посилання окремо, одне питання в кінці."))
    if body.count("?") > 1:
        out.append(("Два і більше питань в одному повідомленні", "tone",
                    "Правило одного питання: спитати одне, дочекатись відповіді, потім наступне."))
    return out


def lint_dialog(msgs):
    found = []
    ours = [(w, t) for w, t in msgs if w != "Клієнт"]
    for who, text in ours:
        for problem, topic, correct in style_problems(text):
            found.append({"problem": problem, "topic": topic, "correct": correct, "who": who, "quote": text[:200]})
    for who, text in ours:
        low = text.lower()
        for rx, problem, topic, correct in LINT_OUT:
            if re.search(rx, low):
                found.append({"problem": problem, "topic": topic, "correct": correct, "who": who, "quote": text[:200]})
    if msgs and msgs[-1][0] != "Клієнт" and re.search(LINT_LAST[0], msgs[-1][1].lower()):
        found.append({"problem": LINT_LAST[1], "topic": LINT_LAST[2], "correct": LINT_LAST[3], "who": msgs[-1][0],
                      "quote": msgs[-1][1][:200]})
    return found


def pick_conversations(day, sample, conversation_id=None, ai_only=False):
    from apps.inbox.models import Conversation, Message
    if conversation_id:
        return list(Conversation.objects.filter(pk=conversation_id))
    done = set(KnowledgeReviewLog.objects.filter(day=day).values_list("conversation_id", flat=True))
    if ai_only:
        # 18.09.2026: перевіряємо саме роботу нашого ІІ-продавця за день (а не лише закриті чати)
        ids = set(Message.objects.filter(created_at__date=day, direction="out", internal=False,
                                         sender_name__startswith="ІІ у каналі")
                  .values_list("conversation_id", flat=True))
        qs = Conversation.objects.filter(pk__in=ids).exclude(pk__in=done).order_by("id")
    else:
        qs = (Conversation.objects.filter(status="closed", last_message_at__date=day)
              .exclude(pk__in=done).order_by("id"))
    good = []
    for conv in qs[:600]:
        dirs = set(conv.messages.filter(internal=False).exclude(text="").values_list("direction", flat=True)[:50])
        if {"in", "out"} <= dirs:
            good.append(conv)
    rnd = random.Random(day.toordinal())
    return good if len(good) <= sample else sorted(rnd.sample(good, sample), key=lambda c: c.id)


def knowledge_for_review(query):
    from .fallbacks import ROP_CHUNKS
    from .reader import merge_with_fallback
    return merge_with_fallback("analyst", ROP_CHUNKS, query=query, limit=20)


def estimate_cost(chars_in, model, calls):
    from apps.crm.ai import PRICING
    pin, pout, _cr, _cw = PRICING.get(model, (1.0, 5.0, 0.1, 1.25))
    tokens_in = chars_in / 3.0
    return round((tokens_in * pin + 600 * calls * pout) / 1_000_000.0, 4)


def ai_review(conv, msgs, model, ai=None):
    if ai is None:
        from apps.crm.ai import claude_json as ai
    text = dialog_text(msgs)
    kb = knowledge_for_review(text[-3000:])
    prompt = ("БАЗА ЗНАНЬ WALLCOV (затверджене + рішення Олега):\n%s\n\nДІАЛОГ №%d (%s):\n%s\n\n"
              "Перевір діалог і поверни JSON." % (kb or "(порожньо)", conv.id,
                                                   conv.channel.name if conv.channel_id else "-", text[-9000:]))
    r = ai(prompt, model=model, max_tokens=900, system=REVIEWER_SYSTEM, cache=True, source=SOURCE_LABEL)
    rows = (r or {}).get("findings") if isinstance(r, dict) else None
    score = (r or {}).get("score") if isinstance(r, dict) else None
    return [f for f in (rows or []) if isinstance(f, dict)][:MAX_FINDINGS], len(prompt), (score if isinstance(score, int) else None)


def create_suggestions(conv, findings, day):
    created = 0
    since = timezone.now() - timedelta(days=14)
    for f in findings:
        ftype = str(f.get("type") or "")
        text = str(f.get("suggested_text") or "").strip()
        if ftype not in ("contradiction", "missed_step", "unknown_question") or not text:
            continue
        title = str(f.get("suggested_title") or f.get("problem") or "").strip()[:300] or "Пропозиція рецензента"
        if KnowledgeItem.objects.filter(source="reviewer", status="draft", title__iexact=title, created_at__gte=since).exists():
            continue
        topic = f.get("topic") if f.get("topic") in TOPICS else guess_topic(title + " " + text)
        quote = str(f.get("quote") or "")[:400]
        problem = str(f.get("problem") or "")[:400]
        item = KnowledgeItem.objects.create(
            kind="qa" if ftype == "unknown_question" else "rule", topic=topic, audience=list(AUDIENCE),
            status="draft", title=title, text=text, source="reviewer",
            source_ref="review:%d:%s" % (conv.id, day.isoformat()),
            internal_note="Рецензент %s — %s: %s\nЦитата: «%s»\nДіалог: %s" % (
                day.strftime("%d.%m"), {"contradiction": "суперечність", "missed_step": "пропущений крок",
                                        "unknown_question": "питання без відповіді"}[ftype], problem, quote,
                conv_link(conv.id)),
            evidence={"conversation_id": conv.id, "link": conv_link(conv.id), "type": ftype,
                      "who": str(f.get("who") or ""), "quote": quote, "problem": problem, "day": day.isoformat()})
        log_version(item, "create", None, "пропозиція рецензента")
        created += 1
    return created


def create_lint_summary(day, lint_by_problem):
    """Одна чернетка на повторювану помилку дня: «у N діалогах …» з посиланнями."""
    created = 0
    for problem, rows in lint_by_problem.items():
        title = "⚠️ %s — %s (%d діал.)" % (problem, day.strftime("%d.%m"), len(rows))
        if KnowledgeItem.objects.filter(source="reviewer", title=title).exists():
            continue
        convs = sorted({r["conversation_id"] for r in rows})
        item = KnowledgeItem.objects.create(
            kind="rule", topic=rows[0]["topic"], audience=list(AUDIENCE), status="draft", title=title[:300],
            text="Правильно: " + rows[0]["correct"], source="reviewer",
            source_ref="lint:%s:%s" % (day.isoformat(), rows[0]["topic"]),
            internal_note="Перевірка кодом (без ІІ). Діалоги: " + ", ".join(conv_link(c) for c in convs[:20]),
            evidence={"conversation_ids": convs, "links": [conv_link(c) for c in convs[:20]], "type": "lint",
                      "quote": rows[0]["quote"], "day": day.isoformat()})
        log_version(item, "create", None, "повторна помилка (перевірка кодом)")
        created += 1
    return created


def run(day=None, sample=None, dry=True, conversation_id=None, ai=None, ai_only=False):
    cfg = KnowledgeSettings.get()
    day = day or (timezone.localdate() - timedelta(days=1))
    sample = int(sample or cfg.reviewer_sample or 20)
    convs = pick_conversations(day, sample, conversation_id, ai_only=ai_only)
    report = {"day": day.isoformat(), "dry": dry, "model": cfg.reviewer_model, "picked": [c.id for c in convs],
              "lint": [], "ai_calls": 0, "ai_findings": 0, "items_created": 0, "errors": [], "chars_in": 0}
    lint_by_problem = {}
    for conv in convs:
        msgs = dialog(conv)
        lint = lint_dialog(msgs)
        for f in lint:
            f["conversation_id"] = conv.id
            report["lint"].append(f)
            lint_by_problem.setdefault(f["problem"], []).append(f)
        report["chars_in"] += len(dialog_text(msgs)[-9000:]) + 6000  # + база знань і інструкція
        if dry:
            continue
        log = KnowledgeReviewLog(conversation_id=conv.id, day=day, lint_findings=len(lint), model=cfg.reviewer_model)
        try:
            findings, _n, score = ai_review(conv, msgs, cfg.reviewer_model, ai=ai)
            if score is not None:
                report.setdefault("scores", []).append(score)
            report["ai_calls"] += 1
            report["ai_findings"] += len(findings)
            log.ai_findings = len(findings)
            log.items_created = create_suggestions(conv, findings, day)
            report["items_created"] += log.items_created
        except Exception as e:  # мережа / ключ — фіксуємо й ідемо далі
            log.error = str(e)[:500]
            report["errors"].append("%d: %s" % (conv.id, str(e)[:120]))
        log.save()
    if not dry:
        report["items_created"] += create_lint_summary(day, lint_by_problem)
    sc = report.get("scores") or []
    report["score_avg"] = round(sum(sc) / len(sc)) if sc else None
    report["est_cost_usd"] = estimate_cost(report["chars_in"], cfg.reviewer_model, len(convs))
    return report
