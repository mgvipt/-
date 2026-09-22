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
        from apps.crm.models import AgentConfig
        _am = AgentConfig.get().analyst_model or "claude-sonnet-4-6"
        r = claude_json(prompt, model=_am, max_tokens=1600, source="Оценка качества диалога (коуч)")
    except Exception:
        r = claude_json(prompt, model="claude-sonnet-4-6", max_tokens=1400, source="Оценка качества диалога (коуч)")
    if not isinstance(r, dict):
        return {"overall": 0, "scores": {}, "error": "bad response"}
    sc = r.get("scores") or {}
    r["scores"] = {k: int(sc.get(k) or 0) for k in DIMENSIONS}
    r["overall"] = int(r.get("overall") or (sum(r["scores"].values()) // max(len(r["scores"]), 1)))
    return r


def ask_analyst(messages, question, context=""):
    """22.09.2026 (Олег: «додати можливість задавати ШІ-РОП питання, менеджери зможуть питати
    конкретно, не лише після аналізу діалогу»). Швидка відповідь на конкретне питання менеджера
    по ЦЬОМУ діалогу — не повний коучинг-розбір (analyze_dialog), а пряма відповідь.
    Повертає dict {"answer": "..."} або {"error": "..."}."""
    q = (question or "").strip()
    if not q:
        return {"error": "Питання порожнє"}
    dialog = _fmt_dialog(messages)
    prompt = (
        "Ти — аналітик продажів і коуч компанії Wallcov (декоративні покриття та фарби для стін), "
        "працюєш у парі з РОП. Менеджер поставив тобі КОНКРЕТНЕ питання про цей діалог з клієнтом — "
        "дай ПРЯМУ відповідь по суті, коротко (2-5 речень), без загального розбору якості. Якщо в "
        "діалозі бракує даних для відповіді — чесно скажи, чого саме бракує.\n\n"
        "ДІАЛОГ:\n%s\n\nКОНТЕКСТ УГОДИ: %s\n\nПИТАННЯ МЕНЕДЖЕРА: %s\n\n"
        'Поверни СТРОГО JSON українською: {"answer": "пряма відповідь на питання"}'
    ) % (dialog or "(діалогу ще немає)", context or "—", q)
    try:
        from apps.crm.models import AgentConfig
        _am = AgentConfig.get().analyst_model or "claude-sonnet-4-6"
        r = claude_json(prompt, model=_am, max_tokens=900, source="ШІ-РОП: питання менеджера")
    except Exception:
        r = claude_json(prompt, model="claude-sonnet-4-6", max_tokens=800, source="ШІ-РОП: питання менеджера")
    if not isinstance(r, dict) or not r.get("answer"):
        return {"error": "Не вдалося отримати відповідь"}
    return {"answer": r["answer"], "question": q}


def label_speakers(transcript):
    """Моно-запис дзвінка → розмітка реплік на МЕНЕДЖЕР/КЛІЄНТ за змістом (Claude)."""
    if not transcript or len(transcript.strip()) < 30:
        return transcript
    prompt = (
        "Це транскрипт телефонного дзвінка менеджера компанії Wallcov (декоративні покриття та фарби для стін) "
        "з клієнтом. Записано ОДНИМ каналом — спікери не розділені. Розділи текст на репліки за змістом: "
        "менеджер консультує, називає ціни, пропонує наступний крок; клієнт питає, відповідає, сумнівається. "
        "Текст реплік НЕ змінюй, лише познач хто говорить.\n"
        "Поверни СТРОГО JSON українською: {\"dialog\": \"МЕНЕДЖЕР: ...\\nКЛІЄНТ: ...\\nМЕНЕДЖЕР: ...\"}\n\n"
        "ТРАНСКРИПТ:\n" + transcript[:6000])
    try:
        r = claude_json(prompt, model="claude-sonnet-4-6", max_tokens=2200, source="Разметка звонка (кто говорит)")
        if isinstance(r, dict) and r.get("dialog"):
            return r["dialog"][:20000]
    except Exception:
        pass
    return transcript
