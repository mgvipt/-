"""ШІ відповідає клієнту в каналах CRM — Viber, Telegram, WhatsApp, Facebook (17.09.2026, Олег:
«а в вайбері й телеграмі теж агент буде відповідати? і в ватсапі»).

ЗА ЗАМОВЧУВАННЯМ ВИМКНЕНО для всіх каналів. Вмикається по одному каналу:
    Channel.config["ai_reply"] = True                       — відповідати всім у цьому каналі
    Channel.config["ai_reply_only_chats"] = ["<chat_id>"]   — спочатку лише цим чатам (перевірка на своєму акаунті)
    Channel.config["ai_reply_after_handoff"] = True         — канал веде Юля ChatPlace, продавець CRM
                                                              підхоплює на оформленні (Instagram, 21.09.2026)

Мозок — той самий, що у веб-чата сайту: ЗАТВЕРДЖЕНІ записи бази знань CRM (apps.knowledge.answer,
агент «yulia_web»), ціни з каталогу, посилання на сторінки кольорів. Замовлення, оплата, сумнів →
«передала менеджеру» + внутрішня нотатка, клієнту нічого не вигадуємо.

Запобіжники (щоб ШІ не заважав людям і не спамив):
  • менеджер у діалозі (призначений або писав останні 12 год) — ШІ мовчить;
  • не більше 1 відповіді на 20 секунд і 15 на добу в одному чаті;
  • тільки вхідні від клієнта у відкритому діалозі, не коментарі Meta, не внутрішні нотатки;
  • відповідь іде окремим потоком: вебхук каналу не чекає ШІ і не відпадає по таймауту;
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
NOTE_PREFIX = "ШІ у каналі"
# 22.09.2026: до перейменування ІІ→ШІ позначка була інша — старі повідомлення теж рахуємо (ліміт на добу, рецензент)
NOTE_PREFIXES = (NOTE_PREFIX, "\u0406\u0406 у каналі")


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


# ── 21.09.2026 (Олег): КОМАНДА «Юля ChatPlace → продавець CRM» ─────────────────
# «у нас була механіка, яка працювала як команда: далі вела діалог від Юлі ChatPlace
# до ШІ-продавця з CRM. Коли відповість ШІ-агент із CRM — у цьому чаті Юля з ChatPlace
# на паузі 10 годин, ніби менеджер включився. А якщо включається менеджер — тоді вже
# і в CRM у цьому чаті зупиняється ШІ-агент».
#
# Як це працює:
#   • Instagram веде Юля з ChatPlace — вона консультує (ефекти, ціни, підбір).
#   • Дійшло до оформлення (вона сказала «передала менеджеру» / «оформлюю замовлення»
#     АБО клієнт сам написав «беру / куди оплатити / реквізити») — чат підхоплює
#     продавець CRM: він уміє створити сделку, надіслати посилання на оплату і реквізити.
#   • Перша ж його відповідь іде через ChatPlace як повідомлення оператора (chats_open),
#     тому ChatPlace ставить свою Юлю на паузу (silenceAfterHumanReply = 600 хв = 10 год).
#   • Далі продавець CRM веде цей чат 10 годин (вікно продовжується з кожною відповіддю).
#   • Написав живий менеджер — продавець CRM замовкає (_manager_active, старе правило).
TAKEOVER_HOURS = 10

# фрази Юлі з ChatPlace, після яких продовжувати має продавець CRM
# 22.09.2026: + російською і з кількома словами між («Передала Ваш запрос менеджеру», «менеджеры свяжутся»)
HANDOFF_RX = re.compile(
    r"передал\w*\s+(?:\S+\s+){0,4}менеджер|переда[юм]\w*\s+(?:\S+\s+){0,3}менеджер|передати\s+менеджер|"
    r"менеджер\w*\s+(?:\S+\s+){0,2}(надішл|пришл|отправ|підтверд|подтверд|зв|свяж|подключ|підключ|оформ|"
    r"підготу|подготов)|зв.?яж[уе]\s+(вас\s+)?з\s+менеджер|свяж\w*\s+(вас\s+)?с\s+менеджер|"
    r"оформлюю\s+(ваше\s+)?замовлення|оформля\w*\s+(ваш\s+)?заказ", re.I)
# клієнт сам показав готовність купити
BUY_RX = re.compile(
    r"\bберу\b|беремо|оформ(ляйте|люйте|ляємо|ити|ляти)|готов[аий]*\s+(купити|оплатити|замовити)|"
    r"куди\s+(оплат|перекаж|скинути|платити)|як\s+оплатити|как\s+оплатить|реквізит|реквизит|"
    r"рахунок\s+на\s+оплат|остаточно|окончательно|давайте\s+оформ|хочу\s+(замовити|купити|оплатити)|"
    # 22.09.2026: російською і «одразу на обʼєм» («На 10 м давайте сразу»)
    r"оформите|оформляйте|хочу\s+(заказать|купить)|куда\s+(оплат|перевест|платить)|готов\w*\s+(купить|оплатить|заказать)|"
    r"давайте\s+(сразу|одразу|відразу|на\s+\d)|\d+\s*(м2|м²|м|кв\w*)\s+давайте", re.I)


def _takeover_channel(channel):
    """Канал, де першим відповідає ChatPlace, а продавець CRM підхоплює на оформленні."""
    return bool(((channel.config or {}) if channel else {}).get("ai_reply_after_handoff"))


def _takeover_until(conv):
    raw = (conv.config or {}).get("ai_takeover_until") or ""
    if not raw:
        return None
    try:
        from django.utils.dateparse import parse_datetime
        return parse_datetime(raw)
    except Exception:
        return None


def hold_chat(conv, hours=TAKEOVER_HOURS):
    """Продавець CRM бере чат на себе на N годин (вікно продовжується з кожною відповіддю)."""
    cfg = dict(conv.config or {})
    cfg["ai_takeover_until"] = (timezone.now() + timedelta(hours=hours)).isoformat()
    conv.config = cfg
    conv.save(update_fields=["config"])


def _took_over(conv, incoming):
    """Чи вже час продавцю CRM вести цей чат (і фіксуємо момент передачі)."""
    until = _takeover_until(conv)
    if until and until > timezone.now():
        return True
    from .models import Message
    last_out = (Message.objects.filter(conversation=conv, direction="out", internal=False)
                .order_by("-id").first())
    why = ""
    if last_out and HANDOFF_RX.search(last_out.text or ""):
        why = "Юля ChatPlace передала на оформлення"
    elif BUY_RX.search(incoming.text or ""):
        why = "клієнт готовий оформлювати"
    if not why:
        return False
    hold_chat(conv)
    _note(conv, "%s: беру чат на себе на %d год — %s. Юля ChatPlace у цьому чаті на паузі."
           % (NOTE_PREFIX, TAKEOVER_HOURS, why))
    return True


def _allowed_chat(channel, conv):
    only = ((channel.config or {}).get("ai_reply_only_chats") or [])
    if not only:
        return True
    return str(conv.external_chat_id) in {str(x) for x in only}


def _manager_active(conv, hours):
    """Менеджер веде цей чат: САМ ПИСАВ клієнту за останні N годин (N — з AI ЦЕНТРУ).
    18.09.2026 (Олег): «якщо менеджер написав клієнту — агент у цьому чаті не пише». Саме написав:
    закріплений за чатом менеджер, який ще нічого не відповів, ШІ не блокує."""
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
    from django.db.models import Q
    by_ai = Q()
    for pref in NOTE_PREFIXES:
        by_ai |= Q(sender_name__startswith=pref)
    day = Message.objects.filter(by_ai, conversation=conv, direction="out", internal=False,
                                 created_at__gte=timezone.now() - timedelta(days=1)).count()
    return day >= max_per_day


def should_reply(conv, incoming):
    """Чи має ШІ відповісти на це повідомлення (лише читання, без мережі)."""
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
        return False          # живий менеджер у чаті — ШІ мовчить (і в CRM, і далі)
    if _takeover_channel(ch) and not _took_over(conv, incoming):
        return False          # діалог поки веде Юля з ChatPlace — не заважаємо
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
    """Повідомлення клієнту від імені ШІ (позначене в переписці)."""
    from .models import Message
    from .services import send_message
    msg = send_message(conv, text)
    Message.objects.filter(id=msg.id).update(sender_name="%s · %s" % (NOTE_PREFIX, conv.channel.name))
    return msg


PAGE_RX = re.compile(r"https://wallcov\.com\.ua/p/([a-z0-9-]+)/")


def _maybe_effect_photos(conv, text):
    """18.09.2026 (Олег): «коли запит на Патеру — відправляй фото ефектів, а не просто слова».
    Якщо ШІ дав посилання на сторінку матеріалу — одразу показуємо фото кожного ефекту з бібліотеки."""
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
    # 23.09.2026: на запит про Галатею — фото Галатеї, про Елеганті — Елеганті (обидва «піщинки»)
    low = (text or "").lower()
    prefer = ("Galateya" if ("галате" in low or "galate" in low) else
              "Eleganti" if ("елеганті" in low or "eleganti" in low or "элеганти" in low) else "")
    rows = effect_photos(mat["name"], limit=3, prefer=prefer)
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
            if _takeover_channel(conv.channel):
                hold_chat(conv)
            return
    except Exception as e:
        _note(conv, "%s: реквізити не надіслані (%s)." % (NOTE_PREFIX, str(e)[:200]))
    try:
        cfg = KnowledgeSettings.get()
        from .ad_context import ad_info, ad_prompt, ad_topic
        ad_ctx = ad_prompt(conv)   # 22.09.2026: продавець знає, з якої реклами клієнт
        ad_q = ad_topic(ad_info(conv).get("ad_title")) if ad_ctx else ""
        msgs = history(conv, incoming)
        calc = _volume_calc(msgs, ad_q)   # 22.09.2026: обʼєм рахує CRM з карток каталогу
        from apps.knowledge.volume_calc import language_hint, prompt_block
        first = not Message.objects.filter(conversation=conv, direction="out", internal=False).exists()
        # 23.09.2026 (Олег): «просто, без зайвого пафосу» — тільки імʼя, без посади й компанії;
        # у першому повідомленні одразу орієнтир ціни, презентація йде другим повідомленням.
        hello = ("ПЕРШИЙ КОНТАКТ у цьому чаті: почни просто — «Вітаю! Мене звати Юля 😊» (без посади і назви "
                 "компанії), далі коротко по суті запиту і ОРІЄНТИР ЦІНИ (ціна тест-набору або за 1 м², "
                 "залежно від питання) + одне відкрите питання. Фото матеріалу і сторінку кольорів CRM "
                 "надішле окремим повідомленням — не дублюй їх у своєму тексті. Далі в діалозі не вітайся.")
        ctx = "\n\n".join(x for x in (ad_ctx, prompt_block(calc), language_hint(incoming.text),
                                      hello if first else "") if x)
        r = answer("yulia_web", msgs, include_drafts=False, model=cfg.webchat_model or None,
                   source="%s: %s" % (NOTE_PREFIX, conv.channel.name), timeout=25,
                   context=ctx, context_query=ad_q)
        text = (r.get("text") or "").strip() or HANDOFF_TEXT
        used = ", ".join("#%d" % u["id"] for u in r.get("used_items") or []) or "—"
        note = ("%s передав менеджеру: %s. Записи: %s." % (NOTE_PREFIX, r.get("handoff_reason") or "—", used)
                if r.get("handoff") else
                "%s відповів з бази знань. Записи: %s. ≈ $%s" % (NOTE_PREFIX, used, (r.get("cost") or {}).get("usd", 0)))
    except Exception as e:
        _note(conv, "%s: не зміг відповісти (%s). Клієнту нічого не надіслано — дайте відповідь вручну."
              % (NOTE_PREFIX, str(e)[:200]))
        return
    # 23.09.2026 (Олег): «якщо мова про вибір кольору — спершу кілька фото, як це виглядає в інтерʼєрі,
    # і вже потім посилання на каталог матеріалу» — щоб у клієнта одразу була презентація.
    _maybe_effect_photos(conv, text)
    try:
        msg = send_message(conv, text)
        Message.objects.filter(id=msg.id).update(sender_name="%s · %s" % (NOTE_PREFIX, conv.channel.name))
    except Exception as e:
        _note(conv, "%s: не вдалося надіслати (%s). Текст: «%s»" % (NOTE_PREFIX, str(e)[:200], text[:600]))
        return
    _note(conv, note)
    if first:
        _first_presentation(conv, msgs, ad_q, text)
    if _takeover_channel(conv.channel):
        hold_chat(conv)       # чат лишається за продавцем CRM ще 10 год
    if r.get("order") and r["order"].get("volume"):
        from apps.knowledge.volume_calc import shown_to_client
        if shown_to_client(msgs, calc):
            _make_volume_offer(conv, calc, r["order"])
        # інакше клієнт суми ще не бачив — лише показали розрахунок, оформлюємо після його «так»
    elif r.get("order"):
        _make_kit_offer(conv, r["order"])


def _first_presentation(conv, msgs, ad_topic_name="", sent_text=""):
    """23.09.2026 (Олег): у вітальному повідомленні — орієнтир ціни, а ДРУГИМ повідомленням одразу презентація:
    фото матеріалу в інтерʼєрі + сторінка кольорів. Матеріал беремо з розмови або з реклами, з якої прийшов клієнт."""
    try:
        from apps.knowledge.volume_calc import COLORS, COLORS_BY_ID, find_material
        if PAGE_RX.search(sent_text or ""):
            return                       # агент уже дав сторінку — другого повідомлення не треба
        mat = find_material([m["text"] for m in msgs], ad_topic_name)
        if not mat:
            return
        url = COLORS_BY_ID.get(mat[0], COLORS.get(mat[1], ""))
        if not url:
            return
        text = "Покажу, як це виглядає в інтерʼєрі 👇\n\nТут уся палітра, фото і відео: %s\n\nНапишіть код кольору, який сподобався 🎨" % url
        _maybe_effect_photos(conv, text)     # спершу фото
        _send(conv, text)                    # потім посилання
        _note(conv, "%s: перший контакт — надіслав презентацію (%s)." % (NOTE_PREFIX, url))
    except Exception as e:
        _note(conv, "%s: презентацію не надіслав (%s)." % (NOTE_PREFIX, str(e)[:150]))


def _volume_calc(msgs, extra=""):
    try:
        from apps.knowledge.volume_calc import for_dialog
        return for_dialog(msgs, extra)
    except Exception:
        return None


def _make_volume_offer(conv, calc, order):
    """22.09.2026 (Олег): «ШІ сам рахує всі обʼєми — вчимо його працювати автономно».
    Сделка «21 Основний продукт» з позиціями РОЗРАХУНКУ CRM (площа × витрата з картки). Прорахунок клієнту
    надсилає make_offer. Тонування обʼєму в каталозі ціни не має → з тонуванням посилання на оплату НЕ шлемо,
    менеджер додає тонування і надсилає посилання; без тонування — посилання LiqPay одразу."""
    from apps.crm.models import Deal, Funnel
    from apps.crm.views import make_offer
    if not calc or not calc.get("ok"):
        _note(conv, "%s: клієнт погодився на обʼєм, але розрахунку немає (площа чи матеріал невідомі) — оформіть вручну."
              % NOTE_PREFIX)
        return
    if not conv.contact_id:
        _note(conv, "%s: немає картки клієнта — оформіть обʼєм вручну." % NOTE_PREFIX)
        return
    mat_id = calc["material"]["product_id"]
    dup = (Deal.objects.filter(contact_id=conv.contact_id, stage__is_won=False, stage__is_lost=False,
                               created_at__gte=timezone.now() - timedelta(hours=24), items__product_id=mat_id)
           .order_by("-id").first())
    if dup is not None:
        _note(conv, "%s: обʼєм уже оформлено в сделці #%s — другу не створюю, перевірте." % (NOTE_PREFIX, dup.id))
        return
    deal = (Deal.objects.filter(contact_id=conv.contact_id, stage__is_won=False, stage__is_lost=False)
            .order_by("-created_at").first())
    if deal is None or deal.items.exists():
        f = Funnel.objects.filter(name__istartswith="21 Основний").first()
        st = f.stages.order_by("order").first() if f else None
        if not (f and st):
            _note(conv, "%s: немає воронки «21 Основний продукт» — оформіть обʼєм вручну." % NOTE_PREFIX)
            return
        deal = Deal.objects.create(title="Обʼєм %s м² · %s" % (_money(calc["area"]), str(conv.contact)[:40]),
                                   funnel=f, stage=st, contact_id=conv.contact_id, owner=conv.assigned_to)
    tint = order.get("tint", True)
    from apps.knowledge.volume_calc import TINT_PRODUCT
    items = [{"name": l["name"], "qty": l["qty"]} for l in calc["lines"]]
    t = calc.get("tint") if tint else None
    if t and t.get("need_color"):
        # 22.09.2026: колорант рахується за кодом кольору — без коду суму не вигадуємо
        _note(conv, "%s: клієнт хоче тонування, але коду кольору ще немає — сделку роблю без тонування, "
              "посилання на оплату НЕ надсилаю." % NOTE_PREFIX)
        t = None
    try:
        res = make_offer(deal, items, send_pay=bool(t) or not tint)
    except Exception as e:
        _note(conv, "%s: не вдалося оформити обʼєм (%s) — зробіть вручну." % (NOTE_PREFIX, str(e)[:200]))
        return
    if not res.get("ok"):
        _note(conv, "%s: сделка #%s — прорахунок обʼєму не створено (%s), перевірте вручну."
              % (NOTE_PREFIX, deal.id, res.get("msg") or "—"))
        return
    miss = (" Без витрати в картці (не пораховано): %s." % "; ".join(calc["missing"])[:300]) if calc["missing"] else ""
    tnote = ""
    if t:   # тонування за регламентом: послуга + тонер (обʼєм тонера орієнтовний — до підбору кольору)
        try:
            from apps.crm.models import DealItem
            from apps.warehouse.models import Product
            p = Product.objects.filter(id=TINT_PRODUCT).first()
            if p:
                DealItem.objects.create(deal=deal, product=p, quantity=1, price=t["total"], cost=0)
                deal.amount = sum((i.total for i in deal.items.all()), 0)
                deal.save(update_fields=["amount"])
                tnote = (" Тонування %s ₴ (колір %s: послуга %s + колорант %s мл)."
                         % (t["total"], calc.get("color") or "—", t["service"], t["ml"]))
        except Exception as e:
            tnote = " Тонування не додано (%s) — додайте вручну." % str(e)[:120]
    _note(conv, "%s: оформив обʼєм %s м² — сделка #%s на %s ₴, прорахунок і посилання на оплату %s надіслано.%s%s"
          % (NOTE_PREFIX, _money(calc["area"]), deal.id, res.get("amount"), res.get("url") or "—", tnote, miss))


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
            # «якщо це продовження діалогу і вибір збігається, ШІ може просто продублювати».
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
