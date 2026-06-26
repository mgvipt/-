"""Аналітик продажів + коуч (працює в парі з РОП). Глибокий розбір діалогу:
оцінка якості по шкалах, чому не веде до продажу, як краще, міні-урок.
Зберігає історію оцінок (для скорингу + гейміфікації)."""
from .ai import claude_json

DIMENSIONS = ["вступ", "виявлення_потреби", "презентація_цінності",
              "робота_з_запереченнями", "заклик_до_дії", "тон_емпатія"]


def _fmt_dialog(messages):
    out = []
    for m in messages:
        who = "КЛІЄНТ" if m.get("direction") == "in" else "МЕНЕДЖЕР"
        txt = (m.get("text") or "").strip()
        if txt:
            out.append("%s: %s" % (who, txt))
    return "\n".join(out)


def analyze_dialog(messages, context="", kind="чат"):
    """Глибокий коучинг-розбір. Повертає dict зі score + рекомендаціями (укр)."""
    dialog = _fmt_dialog(messages)
    if not dialog or len(dialog) < 15:
        return {"overall": 0, "scores": {}, "strengths": "", "why_not_selling": "Замало повідомлень для розбору.",
                "recommended_reply": "", "coaching": "", "empty": True}
    prompt = (
        "Ти — досвідчений аналітик продажів і коуч компанії Wallcov (декоративні покриття та фарби для стін). "
        "Працюєш у парі з РОП: РОП підказує тактику тут і зараз, а ти — ГЛИБОКИЙ розбір як міні-коучинг, щоб менеджер РІС.\n"
        "Розбери %s менеджера з клієнтом. Будь конкретним, з прикладами фраз із діалогу, доброзичливо але чесно.\n\n"
        "ДІАЛОГ:\n%s\n\nКОНТЕКСТ УГОДИ: %s\n\n"
        "Поверни СТРОГО JSON українською, без пояснень навколо:\n"
        "{\n"
        '  "overall": <0-100 загальна якість роботи менеджера>,\n'
        '  "scores": {"вступ":0-100, "виявлення_потреби":0-100, "презентація_цінності":0-100, "робота_з_запереченнями":0-100, "заклик_до_дії":0-100, "тон_емпатія":0-100},\n'
        '  "strengths": "що менеджер зробив ДОБРЕ (1-2 речення, конкретно)",\n'
        '  "why_not_selling": "чому цей діалог НЕ веде до продажу або що ВІДШТОВХУЄ клієнта — конкретна фраза + чому погано",\n'
        '  "recommended_reply": "готова КРАЩА відповідь клієнту прямо зараз (щоб вставити в чат, тон Wallcov, з цінністю і наступним кроком)",\n'
        '  "coaching": "МІНІ-УРОК: 1 конкретна навичка яку прокачати + чому саме це підніме конверсію (1-2 речення)"\n'
        "}"
    ) % (kind, dialog, context or "—")
    try:
        r = claude_json(prompt, model="claude-opus-4-8", max_tokens=1600)
    except Exception:
        r = claude_json(prompt, model="claude-sonnet-4-6", max_tokens=1400)
    if not isinstance(r, dict):
        return {"overall": 0, "scores": {}, "error": "bad response"}
    sc = r.get("scores") or {}
    r["scores"] = {k: int(sc.get(k) or 0) for k in DIMENSIONS}
    r["overall"] = int(r.get("overall") or (sum(r["scores"].values()) // max(len(r["scores"]), 1)))
    return r
