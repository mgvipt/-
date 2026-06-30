"""Фоновий РОП: класифікує ситуацію клієнта в чаті → мітка приоритету.
Викликається з management-команди priority_sweep (крон ~5 хв)."""
from apps.crm.ai import claude_json

# мітка → людська назва (показ у фронті). «quoted» = Просчитано ИИ.
PRIORITY_LABELS = {
    "complaint": "Возмущение",
    "urgent": "Хочет срочно",
    "needs_quote": "Нужен просчёт",
    "quoted": "Просчитано ИИ",
    "thinking": "Думает",
}

_PROMPT = """Ты — РОП (руководитель отдела продаж) компании декоративных покрытий и штукатурок для стен.
Прочитай диалог менеджера с клиентом и определи ОДНУ метку — текущую ситуацию клиента, чтобы менеджер видел приоритет:
- complaint = клиент недоволен, возмущён, жалоба, негатив, претензия
- urgent = хочет купить/получить срочно, готов платить сейчас, "нужно сегодня/завтра"
- needs_quote = просит просчёт/расчёт стоимости, прислал размеры/площадь/фото стен, ждёт цену
- quoted = ему УЖЕ посчитали цену/смету, теперь ждём решения клиента
- thinking = сомневается, "дорого", "подумаю", взял паузу, сравнивает
Если ничего из перечисленного явно не подходит (просто вопрос, приветствие, общая консультация) — верни пустую метку "".
Ответь СТРОГО JSON без лишнего текста: {"tag": "<метка или пусто>", "reason": "<3-5 слов на русском, кратко почему>"}

Диалог:
"""


def classify(messages):
    """messages: список {direction:'in'/'out', text}. Повертає (tag, reason)."""
    lines = []
    has_client = False
    for m in messages[-30:]:
        txt = (m.get("text") or "").strip()
        if not txt:
            continue
        if m.get("direction") == "in":
            who = "Клиент"
            has_client = True
        else:
            who = "Менеджер"
        lines.append(f"{who}: {txt[:300]}")
    if not has_client or not lines:
        return "", ""
    try:
        from apps.crm.models import AgentConfig
        _c = AgentConfig.get()
        r = claude_json("\n".join(lines), model=(_c.priority_model or "claude-haiku-4-5"), max_tokens=120, system=_PROMPT, cache=_c.cache_enabled, source="ИИ-РОП приоритет чатов")
    except Exception:
        return "", ""
    if not isinstance(r, dict):
        return "", ""
    tag = (r.get("tag") or "").strip()
    if tag not in PRIORITY_LABELS:
        tag = ""
    return tag, (r.get("reason") or "").strip()[:200]
