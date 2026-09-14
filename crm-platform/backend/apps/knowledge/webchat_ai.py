"""Веб-чат на сайті відповідає з єдиної бази знань (14.09.2026, ai-kb2). ЗА ЗАМОВЧУВАННЯМ ВИМКНЕНО.

Вмикає лише власник: AI ЦЕНТР → База знань ✓ → Команда агентів → «ІІ відповідає у веб-чаті».
Вимкнено → inbox/webchat.py працює рівно як раніше (одразу «передала менеджеру» або WEBCHAT_SELLER_URL).
Увімкнено → answer("yulia_web", …): лише ЗАТВЕРДЖЕНІ записи з позначкою «Сайт (веб-чат)»; ціни — лише з каталогу CRM;
знижки — лише за затвердженим правилом; замовлення / оплата / невпевненість → «передала менеджеру».
Менеджер бачить внутрішню нотатку (клієнту не йде): чому передано і які записи використано.
"""
from .answer import HANDOFF_TEXT, answer
from .models import KnowledgeSettings

SOURCE = "Веб-чат: ІІ з бази знань"


def enabled():
    """Без створення рядка налаштувань і без мережі: вимкнено → False."""
    try:
        return bool(KnowledgeSettings.objects.filter(id=1).values_list("webchat_ai_enabled", flat=True).first())
    except Exception:
        return False


def history(conv, incoming, limit=12):
    rows = list(conv.messages.filter(internal=False, id__lte=incoming.id).order_by("-id").values("direction", "text")[:limit])
    return [{"role": "client" if r["direction"] == "in" else "agent", "text": r["text"] or ""}
            for r in rows[::-1] if (r["text"] or "").strip()]


def reply(conv, incoming):
    from apps.inbox.models import Message
    try:
        cfg = KnowledgeSettings.get()
        r = answer("yulia_web", history(conv, incoming), include_drafts=False, model=cfg.webchat_model or None,
                   source=SOURCE, timeout=25)
        text = (r.get("text") or "").strip() or HANDOFF_TEXT
        used = ", ".join("#%d" % u["id"] for u in r.get("used_items") or []) or "—"
        if r.get("handoff"):
            note = "ІІ веб-чату передав менеджеру: %s. Записи бази: %s." % (r.get("handoff_reason") or "—", used)
            if r.get("draft_reply"):
                note += " Хотів відповісти: «%s»" % r["draft_reply"][:600]
        else:
            note = "ІІ веб-чату відповів з бази знань. Записи: %s. ≈ $%s" % (used, (r.get("cost") or {}).get("usd", 0))
    except Exception as e:  # ключ / мережа / будь-що — клієнт не чекає, веде менеджер
        text, note = HANDOFF_TEXT, "ІІ веб-чату: помилка (%s) — передано менеджеру." % str(e)[:200]
    msg = Message.objects.create(conversation=conv, direction="out", text=text[:4000],
                                 external_id="web-ai:%s" % incoming.id, sender_name="Юля · Wallcov")
    try:
        Message.objects.create(conversation=conv, direction="out", internal=True, text=note[:2000],
                               external_id="web-ai-note:%s" % incoming.id, sender_name="ІІ веб-чату")
    except Exception:
        pass
    return msg
