"""Особистий асистент: приймання, розшифровка голосових, витяг знань у пропозиції (24.09.2026).

Приймання — від бота @wallcov_smm_bot (Hetzner, wallcov-content-bot) з тим самим секретом CF_INGEST_SECRET.
Бот нічого не надсилає у ці чати. Розшифровка — Gemini (аудіо), витяг — Claude. Обидва з місячним лімітом,
облік у AiUsage (source=assistant.*). Схвалена пропозиція → ЧЕРНЕТКА KnowledgeItem (агенти її не бачать,
доки Олег не затвердить у «AI ЦЕНТР»). Домовленості лишаються в приватному журналі асистента.
"""
import base64
import json
import os
import urllib.request
from datetime import datetime, timezone as dt_tz

from django.db.models import Sum
from django.utils import timezone

from .models import AssistantChat, AssistantMessage, AssistantProposal, AssistantSettings

TRANSCRIBE_SOURCE = "assistant.transcribe"
EXTRACT_SOURCE = "assistant.extract"
GEMINI_MODEL = "gemini-3.6-flash"
GEMINI_PRICE = (0.50, 3.00)  # ОЦІНКА $/1M, як у контент-заводі
BATCH = 150


class BudgetError(Exception):
    pass


def month_spent():
    from apps.crm.models import AiUsage
    start = timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return float(AiUsage.objects.filter(source__startswith="assistant.", created_at__gte=start)
                 .aggregate(s=Sum("cost_usd"))["s"] or 0)


def _check_budget():
    s = AssistantSettings.get()
    if month_spent() >= float(s.monthly_budget_usd):
        raise BudgetError(f"Досягнуто місячного ліміту асистента ${float(s.monthly_budget_usd):.2f}.")


# ── Приймання ───────────────────────────────────────────────────────────────────────────────────

def _kind_and_file(m):
    for key, kind in (("voice", "voice"), ("video_note", "video_note"), ("audio", "voice")):
        if m.get(key):
            return kind, m[key].get("file_id", ""), m[key].get("duration")
    if m.get("photo"):
        return "photo", m["photo"][-1].get("file_id", ""), None
    if m.get("document"):
        return "document", m["document"].get("file_id", ""), None
    if m.get("text") or m.get("caption"):
        return "text", "", None
    return "other", "", None


def ingest(update):
    """business_message / edited_business_message / message (група) → AssistantMessage. Повертає статус."""
    s = AssistantSettings.get()
    m = (update.get("business_message") or update.get("edited_business_message") or update.get("message")
         or update.get("edited_message"))
    if not m or not m.get("chat"):
        return "skip"
    is_business = bool(update.get("business_message") or update.get("edited_business_message"))
    c = m["chat"]
    if not is_business and c.get("type") == "private":
        return "skip"  # звичайні особисті повідомлення боту — не наша справа
    title = c.get("title") or " ".join(x for x in (c.get("first_name"), c.get("last_name")) if x) or c.get("username", "")
    chat, _ = AssistantChat.objects.get_or_create(chat_id=c["id"], defaults={
        "title": title[:200], "username": c.get("username", "") or "",
        "kind": AssistantChat.Kind.BUSINESS if is_business else AssistantChat.Kind.GROUP,
        "enabled": is_business})  # групи — лише після вмикання Олегом
    if not chat.enabled:
        return "chat-disabled"
    frm = m.get("from") or {}
    from_owner = bool(s.owner_tg_id and frm.get("id") == s.owner_tg_id)
    kind, file_id, duration = _kind_and_file(m)
    author = " ".join(x for x in (frm.get("first_name"), frm.get("last_name")) if x) or frm.get("username", "")
    AssistantMessage.objects.update_or_create(chat=chat, message_id=m["message_id"], defaults={
        "from_owner": from_owner, "author": author[:160], "sender_id": frm.get("id"), "kind": kind,
        "text": (m.get("text") or m.get("caption") or "")[:8000], "file_id": file_id, "duration": duration,
        "sent_at": datetime.fromtimestamp(m.get("date", 0), tz=dt_tz.utc),
    })
    return "saved"


def connection(update):
    """business_connection: запамʼятовуємо Telegram id Олега (хто підключив бота)."""
    bc = update.get("business_connection") or {}
    uid = (bc.get("user") or {}).get("id")
    if uid:
        s = AssistantSettings.get()
        s.owner_tg_id = uid
        s.save(update_fields=["owner_tg_id"])
        AssistantMessage.objects.filter(sender_id=uid, from_owner=False).update(from_owner=True)
        return "owner-set"
    return "skip"


# ── Розшифровка голосових ──────────────────────────────────────────────────────────────────────

def _gemini_transcribe(audio, mime):
    key = os.environ.get("GEMINI_API_KEY", "")
    body = {"contents": [{"role": "user", "parts": [
        {"inlineData": {"mimeType": mime, "data": base64.b64encode(audio).decode()}},
        {"text": "Дослівно розшифруй мовлення (українська або російська — як говорять). Лише текст, без коментарів."}]}],
        "generationConfig": {"maxOutputTokens": 4000, "thinkingConfig": {"thinkingLevel": "low"}}}
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=180) as r:
        resp = json.load(r)
    u = resp.get("usageMetadata") or {}
    tin = int(u.get("promptTokenCount") or 0)
    tout = int(u.get("candidatesTokenCount") or 0) + int(u.get("thoughtsTokenCount") or 0)
    from apps.crm.models import AiUsage
    AiUsage.objects.create(source=TRANSCRIBE_SOURCE, model=GEMINI_MODEL, in_tok=tin, out_tok=tout,
                           cost_usd=(tin * GEMINI_PRICE[0] + tout * GEMINI_PRICE[1]) / 1_000_000)
    return "".join(p.get("text", "") for p in ((resp.get("candidates") or [{}])[0].get("content") or {}).get("parts", []))


def transcribe_pending(limit=30):
    from apps.content_factory.telegram import _tg, tg_config
    done = 0
    for m in AssistantMessage.objects.filter(kind__in=["voice", "video_note"], transcribed_at=None).exclude(file_id="")[:limit]:
        _check_budget()
        try:
            path = _tg("getFile", {"file_id": m.file_id})["file_path"]
            with urllib.request.urlopen(f"https://api.telegram.org/file/bot{tg_config()[0]}/{path}", timeout=120) as r:
                audio = r.read()
            mime = "video/mp4" if m.kind == "video_note" else "audio/ogg"
            m.transcript = _gemini_transcribe(audio, mime).strip()[:20000]
        except Exception as e:  # файл завеликий (>20 МБ для бота) або мережа — позначаємо, щоб не крутити по колу
            m.transcript = ""
            m.text = (m.text + f"\n[не вдалося розшифрувати: {str(e)[:80]}]").strip()
        m.transcribed_at = timezone.now()
        m.save(update_fields=["transcript", "text", "transcribed_at"])
        done += 1
    return done


# ── Витяг знань ────────────────────────────────────────────────────────────────────────────────

SYSTEM = """Ти — особистий асистент Олега, власника Wallcov (декоративні штукатурки й фарби, Україна).
Отримаєш уривок переписки з одним співрозмовником чи групою (О: — сказав Олег, інші — співрозмовник/учасники).
Витягни ЛИШЕ корисне для бізнесу, що варто памʼятати: факти про товари/процеси, ціни й умови постачальників,
домовленості (хто, що, до коли), рішення Олега. Не вигадуй і не узагальнюй того, чого немає в тексті.
Пропускай побутове, особисте, привітання, повтори. Паролі, номери карток, коди — НІКОЛИ не записуй.
Відповідай ЛИШЕ JSON: {"items":[{"kind":"fact|price|agreement|decision","title":"до 80 символів","text":"суть 1–4 речення",
"who":"з ким / про кого","due":"YYYY-MM-DD або ''","quote_ids":[номери повідомлень]}]}. Якщо нічого — {"items":[]}."""


def _dialog(msgs):
    lines = []
    for m in msgs:
        who = "О" if m.from_owner else (m.author or "Співрозмовник")
        body = m.body.replace("\n", " ")[:600]
        if body:
            lines.append(f"[{m.id}] {m.sent_at:%d.%m %H:%M} {who}: {body}")
    return "\n".join(lines)


def extract(call=None, max_chats=20):
    """Нові (ще не розібрані) повідомлення → пропозиції. Повертає кількість нових пропозицій."""
    s = AssistantSettings.get()
    made = 0
    chats = AssistantChat.objects.filter(enabled=True, messages__processed_at=None).distinct()[:max_chats]
    for chat in chats:
        msgs = list(chat.messages.filter(processed_at=None).exclude(kind__in=["voice", "video_note"], transcribed_at=None)
                    .order_by("sent_at")[:BATCH])
        text = _dialog(msgs)
        if not msgs:
            continue
        if len(text) < 40:
            chat.messages.filter(id__in=[m.id for m in msgs]).update(processed_at=timezone.now())
            continue
        _check_budget()
        if call is None:
            from apps.crm.ai import claude_json
            call = lambda p: claude_json(p, model=s.model, max_tokens=3000, system=SYSTEM, source=EXTRACT_SOURCE)
        r = call(f"Чат: {chat.title}\n\n{text}") or {}
        by_id = {m.id: m for m in msgs}
        for it in (r.get("items") or [])[:30]:
            if not isinstance(it, dict) or not it.get("title"):
                continue
            kind = it.get("kind") if it.get("kind") in AssistantProposal.Kind.values else "fact"
            ev = [{"message_id": i, "quote": by_id[i].body[:300]} for i in (it.get("quote_ids") or []) if i in by_id][:5]
            due = None
            try:
                due = datetime.strptime(it.get("due") or "", "%Y-%m-%d").date()
            except ValueError:
                pass
            AssistantProposal.objects.create(kind=kind, title=str(it["title"])[:200], text=str(it.get("text", ""))[:4000],
                                             who=str(it.get("who", ""))[:160], due=due, chat=chat, evidence=ev)
            made += 1
        chat.messages.filter(id__in=[m.id for m in msgs]).update(processed_at=timezone.now())
    return made


def accept(proposal):
    """Схвалити: факт/ціна/рішення → ЧЕРНЕТКА в базі знань CRM (агенти не бачать до затвердження в AI ЦЕНТР).
    Домовленість лишається в приватному журналі."""
    if proposal.kind in (AssistantProposal.Kind.FACT, AssistantProposal.Kind.PRICE, AssistantProposal.Kind.DECISION,
                         AssistantProposal.Kind.STYLE) and not proposal.knowledge_item_id:
        from apps.knowledge.models import KnowledgeItem
        topic = "pricing" if proposal.kind == AssistantProposal.Kind.PRICE else "tone" if proposal.kind == "style" else "other"
        item = KnowledgeItem.objects.create(
            kind="rule" if proposal.kind == "style" else "fact", topic=topic, status="draft", source="manual",
            title=proposal.title[:300], text=proposal.text,
            internal_note=f"Особистий асистент · {proposal.who or ''} · чат «{proposal.chat or ''}» · пропозиція #{proposal.id}"[:1000])
        proposal.knowledge_item_id = item.id
    proposal.status = AssistantProposal.Status.ACCEPTED
    proposal.save(update_fields=["status", "knowledge_item_id"])
    return proposal
