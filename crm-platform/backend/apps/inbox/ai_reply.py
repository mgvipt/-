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

MAX_PER_DAY = 15          # запасні значення, якщо налаштування AI ЦЕНТРУ недоступні
SILENCE_HOURS = 12
MIN_SECONDS = 20
NOTE_PREFIX = "ІІ у каналі"


def _limits():
    """Налаштування з AI ЦЕНТРУ (База знань → Команда агентів): пауза після менеджера і ліміт на добу."""
    try:
        from apps.knowledge.models import KnowledgeSettings
        row = KnowledgeSettings.objects.filter(id=1).values("ai_silence_hours", "ai_max_per_day").first()
        if row:
            return int(row["ai_silence_hours"]), int(row["ai_max_per_day"])
    except Exception:
        pass
    return SILENCE_HOURS, MAX_PER_DAY


def channel_on(channel):
    cfg = (channel.config or {}) if channel else {}
    return bool(cfg.get("ai_reply"))


def _allowed_chat(channel, conv):
    only = ((channel.config or {}).get("ai_reply_only_chats") or [])
    if not only:
        return True
    return str(conv.external_chat_id) in {str(x) for x in only}


def _manager_active(conv, hours):
    """Менеджер веде цей чат: САМ ПИСАВ клієнту за останні N годин (N — з AI ЦЕНТРУ).
    18.09.2026 (Олег): «якщо менеджер написав клієнту — агент у цьому чаті не пише». Саме написав:
    закріплений за чатом менеджер, який ще нічого не відповів, ІІ не блокує."""
    from .models import Message
    if hours <= 0:
        return False
    return Message.objects.filter(conversation=conv, direction="out", sender__isnull=False,
                                  created_at__gte=timezone.now() - timedelta(hours=hours)).exists()


def _throttled(conv, max_per_day):
    from .models import Message
    key = "ai_reply_%s" % conv.id
    if not cache.add(key, 1, MIN_SECONDS):
        return True
    day = Message.objects.filter(conversation=conv, direction="out", internal=False,
                                 sender_name__startswith=NOTE_PREFIX,
                                 created_at__gte=timezone.now() - timedelta(days=1)).count()
    return day >= max_per_day


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
    hours, max_per_day = _limits()
    if _manager_active(conv, hours):
        return False
    return not _throttled(conv, max_per_day)


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
        _note(conv, "%s: не зміг відповісти (%s). Клієнту нічого не надіслано — дайте відповідь вручну."
              % (NOTE_PREFIX, str(e)[:200]))
        return
    try:
        msg = send_message(conv, text)
        Message.objects.filter(id=msg.id).update(sender_name="%s · %s" % (NOTE_PREFIX, conv.channel.name))
    except Exception as e:
        _note(conv, "%s: не вдалося надіслати (%s). Текст: «%s»" % (NOTE_PREFIX, str(e)[:200], text[:600]))
        return
    _note(conv, note)
    if r.get("order"):
        _make_kit_offer(conv, r["order"])


MAX_AUTO_ORDER = 2000        # ₴ — вище цієї суми оформлює менеджер


def _make_kit_offer(conv, order):
    """18.09.2026 (Олег): «клієнт погодився — скидай посилання на тест-набір, а про обʼєм питай потім».
    Створюємо сделку з обраним тест-набором і CRM сама надсилає прорахунок + посилання LiqPay (make_offer)."""
    from apps.crm.models import Deal, Funnel
    from apps.crm.views import _find_product, make_offer
    name = (order.get("product") or "").strip()
    prod = _find_product(name)
    if not prod:
        _note(conv, "%s: хотів оформити «%s» — такого товару немає в номенклатурі, оформіть, будь ласка, вручну."
              % (NOTE_PREFIX, name[:80]))
        return
    if float(prod.price or 0) <= 0 or float(prod.price or 0) > MAX_AUTO_ORDER:
        _note(conv, "%s: «%s» — %s ₴, це поза автоматичним оформленням, зробіть вручну."
              % (NOTE_PREFIX, prod.name[:60], prod.price))
        return
    if not conv.contact_id:
        _note(conv, "%s: немає картки клієнта — оформіть замовлення вручну." % NOTE_PREFIX)
        return
    from apps.crm.models import PayLink
    recent = (Deal.objects.filter(contact_id=conv.contact_id, stage__is_won=False, stage__is_lost=False,
                                  created_at__gte=timezone.now() - timedelta(hours=24))
              .filter(items__isnull=False).order_by("-created_at").first())
    if recent is not None:
        paid = sum(float(p.amount) for p in recent.payments.all() if p.is_paid)
        if paid <= 0:
            # 18.09.2026 (Олег: «продублювались повідомлення на оплату»): друге посилання не створюємо
            pl = PayLink.objects.filter(deal=recent).order_by("-id").first()
            _note(conv, "%s: замовлення вже оформлене — сделка #%s на %s ₴%s. Нового посилання не створюю."
                  % (NOTE_PREFIX, recent.id, recent.amount,
                     (", посилання https://crm.wallcovdec.com.ua/p/%s/" % pl.code) if pl else ""))
            return
    deal = (Deal.objects.filter(contact_id=conv.contact_id, stage__is_won=False, stage__is_lost=False)
            .order_by("-created_at").first())
    if deal is None or deal.items.exists():
        f = Funnel.objects.filter(name__istartswith="22 Тестовий набір").first() or Funnel.objects.order_by("id").first()
        st = f.stages.order_by("order").first() if f else None
        if not (f and st):
            _note(conv, "%s: немає воронки для тест-наборів — оформіть вручну." % NOTE_PREFIX)
            return
        deal = Deal.objects.create(title="Тест-набір · %s" % str(conv.contact)[:40], funnel=f, stage=st,
                                   contact_id=conv.contact_id, owner=conv.assigned_to)
    try:
        res = make_offer(deal, [{"name": prod.name, "qty": order.get("qty") or 1}])
    except Exception as e:
        _note(conv, "%s: не вдалося оформити (%s) — зробіть вручну." % (NOTE_PREFIX, str(e)[:200]))
        return
    if res.get("ok"):
        _note(conv, "%s: оформив сделку #%s на %s ₴ (%s) і надіслав посилання на оплату %s"
              % (NOTE_PREFIX, deal.id, res.get("amount"), prod.name[:50], res.get("url") or "—"))
    else:
        _note(conv, "%s: сделка #%s — оффер не створено (%s), перевірте вручну."
              % (NOTE_PREFIX, deal.id, res.get("msg") or "—"))


def maybe_reply(conv, incoming):
    """Викликається з ingest(): якщо канал увімкнено — відповідаємо окремим потоком."""
    try:
        if not should_reply(conv, incoming):
            return False
        threading.Thread(target=reply_now, args=(conv.id,), daemon=True).start()
        return True
    except Exception:
        return False
