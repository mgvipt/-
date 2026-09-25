"""Навчання контент-заводу знаннями ззовні (25.09.2026): текст, файл або посилання → записи бази знань блогу.

Джерела: вставлений текст (напр. інструкції з проєкту ChatGPT), файл .txt/.md/.docx/.pdf, сторінка за посиланням.
ШІ (Sonnet, частинами ≤8000 символів, до 4 частин ≈$0.02–0.08) розкладає на записи: факт / правило / приклад / заборона,
і окремо пропонує доповнення до майстер-промту. НІЧОГО не зберігає — Олег вибирає галочками, що додати (BlogFact).
"""
import html
import io
import re
import urllib.request
import zipfile

from . import blogs
from .reels import clean_text

SOURCE = "content_factory.learn"
CHUNK = 8000
MAX_CHUNKS = 4

TASK = """Тобі дали матеріал (інструкцію, промт, статтю, нотатки), яким треба НАВЧИТИ генератор контенту блогу.
Розклади його на записи бази знань блогу:
- rule — правило, як робити контент (структура, стиль, дизайн, персонажі, формат, тон);
- fact — факт про продукт/героїв/світ блогу, що знадобиться в текстах;
- example — вдалий приклад тексту, сцени, заголовка (дослівно, якщо коротко);
- ban — чого робити не можна.
Кожен запис — окрема думка: title до 12 слів, text 1–5 речень, без води. Не вигадуй того, чого немає в матеріалі.
Пропускай те, що не стосується цього блогу або дублює майстер-промт блогу.
master_add — що варто ДОПИСАТИ в майстер-промт (головні принципи, 0–6 рядків у форматі «Пункт: …»), або "".
Відповідай ЛИШЕ JSON: {"items":[{"kind":"rule|fact|example|ban","title":"...","text":"..."}],"master_add":""}"""


class LearnError(Exception):
    pass


def text_from_file(name, data):
    name = (name or "").lower()
    if name.endswith((".txt", ".md", ".csv", ".json")):
        return data.decode("utf-8", errors="replace")
    if name.endswith(".docx"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                xml = z.read("word/document.xml").decode("utf-8", errors="replace")
        except (KeyError, zipfile.BadZipFile):
            raise LearnError("Не вдалося прочитати .docx.")
        xml = re.sub(r"</w:p>", "\n", xml)
        return html.unescape(re.sub(r"<[^>]+>", "", xml))
    if name.endswith(".pdf"):
        from pdfminer.high_level import extract_text
        try:
            return extract_text(io.BytesIO(data))
        except Exception:
            raise LearnError("Не вдалося прочитати PDF (можливо, це скан без тексту).")
    raise LearnError("Підтримуються .txt, .md, .docx, .pdf.")


def text_from_url(url):
    if not re.match(r"^https?://", url or ""):
        raise LearnError("Посилання має починатися з http:// або https://.")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Wallcov content factory)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read(3_000_000).decode(r.headers.get_content_charset() or "utf-8", errors="replace")
    except Exception as e:
        raise LearnError(f"Сторінка не відкрилась: {str(e)[:120]}")
    raw = re.sub(r"(?is)<(script|style|noscript|svg|nav|footer|header)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<(br|/p|/div|/li|/h\d)[^>]*>", "\n", raw)
    return html.unescape(re.sub(r"<[^>]+>", " ", raw))


def _norm(text):
    text = re.sub(r"[ \t]+", " ", text or "")
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def extract(blog, text, call=None):
    """Текст → пропозиції записів (не зберігає). Повертає {items, master_add, chunks, chars}."""
    text = _norm(text)
    if len(text) < 40:
        raise LearnError("Замало тексту для навчання.")
    chunks = [text[i:i + CHUNK] for i in range(0, len(text), CHUNK)][:MAX_CHUNKS]
    system = blogs.system_for(blog, TASK, platform=False)
    existing = "\n".join(f"- {f.title}" for f in blog.facts.all()[:80])
    items, master = [], []
    for n, ch in enumerate(chunks):
        prompt = f"Частина {n + 1} з {len(chunks)} матеріалу:\n\n{ch}\n\nУже є в базі блогу (не дублюй):\n{existing or '(порожньо)'}"
        if call is None:
            from apps.crm.ai import claude_json
            do = lambda p: claude_json(p, model="claude-sonnet-4-6", max_tokens=1500, system=system, source=SOURCE)
        else:
            do = call
        try:
            r = do(prompt) or {}
        except TimeoutError:
            r = do(prompt) or {}
        for it in (r.get("items") or [])[:25]:
            if not isinstance(it, dict) or not it.get("title"):
                continue
            kind = it.get("kind") if it.get("kind") in ("rule", "fact", "example", "ban") else "fact"
            items.append({"kind": kind, "title": clean_text(str(it["title"]))[:200], "text": str(it.get("text") or "").strip()[:2000]})
        if r.get("master_add"):
            master.append(str(r["master_add"]).strip())
    seen, uniq = set(), []
    for it in items:  # однакові заголовки з різних частин — один запис
        k = it["title"].lower()
        if k not in seen:
            seen.add(k)
            uniq.append(it)
    return {"items": uniq, "master_add": "\n".join(master)[:3000], "chunks": len(chunks), "chars": len(text),
            "truncated": len(text) > CHUNK * MAX_CHUNKS}
