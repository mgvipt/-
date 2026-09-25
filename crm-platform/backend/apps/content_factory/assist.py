"""ШІ-помічник редактора (25.09.2026): вичитка тексту й поради до рилса, привʼязані до МЕТИ блогу.

Вичитка — Haiku (≈$0.001–0.003): орфографія, пунктуація, незграбні формулювання й ШІ-штампи. Факти й цифри не міняє.
Поради — Sonnet (≈$0.01–0.02): не більше 5, кожна повʼязана з метою блогу й виражена дією, яку CRM вміє виконати
(перехід, рух камери, заміна/перегенерація кадру, зміна тексту, додати елемент у кадр). Порада без звʼязку з метою —
відкидається: краще 2 корисні, ніж 5 «для галочки».
"""
from . import blogs
from .reels import clean_text

SOURCE = "content_factory.assist"

PROOF = """Ти редактор-коректор. Виправ текст: орфографія, пунктуація, узгодження, незграбні або канцелярські формулювання,
ШІ-штампи («Плануєш… і не знаєш…», «Хочеш…, але боїшся…», «Мрієш про…», «А ти знала…»), емодзі-прикраси.
НЕ змінюй факти, цифри, ціни, назви матеріалів, посилання, телефони й зміст. Зберігай мову оригіналу, абзаци й тон блогу.
Якщо текст уже добрий — поверни його без змін і порожній список.
Відповідай ЛИШЕ JSON: {"text":"виправлений текст","changes":[{"was":"...","now":"...","why":"коротко"}]}"""

ADVICE = """Ти продюсер коротких вертикальних роликів. Подивись сценарій ролика й дай ДО 5 порад, як зробити, щоб він краще чіпляв.
Кожна порада ОБОВʼЯЗКОВО служить меті блогу (поле «Мета блогу») — поясни як. Якщо порада не наближає до мети — не пиши її.
Не радь те, що вже є. Не радь музику (її додають у соцмережі). Не пропонуй вигадані факти.
Кожна порада — одна дія з цього списку (поле action):
- {"type":"transition","beat":N,"value":"fade|slide|zoom|cut"} — перехід ПЕРЕД кадром N (N з 0);
- {"type":"motion","beat":N,"value":"zoomin|zoomout|none"} — рух камери в кадрі N;
- {"type":"text","beat":N,"value":"новий текст до 7 слів"} — змінити текст на кадрі N;
- {"type":"edit_frame","beat":N,"value":"що додати/змінити в кадрі (елемент, стрілка, акцент)"} — ШІ домалює в кадр N;
- {"type":"regenerate","beat":N,"value":"опис нового кадру"} — замінити кадр N ШІ-кадром;
- {"type":"seconds","beat":N,"value":2.0} — нова тривалість кадру N.
Для блогу з правилом «фактура завжди справжня» НЕ пропонуй regenerate/edit_frame для кадрів із декоративним покриттям.
У title не пиши номер кадру (його видно окремо).
Відповідай ЛИШЕ JSON: {"advice":[{"title":"до 8 слів","why":"як це служить меті, 1 речення","action":{...}}]}"""

ACTIONS = {"transition": {"fade", "slide", "zoom", "cut"}, "motion": {"zoomin", "zoomout", "none"}}


def proofread(text, blog=None, call=None):
    text = (text or "").strip()
    if not text:
        return {"text": "", "changes": []}
    if call is None:
        from apps.crm.ai import claude_json
        system = PROOF + (f"\n\nТон блогу «{blog.name}»:\n{blog.master_prompt[:1500]}" if blog else "")
        call = lambda p: claude_json(p, model="claude-haiku-4-5", max_tokens=min(4000, 400 + len(text) // 2),
                                     system=system, source=SOURCE)
    r = call(text[:6000]) or {}
    out = str(r.get("text") or "").strip() or text
    changes = [{"was": str(c.get("was") or "")[:200], "now": str(c.get("now") or "")[:200], "why": str(c.get("why") or "")[:160]}
               for c in (r.get("changes") or []) if isinstance(c, dict)][:30]
    return {"text": out, "changes": changes}


def reel_advice(reel, call=None):
    blog = reel.blog or blogs.default_blog()
    if not (blog.goal or "").strip():
        raise ValueError(f"Вкажіть мету блогу «{blog.name}» у розділі «Блоги» — без неї поради будуть навмання.")
    lines = []
    for i, b in enumerate(reel.beats):
        what = "ШІ-кадр" if b.get("image_id") else "справжній кадр"
        fx = b.get("fx") or {}
        lines.append(f"[{i}] {b.get('seconds')} с · {what} · текст: «{b.get('text', '')}» · перехід: {fx.get('transition', 'cut')} · рух: {fx.get('motion', 'none')}"
                     + (f" · у кадрі: {b.get('prompt')}" if b.get("prompt") else ""))
    prompt = (f"Ролик: {reel.title}\nТема: {reel.topic}\nТривалість: {reel.duration} с\nПідпис: {reel.caption[:600]}\n\nКадри:\n"
              + "\n".join(lines))
    if call is None:
        from apps.crm.ai import claude_json
        call = lambda p: claude_json(p, model="claude-sonnet-4-6", max_tokens=1500,
                                     system=blogs.system_for(blog, ADVICE), source=SOURCE)
    r = call(prompt) or {}
    out = []
    for a in (r.get("advice") or [])[:5]:
        act = a.get("action") if isinstance(a, dict) else None
        if not isinstance(act, dict):
            continue
        t, beat, val = act.get("type"), act.get("beat"), act.get("value")
        try:
            beat = int(beat)
        except (TypeError, ValueError):
            continue
        if not 0 <= beat < len(reel.beats):
            continue
        if t in ACTIONS and val not in ACTIONS[t]:
            continue
        if t == "seconds":
            try:
                val = max(0.8, min(float(val), 8.0))
            except (TypeError, ValueError):
                continue
        elif t in ("text", "edit_frame", "regenerate"):
            val = clean_text(str(val or ""))[:300 if t != "text" else 80]
            if not val:
                continue
        elif t not in ACTIONS:
            continue
        if t in ("edit_frame", "regenerate") and blog.label_ai and not reel.beats[beat].get("image_id"):
            continue  # Wallcov: справжню фактуру не перемальовуємо
        out.append({"title": clean_text(str(a.get("title") or ""))[:80], "why": clean_text(str(a.get("why") or ""))[:240],
                    "action": {"type": t, "beat": beat, "value": val}})
    return out
