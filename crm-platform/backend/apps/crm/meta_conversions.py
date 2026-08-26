"""CRM -> Meta Conversions API: mapping, privacy-safe outbox and controlled send."""

import hashlib
import json
import os
import re
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.db import transaction
from django.utils import timezone

from .models import Deal, Lead, MetaConversionEvent, Payment


def _key(value):
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


# Назви взяті з live CRM 21.08.2026. Платіжні стадії тут навмисно відсутні:
# Purchase створюється лише з реально оплаченого Payment.
STAGE_EVENT_NAMES = {
    # ── Стадія CRM → подія Meta → ярлик у Direct ──────────────────────────
    # LeadSubmitted → ярлик «Лид»
    _key("Лід отриманий"): "LeadSubmitted",
    _key("Взято в роботу"): "LeadSubmitted",
    _key("Данні для розрахунку"): "LeadSubmitted",
    _key("Новая заявка"): "LeadSubmitted",
    _key("Нове замовлення з сайту"): "LeadSubmitted",
    _key("Не обработан"): "LeadSubmitted",
    _key("Виявлення потреби"): "LeadSubmitted",
    _key("Выявление потребности"): "LeadSubmitted",
    _key("Вхідні ліди"): "LeadSubmitted",
    _key("Новая"): "LeadSubmitted",
    # QualifiedLead → клієнт підтверджений як цільовий
    _key("Контакт встановлений"): "QualifiedLead",
    _key("Контакт установлен"): "QualifiedLead",
    _key("Первый контакт"): "QualifiedLead",
    _key("Кваліфікований"): "QualifiedLead",
    _key("Підбір рішення"): "QualifiedLead",
    # ViewContent → показали прорахунок / КП
    _key("Розрахунок здійснено"): "ViewContent",
    _key("Розрахунок здійснено (КП)"): "ViewContent",
    _key("Розрахунок здійснен"): "ViewContent",
    _key("Расчёт отправлен"): "ViewContent",
    _key("Выслал каталог"): "ViewContent",
    _key("Выставлен счет"): "ViewContent",
    # InitiateCheckout → домовились платити
    _key("Домовились про оплату"): "InitiateCheckout",
    _key("Ожидаем оплату"): "InitiateCheckout",
    _key("Cчёт на предоплату"): "InitiateCheckout",
    _key("Счёт на предоплату"): "InitiateCheckout",
    _key("Финальный счёт"): "InitiateCheckout",
    # Purchase → ярлик «Оплачено»
    _key("Оплату отримано"): "Purchase",
    _key("Получена полная оплата по заявке"): "Purchase",
    # OrderCreated → ярлик «Размещен заказ»
    _key("Заброньовано"): "OrderCreated",
    # OrderShipped → ярлик «Отправлено»
    _key("Відвантаження"): "OrderShipped",
    _key("НП_ТТН створена"): "OrderShipped",
    _key("НП_Відправленя в Мог.-Под."): "OrderShipped",
    _key("НП_В дорозі"): "OrderShipped",
    # OrderDelivered → доставлено клієнту
    _key("НП_Прибув на відділення"): "OrderDelivered",
    _key("Отримано"): "OrderDelivered",
    _key("Успішна угода"): "OrderDelivered",
    _key("Сделка успешна"): "OrderDelivered",
    # OrderCanceled → скасування вже оплаченого
    _key("Скасовано після оплати"): "OrderCanceled",
}

# Ніколи не відправляємо кадрову, технічну або архівну воронку. Назви взяті
# безпосередньо з live CRM; нова воронка повинна бути додана сюди свідомо.
ALLOWED_FUNNELS = {
    _key("Лиды"),
    _key("1.С/Покрытия для стен"),
    _key("4.С/Алмазне + Вентиляція"),
    _key("7.РЕК/Лендинг"),
    _key("6.С/ОПТ_Дилеры"),
    _key("9.TikTok"),
    _key("10. База клиентов"),
    _key("21 Основний продукт"),
    _key("22 Тестовий набір"),
    _key("23 Інтернет-магазин"),
    _key("Лендинг · wallcovdliastin.com.ua"),
}

# `source=instagram/facebook` не доводить, що клієнт прийшов з реклами: це може
# бути органічний Direct, коментар або картка, створена менеджером. У Meta
# відправляємо лише записи з підтвердженим рекламним/lead-form ідентифікатором.
QUALIFYING_ATTRIBUTION_KINDS = {"paid_ad", "lead_form"}
ATTRIBUTION_ID_FIELDS = ("lead_id", "ad_id", "campaign_id", "referral_id")


def normalized_meta_attribution(entity):
    raw = getattr(entity, "meta_attribution", None) or {}
    if not isinstance(raw, dict):
        return {}
    allowed = {
        "source_kind", "platform", "lead_id", "form_id", "ad_id", "adset_id",
        "campaign_id", "referral_id", "content_id", "source_context",
        "campaign_name", "adset_name", "ad_name", "form_name",
    }
    return {key: str(value).strip() for key, value in raw.items()
            if key in allowed and value not in (None, "")}


def has_verified_meta_attribution(entity):
    attr = normalized_meta_attribution(entity)
    if attr.get("source_kind") not in QUALIFYING_ATTRIBUTION_KINDS:
        return False
    if attr.get("platform") not in ("facebook", "instagram"):
        return False
    return any(attr.get(key) for key in ATTRIBUTION_ID_FIELDS)


def event_has_verified_meta_attribution(event):
    """Повторна перевірка перед send; підтримує snapshot видаленого після конвертації ліда."""
    source = event.payment.deal if event.payment_id else (event.deal or event.lead)
    if source is not None:
        return has_verified_meta_attribution(source)
    custom = (event.payload or {}).get("custom_data") or {}
    if custom.get("meta_source_kind") not in QUALIFYING_ATTRIBUTION_KINDS:
        return False
    if custom.get("meta_platform") not in ("facebook", "instagram"):
        return False
    return any(custom.get(f"meta_{key}") for key in ATTRIBUTION_ID_FIELDS)


def event_name_for_stage(stage):
    if not stage or stage.is_lost or getattr(stage.funnel, "is_archive", False):
        return None
    if _key(stage.funnel.name) not in ALLOWED_FUNNELS:
        return None
    return STAGE_EVENT_NAMES.get(_key(stage.name))


def _sha256(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_phone(value):
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if digits.startswith("380"):
        return digits[:12]
    if digits.startswith("0") and len(digits) >= 10:
        return "38" + digits[:10]
    if len(digits) == 9:
        return "380" + digits
    return digits


def _user_data(contact):
    """Meta user_data only with SHA-256 normalized values; no raw PII in DB/logs."""
    data = {}
    if not contact:
        return data
    phone = _normalize_phone(contact.phone)
    email = (contact.email or "").strip().lower()
    first_name = (contact.first_name or "").strip().lower()
    last_name = (contact.last_name or "").strip().lower()
    if phone:
        data["ph"] = [_sha256(phone)]
    if email:
        data["em"] = [_sha256(email)]
    if first_name:
        data["fn"] = [_sha256(first_name)]
    if last_name:
        data["ln"] = [_sha256(last_name)]
    data["external_id"] = [_sha256(f"crm-contact-{contact.pk}")]
    return data


def _messaging_identity(contact):
    """IGSID/PSID переписки клієнта у ПРЯМОМУ Meta-каналі + тип каналу.

    Meta зіставляє події бізнес-листування не за поштою/телефоном (яких у
    Direct-клієнтів немає), а за ідентифікатором самої переписки. Повертає
    (channel, ident, account_id) або (None, None, None)."""
    if not contact or not getattr(contact, "pk", None):
        return (None, None, None)
    try:
        from apps.inbox.models import Conversation
        row = (Conversation.objects
               .filter(contact_id=contact.pk, channel__config__meta=True,
                       channel__kind__in=("instagram", "facebook"))
               .exclude(external_chat_id="")
               .exclude(external_chat_id__startswith="comment:")
               .order_by("-last_message_at")
               .values_list("external_chat_id", "channel__kind", "channel__config")
               .first())
        if not row:
            return (None, None, None)
        ident, kind, cfg = row
        cfg = cfg or {}
        if kind == "instagram":
            acc = str(cfg.get("ig_account_id") or os.environ.get("META_IG_ACCOUNT_ID", "")).strip()
            return ("instagram", str(ident), acc) if acc else (None, None, None)
        acc = str(cfg.get("page_id") or "").strip()
        return ("messenger", str(ident), acc) if acc else (None, None, None)
    except Exception:
        return (None, None, None)


def _money(value):
    return float(Decimal(value or 0).quantize(Decimal("0.01")))


def _server_event(*, event_id, event_name, occurred_at, contact, custom_data):
    """Формат Meta «Conversions API for Business Messaging»: якщо знаємо
    переписку (IGSID/PSID) — шлемо business_messaging, щоб Meta реально
    зіставила подію з рекламою. Інакше — старий system_generated."""
    base = {
        "event_name": event_name,
        "event_time": int(occurred_at.timestamp()),
        "event_id": event_id,
        "custom_data": custom_data,
    }
    channel, ident, account_id = _messaging_identity(contact)
    if channel and ident and account_id:
        user_data = dict(_user_data(contact))
        if channel == "instagram":
            user_data["ig_account_id"] = account_id
            user_data["ig_sid"] = ident
        else:
            user_data["page_id"] = account_id
            user_data["page_scoped_user_id"] = ident
        base["action_source"] = "business_messaging"
        base["messaging_channel"] = channel
        base["user_data"] = user_data
        return base
    base["action_source"] = "system_generated"
    base["user_data"] = _user_data(contact)
    return base


def queue_stage_event(entity, *, occurred_at=None):
    """Create one idempotent event per entity/stage. Returns event or None."""
    if not isinstance(entity, (Lead, Deal)) or not entity.pk or not entity.stage_id:
        return None
    if not has_verified_meta_attribution(entity):
        return None
    stage = entity.stage
    event_name = event_name_for_stage(stage)
    if not event_name:
        return None
    source_type = "lead" if isinstance(entity, Lead) else "deal"
    event_id = f"crm-{source_type}-{entity.pk}-stage-{stage.pk}-{event_name.lower()}"
    occurred_at = occurred_at or entity.updated_at or timezone.now()
    custom_data = {
        "currency": "UAH",
        "value": _money(entity.amount),
        "crm_source": entity.source,
        "crm_funnel": entity.funnel.name,
        "crm_stage": stage.name,
        "crm_object_type": source_type,
        "crm_object_id": str(entity.pk),
    }
    attr = normalized_meta_attribution(entity)
    custom_data.update({f"meta_{key}": value for key, value in attr.items()})
    payload = _server_event(
        event_id=event_id,
        event_name=event_name,
        occurred_at=occurred_at,
        contact=entity.contact,
        custom_data=custom_data,
    )
    defaults = {
        "event_name": event_name,
        "source_type": source_type,
        "source_id": entity.pk,
        "contact": entity.contact,
        "stage": stage,
        "occurred_at": occurred_at,
        "payload": payload,
        "lead": entity if source_type == "lead" else None,
        "deal": entity if source_type == "deal" else None,
    }
    event, _ = MetaConversionEvent.objects.get_or_create(event_id=event_id, defaults=defaults)
    return event


def queue_payment_event(payment, *, occurred_at=None):
    """Queue Purchase only for a persisted, actually paid Payment."""
    if not isinstance(payment, Payment) or not payment.pk or not payment.is_paid:
        return None
    deal = payment.deal
    if not has_verified_meta_attribution(deal):
        return None
    event_id = f"crm-payment-{payment.pk}-purchase"
    occurred_at = occurred_at or payment.created_at or timezone.now()
    order_id = payment.external_id or f"crm-payment-{payment.pk}"
    custom_data = {
        "currency": "UAH",
        "value": _money(payment.amount),
        "order_id": order_id,
        "crm_payment_provider": payment.provider,
        "crm_deal_id": str(deal.pk),
        "crm_funnel": deal.funnel.name,
        "crm_stage": deal.stage.name,
    }
    attr = normalized_meta_attribution(deal)
    custom_data.update({f"meta_{key}": value for key, value in attr.items()})
    payload = _server_event(
        event_id=event_id,
        event_name="Purchase",
        occurred_at=occurred_at,
        contact=deal.contact,
        custom_data=custom_data,
    )
    event, _ = MetaConversionEvent.objects.get_or_create(
        event_id=event_id,
        defaults={
            "event_name": "Purchase",
            "source_type": "payment",
            "source_id": payment.pk,
            "contact": deal.contact,
            "deal": deal,
            "payment": payment,
            "stage": deal.stage,
            "occurred_at": occurred_at,
            "payload": payload,
        },
    )
    return event


def capi_config():
    return {
        "enabled": os.environ.get("META_CAPI_ENABLED", "0") == "1",
        "dataset_id": os.environ.get("META_CAPI_DATASET_ID", "").strip(),
        # окремий CAPI-токен НЕ обовʼязковий: якщо не заданий — беремо системний
        # рекламний токен (System User, ads_management), яким уже ходить синхронізація.
        "access_token": (os.environ.get("META_CAPI_ACCESS_TOKEN", "").strip()
                         or os.environ.get("META_MARKETING_ACCESS_TOKEN", "").strip()),
        "graph_version": os.environ.get("META_CAPI_GRAPH_VERSION", "v21.0").strip() or "v21.0",
        "test_event_code": os.environ.get("META_CAPI_TEST_EVENT_CODE", "").strip(),
    }


def send_event(event, *, test_event_code=""):
    """Send one outbox row. Caller must explicitly enable CAPI and request send."""
    if not event_has_verified_meta_attribution(event):
        raise RuntimeError("Meta event is blocked: no verified paid-ad/lead-form attribution")
    config = capi_config()
    if not config["enabled"]:
        raise RuntimeError("META_CAPI_ENABLED=1 is required for sending")
    if not config["dataset_id"] or not config["access_token"]:
        raise RuntimeError("META_CAPI_DATASET_ID and META_CAPI_ACCESS_TOKEN are required")
    body = {"data": [event.payload]}
    code = (test_event_code or config["test_event_code"]).strip()
    if code:
        body["test_event_code"] = code
    query = urlencode({"access_token": config["access_token"]})
    url = f"https://graph.facebook.com/{config['graph_version']}/{config['dataset_id']}/events?{query}"
    request = Request(
        url,
        data=json.dumps(body, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8") or "{}")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"Meta HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"Meta network error: {exc}") from exc
    if result.get("events_received") != 1:
        raise RuntimeError(f"Meta did not confirm one event: {str(result)[:400]}")
    return result


def process_event(event_id, *, test_event_code=""):
    """Atomically claim and send one pending/failed event."""
    with transaction.atomic():
        event = MetaConversionEvent.objects.select_for_update().get(pk=event_id)
        if event.status not in ("pending", "failed") or event.attempts >= 5:
            return event, False
        if not event_has_verified_meta_attribution(event):
            event.status = "skipped"
            event.last_error = "No verified Meta paid-ad/lead-form attribution"
            event.save(update_fields=["status", "last_error", "updated_at"])
            return event, False
        event.status = "processing"
        event.attempts += 1
        event.last_error = ""
        event.save(update_fields=["status", "attempts", "last_error", "updated_at"])
    try:
        send_event(event, test_event_code=test_event_code)
    except Exception as exc:
        event.status = "failed"
        event.last_error = str(exc)[:500]
        event.save(update_fields=["status", "last_error", "updated_at"])
        return event, False
    event.status = "sent"
    event.sent_at = timezone.now()
    event.last_error = ""
    event.save(update_fields=["status", "sent_at", "last_error", "updated_at"])
    return event, True
