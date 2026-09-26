# -*- coding: utf-8 -*-
"""Нічний розбір діалогів і тижневий аудит (Олег, 26.09.2026).

«Продавці мають працювати синхронно, а РОП — перевіряти і виправляти, щоб покращувати конверсію.»

Щоночі о 5:00 CRM читає вчорашні діалоги, сама (кодом, без ШІ) знаходить формальні помилки,
показує найгірші випадки ШІ-РОПу і складає ОДИН звіт: що зламалось, у кого, і які правила
варто додати. Правила не застосовуються самі — Олег підтверджує кожне.

Щопонеділка — тижневий аудит: скільки діалогів дійшли до ціни → накладної → оплати,
і як це змінилось після вже прийнятих правил.
"""
import difflib
import json
import re
from datetime import timedelta

from django.utils import timezone

# ── формальні перевірки (рахує код, не ШІ — тому безкоштовні й однозначні) ─────────────
TAGS = {
    "no_question": "останнє повідомлення без питання",
    "silence": "клієнт замовк після нашої відповіді",
    "slow_reply": "відповіли клієнту пізніше ніж за 30 хв",
    "dup_pay_link": "посилання на оплату надіслали двічі",
    "repeat": "агент повторив сам себе",
    "wrong_page": "дали сторінку ліпнини/загальний каталог замість матеріалу",
    "price_dump": "перелік із трьох і більше цін в одному повідомленні",
}
PAY_RX = re.compile(r"crm\.wallcovdec\.com\.ua/p/", re.I)
WRONG_PAGE_RX = re.compile(r"wallcov\.com\.ua/p/(orac|cezar)/|wallcov\.com\.ua/p/\s|wallcov\.com\.ua/p/$", re.I)
PRICE_RX = re.compile(r"\d[\d\s]{1,6}\s?(?:грн|₴)", re.I)
WORK_HOURS = (8, 21)


def _norm(t):
    return re.sub(r"\s+", " ", (t or "").strip().lower())[:400]


def check_dialog(msgs, day_end):
    """msgs — [{dir, text, at, internal, sender}] за день, у хронології. Повертає теги й цитати."""
    out = []
    ours = [m for m in msgs if m["dir"] == "out" and not m["internal"] and (m["text"] or "").strip()]
    theirs = [m for m in msgs if m["dir"] == "in" and not m["internal"]]
    if not ours:
        return out
    last = msgs[-1]
    last_out = ours[-1]
    if "?" not in (last_out["text"] or "") and last["dir"] == "out":
        out.append(("no_question", (last_out["text"] or "")[-160:]))
    if last["dir"] == "out" and (day_end - last["at"]) > timedelta(hours=4) and theirs:
        out.append(("silence", (last_out["text"] or "")[-160:]))
    for c in theirs:
        nxt = next((m for m in ours if m["at"] > c["at"]), None)
        if nxt is None:
            continue
        if WORK_HOURS[0] <= timezone.localtime(c["at"]).hour < WORK_HOURS[1] and \
                (nxt["at"] - c["at"]) > timedelta(minutes=30):
            mins = int((nxt["at"] - c["at"]).total_seconds() // 60)
            out.append(("slow_reply", "чекав %s хв: «%s»" % (mins, (c["text"] or "")[:90])))
            break
    pays = [m for m in ours if PAY_RX.search(m["text"] or "")]
    if len(pays) > 1:
        out.append(("dup_pay_link", (pays[-1]["text"] or "")[:160]))
    for i in range(1, len(ours)):
        a, b = _norm(ours[i - 1]["text"]), _norm(ours[i]["text"])
        if len(a) > 60 and difflib.SequenceMatcher(None, a, b).ratio() > 0.82:
            out.append(("repeat", (ours[i]["text"] or "")[:160]))
            break
    for m in ours:
        if WRONG_PAGE_RX.search(m["text"] or ""):
            out.append(("wrong_page", (m["text"] or "")[:160]))
            break
    for m in ours:
        if len(PRICE_RX.findall(m["text"] or "")) >= 3:
            out.append(("price_dump", (m["text"] or "")[:180]))
            break
    return out


def collect(day_start, day_end, limit=150):
    """Діалоги з клієнтами за період: хронологія повідомлень + хто вів."""
    from apps.inbox.models import Conversation, Message
    ids = list(Message.objects.filter(created_at__gte=day_start, created_at__lt=day_end, internal=False)
               .values_list("conversation_id", flat=True).distinct()[:limit * 2])
    out = []
    for conv in Conversation.objects.filter(id__in=ids).select_related("contact", "channel", "assigned_to")[:limit]:
        rows = list(Message.objects.filter(conversation=conv, created_at__lt=day_end)
                    .order_by("id").values("direction", "text", "created_at", "internal", "sender_name")[:120])
        msgs = [{"dir": r["direction"], "text": r["text"], "at": r["created_at"],
                 "internal": r["internal"], "sender": r["sender_name"] or ""} for r in rows]
        today = [m for m in msgs if m["at"] >= day_start]
        if not any(m["dir"] == "in" and not m["internal"] for m in today):
            continue
        who = sorted({(m["sender"] or "").strip() for m in today
                      if m["dir"] == "out" and not m["internal"] and (m["sender"] or "").strip()})
        out.append({"conv": conv, "msgs": msgs, "today": today, "who": who})
    return out


def _dialog_text(msgs, limit=26):
    return "\n".join(("Клієнт: " if m["dir"] == "in" else "Ми: ") + re.sub(r"\s+", " ", (m["text"] or ""))[:300]
                     for m in msgs[-limit:] if (m["text"] or "").strip() and not m["internal"])


AI_SYSTEM = (
    "Ти — РОП Wallcov (декоративні покриття). Розбираєш вчорашні переписки продавців — це і люди, "
    "і наші ШІ-агенти. Пишеш українською, коротко, по суті, без загальних порад типу «будьте уважніші». "
    "Твоя мета — знайти, що конкретно завадило продажу, і як це виправити одним реченням правила."
)


def ai_dialogs(items, model="claude-haiku-4-5"):
    """Розбір проблемних діалогів пачками. Повертає {conv_id: {...}}."""
    from .ai import claude_json
    res = {}
    for i in range(0, len(items), 5):
        chunk = items[i:i + 5]
        blocks = []
        for it in chunk:
            blocks.append("=== ДІАЛОГ %s (%s, канал %s) ===\nФормальні зауваження: %s\n%s"
                          % (it["conv"].id, str(it["conv"].contact)[:30],
                             it["conv"].channel.name if it["conv"].channel_id else "—",
                             ", ".join(TAGS.get(t, t) for t, _q in it["tags"]) or "—",
                             _dialog_text(it["msgs"])))
        prompt = ("Розбери кожен діалог. Для КОЖНОГО поверни JSON-обʼєкт у масиві \"dialogs\":\n"
                  "{\"id\": <номер діалогу>, \"problem\": \"що саме завадило продажу, 1 речення\", "
                  "\"quote\": \"наша фраза, після якої стало гірше\", "
                  "\"better\": \"як треба було написати, готовий текст клієнту\", "
                  "\"tag\": \"коротка категорія 1-3 слова\"}\n"
                  "Якщо діалог нормальний — problem: \"ок\".\n\n" + "\n\n".join(blocks))
        try:
            data = claude_json(prompt, model=model, max_tokens=1800, system=AI_SYSTEM, cache=True,
                               source="ШІ-РОП: нічний розбір")
        except Exception:
            continue
        for d in (data.get("dialogs") or []):
            try:
                res[int(d.get("id"))] = d
            except Exception:
                continue
    return res


def ai_summary(stats, issues, model="claude-sonnet-4-6"):
    """Підсумок дня: системні проблеми + пропозиції правил (Олег підтверджує кожне)."""
    from .ai import claude_json
    body = json.dumps({"статистика": stats, "проблеми": issues[:40]}, ensure_ascii=False)[:14000]
    prompt = (
        "Ось розбір учорашніх діалогів Wallcov.\n%s\n\n"
        "Поверни JSON:\n"
        "{\"summary\": \"3-5 рядків простою мовою: що вчора заважало продавати. Без води.\",\n"
        " \"systemic\": [\"проблема, що повторилась у 3+ діалогах\"],\n"
        " \"proposals\": [{\"title\": \"коротка назва правила\", "
        "\"rule\": \"готовий текст правила для наших продавців, 1-3 речення, наказовий тон\", "
        "\"why\": \"на чому ґрунтується — скільки діалогів\", \"examples\": [номери діалогів]}]}\n"
        "Пропонуй максимум 3 правила і тільки те, що видно з даних. Якщо системних проблем немає — "
        "порожній список." % body)
    try:
        return claude_json(prompt, model=model, max_tokens=1600, system=AI_SYSTEM,
                           source="ШІ-РОП: підсумок дня")
    except Exception as e:
        return {"summary": "Не вдалося зробити підсумок (%s)" % str(e)[:120], "systemic": [], "proposals": []}


# ── денний розбір ─────────────────────────────────────────────────────────────────────
def run_daily(day=None, send_tg=True, ai=True):
    from .models import DialogReview
    from django.db.models import Sum
    from apps.crm.models import AiUsage
    now = timezone.localtime()
    day = day or (now.date() - timedelta(days=1))
    start = timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.min.time()))
    end = start + timedelta(days=1)
    items = collect(start, end)
    for it in items:
        it["tags"] = check_dialog(it["today"], end)
    bad = [it for it in items if it["tags"]]
    bad.sort(key=lambda x: -len(x["tags"]))
    bad = bad[:25]
    ai_rows = ai_dialogs(bad) if (ai and bad) else {}
    issues = []
    for it in bad:
        d = ai_rows.get(it["conv"].id) or {}
        if (d.get("problem") or "").strip().lower() in ("ок", "ok", "нормально"):
            continue
        issues.append({
            "conv_id": it["conv"].id,
            "contact": str(it["conv"].contact)[:60] if it["conv"].contact_id else "",
            "channel": it["conv"].channel.name if it["conv"].channel_id else "",
            "who": ", ".join(it["who"])[:80],
            "tags": [t for t, _q in it["tags"]],
            "tag_text": "; ".join(TAGS.get(t, t) for t, _q in it["tags"]),
            "quotes": [q for _t, q in it["tags"]][:3],
            "problem": (d.get("problem") or "")[:400],
            "better": (d.get("better") or "")[:600],
            "ai_tag": (d.get("tag") or "")[:40],
        })
    stats = day_stats(start, end, items)
    summ = ai_summary(stats, issues) if (ai and issues) else {"summary": "Проблемних діалогів не знайдено.",
                                                             "systemic": [], "proposals": []}
    props = []
    for n, p in enumerate((summ.get("proposals") or [])[:3], 1):
        props.append({"n": n, "title": (p.get("title") or "")[:120], "rule": (p.get("rule") or "")[:900],
                      "why": (p.get("why") or "")[:300], "examples": p.get("examples") or [], "status": "new"})
    cost = (AiUsage.objects.filter(created_at__gte=now - timedelta(minutes=30),
                                   source__startswith="ШІ-РОП: ").aggregate(s=Sum("cost_usd")).get("s") or 0)
    rev = DialogReview.objects.create(kind="daily", period_start=day, period_end=day,
                                      summary=(summ.get("summary") or "")[:4000],
                                      metrics={"stats": stats, "systemic": (summ.get("systemic") or [])[:6]},
                                      issues=issues, proposals=props, cost_usd=round(float(cost), 4))
    if send_tg:
        notify_owner(rev)
    return rev


def day_stats(start, end, items):
    """Скільки діалогів, скільки дійшли до ціни / накладної / оплати."""
    from apps.crm.models import Deal, Payment
    price = sum(1 for it in items if any(PRICE_RX.search(m["text"] or "")
                                         for m in it["today"] if m["dir"] == "out" and not m["internal"]))
    docs = sum(1 for it in items if any("/d/" in (m["text"] or "")
                                        for m in it["today"] if m["dir"] == "out" and not m["internal"]))
    pays = Payment.objects.filter(created_at__gte=start, created_at__lt=end, is_paid=True).count()
    deals = Deal.objects.filter(created_at__gte=start, created_at__lt=end).count()
    return {"dialogs": len(items), "with_price": price, "with_invoice": docs,
            "deals": deals, "payments": pays}


# ── тижневий аудит ────────────────────────────────────────────────────────────────────
def run_weekly(send_tg=True):
    from .models import DialogReview
    now = timezone.localtime()
    end_day = now.date()
    start_day = end_day - timedelta(days=7)
    prev_start = start_day - timedelta(days=7)
    start = timezone.make_aware(timezone.datetime.combine(start_day, timezone.datetime.min.time()))
    end = timezone.make_aware(timezone.datetime.combine(end_day, timezone.datetime.min.time()))
    p_start = timezone.make_aware(timezone.datetime.combine(prev_start, timezone.datetime.min.time()))
    cur = collect(start, end, limit=400)
    prev = collect(p_start, start, limit=400)
    for it in cur:
        it["tags"] = check_dialog(it["today"], end)
    for it in prev:
        it["tags"] = check_dialog(it["today"], start)
    def agg(rows, s, e):
        st = day_stats(s, e, rows)
        bad = [it for it in rows if it["tags"]]
        tags = {}
        for it in rows:
            for t, _q in it["tags"]:
                tags[t] = tags.get(t, 0) + 1
        st["with_issues"] = len(bad)
        st["tags"] = tags
        return st
    a, b = agg(cur, start, end), agg(prev, p_start, start)
    daily = DialogReview.objects.filter(kind="daily", period_start__gte=start_day).order_by("period_start")
    rules = [p for r in daily for p in (r.proposals or []) if p.get("status") == "approved"]
    summ = ai_week({"цей_тиждень": a, "минулий_тиждень": b,
                    "правила_прийняті": [p.get("title") for p in rules]})
    rev = DialogReview.objects.create(kind="weekly", period_start=start_day, period_end=end_day,
                                      summary=(summ.get("summary") or "")[:4000],
                                      metrics={"current": a, "previous": b,
                                               "approved_rules": [p.get("title") for p in rules]},
                                      issues=[], proposals=[])
    if send_tg:
        notify_owner(rev)
    return rev


def ai_week(data, model="claude-sonnet-4-6"):
    from .ai import claude_json
    prompt = ("Тижневий аудит продажів Wallcov. Цифри:\n%s\n\n"
              "Поверни JSON {\"summary\": \"6-10 рядків простою мовою: що покращилось, що погіршилось, "
              "чи спрацювали прийняті правила, на чому сфокусуватись наступного тижня. Наводь цифри.\"}"
              % json.dumps(data, ensure_ascii=False)[:8000])
    try:
        return claude_json(prompt, model=model, max_tokens=1200, system=AI_SYSTEM,
                           source="ШІ-РОП: тижневий аудит")
    except Exception as e:
        return {"summary": "Не вдалося зробити підсумок (%s)" % str(e)[:120]}


# ── звіт Олегу в Telegram ─────────────────────────────────────────────────────────────
def report_text(rev):
    s = rev.metrics.get("stats") or {}
    if rev.kind == "weekly":
        c = rev.metrics.get("current") or {}
        p = rev.metrics.get("previous") or {}
        head = ("📊 <b>Тижневий аудит продажів</b> (%s — %s)\n\n"
                "Діалогів: %s (було %s)\nЗ ціною: %s (було %s)\nЗ накладною: %s (було %s)\n"
                "Сделок: %s (було %s) · Оплат: %s (було %s)\nДіалогів із зауваженнями: %s (було %s)\n\n"
                % (rev.period_start.strftime("%d.%m"), rev.period_end.strftime("%d.%m"),
                   c.get("dialogs"), p.get("dialogs"), c.get("with_price"), p.get("with_price"),
                   c.get("with_invoice"), p.get("with_invoice"), c.get("deals"), p.get("deals"),
                   c.get("payments"), p.get("payments"), c.get("with_issues"), p.get("with_issues")))
        return head + (rev.summary or "")
    lines = ["🌙 <b>Розбір діалогів за %s</b>\n" % rev.period_start.strftime("%d.%m"),
             "Діалогів: %s · з ціною: %s · з накладною: %s · оплат: %s"
             % (s.get("dialogs"), s.get("with_price"), s.get("with_invoice"), s.get("payments")),
             "Із зауваженнями: %s\n" % len(rev.issues or [])]
    if rev.summary:
        lines.append(rev.summary + "\n")
    for p in (rev.proposals or []):
        lines.append("➕ <b>Правило %s. %s</b>\n%s\n<i>%s</i>" % (p.get("n"), p.get("title"),
                                                                  p.get("rule"), p.get("why")))
    if rev.proposals:
        lines.append("\nВідповідай «правило 1», «правило 1 і 2» або «ні» — підтверджені одразу підуть "
                     "у базу знань для всіх агентів.")
    lines.append("\nДеталі: https://crm.wallcovdec.com.ua/dialog-review")
    return "\n".join(lines)


def notify_owner(rev):
    import urllib.parse
    import urllib.request
    try:
        from apps.assistant.models import AssistantSettings
        from apps.assistant.services import _bot_token
        s = AssistantSettings.objects.first()
        token, chat = _bot_token(), getattr(s, "owner_tg_id", None)
        if not (token and chat):
            return False
        data = urllib.parse.urlencode({"chat_id": chat, "text": report_text(rev)[:4000],
                                       "parse_mode": "HTML",
                                       "disable_web_page_preview": "true"}).encode()
        urllib.request.urlopen("https://api.telegram.org/bot%s/sendMessage" % token, data=data, timeout=25)
        return True
    except Exception:
        return False
