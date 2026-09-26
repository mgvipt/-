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
import time
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
    "send_failed": "наше повідомлення НЕ дійшло до клієнта",
}
BAD_STATUS = ("failed", "window_risk")
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
        out.append(("no_question", "[%s] %s" % (_stamp(last_out), (last_out["text"] or "")[-160:])))
    if last["dir"] == "out" and (day_end - last["at"]) > timedelta(hours=4) and theirs:
        out.append(("silence", "[%s] %s" % (_stamp(last_out), (last_out["text"] or "")[-160:])))
    for c in theirs:
        nxt = next((m for m in ours if m["at"] > c["at"]), None)
        if nxt is None:
            continue
        if WORK_HOURS[0] <= timezone.localtime(c["at"]).hour < WORK_HOURS[1] and \
                (nxt["at"] - c["at"]) > timedelta(minutes=30):
            mins = int((nxt["at"] - c["at"]).total_seconds() // 60)
            out.append(("slow_reply", "[%s] клієнт чекав %s хв: «%s» → відповіли [%s]"
                        % (_stamp(c), mins, (c["text"] or "")[:90], _stamp(nxt))))
            break
    pays = [m for m in ours if PAY_RX.search(m["text"] or "")]
    if len(pays) > 1:
        out.append(("dup_pay_link", "посилання о %s і о %s" % (_stamp(pays[0]), _stamp(pays[-1]))))
    for i in range(1, len(ours)):
        a, b = _norm(ours[i - 1]["text"]), _norm(ours[i]["text"])
        if len(a) > 60 and difflib.SequenceMatcher(None, a, b).ratio() > 0.82:
            out.append(("repeat", "[%s] і [%s]: «%s»" % (_stamp(ours[i - 1]), _stamp(ours[i]),
                                                          (ours[i]["text"] or "")[:120])))
            break
    for m in ours:
        if WRONG_PAGE_RX.search(m["text"] or ""):
            out.append(("wrong_page", (m["text"] or "")[:160]))
            break
    for m in ours:
        if len(PRICE_RX.findall(m["text"] or "")) >= 3:
            out.append(("price_dump", "[%s] %s" % (_stamp(m), (m["text"] or "")[:180])))
            break
    dead = [m for m in msgs if m["dir"] == "out" and not m["internal"] and m.get("status") in BAD_STATUS]
    if dead:
        out.append(("send_failed", "%s повідомлень не дійшло, останнє [%s]: «%s»"
                    % (len(dead), _stamp(dead[-1]), (dead[-1]["text"] or "")[:90])))
    return out


# хто писав клієнту: за підписом повідомлення видно, який саме агент помилився
AGENT_LABEL = {"chatplace": "Юля ChatPlace", "crm": "Продавець CRM", "human": "Менеджер"}


def actors(msgs):
    """Хто вів діалог з нашого боку: Юля ChatPlace (echo «ai_assistant»), продавець CRM
    («ШІ у каналі …»), живий менеджер. Від цього залежить, кого саме вчимо."""
    out = []
    for m in msgs:
        if m["dir"] != "out" or m["internal"] or not (m["text"] or "").strip():
            continue
        who = (m["sender"] or "").strip()
        if who.startswith("ai_assistant"):
            kind = "chatplace"
        elif who.startswith("ШІ у каналі") or who.startswith("CRM"):
            kind = "crm"
        elif who and who != "operator":
            kind = "human"
        else:
            continue
        if kind not in out:
            out.append(kind)
    return out


def collect(day_start, day_end, limit=150):
    """Діалоги з клієнтами за період: хронологія повідомлень + хто вів."""
    from apps.inbox.models import Conversation, Message
    ids = list(Message.objects.filter(created_at__gte=day_start, created_at__lt=day_end, internal=False)
               .values_list("conversation_id", flat=True).distinct()[:limit * 2])
    out = []
    for conv in Conversation.objects.filter(id__in=ids).select_related("contact", "channel", "assigned_to")[:limit]:
        rows = list(Message.objects.filter(conversation=conv, created_at__lt=day_end)
                    .order_by("id").values("direction", "text", "created_at", "internal",
                                          "sender_name", "status")[:120])
        msgs = [{"dir": r["direction"], "text": r["text"], "at": r["created_at"],
                 "internal": r["internal"], "sender": r["sender_name"] or "",
                 "status": r["status"]} for r in rows]
        today = [m for m in msgs if m["at"] >= day_start]
        if not any(m["dir"] == "in" and not m["internal"] for m in today):
            continue
        who = sorted({(m["sender"] or "").strip() for m in today
                      if m["dir"] == "out" and not m["internal"] and (m["sender"] or "").strip()})
        out.append({"conv": conv, "msgs": msgs, "today": today, "who": who})
    return out


def _stamp(m):
    try:
        return timezone.localtime(m["at"]).strftime("%d.%m %H:%M")
    except Exception:
        return ""


def _dialog_text(msgs, limit=26):
    """Кожен рядок із датою й часом — щоб аналітик міг точно вказати, де саме зламалось."""
    return "\n".join("[%s] %s%s" % (_stamp(m), "Клієнт: " if m["dir"] == "in" else "Ми: ",
                                     re.sub(r"\s+", " ", (m["text"] or ""))[:300])
                     for m in msgs[-limit:] if (m["text"] or "").strip() and not m["internal"])


def ai_system():
    """Персона аналітика = ТОЙ САМИЙ ШІ-РОП, що підказує менеджерам у чаті (єдина роль і єдина
    модель продажу — golden pattern, заборона вигадувати цифри, робота із запереченнями),
    плюс завдання саме нічного розбору."""
    try:
        from .coach_prompt import COACH_SYSTEM
        base = COACH_SYSTEM
    except Exception:
        base = ""
    return (base + "\n\n---\n\n## РЕЖИМ: НІЧНИЙ РОЗБІР (26.09.2026)\n"
            "Зараз ти працюєш у РЕЖИМІ 2 — АНАЛІТИК. Читаєш учорашні переписки (і людей, і наших "
            "ШІ-агентів) і шукаєш, що конкретно завадило продажу. Звіряєшся з нашою моделлю продажу "
            "(golden pattern з 11 кроків вище) і з еталонними діалогами, які реально закінчились "
            "оплатою. Пишеш українською, коротко, без загальних порад типу «будьте уважніші»: "
            "тільки конкретна причина, цитата і готова краща фраза.")


AI_SYSTEM = ""   # сумісність зі старим кодом; справжня персона — в ai_system()

SHORT_SYSTEM = (
    "Ти — РОП Wallcov (декоративні покриття: мокрий шовк, Галатея, Патера, Вельвет Луна). "
    "Читаєш переписки продавців — і людей, і наших ШІ-агентів — і шукаєш, що завадило продажу.\n"
    "НАША МОДЕЛЬ ПРОДАЖУ (звіряйся з нею):\n"
    "1) один матеріал і одна ціна-якір замість переліку 4 опцій; 2) фото/відео матеріалу обовʼязково; "
    "3) кваліфікація через РОЗРАХУНКОВІ дані (площа, приміщення), і лише коли клієнт уже готовий; "
    "4) точна цифра з каталогу — ніколи не вигадана; 5) один чіткий наступний крок і питання в кінці "
    "КОЖНОГО повідомлення; 6) готовий купити → накладна/реквізити, а не нова кваліфікація; "
    "7) заперечення → конкретне відпрацювання, не знижка (максимум 10%); "
    "8) від тригера до оплати у наших кращих діалогах — 20 хв до 3 годин.\n"
    "ЗАБОРОНЕНО в наших відповідях: прайс-дамп із 3+ цін, повтор тієї самої фрази, «звертайтесь, коли "
    "визначитесь», «уточню у Олега», вигадані цифри, дублювання посилання на оплату.\n"
    "Пиши українською, коротко, конкретно: причина, цитата, готова краща фраза. Без порад «будьте уважніші»."
)


IG_BOT = "647e28e9-73fd-4f06-81cc-5970409a7381"
TT_BOT = "4aab5db8-4efa-46aa-a0bf-56fc20610b35"
_RULES_CACHE = {"at": 0, "text": ""}


def _crm_rules():
    """Чинні правила продавця CRM: майстер-промт + затверджені правила бази знань."""
    import re as _re
    out = []
    try:
        from apps.knowledge.seller_prompt import MASTER
        for line in MASTER.split("\n"):
            t = line.strip()
            if t.startswith("•") and len(t) > 25:
                out.append("  " + t[:150])
            elif t and t == t.upper() and 8 < len(t) < 80:
                out.append("· " + t)
    except Exception:
        pass
    try:
        from apps.knowledge.models import KnowledgeItem
        for it in (KnowledgeItem.objects.filter(status="approved")
                   .order_by("-updated_at").values_list("title", flat=True)[:40]):
            out.append("  • [база знань] %s" % (it or "")[:110])
    except Exception:
        pass
    return "\n".join(out[:90])


def _yulia_rules():
    """Чинні правила Юлі ChatPlace: загальні правила + тематичні (читаємо просто з ChatPlace)."""
    import re as _re
    from apps.inbox import chatplace as cp
    out = []
    try:
        rules = (cp._mcp("ai_agent_topic_rules_list", {"botId": IG_BOT}) or {}).get("items") or []
        for r in rules:
            out.append("  • [тематичне] %s — %s" % (r.get("name"), (r.get("description") or "")[:110]))
    except Exception:
        pass
    try:
        st = cp._mcp("ai_agent_status", {"botId": IG_BOT}) or {}
        gr = st.get("globalRules") or ""
        for chunk in _re.split(r"\n(?=\d{1,2}[.)] )", gr):
            t = _re.sub(r"\s+", " ", chunk).strip()
            if len(t) > 20:
                out.append("  • " + t[:150])
    except Exception as e:
        out.append("  (не вдалося прочитати загальні правила: %s)" % str(e)[:80])
    return "\n".join(out[:90])


def rules_index(ttl=1800):
    """Скорочений список ЧИННИХ правил обох агентів — щоб аналітик не пропонував те, що вже є."""
    now = time.time()
    if _RULES_CACHE["text"] and now - _RULES_CACHE["at"] < ttl:
        return _RULES_CACHE["text"]
    text = ("ЧИННІ ПРАВИЛА ПРОДАВЦЯ CRM:\n%s\n\nЧИННІ ПРАВИЛА ЮЛІ CHATPLACE:\n%s"
            % (_crm_rules(), _yulia_rules()))[:6500]
    _RULES_CACHE.update({"at": now, "text": text})
    return text


def good_dialogs(days=30, limit=3):
    """Еталони: діалоги, що закінчились ОПЛАТОЮ — щоб аналітик рівнявся на наш реальний успіх,
    а не на абстрактну теорію (Олег 26.09.2026: «у нього мають бути дані про якісні діалоги»)."""
    from apps.crm.models import Payment
    from apps.inbox.models import Conversation
    since = timezone.now() - timedelta(days=days)
    out = []
    seen = set()
    for p in (Payment.objects.filter(is_paid=True, created_at__gte=since)
              .select_related("deal").order_by("-id")[:60]):
        cid = getattr(p.deal, "contact_id", None)
        if not cid or cid in seen:
            continue
        conv = (Conversation.objects.filter(contact_id=cid).order_by("-last_message_at").first())
        if conv is None:
            continue
        rows = list(conv.messages.filter(internal=False, created_at__lte=p.created_at)
                    .order_by("-id").values("direction", "text")[:18])[::-1]
        if len(rows) < 6:
            continue
        seen.add(cid)
        body = "\n".join(("Клієнт: " if r["direction"] == "in" else "Ми: ")
                          + re.sub(r"\s+", " ", (r["text"] or ""))[:220] for r in rows if (r["text"] or "").strip())
        out.append("--- ЕТАЛОН (закінчився оплатою %s грн) ---\n%s" % (p.amount, body))
        if len(out) >= limit:
            break
    return "\n\n".join(out)


def past_feedback(days=14, limit=12):
    """Поправки Олега: де він сказав, що розбір був неправильний, і які правила відхилив.
    Йдуть у промпт, щоб аналітик не повторював ту саму помилку (Олег 26.09.2026)."""
    from .models import DialogReview
    since = (timezone.localtime() - timedelta(days=days)).date()
    lines = []
    for r in DialogReview.objects.filter(period_start__gte=since).order_by("-id")[:20]:
        for it in (r.issues or []):
            fb = it.get("feedback") or {}
            if fb.get("verdict") == "wrong":
                lines.append("• Висновок «%s» Олег назвав неправильним: %s"
                             % ((it.get("problem") or "")[:120], (fb.get("note") or "—")[:200]))
        for p in (r.proposals or []):
            if p.get("status") == "declined":
                lines.append("• Правило «%s» відхилено: %s"
                             % (p.get("title"), (p.get("note") or "без пояснення")[:200]))
    lines = lines[:limit]
    return ("ПОПРАВКИ ВЛАСНИКА (не повторюй цих висновків):\n" + "\n".join(lines)) if lines else ""


CLOSED_RX = re.compile(r"ознайомлю|заготовк|шаблонн\w* фраз|беру.{0,12}у роботу", re.I)


def _clean_closed(d):
    """Тема «менеджер узяв запит» закрита — правила вже оновлені. Якщо аналітик усе одно про неї
    написав, прибираємо саме ці речення, а не весь розбір діалогу."""
    for k in ("problem", "why", "fix", "better", "employee", "script"):
        v = (d.get(k) or "").strip()
        if not v:
            continue
        keep = [p for p in re.split(r"(?<=[.!?])\s+", v) if not CLOSED_RX.search(p)]
        d[k] = " ".join(keep).strip()
    d["steps"] = [x for x in (d.get("steps") or []) if not CLOSED_RX.search(str(x))]
    return d


def polish(rows, model="claude-sonnet-4-6"):
    """Вичитка: Haiku інколи змішує українську з російською. Один дешевий прохід —
    і всі тексти, які читає Олег і менеджери, чистою українською."""
    from .ai import claude_json
    items = [{"id": k, "problem": v.get("problem", ""), "better": v.get("better", ""),
              "fix": v.get("fix", ""), "employee": v.get("employee", "")}
             for k, v in rows.items()]
    for i in range(0, len(items), 8):
        chunk = items[i:i + 8]
        try:
            r = claude_json(
                "Перепиши ці тексти ЧИСТОЮ УКРАЇНСЬКОЮ мовою, не міняючи змісту і не додаючи нічого. "
                "Прибери русизми, помилкові форми й чужі слова. Поверни JSON "
                "{\"items\": [{\"id\": …, \"problem\": …, \"better\": …, \"fix\": …, \"employee\": …}]}\n\n"
                + json.dumps(chunk, ensure_ascii=False)[:9000],
                model=model, max_tokens=2600, source="ШІ-РОП: вичитка")
        except Exception:
            continue
        for it in (r.get("items") or []):
            k = it.get("id")
            if k in rows:
                for f in ("problem", "better", "fix", "employee"):
                    if (it.get(f) or "").strip():
                        rows[k][f] = it[f]
    return rows


def ai_dialogs(items, model="claude-haiku-4-5"):
    """Розбір проблемних діалогів пачками. Повертає {conv_id: {...}}."""
    from .ai import claude_json
    res = {}
    for i in range(0, len(items), 5):
        chunk = items[i:i + 5]
        blocks = []
        for it in chunk:
            who = [AGENT_LABEL[a] for a in actors(it.get("today") or it["msgs"])]
            blocks.append("=== ДІАЛОГ %s (%s, канал %s) ===\nЗ нашого боку писали: %s\n"
                          "Формальні зауваження: %s\n%s"
                          % (it["conv"].id, str(it["conv"].contact)[:30],
                             it["conv"].channel.name if it["conv"].channel_id else "—",
                             ", ".join(who) or "невідомо",
                             ", ".join(TAGS.get(t, t) for t, _q in it["tags"]) or "—",
                             _dialog_text(it["msgs"])))
        extra = "\n\n".join(x for x in (GOOD_CACHE.get("text") or "", past_feedback()) if x)
        prompt = ((extra + "\n\n" if extra else "")
                  + "Розбери кожен діалог. Для КОЖНОГО поверни JSON-обʼєкт у масиві \"dialogs\":\n"
                  "{\"id\": <номер діалогу>, \"problem\": \"що саме завадило продажу, 1 речення\", "
                  "\"quote\": \"наша фраза, після якої стало гірше — ОБОВʼЯЗКОВО з часом у форматі "
                  "[дд.мм гг:хх], як у переписці\", "
                  "\"better\": \"як треба було написати, готовий текст клієнту\", "
                  "\"why\": \"чому клієнт відреагував саме так — логіка з його боку, 1-2 речення\", "
                  "\"steps\": [\"2-4 конкретні наступні кроки саме в ЦЬОМУ чаті, по одному рядку, "
                  "у порядку виконання\"], "
                  "\"existing\": \"якщо цей випадок УЖЕ покритий чинним правилом — назви його одним рядком; "
                  "якщо правила немає — порожній рядок\", "
                  "\"missing_in\": [\"crm\" і/або \"chatplace\" — у кого з агентів цього правила ЩЕ НЕМАЄ; "
                  "якщо є в обох — порожній список\"], "
                  "\"fix\": \"ГОТОВЕ правило для агента, 1-2 речення наказовим тоном — саме те, що треба "
                  "дописати в його інструкцію, щоб такого більше не було\", "
                  "\"agents\": [\"crm\" і/або \"chatplace\" і/або \"human\" — кого саме вчимо, "
                  "виходячи з того, хто писав клієнту в цьому діалозі], "
                  "\"employee\": \"якщо діалог вів ЖИВИЙ менеджер — що конкретно сказати цій людині "
                  "(чому саме так краще, одним реченням); якщо тільки ШІ — порожній рядок\", "
                  "\"script\": \"який наш шаблон/скрипт варто переписати через цей випадок — назви його "
                  "своїми словами; якщо не про скрипт — порожній рядок\", "
                  "\"tag\": \"коротка категорія 1-3 слова\"}\n"
                  "Якщо діалог нормальний — problem: \"ок\".\n"
                  "ВСІ поля пиши ЧИСТОЮ УКРАЇНСЬКОЮ — без російських та інших слів. "
                  "У \"existing\" пиши коротко, до 12 слів: назву правила, яке порушено.\n"
                  "У системному блоці є ЧИННІ правила обох агентів. Спершу перевір, чи випадок уже "
                  "ними покритий: якщо так — це ПОРУШЕННЯ наявного правила, а не привід вигадувати нове "
                  "(напиши його в \"existing\"). Нове правило пропонуй лише коли в чинних його справді немає. "
                  "Наша мета — щоб продавець CRM умів усе те саме, що Юля ChatPlace, і Юлю можна було "
                  "вимкнути: якщо правило є у Юлі, але немає у продавця CRM — став \"crm\" у missing_in.\n"
                  "⛔ Про службову фразу «менеджер узяв ваш запит / ознайомлююсь / збираю інформацію» "
                  "не пиши ВЗАГАЛІ — правила по ній уже оновлені, це закрите питання.\n"
                  "ВАЖЛИВО: ми поступово вчимо ПРОДАВЦЯ CRM, щоб згодом вимкнути Юлю ChatPlace. "
                  "Тому якщо помилку зробила Юля ChatPlace, а продавець CRM у цьому чаті теж працює — "
                  "став обох, щоб правило лягло і в нашого агента.\n\n" + "\n\n".join(blocks))
        try:
            system = SHORT_SYSTEM + "\n\n" + rules_index()
            data = claude_json(prompt, model=model, max_tokens=4000, system=system, cache=True,
                               source="ШІ-РОП: нічний розбір")
        except Exception:
            continue
        for d in (data.get("dialogs") or []):
            try:
                res[int(d.get("id"))] = _clean_closed(d)
            except Exception:
                continue
    if res:
        try:
            res = polish(res)
        except Exception:
            pass
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
        " \"agents_plan\": [\"2-3 пункти: чого саме навчити ШІ-агентів, щоб конверсія зросла\"],\n"
        " \"people_plan\": [\"2-3 пункти: що сказати живим менеджерам або який скрипт переписати\"],\n"
        " \"delivery_note\": \"що робити з повідомленнями, які не дійшли (якщо такі були)\",\n"
        " \"proposals\": [{\"title\": \"коротка назва правила\", "
        "\"rule\": \"готовий текст правила для наших продавців, 1-3 речення, наказовий тон\", "
        "\"why\": \"на чому ґрунтується — скільки діалогів\", \"examples\": [номери діалогів]}]}\n"
        "Пропонуй максимум 3 правила і тільки те, що видно з даних. Якщо системних проблем немає — "
        "порожній список." % body)
    try:
        return claude_json(prompt, model=model, max_tokens=2600, system=ai_system(),
                           source="ШІ-РОП: підсумок дня")
    except Exception as e:
        return {"summary": "Не вдалося зробити підсумок (%s)" % str(e)[:120], "systemic": [], "proposals": []}


# ── денний розбір ─────────────────────────────────────────────────────────────────────
GOOD_CACHE = {}


def run_daily(day=None, send_tg=True, ai=True, days=1):
    from .models import DialogReview
    from django.db.models import Sum
    from apps.crm.models import AiUsage
    now = timezone.localtime()
    day = day or (now.date() - timedelta(days=1))
    days = max(1, int(days or 1))
    end = timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.min.time())) + timedelta(days=1)
    start = end - timedelta(days=days)
    items = collect(start, end, limit=150 * days if days > 1 else 150)
    for it in items:
        it["tags"] = check_dialog(it["today"], end)
    bad = [it for it in items if it["tags"]]
    bad.sort(key=lambda x: -len(x["tags"]))
    bad = bad[:25]
    if ai and bad:
        GOOD_CACHE["text"] = ("ЕТАЛОННІ ДІАЛОГИ НАШОЇ КОМПАНІЇ (на них рівняйся):\n%s" % good_dialogs()) \
            if good_dialogs() else ""
    ai_rows = ai_dialogs(bad) if (ai and bad) else {}
    issues = []
    for it in bad:
        d = ai_rows.get(it["conv"].id) or {}
        if (d.get("problem") or "").strip().lower() in ("ок", "ok", "нормально"):
            continue
        seen_actors = actors(it.get("today") or it["msgs"])
        ags = [a for a in (d.get("agents") or []) if a in AGENT_LABEL] or seen_actors
        issues.append({
            "fix": (d.get("fix") or "")[:600],
            "why": (d.get("why") or "")[:500],
            "existing_rule": (d.get("existing") or "")[:300],
            "employee": (d.get("employee") or "")[:400],
            "script": (d.get("script") or "")[:300],
            "missing_in": [x for x in (d.get("missing_in") or []) if x in ("crm", "chatplace")],
            "steps": [str(x)[:220] for x in (d.get("steps") or [])][:4],
            "agents": ags,
            "agent_names": [AGENT_LABEL[a] for a in ags],
            "when": ("%s — %s" % (_stamp((it.get("today") or it["msgs"])[0]),
                                   _stamp((it.get("today") or it["msgs"])[-1]))) if (it.get("today") or it["msgs"]) else "",
            "quote_at": (d.get("quote") or "")[:200],
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
    stats["delivery"] = delivery_stats(start, end)
    summ = ai_summary(stats, issues) if (ai and issues) else {"summary": "Проблемних діалогів не знайдено.",
                                                             "systemic": [], "proposals": []}
    props = []
    for n, p in enumerate((summ.get("proposals") or [])[:3], 1):
        props.append({"n": n, "title": (p.get("title") or "")[:120], "rule": (p.get("rule") or "")[:900],
                      "why": (p.get("why") or "")[:300], "examples": p.get("examples") or [], "status": "new"})
    cost = (AiUsage.objects.filter(created_at__gte=now - timedelta(minutes=30),
                                   source__startswith="ШІ-РОП: ").aggregate(s=Sum("cost_usd")).get("s") or 0)
    rev = DialogReview.objects.create(kind="daily",
                                      period_start=(day - timedelta(days=days - 1)), period_end=day,
                                      summary=(summ.get("summary") or "")[:4000],
                                      metrics={"stats": stats, "systemic": (summ.get("systemic") or [])[:6],
                                               "agents_plan": (summ.get("agents_plan") or [])[:4],
                                               "people_plan": (summ.get("people_plan") or [])[:4],
                                               "delivery_note": (summ.get("delivery_note") or "")[:600]},
                                      issues=issues, proposals=props, cost_usd=round(float(cost), 4))
    if send_tg:
        notify_owner(rev)
    return rev


def delivery_stats(start, end):
    """Де наші повідомлення не дійшли до клієнта (Олег 26.09.2026).
    failed — канал не прийняв (найчастіше Instagram поза вікном 24 год або відмова ChatPlace);
    window_risk — ми знали, що вікно ось-ось закриється."""
    from apps.inbox.models import Message
    rows = list(Message.objects.filter(created_at__gte=start, created_at__lt=end, direction="out",
                                       internal=False, status__in=BAD_STATUS)
                .select_related("conversation", "conversation__contact", "conversation__channel")
                .order_by("-id")[:60])
    by_channel, by_kind, samples = {}, {}, []
    for m in rows:
        ch = m.conversation.channel.name if m.conversation.channel_id else "—"
        by_channel[ch] = by_channel.get(ch, 0) + 1
        by_kind[m.status] = by_kind.get(m.status, 0) + 1
        if len(samples) < 8:
            samples.append({"conv_id": m.conversation_id, "status": m.status, "channel": ch,
                            "contact": str(m.conversation.contact)[:40] if m.conversation.contact_id else "",
                            "text": (m.text or "")[:120],
                            "kind": "фото/каталог" if ("📷" in (m.text or "") or "/f/" in (m.text or ""))
                                    else "текст"})
    return {"total": len(rows), "by_channel": by_channel, "by_kind": by_kind, "samples": samples}


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
        return claude_json(prompt, model=model, max_tokens=1200, system=ai_system(),
                           source="ШІ-РОП: тижневий аудит")
    except Exception as e:
        return {"summary": "Не вдалося зробити підсумок (%s)" % str(e)[:120]}


# ── звіт Олегу в Telegram ─────────────────────────────────────────────────────────────
def ask_about_dialog(rev, conv_id, question):
    """Менеджер/власник питає ШІ-РОПа, ЧОМУ він так оцінив діалог. Відповідає та сама персона,
    що робила розбір, і бачить і саму переписку, і свій висновок (Олег 26.09.2026)."""
    from apps.inbox.models import Conversation
    from .ai import claude_json
    conv = Conversation.objects.filter(id=conv_id).first()
    if conv is None:
        return {"error": "чат не знайдено"}
    issue = next((i for i in (rev.issues or []) if int(i.get("conv_id") or 0) == int(conv_id)), {})
    rows = list(conv.messages.filter(internal=False).order_by("-id")
                .values("direction", "text")[:40])[::-1]
    dialog = "\n".join(("Клієнт: " if r["direction"] == "in" else "Ми: ")
                        + re.sub(r"\s+", " ", (r["text"] or ""))[:300] for r in rows if (r["text"] or "").strip())
    prev = "\n".join("Питання: %s\nВідповідь: %s" % (q.get("q"), q.get("a")) for q in (issue.get("qa") or [])[-3:])
    prompt = ("Твій розбір цього діалогу (%s):\nПроблема: %s\nЧому: %s\nЩо треба було написати: %s\n"
              "Правило для агента: %s\n\nПЕРЕПИСКА:\n%s\n\n%s\nВЛАСНИК ПИТАЄ: %s\n\n"
              "Відповідай по суті, коротко (до 6 речень), українською. Якщо власник має рацію і твій "
              "висновок був неправильний — скажи це прямо і сформулюй правильний висновок. "
              "Поверни JSON {\"answer\": \"...\"}."
              % (str(conv.contact)[:40] if conv.contact_id else conv.id,
                 issue.get("problem") or "—", issue.get("why") or "—", issue.get("better") or "—",
                 issue.get("fix") or "—", dialog[-6000:],
                 ("ПОПЕРЕДНІ ПИТАННЯ ПО ЦЬОМУ ДІАЛОГУ:\n%s\n" % prev) if prev else "",
                 (question or "").strip()[:600]))
    try:
        r = claude_json(prompt, model="claude-sonnet-4-6", max_tokens=900, system=ai_system(),
                        source="ШІ-РОП: питання по розбору")
        ans = (r.get("answer") or r.get("suggestion") or "").strip()
    except Exception as e:
        return {"error": str(e)[:200]}
    if not ans:
        return {"error": "порожня відповідь"}
    issues = list(rev.issues or [])
    target = next((i for i in issues if int(i.get("conv_id") or 0) == int(conv_id)), None)
    if target is not None:
        qa = list(target.get("qa") or [])
        qa.append({"q": (question or "").strip()[:600], "a": ans[:2000],
                   "at": timezone.now().isoformat()})
        target["qa"] = qa[-10:]
        rev.issues = issues
        rev.save(update_fields=["issues"])
    return {"answer": ans}


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
