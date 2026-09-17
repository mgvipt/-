"""ІІ відповідає клієнту в каналах CRM — Viber, Telegram, WhatsApp, Facebook (17.09.2026, Олег:
«а в вайбері й телеграмі теж агент буде відповідати? і в ватсапі»).

ЗА ЗАМОВЧУВАННЯМ ВИМКНЕНО для всіх каналів. Вмикається по одному каналу:
    Channel.config["ai_reply"] = True                       — відповідати всім у цьому каналі
    Channel.config["ai_reply_only_chats"] = ["<chat_id>"]   — спочатку лише цим чатам (перевірка на своєму акаунті)

Мозок — той самий, що у веб-чата сайту: ЗАТВЕРДЖЕНІ записи бази знань CRM (apps.knowledge.answer,
агент «yulia_web»), ціни з каталогу, посилання на сторінки кольорів. Замовлення, оплата, сумнів →
«передала менеджеру» + внутрішня нотатка, клієнту нічого не вигадуємо.

Запобіжники (щоб ІІ не заважав людям і не спамив):
  • менеджер у діалозі (призначений або писав останні 12 год) — ІІ мовчить;
  • не більше 1 відповіді на 20 секунд і 15 на добу в одному чаті;
  • тільки вхідні від клієнта у відкритому діалозі, не коментарі Meta, не внутрішні нотатки;
  • відповідь іде окремим потоком: вебхук каналу не чекає ІІ і не відпадає по таймауту;
  • будь-яка помилка → клієнту нічого, менеджер бачить нотатку.
"""
import threading
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

MAX_PER_DAY = 15
MIN_SECONDS = 20
NOTE_PREFIX = "ІІ у каналі"


def channel_on(channel):
    cfg = (channel.config or {}) if channel else {}
    return bool(cfg.get("ai_reply"))


def _allowed_chat(channel, conv):
    only = ((channel.config or {}).get("ai_reply_only_chats") or [])
    if not only:
        return True
    return str(conv.external_chat_id) in {str(x) for x in only}


def _manager_active(conv):
    from .models import Message
    if conv.assigned_to_id:
        return True
    return Message.objects.filter(conversation=conv, direction="out", sender__isnull=False,
                                  created_at__gte=timezone.now() - timedelta(hours=12)).exists()


def _throttled(conv):
    from .models import Message
    key = "ai_reply_%s" % conv.id
    if not cache.add(key, 1, MIN_SECONDS):
        return True
    day = Message.objects.filter(conversation=conv, direction="out", internal=False,
                                 sender_name__startswith=NOTE_PREFIX,
                                 created_at__gte=timezone.now() - timedelta(days=1)).count()
    return day >= MAX_PER_DAY


def should_reply(conv, incoming):
    """Чи має ІІ відповісти на це повідомлення (лише читання, без мережі)."""
    if incoming is None or incoming.direction != "in" or incoming.internal:
        return False
    if not (incoming.text or "").strip():
        return False                      # фото/голосове без тексту — веде менеджер
    ch = conv.channel
    if not channel_on(ch) or not _allowed_chat(ch, conv):
        return False
    if conv.status != "open" or str(conv.external_chat_id or "").startswith("comment:"):
        return False
    if _manager_active(conv):
        return False
    return not _throttled(conv)


def _note(conv, text):
    from .models import Message
    Message.objects.create(conversation=conv, direction="out", internal=True, text=text[:4000],
                           sender_name="%s · службова нотатка" % NOTE_PREFIX)


def reply_now(conv_id):
    """Відповідь клієнту (виконується у окремому потоці)."""
    from apps.knowledge.answer import HANDOFF_TEXT, answer
    from apps.knowledge.models import KnowledgeSettings
    from apps.knowledge.webchat_ai import history
    from .models import Conversation, Message
    from .services import send_message
    conv = Conversation.objects.filter(id=conv_id).select_related("channel").first()
    if conv is None:
        return
    incoming = conv.messages.filter(direction="in", internal=False).order_by("-id").first()
    if incoming is None:
        return
    try:
        cfg = KnowledgeSettings.get()
        r = answer("yulia_web", history(conv, incoming), include_drafts=False, model=cfg.webchat_model or None,
                   source="%s: %s" % (NOTE_PREFIX, conv.channel.name), timeout=25)
        text = (r.get("text") or "").strip() or HANDOFF_TEXT
        used = ", ".join("#%d" % u["id"] for u in r.get("used_items") or []) or "—"
        note = ("%s передав менеджеру: %s. Записи: %s." % (NOTE_PREFIX, r.get("handoff_reason") or "—", used)
                if r.get("handoff") else
                "%s відповів з бази знань. Записи: %s. ≈ $%s" % (NOTE_PREFIX, used, (r.get("cost") or {}).get("usd", 0)))
    except Exception as e:
        _note(conv, "%s: помилка (%s) — відповідає менеджер." % (NOTE_PREFIX, str(e)[:200]))
        return
    try:
        msg = send_message(conv, text)
        Message.objects.filter(id=msg.id).update(sender_name="%s · %s" % (NOTE_PREFIX, conv.channel.name))
    except Exception as e:
        _note(conv, "%s: не вдалося надіслати (%s). Текст: «%s»" % (NOTE_PREFIX, str(e)[:200], text[:600]))
        return
    _note(conv, note)


def maybe_reply(conv, incoming):
    """Викликається з ingest(): якщо канал увімкнено — відповідаємо окремим потоком."""
    try:
        if not should_reply(conv, incoming):
            return False
        threading.Thread(target=reply_now, args=(conv.id,), daemon=True).start()
        return True
    except Exception:
        return False
