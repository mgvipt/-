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
import re
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



# 18.09.2026 (Олег): «якщо клієнт скаже — може, у вас є реквізити, — тоді надсилаємо реквізити,
# щоб клієнт не пропав і не передумав». Текст реквізитів лежить у базі знань (AI ЦЕНТР), щоб Олег
# міг їх виправити без програміста: запис із назвою «Реквізити для оплати».
REQ_TITLE = "Реквізити для оплати"
REQ_ASK = re.compile(r"реквізит|реквизит|\bрахунок\b|\bрахунки\b|\bсчет\b|\bсчёт\b|iban|безготівк|безнал", re.I)
REQ_PAID = re.compile(r"оплат(ив|ила|ила ж|или)|сплат(ив|ила)|перекину[вл]|перерахув|квитанц|чек надісл", re.I)



def _money(v):
    v = float(v or 0)
    return ("%.0f" % v) if abs(v - round(v)) < 0.01 else ("%.2f" % v)


def _send(conv, text):
    """Повідомлення клієнту від імені ІІ (позначене в переписці)."""
    from .models import Message
    from .services import send_message
    msg = send_message(conv, text)
    Message.objects.filter(id=msg.id).update(sender_name="%s · %s" % (NOTE_PREFIX, conv.channel.name))
    return msg


PAGE_RX = re.compile(r"https://wallcov\.com\.ua/p/([a-z0-9-]+)/")


def _maybe_effect_photos(conv, text):
    """18.09.2026 (Олег): «коли запит на Патеру — відправляй фото ефектів, а не просто слова».
    Якщо ІІ дав посилання на сторінку матеріалу — одразу показуємо фото кожного ефекту з бібліотеки."""
    from .models import Message
    from .showcase import effect_photos, file_url, material_by_slug
    m = PAGE_RX.search(text or "")
    if not m:
        return
    slug = m.group(1)
    mat = material_by_slug(slug)
    if not mat:
        return
    mark = "фото ефектів %s" % slug
    if Message.objects.filter(conversation=conv, internal=True, text__contains=mark).exists():
        return                                    # у цьому діалозі вже показували
    rows = effect_photos(mat["name"], limit=3)
    if len(rows) < 2:
        return
    lines = ["Ось як %s виглядає в різних ефектах 👇" % mat["name"]]
    atts = []
    for eff, it in rows:
        url = file_url(it)
        if not url:
            continue
        lines.append("📷 %s\n%s" % (eff, url))
        atts.append({"type": "image", "url": url, "name": eff, "library_asset_id": it.id,
                     "color_code": it.color_code})
    if not atts:
        return
    try:
        msg = _send(conv, "\n\n".join(lines))
        Message.objects.filter(id=msg.id).update(attachments=atts)
        _note(conv, "%s: надіслав %s (%s)." % (NOTE_PREFIX, mark, ", ".join(a["name"] for a in atts)))
    except Exception as e:
        _note(conv, "%s: не вдалося надіслати фото ефектів (%s)." % (NOTE_PREFIX, str(e)[:150]))


def _requisites_text():
    """Затверджений запис бази знань з реквізитами ФОП (редагується в AI ЦЕНТРІ)."""
    from apps.knowledge.models import KnowledgeItem
    it = (KnowledgeItem.objects.filter(status="approved", title__istartswith=REQ_TITLE)
          .order_by("-updated_at").first())
    return (it.text or "").strip() if it else ""


def _maybe_requisites(conv, incoming):
    """Клієнт просить рахунок/реквізити — надсилаємо їх самі, а не передаємо менеджеру."""
    from .services import send_message
    from .models import Message
    text_in = (incoming.text or "")
    if not REQ_ASK.search(text_in) or REQ_PAID.search(text_in):
        return False
    deal, amount = None, None
    if conv.contact_id:
        from apps.crm.models import Deal
        deal = (Deal.objects.filter(contact_id=conv.contact_id, stage__is_won=False, stage__is_lost=False)
                .filter(items__isnull=False).order_by("-created_at").first())
    if deal is not None:
        # штатна механіка CRM (та сама, що кнопка менеджера «Прийняти оплату → За реквізитами»):
        # текст + IBAN + призначення окремо, стадія «Домовились про оплату», оплата підтягнеться з банку
        from apps.crm.views import send_requisites
        r = send_requisites(deal, conv=conv, sender_name="%s · %s" % (NOTE_PREFIX, conv.channel.name))
        if r.get("ok"):
            _note(conv, "%s: клієнт попросив реквізити — надіслав рахунок ФОП по сделці #%s на %s ₴ "
                        "(оплата підтягнеться з банку за призначенням платежу)."
                  % (NOTE_PREFIX, deal.id, _money(r.get("amount"))))
        else:
            _note(conv, "%s: клієнт просить реквізити (сделка #%s), надіслати не вдалося — зробіть вручну."
                  % (NOTE_PREFIX, deal.id))
        return True
    body = _requisites_text()
    if not body:
        return False
    if deal is not None:
        paid = sum(float(p.amount) for p in deal.payments.all() if p.is_paid)
        left = float(deal.amount or 0) - paid
        if left > 0:
            amount = ("%.0f" % left) if abs(left - round(left)) < 0.01 else ("%.2f" % left)
    lines = []
    for ln in body.splitlines():
        if "{номер}" in ln or "{сума}" in ln:
            if deal is None or ("{сума}" in ln and amount is None):
                continue
            ln = ln.replace("{номер}", str(deal.id)).replace("{сума}", amount or "")
        lines.append(ln)
    text = "\n".join(lines).strip()
    try:
        msg = send_message(conv, text)
        Message.objects.filter(id=msg.id).update(sender_name="%s · %s" % (NOTE_PREFIX, conv.channel.name))
    except Exception as e:
        _note(conv, "%s: не вдалося надіслати реквізити (%s)." % (NOTE_PREFIX, str(e)[:200]))
        return True
    _note(conv, "%s: клієнт попросив реквізити — надіслав рахунок ФОП%s."
          % (NOTE_PREFIX, (" по сделці #%s" % deal.id) if deal else ""))
    return True


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
        if _maybe_requisites(conv, incoming):
            return
    except Exception as e:
        _note(conv, "%s: реквізити не надіслані (%s)." % (NOTE_PREFIX, str(e)[:200]))
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
    _maybe_effect_photos(conv, text)
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
        same = recent.items.filter(product_id=prod.id).exists()
        if paid <= 0 and same:
            # 18.09.2026 (Олег): другої сделки не створюємо, але клієнту надсилаємо ТЕ САМЕ посилання ще раз —
            # «якщо це продовження діалогу і вибір збігається, ІІ може просто продублювати».
            pl = PayLink.objects.filter(deal=recent).order_by("-id").first()
            if pl is None:
                _note(conv, "%s: сделка #%s вже є, але посилання на оплату немає — надішліть вручну."
                      % (NOTE_PREFIX, recent.id))
                return
            url = "https://crm.wallcovdec.com.ua/p/%s/" % pl.code
            try:
                _send(conv, "%s — %s грн\n💳 Оплатити онлайн 👉 %s" % (prod.name, _money(recent.amount), url))
                _note(conv, "%s: замовлення вже оформлене (сделка #%s) — надіслав те саме посилання %s"
                      % (NOTE_PREFIX, recent.id, url))
            except Exception as e:
                _note(conv, "%s: замовлення вже оформлене (сделка #%s), посилання %s — надіслати не вдалося (%s)."
                      % (NOTE_PREFIX, recent.id, url, str(e)[:150]))
            return
        if paid <= 0 and not same:
            _note(conv, "%s: у клієнта вже є неоплачена сделка #%s на %s ₴, а тепер просить «%s» — оформлюю окремо."
                  % (NOTE_PREFIX, recent.id, recent.amount, prod.name[:50]))
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
