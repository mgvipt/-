"""Відгуки покупців: кому і коли просити, журнал «кому б відправили», прийом відгуку з сайту, стрічка для магазину.

Рішення Олега 12.09.2026:
- старт — статус НП «Отримано»; основне замовлення — через 10 днів, тест-набір — через 5
  (тест-набір — лише якщо менеджер зараз не веде продаж по клієнту);
- канал: месенджер, де вже є діалог (e-chat WhatsApp / Viber / Telegram); Instagram / Facebook / TikTok —
  лише у 24-годинному вікні; інакше пишемо першими за телефоном через e-chat (WhatsApp → Viber → Telegram);
- одне нагадування через 5 днів; не більше 1 просьби на клієнта за 60 днів; «стоп» = відписка;
- ВІДПРАВКА ВИМКНЕНА (send_enabled=False): прогін лише веде журнал «відправили б».
- 13.09.2026: тексти В1 / Т1 / нагадування затверджені Олегом; тестовий режим (test_mode) — просьби (авто і кнопка
  «⭐ Попросити відгук») лише контактам зі списку; дата старту відсікає посилки, отримані раніше, навіть якщо
  просьба вже в журналі; відповідь клієнта на просьбу не запускає ІІ-агента (is_review_reply).
Клієнта визначаємо лише через угоду → її контакт (ніколи за іменем).
"""
import base64
import binascii
import os
import re
import secrets
import string
import uuid
from collections import Counter
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.crm.models import ActivityLog, Deal, Task, log_activity
from apps.inbox.models import Channel, Conversation, Message
from .models import Review, ReviewOptOut, ReviewPhoto, ReviewRequest, ReviewSettings
from .photos import process_photo

SHOP_URL = os.environ.get("SHOP_PUBLIC_URL") or "https://wallcov.com.ua"
CRM_URL = os.environ.get("CRM_PUBLIC_URL") or "https://crm.wallcovdec.com.ua"
CODE_CHARS = string.ascii_letters + string.digits
CODE_RE = re.compile(r"^[A-Za-z0-9]{12}$")
PHOTO_SALT = "wallcov-review-photo"
MESSENGER_KINDS = ("echat_whatsapp", "echat", "echat_telegram", "telegram", "viber", "whatsapp")
NEW_BY_PHONE = ("echat_whatsapp", "echat", "echat_telegram")
WINDOW_KINDS = ("instagram", "facebook", "tiktok")
CHANNEL_LABEL = {"echat_whatsapp": "WhatsApp", "echat": "Viber", "echat_telegram": "Telegram", "telegram": "Telegram-бот",
                 "viber": "Viber-бот", "whatsapp": "WhatsApp", "instagram": "Instagram", "facebook": "Facebook",
                 "tiktok": "TikTok"}
STOP_RE = re.compile(r"(^|[^\w])(стоп|stop|не\s*пиш|не\s*турбу|відпиш|отпиш|не\s*треба|не\s*надо)", re.IGNORECASE)
NOT_CLIENT_KINDS = {"staff", "supplier", "master", "partner"}
ACTIVE = ("sent", "reminded", "test")
ROOMS = {"living", "bedroom", "kitchen", "bathroom", "hallway", "kids", "commercial", "other", ""}
APPLIED = {"self", "master", "unknown"}
MAX_PHOTOS = 5
ANON_NAME = "Покупець Wallcov"
REVIEW_LINK_MARK = "/vidguk/"
NAME_KEYS = ("{імʼя}", "{ім'я}")
PREVIEW_CODE = "•" * 12


class ReviewError(Exception):
    def __init__(self, code, detail, status=400, field=None):
        super().__init__(detail)
        self.code, self.detail, self.status, self.field = code, detail, status, field

    def body(self):
        data = {"ok": False, "code": self.code, "detail": self.detail}
        if self.field:
            data["field"] = self.field
        return data


def new_code():
    while True:
        code = "".join(secrets.choice(CODE_CHARS) for _ in range(12))
        if not ReviewRequest.objects.filter(code=code).exists():
            return code


def review_link(code):
    return "%s/vidguk/%s" % (SHOP_URL.rstrip("/"), code)


def suggested_name(contact):
    if not contact:
        return ANON_NAME
    first = (contact.first_name or "").strip()
    last = (contact.last_name or "").strip()
    if not first:
        return ANON_NAME
    return ("%s %s." % (first, last[0].upper())) if last else first


def _label(kind):
    return CHANNEL_LABEL.get(kind, kind)


# ── коли посилку отримано і що купили ─────────────────────────────────────

def _is_received_stage(stage):
    name = (stage.name or "").lower()
    return "отримано" in name and "оплат" not in name


def received_at_for(deal):
    """Момент «Отримано»: з журналу переходів (НП-поллер пише «… → Отримано (НП: …)»)."""
    logged = (ActivityLog.objects.filter(kind="deal", object_id=deal.id, detail__contains="→ Отримано")
              .order_by("created_at").values_list("created_at", flat=True).first())
    if logged:
        return logged
    if deal.stage_id and _is_received_stage(deal.stage):
        return deal.stage_changed_at
    if deal.stage_id and deal.stage.is_won:
        return deal.closed_at or deal.stage_changed_at
    return None


def test_category_ids():
    from apps.warehouse.models import ProductCategory
    ids = set(ProductCategory.objects.filter(name__icontains="Тестові набори").values_list("id", flat=True))
    frontier = list(ids)
    while frontier:
        children = [c for c in ProductCategory.objects.filter(parent_id__in=frontier).values_list("id", flat=True) if c not in ids]
        ids.update(children)
        frontier = children
    return ids


def service_category_ids():
    """Інструменти, витратні матеріали й тара — не «матеріал» для тексту просьби (разом з підкатегоріями).
    Назви порівнюємо в Python: SQLite (тести) не шукає кирилицю без урахування регістру."""
    from apps.warehouse.models import ProductCategory
    rows = list(ProductCategory.objects.values_list("id", "name", "parent_id"))
    ids = {cid for cid, name, _ in rows
           if any(key in (name or "").lower() for key in ("інструмент", "инструмент", "витратн"))
           or (name or "").strip().lower() == "тара"}
    grown = True
    while grown:
        grown = False
        for cid, _, parent in rows:
            if parent in ids and cid not in ids:
                ids.add(cid)
                grown = True
    return ids


def short_material(name):
    """Коротка назва для тексту: «Galateya Silver (Lui 0188). декоративна…» → «Galateya Silver»,
    «Sirena Silk — тестовий набір "Мокрий шовк"…» → «Sirena Silk»."""
    full = re.sub(r"\s+", " ", name or "").strip()
    short = re.split(r"\s[—–-]\s|[(\"«.,]", full, maxsplit=1)[0].strip()
    return (short or full)[:40]


def material_name(req):
    """{матеріал}: найбільша сума серед матеріалів угоди (без інструментів і тари), коротка назва."""
    if not req.deal_id:
        return ""
    service = service_category_ids()
    best = None
    for item in req.deal.items.select_related("product"):
        if not item.product_id or item.product.category_id in service:
            continue
        total = item.quantity * item.price
        if best is None or total > best[0]:
            best = (total, item.product.name)
    return short_material(best[1]) if best else ""


def classify(deal, cfg, test_cats):
    if deal.funnel_id in (cfg.test_funnel_ids or []):
        return "test"
    items = list(deal.items.select_related("product"))
    if items and all(i.product_id and i.product.category_id in test_cats for i in items):
        return "test"
    return "main"


def products_for(req):
    """Товари угоди для форми: лише позиції з номенклатури, головна — найбільша сума серед матеріалів
    (інструменти й тара — в кінці списку і головними стають, лише коли матеріалів немає)."""
    if not req.deal_id:
        return []
    service = service_category_ids()
    rows = []
    for item in req.deal.items.select_related("product").order_by("id"):
        if not item.product_id:
            continue
        rows.append((item.product.category_id in service, -(item.quantity * item.price), item.product))
    seen, out = set(), []
    for _service, _neg_total, product in sorted(rows, key=lambda r: (r[0], r[1])):
        if product.id in seen:
            continue
        seen.add(product.id)
        out.append({"crm_product_id": product.id, "name": product.name, "shop_slug": product.shop_slug or None,
                    "is_primary": not out})
    return out


# ── канал ─────────────────────────────────────────────────────────────────

def choose_channel(contact, now):
    """Куди писати: діалог у месенджері → Instagram/Facebook/TikTok у вікні 24 год → новий e-chat за телефоном."""
    convs = list(Conversation.objects.filter(contact_id=contact.id, channel__is_active=True).select_related("channel")
                 .exclude(channel__kind="web").exclude(external_chat_id__startswith="comment:"))
    last_in = {c.id: c.messages.filter(direction="in").order_by("-created_at").values_list("created_at", flat=True).first()
               for c in convs}
    dialogs = [c for c in convs if c.channel.kind in MESSENGER_KINDS and last_in[c.id]]
    if dialogs:
        conv = max(dialogs, key=lambda c: last_in[c.id])
        return {"kind": "dialog", "conversation": conv, "channel": conv.channel,
                "label": "%s — діалог уже є" % _label(conv.channel.kind)}
    window = [c for c in convs if c.channel.kind in WINDOW_KINDS and last_in[c.id]
              and now - last_in[c.id] < timedelta(hours=23)]
    if window:
        conv = max(window, key=lambda c: last_in[c.id])
        return {"kind": "window", "conversation": conv, "channel": conv.channel,
                "label": "%s — клієнт писав менше 24 год тому" % _label(conv.channel.kind)}
    if len(re.sub(r"\D", "", contact.phone or "")) >= 10:
        for kind in NEW_BY_PHONE:
            channel = Channel.objects.filter(kind=kind, is_active=True).order_by("id").first()
            if channel:
                return {"kind": "new", "conversation": None, "channel": channel,
                        "label": "%s — новий діалог за номером" % _label(kind)}
    if any(c.channel.kind in WINDOW_KINDS for c in convs):
        return {"kind": "wait_window", "conversation": None, "channel": None,
                "label": "лише Instagram/Facebook/TikTok, вікно 24 год закрите — чекаємо, поки клієнт напише"}
    return {"kind": "none", "conversation": None, "channel": None,
            "label": "немає каналу: ні діалогу в месенджері, ні телефону"}


# ── прогін: знайти, перевірити, записати в журнал (або надіслати, коли дозволять) ──

def texts_ready(cfg):
    """Тексти затверджені і в кожному є {посилання}."""
    texts = (cfg.text_main, cfg.text_test, cfg.text_remind)
    return bool(cfg.texts_approved and all("{посилання}" in (t or "") for t in texts))


def live_allowed(cfg):
    return bool(cfg.send_enabled and texts_ready(cfg))


def contact_allowed(cfg, contact_id):
    """Тестовий режим (за замовчуванням увімкнений): лише контакти зі списку; порожній список — нікому.
    Поза тестовим режимом — усім (решта правил лишаються)."""
    if cfg.test_mode:
        return contact_id in (cfg.allowlist_contact_ids or [])
    return True


def is_review_reply(contact_id, now=None, days=60):
    """Клієнт відповідає на нашу просьбу про відгук: останнє НАШЕ (не службове) повідомлення в чатах клієнта
    за `days` днів — з посиланням на відгук. Тоді ІІ-агент не чіпає ліди й угоди клієнта: «дякую» на просьбу —
    не продаж і не привід відкривати чи рухати угоду. Щойно менеджер напише щось інше — агент працює як завжди."""
    if not contact_id:
        return False
    now = now or timezone.now()
    last_out = (Message.objects.filter(conversation__contact_id=contact_id, direction="out", internal=False,
                                       created_at__gte=now - timedelta(days=days))
                .order_by("-created_at", "-id").values_list("text", flat=True).first())
    return bool(last_out and REVIEW_LINK_MARK in last_out)


def discover(cfg, now, stats):
    test_cats = test_category_ids()
    qs = (Deal.objects.exclude(ttn="").filter(contact__isnull=False, stage__is_lost=False)
          .filter(Q(stage__is_won=True) | (Q(stage__name__icontains="отримано") & ~Q(stage__name__icontains="оплат")))
          .exclude(funnel_id__in=cfg.excluded_funnel_ids or []).exclude(funnel__is_archive=True)
          .exclude(review_requests__kind__in=("main", "test"))
          .select_related("stage", "funnel", "contact").order_by("id"))
    if cfg.start_date:
        qs = qs.filter(Q(stage_changed_at__date__gte=cfg.start_date) | Q(closed_at__date__gte=cfg.start_date))
    for deal in qs[:500]:
        received = received_at_for(deal)
        kind = classify(deal, cfg, test_cats)
        delay = cfg.delay_test_days if kind == "test" else cfg.delay_main_days
        req = ReviewRequest(deal=deal, contact=deal.contact, kind=kind, code=new_code(), received_at=received)
        if not received or (cfg.start_date and timezone.localtime(received).date() < cfg.start_date):
            req.status, req.reason = "skipped", "посилку отримано до старту відгуків (%s)" % cfg.start_date
        else:
            req.due_at = received + timedelta(days=delay)
            req.expires_at = req.due_at + timedelta(days=cfg.expire_days)
            req.status, req.reason = "scheduled", "чекаємо %s днів після «Отримано»" % delay
        try:
            with transaction.atomic():
                req.save()
        except IntegrityError:
            continue  # паралельний прогін уже створив просьбу для цієї угоди
        stats["new_" + req.status] += 1


def evaluate(req, cfg, now, live=False):
    """→ (status, reason, plan). status: ok / waiting / skipped / cancelled / opted_out.
    live=False (журнал): «відправили б» теж рахуємо як просьбу — імітуємо правило 60 днів."""
    deal = Deal.objects.select_related("stage", "funnel", "owner").filter(pk=req.deal_id).first() if req.deal_id else None
    contact = req.contact
    if not deal or not contact:
        return "cancelled", "угоду або клієнта видалено", None
    if req.kind in ("main", "test") and cfg.start_date and (
            not req.received_at or timezone.localtime(req.received_at).date() < cfg.start_date):
        # дата старту: старі посилки не просимо, навіть якщо просьба вже стоїть у журналі (13.09)
        return "skipped", "посилку отримано до дати старту відгуків (%s)" % cfg.start_date.strftime("%d.%m.%Y"), None
    stage_name = (deal.stage.name or "").lower()
    if deal.stage.is_lost or "поверн" in stage_name or "скасов" in stage_name:
        return "cancelled", "угоду скасовано або повернено", None
    if ReviewOptOut.objects.filter(contact_id=contact.id).exists():
        return "opted_out", "клієнт відмовився від просьб про відгук", None
    bad = NOT_CLIENT_KINDS & set(contact.kinds or [])
    if bad:
        return "skipped", "не покупець (%s)" % ", ".join(sorted(bad)), None
    since = now - timedelta(days=cfg.repeat_block_days)
    asked = Q(status__in=("sent", "reminded", "submitted"), sent_at__gte=since)
    if not live:
        asked |= Q(status="would_send", journal_at__gte=since)
    other = (ReviewRequest.objects.filter(contact_id=contact.id).exclude(pk=req.pk)
             .filter(asked).order_by("-id").first())
    if other:
        return "skipped", "клієнта вже просили за останні %s днів (угода #%s)" % (cfg.repeat_block_days, other.deal_id), None
    if req.kind == "test":
        not_main = list(cfg.test_funnel_ids or []) + list(cfg.excluded_funnel_ids or [])
        if contact.deals.exclude(pk=deal.pk).exclude(funnel_id__in=not_main).filter(created_at__gt=deal.created_at).exists():
            return "skipped", "після тест-набору вже є основне замовлення — спитаємо про нього", None
        open_sale = (contact.deals.exclude(pk=deal.pk).filter(stage__is_won=False, stage__is_lost=False)
                     .exclude(funnel_id__in=cfg.excluded_funnel_ids or []).exists())
        manager_wrote = Message.objects.filter(conversation__contact_id=contact.id, direction="out", internal=False,
                                               sender__isnull=False,
                                               created_at__gte=now - timedelta(hours=cfg.manager_quiet_hours)).exists()
        if open_sale or manager_wrote:
            return "waiting", "менеджер зараз веде продаж по клієнту — не заважаємо", None
    plan = choose_channel(contact, now)
    if plan["kind"] in ("wait_window", "none"):
        return "waiting", plan["label"], plan
    conv = plan.get("conversation")
    if conv is not None:
        last = conv.messages.filter(internal=False).order_by("-created_at", "-id").first()
        if last and last.direction == "in" and now - last.created_at < timedelta(days=3):
            return "waiting", "клієнт чекає відповіді менеджера — не перебиваємо", plan
    return "ok", plan["label"], plan


def _set_plan(req, plan):
    req.channel_plan = plan["kind"]
    req.channel_label = plan["label"][:120]
    req.channel = plan.get("channel")
    req.conversation = plan.get("conversation")


def _drop_name(text):
    """Імені немає: «Доброго дня, {імʼя}!» → «Доброго дня!», «{імʼя}, нагадаю» → «Нагадаю»."""
    for key in NAME_KEYS:
        mark = re.escape(key)
        text = re.sub(r",\s*" + mark, "", text)
        text = re.sub(r"(^|\n)[ \t]*" + mark + r"[ \t]*,?[ \t]*(\w)", lambda m: m.group(1) + m.group(2).upper(), text)
        text = text.replace(key, "")
    return text


def render(template, req, kind=None):
    """Текст просьби. {менеджер} — ім'я відповідального за угоду (як у повідомленнях НП), інакше «команда Wallcov»;
    {матеріал} — коротка назва головного матеріалу (без інструментів); без імені клієнта речення без звертання."""
    contact, deal = req.contact, req.deal
    kind = kind or req.kind
    name = ((contact.first_name if contact else "") or "").strip()
    owner_name = ((deal.owner.first_name if deal and deal.owner_id else "") or "").strip()
    material = material_name(req) or ("" if kind == "test" else "покриття")
    text = template if name else _drop_name(template)
    if not owner_name:
        text = text.replace("{менеджер} з Wallcov", "команда Wallcov")  # не «команда Wallcov з Wallcov»
    manager = owner_name or "команда Wallcov"
    for key, value in ((NAME_KEYS[0], name), (NAME_KEYS[1], name), ("{менеджер}", manager), ("{матеріал}", material),
                       ("{посилання}", review_link(req.code))):
        text = text.replace(key, value)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def _conversation_for_new(req, channel):
    conv = (Conversation.objects.filter(contact_id=req.contact_id, channel=channel)
            .order_by("-last_message_at", "-id").first())
    if conv:
        return conv
    digits = re.sub(r"\D", "", req.contact.phone or "")
    if len(digits) == 10 and digits.startswith("0"):
        digits = "38" + digits
    owner_id = (req.deal.owner_id if req.deal_id else None) or req.contact.owner_id
    return Conversation.objects.create(channel=channel, contact=req.contact, external_chat_id=digits,
                                       title=str(req.contact), assigned_to_id=owner_id)


def _send_request(req, plan, cfg, now):
    from apps.inbox.services import send_message
    # Страховка від дублів (урок НП 01.09): стан — лише тут, і перевіряємо факт у чатах клієнта.
    if Message.objects.filter(conversation__contact_id=req.contact_id, direction="out", text__contains="/vidguk/",
                              created_at__gte=now - timedelta(days=cfg.repeat_block_days)).exists():
        req.status, req.reason = "skipped", "у чаті клієнта вже є посилання на відгук"
        return
    conv = plan.get("conversation") or _conversation_for_new(req, plan["channel"])
    template = cfg.text_test if req.kind == "test" else cfg.text_main
    msg = send_message(conv, render(template, req), user=None)
    req.message, req.conversation, req.channel = msg, conv, conv.channel
    req.status, req.sent_at = "sent", now
    req.expires_at = now + timedelta(days=cfg.expire_days)
    req.reason = "надіслано: %s" % plan["label"]
    log_activity("deal", req.deal_id, "Відгук: просьба надіслана", plan["label"], None, "Відгуки")


def _ask_manager_task(req, now):
    """Лише Instagram і вікно так і не відкрилось — просимо менеджера надіслати посилання, коли клієнт напише."""
    deal = req.deal
    owner = deal.owner if deal and deal.owner_id and deal.owner.is_active else None
    Task.objects.create(kind="manager", priority="normal", status="open", deal=deal, contact=req.contact,
                        title="Попросити відгук (угода #%s)" % req.deal_id, assignee=owner,
                        department=(owner.department if owner else None),
                        body="Клієнт пише лише в Instagram, вікно 24 год закрите. Коли клієнт напише — "
                             "надішліть посилання на відгук: %s" % review_link(req.code),
                        due_at=now + timedelta(days=14))
    req.status, req.sent_at = "sent", now
    req.expires_at = now + timedelta(days=60)
    req.reason = "посилання передано менеджеру задачею"


def _reminders(cfg, now, stats):
    from apps.inbox.services import send_message
    qs = (ReviewRequest.objects.filter(status="sent", reminded_at__isnull=True, is_test=False, message__isnull=False,
                                       sent_at__lte=now - timedelta(days=cfg.remind_after_days))
          .select_related("conversation__channel", "contact", "deal")[:cfg.per_run_cap])
    for req in qs:
        conv = req.conversation
        if not conv or ReviewOptOut.objects.filter(contact_id=req.contact_id).exists():
            continue
        if not contact_allowed(cfg, req.contact_id):
            continue  # тестовий режим: нагадуємо лише тестовим контактам
        if conv.channel.kind in WINDOW_KINDS:
            last_in = conv.messages.filter(direction="in").order_by("-created_at").values_list("created_at", flat=True).first()
            if not last_in or now - last_in > timedelta(hours=23):
                continue
        try:
            req.reminder_message = send_message(conv, render(cfg.text_remind, req), user=None)
            req.status, req.reminded_at = "reminded", now
            stats["reminded"] += 1
        except Exception as exc:  # noqa: BLE001 — лог у журнал, прогін триває
            req.attempts += 1
            req.last_error = str(exc)[:300]
        req.save()


def _stop_words(now, stats):
    for req in ReviewRequest.objects.filter(status__in=("sent", "reminded"), conversation__isnull=False, sent_at__isnull=False):
        texts = Message.objects.filter(conversation_id=req.conversation_id, direction="in",
                                       created_at__gte=req.sent_at).values_list("text", flat=True)
        if any(STOP_RE.search(t or "") for t in texts):
            ReviewOptOut.objects.get_or_create(contact_id=req.contact_id,
                                               defaults={"reason": "keyword", "note": "відповів на просьбу про відгук"})
            req.status, req.reason = "opted_out", "клієнт відповів «стоп» — більше не просимо"
            req.save(update_fields=["status", "reason", "updated_at"])
            stats["opted_out"] += 1


def run_sweep(now=None, force_dry=False):
    """Один прогін. Поки відправка вимкнена — лише журнал (статус «would_send»), жодних повідомлень і задач."""
    now = now or timezone.now()
    cfg = ReviewSettings.get()
    stats = Counter()
    live = live_allowed(cfg) and not force_dry
    discover(cfg, now, stats)
    local = timezone.localtime(now).time()
    in_hours = cfg.send_from <= local <= cfg.send_to
    sent = 0
    due = (ReviewRequest.objects.filter(status__in=("scheduled", "waiting"), due_at__lte=now, is_test=False)
           .select_related("contact", "deal").order_by("due_at")[:300])
    for req in due:
        status, reason, plan = evaluate(req, cfg, now, live=live)
        req.checked_at = now
        if status == "ok":
            _set_plan(req, plan)
            allowlisted = contact_allowed(cfg, req.contact_id)
            if live and allowlisted and in_hours and sent < cfg.per_run_cap:
                try:
                    _send_request(req, plan, cfg, now)
                    if req.status == "sent":
                        sent += 1
                        stats["sent"] += 1
                    else:
                        stats[req.status] += 1
                except Exception as exc:  # noqa: BLE001
                    req.attempts += 1
                    req.last_error = str(exc)[:300]
                    req.status, req.reason = "waiting", "помилка відправки — повторимо"
                    stats["errors"] += 1
            elif live and allowlisted:
                req.status = "waiting"
                req.reason = "надішлемо в години розсилки (%s–%s)" % (cfg.send_from.strftime("%H:%M"), cfg.send_to.strftime("%H:%M"))
                stats["waiting"] += 1
            else:
                if live:
                    why = "тестовий режим — клієнта немає в списку тестових"
                elif texts_ready(cfg):
                    why = "автоматична відправка вимкнена"
                else:
                    why = "відправка вимкнена — тексти ще не затверджені"
                req.status, req.journal_at = "would_send", now
                req.reason = ("Надіслали б: %s (%s)" % (plan["label"], why))[:300]
                stats["would_send"] += 1
        elif status == "waiting":
            if req.due_at and now > req.due_at + timedelta(days=cfg.window_wait_days):
                if live and plan and plan["kind"] == "wait_window":
                    _ask_manager_task(req, now)
                    stats["manager_task"] += 1
                else:
                    req.status = "skipped"
                    req.reason = ("чекали %s днів: %s" % (cfg.window_wait_days, reason))[:300]
                    stats["skipped"] += 1
            else:
                req.status, req.reason = "waiting", reason[:300]
                if plan:
                    _set_plan(req, plan)
                stats["waiting"] += 1
        else:
            req.status, req.reason = status, reason[:300]
            stats[status] += 1
        req.save()
    if live:
        _reminders(cfg, now, stats)
    _stop_words(now, stats)
    stats["expired"] += (ReviewRequest.objects
                         .filter(status__in=("scheduled", "waiting", "would_send", "sent", "reminded"), expires_at__lt=now)
                         .update(status="expired", reason="минув термін посилання", updated_at=now))
    stats["live"] = int(live)
    return dict(stats)


# ── кнопка «⭐ Попросити відгук» (вручну: чат / картка угоди) ─────────────

def deal_for_conversation(conv):
    """Угода для кнопки в чаті: клієнт — лише через контакт цього чату (ніколи за іменем); остання не програшна
    угода з ТТН, інакше остання не програшна."""
    if not conv or not conv.contact_id:
        return None
    qs = (Deal.objects.filter(contact_id=conv.contact_id).exclude(stage__is_lost=True)
          .select_related("stage", "owner", "contact", "funnel"))
    return qs.exclude(ttn="").order_by("-id").first() or qs.order_by("-id").first()


def _manual_plan(conv, now):
    """Канал для кнопки в конкретному чаті → (plan, причина відмови)."""
    kind = conv.channel.kind
    if kind == "web" or str(conv.external_chat_id or "").startswith("comment:"):
        return None, "У цей чат просьбу не надсилаємо (веб-чат або коментар) — відкрийте месенджер клієнта"
    if kind in WINDOW_KINDS:
        last_in = conv.messages.filter(direction="in").order_by("-created_at").values_list("created_at", flat=True).first()
        if not last_in or now - last_in > timedelta(hours=23):
            return None, ("%s: клієнт писав понад 24 години тому — повідомлення не дійде. "
                          "Натисніть кнопку, коли клієнт напише" % _label(kind))
        return {"kind": "window", "conversation": conv, "channel": conv.channel,
                "label": "%s — цей чат (вікно 24 год відкрите)" % _label(kind)}, ""
    return {"kind": "dialog", "conversation": conv, "channel": conv.channel, "label": "%s — цей чат" % _label(kind)}, ""


def manual_ask(deal, conv=None, user=None, send=False, now=None):
    """Кнопка «⭐ Попросити відгук». send=False — лише показати точний текст і канал (нічого не створює);
    send=True — надіслати від імені менеджера. Запобіжники ті самі, що в автоматиці: тестовий режим, «не просити»,
    1 просьба на N днів, вікно Instagram. Не залежить від send_enabled: це ручна дія менеджера. → dict для фронтенду."""
    now = now or timezone.now()
    cfg = ReviewSettings.get()
    contact = deal.contact if deal and deal.contact_id else None
    out = {"ok": False, "can_send": False, "sent": False, "reason": "", "text": "", "channel_label": "",
           "deal_id": deal.id if deal else None, "deal_title": deal.title if deal else "",
           "conversation_id": conv.id if conv else None, "test_mode": cfg.test_mode}

    def refuse(reason):
        out["reason"] = reason
        return out

    if contact is None:
        return refuse("В угоді немає клієнта — просьбу не привʼязати")
    if not texts_ready(cfg):
        return refuse("Тексти просьби ще не затверджені (Відгуки → Тексти і запуск)")
    if not contact_allowed(cfg, contact.id):
        return refuse("Поки йде перевірка, кнопка працює лише для тестових контактів (Відгуки → Тексти і запуск)")
    if ReviewOptOut.objects.filter(contact_id=contact.id).exists():
        return refuse("Клієнт просив не надсилати йому просьби про відгук")
    bad = NOT_CLIENT_KINDS & set(contact.kinds or [])
    if bad and contact.id not in (cfg.allowlist_contact_ids or []):
        return refuse("Це не покупець (%s)" % ", ".join(sorted(bad)))
    stage_name = ((deal.stage.name if deal.stage_id else "") or "").lower()
    if deal.stage_id and (deal.stage.is_lost or "поверн" in stage_name or "скасов" in stage_name):
        return refuse("Угоду скасовано або повернено")
    since = now - timedelta(days=cfg.repeat_block_days)
    prev = (ReviewRequest.objects.filter(contact_id=contact.id, status__in=("sent", "reminded", "submitted"),
                                         sent_at__gte=since).order_by("-sent_at").first())
    if prev:
        return refuse("Клієнта вже просили %s (угода #%s) — не частіше 1 разу на %s днів"
                      % (timezone.localtime(prev.sent_at).strftime("%d.%m"), prev.deal_id, cfg.repeat_block_days))
    if Message.objects.filter(conversation__contact_id=contact.id, direction="out", text__contains=REVIEW_LINK_MARK,
                              created_at__gte=since).exists():
        return refuse("У чаті клієнта вже є посилання на відгук за останні %s днів" % cfg.repeat_block_days)
    if conv is not None:
        if conv.contact_id != contact.id:
            return refuse("Цей чат належить іншому клієнту, ніж угода #%s" % deal.id)
        plan, why = _manual_plan(conv, now)
        if plan is None:
            return refuse(why)
    else:
        plan = choose_channel(contact, now)
        if plan["kind"] in ("wait_window", "none"):
            return refuse("Немає куди надіслати: " + plan["label"])
    kind = classify(deal, cfg, test_category_ids())
    template = cfg.text_test if kind == "test" else cfg.text_main
    req = ReviewRequest(deal=deal, contact=contact, kind="manual", code=PREVIEW_CODE)
    out.update(channel_label=plan["label"], kind=kind, text=render(template, req, kind),
               conversation_id=plan["conversation"].id if plan.get("conversation") else None)
    if not send:
        out.update(ok=True, can_send=True, reason="Перевірте текст і канал — повідомлення піде лише після «Надіслати»")
        return out
    from apps.inbox.services import send_message
    author = user if user is not None and user.is_authenticated else None
    who = (author.get_full_name() or author.username) if author else "менеджер"
    req.code = new_code()
    req.status, req.sent_at = "sent", now
    req.received_at = received_at_for(deal)
    req.expires_at = now + timedelta(days=cfg.expire_days)
    req.created_by = author
    req.channel_plan = "manual"
    req.channel_label = plan["label"][:120]
    req.reason = ("вручну: %s натиснув(ла) «Попросити відгук»" % who)[:300]
    conv_to = plan.get("conversation") or _conversation_for_new(req, plan["channel"])
    req.conversation, req.channel = conv_to, conv_to.channel
    req.save()
    text = render(template, req, kind)
    try:
        req.message = send_message(conv_to, text, user=author)
    except Exception as exc:  # noqa: BLE001 — просьбу скасовуємо, посилання не діє
        req.status, req.last_error = "cancelled", str(exc)[:300]
        req.reason = "не вдалося надіслати — посилання скасовано"
        req.save(update_fields=["status", "last_error", "reason", "updated_at"])
        return refuse("Не вдалося надіслати: %s" % str(exc)[:200])
    req.save(update_fields=["message", "updated_at"])
    (ReviewRequest.objects.filter(deal=deal, kind__in=("main", "test"), status__in=("scheduled", "waiting", "would_send"))
     .update(status="cancelled", reason="менеджер уже попросив відгук вручну", updated_at=now))
    log_activity("deal", deal.id, "Відгук: просьба надіслана вручну", plan["label"], author)
    out.update(ok=True, can_send=False, sent=True, text=text, conversation_id=conv_to.id, request_id=req.id,
               reason="Надіслано. Відгук клієнта зʼявиться в розділі «Відгуки → На перевірці»")
    return out


# ── магазин: приглашення, відгук, стрічка ─────────────────────────────────

def invite_status(req, now):
    if req.status == "submitted" or Review.objects.filter(request=req).exists():
        return "submitted"
    if req.status == "expired" or (req.status in ACTIVE and req.expires_at and now > req.expires_at):
        return "expired"
    if req.status in ("cancelled", "opted_out"):
        return "cancelled"
    if req.status in ACTIVE:
        return "active"
    return None  # посилання не надсилали — для магазину його «не існує»


def invite_payload(code, mark_opened=False, now=None):
    now = now or timezone.now()
    req = ReviewRequest.objects.select_related("contact", "deal").filter(code=code).first() if CODE_RE.match(code or "") else None
    status = invite_status(req, now) if req else None
    if status is None:
        raise ReviewError("not_found", "Посилання не знайдено", 404)
    if mark_opened and status == "active" and not req.opened_at:
        req.opened_at = now
        req.save(update_fields=["opened_at", "updated_at"])
    cfg = ReviewSettings.get()
    return {"code": req.code, "status": status, "can_submit": status == "active", "kind": req.kind,
            "is_test": req.is_test, "first_name": ((req.contact.first_name if req.contact else "") or "").strip(),
            "suggested_display_name": suggested_name(req.contact),
            "expires_at": timezone.localtime(req.expires_at).isoformat() if req.expires_at else None,
            "products": products_for(req), "google_review_url": cfg.google_review_url}


def _text(body, key, limit):
    value = body.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ReviewError("validation", "Поле %s має бути текстом" % key, field=key)
    value = value.strip()
    if len(value) > limit:
        raise ReviewError("validation", "Поле %s довше за %s символів" % (key, limit), field=key)
    return value


def _decode_photos(items):
    if items in (None, ""):
        return []
    if not isinstance(items, list) or len(items) > MAX_PHOTOS:
        raise ReviewError("validation", "Можна додати до %s фото" % MAX_PHOTOS, field="photos")
    out = []
    for item in items:
        encoded = item.get("data") if isinstance(item, dict) else None
        if not isinstance(encoded, str) or len(encoded) > 2_700_000:
            raise ReviewError("validation", "Фото завелике або пошкоджене", field="photos")
        try:
            raw = base64.b64decode(encoded, validate=True)
            out.append(process_photo(raw))
        except (binascii.Error, ValueError) as exc:
            raise ReviewError("validation", str(exc) if isinstance(exc, ValueError) and str(exc) else "Не вдалося прочитати фото",
                              field="photos")
    return out


def _low_rating_task(review, req, now):
    from apps.accounts.models import Department
    deal = req.deal
    owner = deal.owner if deal and deal.owner_id and deal.owner.is_active else None
    dept = getattr(owner, "department", None) if owner else None
    if dept is None and deal:
        dept = deal.funnel.departments.order_by("id").first()
    if dept is None:
        dept = Department.objects.filter(name__icontains="продаж").order_by("id").first()
    test = review.is_test
    return Task.objects.create(
        kind="manager", priority="high", status="open", deal=deal, contact=req.contact,
        title=("ТЕСТ · " if test else "") + "Відгук %s★ — зв’яжіться з клієнтом (угода #%s)" % (review.rating, req.deal_id or "—"),
        body=("Клієнт залишив на сайті відгук %s★: «%s».\nСпершу зв’яжіться і вирішіть проблему. Публічну відповідь "
              "від Wallcov дає Олег у розділі «Відгуки». Бонусів за відгук не пропонувати."
              % (review.rating, (review.text or "без тексту")[:500])),
        assignee=None if test else owner, department=None if test else dept,
        due_at=now + timedelta(hours=24), created_by_agent=False)


def submit_review(body, now=None):
    """Відгук з форми магазину. → (review, duplicate)."""
    now = now or timezone.now()
    try:
        event = uuid.UUID(str(body.get("event_uuid") or ""))
    except ValueError:
        raise ReviewError("validation", "event_uuid має бути UUID", field="event_uuid")
    code = str(body.get("code") or "")
    if not CODE_RE.match(code):
        raise ReviewError("not_found", "Посилання не знайдено", 404)
    existing = Review.objects.select_related("request").filter(event_uuid=event).first()
    if existing:
        if not existing.request or existing.request.code != code:
            raise ReviewError("validation", "event_uuid вже використано для іншого посилання", field="event_uuid")
        return existing, True
    rating = body.get("rating")
    if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5:
        raise ReviewError("validation", "Оцінка — ціле число від 1 до 5", field="rating")
    text = _text(body, "text", 3000)
    room = _text(body, "room", 20)
    if room not in ROOMS:
        raise ReviewError("validation", "Невідоме приміщення", field="room")
    applied_by = _text(body, "applied_by", 10) or "unknown"
    if applied_by not in APPLIED:
        raise ReviewError("validation", "applied_by: self / master / unknown", field="applied_by")
    display_name = _text(body, "display_name", 60)
    city = _text(body, "city", 60)
    anonymous = body.get("anonymous") is True
    if not isinstance(body.get("consent_site"), bool):
        raise ReviewError("validation", "consent_site: true або false", field="consent_site")
    consent_version = _text(body, "consent_version", 40)
    if not consent_version:
        raise ReviewError("validation", "Потрібна версія тексту згоди", field="consent_version")
    product_ids = body.get("product_ids") or []
    if not isinstance(product_ids, list) or len(product_ids) > 20 or any(isinstance(p, bool) or not isinstance(p, int) for p in product_ids):
        raise ReviewError("validation", "product_ids — список id товарів", field="product_ids")
    submitted_at = parse_datetime(str(body.get("submitted_at") or "")) or now
    photos = _decode_photos(body.get("photos"))
    with transaction.atomic():
        req = ReviewRequest.objects.select_for_update().filter(code=code).first()
        if not req:
            raise ReviewError("not_found", "Посилання не знайдено", 404)
        existing = Review.objects.filter(event_uuid=event).first()
        if existing:
            return existing, True
        status = invite_status(req, now)
        if status is None:
            raise ReviewError("not_found", "Посилання не знайдено", 404)
        if status == "submitted":
            raise ReviewError("already_submitted", "Відгук за цим посиланням уже отримано", 409)
        if status in ("expired", "cancelled"):
            raise ReviewError(status, "Посилання застаріло — напишіть нам у чат" if status == "expired"
                              else "Посилання більше не діє — напишіть нам у чат", 410)
        allowed = {p["crm_product_id"]: p for p in products_for(req)}
        unknown = [p for p in product_ids if p not in allowed]
        if unknown:
            raise ReviewError("validation", "Товар не з цього замовлення: %s" % unknown[0], field="product_ids")
        chosen = [dict(allowed[p], is_primary=(i == 0)) for i, p in enumerate(dict.fromkeys(product_ids))]
        if not chosen:
            chosen = [p for p in allowed.values() if p["is_primary"]]
        review = Review.objects.create(
            request=req, deal_id=req.deal_id, contact_id=req.contact_id, event_uuid=event, rating=rating,
            text=text, text_original=text, room=room, applied_by=applied_by,
            display_name=display_name or suggested_name(req.contact), anonymous=anonymous, city=city,
            consent_site=body.get("consent_site") is True, consent_social=body.get("consent_social") is True,
            consent_version=consent_version, consent_at=now, products=chosen, kind=req.kind, is_test=req.is_test,
            submitted_at=submitted_at)
        for index, photo in enumerate(photos):
            ReviewPhoto.objects.create(review=review, token="p_" + secrets.token_urlsafe(18), sort=index, **photo)
        req.status, req.submitted_at = "submitted", now
        req.save(update_fields=["status", "submitted_at", "updated_at"])
        if rating <= 3:
            review.task = _low_rating_task(review, req, now)
            review.save(update_fields=["task"])
        if req.deal_id:
            log_activity("deal", req.deal_id, "Відгук %s★ з сайту" % rating, text[:200], None, "Відгуки")
    return review, False


def public_name(review):
    return ANON_NAME if review.anonymous else (review.display_name or ANON_NAME)


def photo_url(photo, thumb=False):
    return "%s/api/reviews/photo/%s/%s" % (CRM_URL.rstrip("/"), photo.token, "?size=thumb" if thumb else "")


def public_review(review):
    updated = timezone.localtime(review.updated_at).isoformat()
    if review.status != "published":
        return {"review_id": review.id, "status": "removed", "updated_at": updated}
    return {
        "review_id": review.id, "status": "published", "rating": review.rating, "text": review.text,
        "reply": ({"text": review.reply_text, "replied_at": timezone.localtime(review.replied_at).isoformat()
                   if review.replied_at else None} if review.reply_text else None),
        "display_name": public_name(review), "city": review.city, "room": review.room,
        "applied_by": review.applied_by, "kind": review.kind, "is_test": review.is_test,
        "verified_purchase": review.request_id is not None, "featured": review.featured,
        "products": review.products or [],
        "photos": [{"photo_id": p.token, "url": photo_url(p), "thumb_url": photo_url(p, True),
                    "width": p.width, "height": p.height} for p in review.photos.all() if p.is_public],
        "published_at": timezone.localtime(review.published_at).isoformat() if review.published_at else None,
        "updated_at": updated,
    }


def published_feed(body, now=None):
    now = now or timezone.now()
    raw_since = body.get("updated_since")
    since = parse_datetime(str(raw_since)) if raw_since else None
    if raw_since and since is None:
        raise ReviewError("validation", "updated_since — дата ISO 8601", field="updated_since")
    limit = body.get("limit", 100)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
        raise ReviewError("validation", "limit — від 1 до 200", field="limit")
    qs = Review.objects.filter(published_at__isnull=False)
    if body.get("include_test") is not True:
        qs = qs.filter(is_test=False)
    if since:
        qs = qs.filter(updated_at__gt=since)
    cursor = body.get("cursor")
    if cursor:
        try:
            at_raw, id_raw = str(cursor).rsplit("|", 1)
            at, last_id = parse_datetime(at_raw), int(id_raw)
            if at is None:
                raise ValueError
        except ValueError:
            raise ReviewError("validation", "Некоректний cursor", field="cursor")
        qs = qs.filter(Q(updated_at__gt=at) | Q(updated_at=at, id__gt=last_id))
    rows = list(qs.order_by("updated_at", "id").prefetch_related("photos")[:limit + 1])
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = "%s|%s" % (rows[-1].updated_at.isoformat(), rows[-1].id)
    return {"ok": True, "api_version": 1, "server_time": timezone.localtime(now).isoformat(),
            "next_cursor": next_cursor, "reviews": [public_review(r) for r in rows]}
