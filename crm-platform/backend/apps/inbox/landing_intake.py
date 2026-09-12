"""Transactional landing intake. No messages are sent to external channels here."""
import base64
import hashlib
import io
import json
import re
import secrets
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db import connection, transaction
from django.db.models import F
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError

from apps.accounts.models import User
from apps.crm.models import Contact, Deal, Funnel, Task
from .models import LandingSubmission, Message, Notification, SharedLink
from .services import _phone_variants

LANDING_ID = "wallcovdliastin.com.ua"
# Сайти, з яких CRM приймає заявки: landing_id → воронка (12.09.2026, рішення Олега).
# wallcovdliastin — як і раніше (воронка 22, прайс Шовк/Вельвет, ті самі хеші й тексти).
# Назва воронки лендингу МАЄ містити «Лендинг» — по ній рахує аналітика «Сайт · Google».
# Новий сайт додається сюди свідомо + воронка (manage.py ensure_landing_funnels).
LANDINGS = {
    LANDING_ID: {"funnel": "Лендинг · wallcovdliastin.com.ua", "priced": True},
    "dekoratyvna-shtukaturka.com.ua": {"funnel": "Лендинг · dekoratyvna-shtukaturka.com.ua", "priced": False},
    # Інтернет-магазин: форми «Отримати розрахунок» у статтях і квіз (підписаний запит сервер→сервер).
    "wallcov.com.ua": {"funnel": "23 Інтернет-магазин wallcov.com.ua", "priced": False, "attribution": True},
}
class SubmissionConflict(ValueError):
    """Той самий номер звернення, але інший зміст (для підписаного API → 409)."""


PREFERRED = {"phone", "telegram", "viber"}
PREFERRED_EXTRA = {"whatsapp"}  # тільки для нових сайтів — поведінка wallcovdliastin не змінюється
PRICES ={"sirena": ("Шовк · Сирена", "0.15", "1265"),
          "luna": ("Вельвет · Луна", "0.25", "780"),
          "mermi": ("Шовк · Мерми", "0.15", "1078")}
TOUCH_KEYS = {"utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
              "fbclid", "gclid", "landing_path", "first_referrer", "referrer", "path"}


def normalize_phone(value):
    raw = str(value or "").strip()[:32]
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10 and digits.startswith("0"):
        digits = "38" + digits
    if not (10 <= len(digits) <= 15) or (digits.startswith("380") and len(digits) != 12):
        raise ValueError("Вкажіть коректний номер телефону, наприклад +380 67 123 45 67")
    return "+" + digits


def clean_touch(value):
    if not isinstance(value, dict):
        return {}
    return {key: str(value[key])[:300] for key in TOUCH_KEYS if key in value and isinstance(value[key], (str, int))}


def _slug(value, limit=120):
    return re.sub(r"[^a-z0-9_./-]", "", str(value or "").strip().lower())[:limit]


def _quiz(value):
    """Відповіді квізу: до 20 пар «питання → відповідь», лише текст."""
    if not isinstance(value, dict):
        return {}
    out = {}
    for key, val in list(value.items())[:20]:
        if isinstance(val, (list, tuple)):
            val = ", ".join(str(v) for v in val[:10])
        if isinstance(val, (str, int, float)):
            out[str(key)[:80]] = str(val)[:200]
    return out


def _unpriced_calc(intent):
    # Сайти без прайсу в CRM: суму рахує менеджер після консультації.
    return {"minimum_order": "", "estimate_from": "0", "estimate_to": "0",
            "estimate_kind": "sample_request" if intent == "sample" else "needs_consultation",
            "volume_kg": "", "price_per_kg": "", "consumption_kg_m2": ""}


def calculate(product, area, intent):
    if intent == "sample":
        return {"minimum_order": "220.00", "estimate_from": "220.00", "estimate_to": "220.00",
                "estimate_kind": "sample_from", "volume_kg": "", "price_per_kg": "", "consumption_kg_m2": ""}
    p = PRICES.get(product)
    volume = area * Decimal(p[1]) if area is not None and p else None
    cost = (volume * Decimal(p[2])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if volume is not None else Decimal("0")
    return {"minimum_order": "220.00", "estimate_from": str(max(Decimal("220"), cost)) if volume is not None else "0",
            "estimate_to": str(max(Decimal("220"), cost)) if volume is not None else "0",
            "estimate_kind": "minimum_consumption" if volume is not None else "needs_consultation",
            "volume_kg": str(volume) if volume is not None else "",
            "consumption_kg_m2": p[1] if p else "", "price_per_kg": p[2] if p else ""}


def selection_details(data, area, product, intent):
    """Canonical optional inputs, included in the immutable request hash.

    No added keys for legacy payloads: their existing receipt hashes stay valid.
    Dimensions describe all four walls of a rectangular room, not floor area.
    """
    extra = {}
    if "area_mode" in data or "room_dimensions" in data:
        mode = data.get("area_mode")
        if mode not in {"known", "dimensions", "help"}:
            raise ValueError("Оберіть спосіб визначення площі")
        dimensions = None
        if intent == "sample":
            mode, area = "help", None  # A sample never requires whole-room measurements.
        elif mode == "help":
            area = None
        elif mode == "known":
            if area is None:
                raise ValueError("Вкажіть площу стін або оберіть допомогу")
        else:
            raw = data.get("room_dimensions")
            if not isinstance(raw, dict):
                raise ValueError("Вкажіть розміри кімнати")
            values = {}
            for key in ("length", "width", "height", "openings"):
                value = raw.get(key, "0" if key == "openings" else "")
                text = str(value).strip().replace(",", ".")
                if key == "openings" and not text:
                    text = "0"
                if not re.fullmatch(r"[0-9]{1,6}(?:\.[0-9]{1,6})?", text):
                    raise ValueError("Вкажіть розміри додатними числами в метрах")
                try:
                    number = Decimal(text)
                except InvalidOperation:
                    raise ValueError("Не вдалося прочитати розміри кімнати")
                if key != "openings" and not (0 < number <= 100):
                    raise ValueError("Розміри мають бути більше нуля та до 100 метрів")
                values[key] = number
            gross = 2 * (values["length"] + values["width"]) * values["height"]
            net = gross - values["openings"]
            if values["openings"] >= gross or not (1 <= net <= 1000):
                raise ValueError("Перевірте розміри та площу вікон і дверей")
            calculated = net.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            if area is None or area != calculated:
                raise ValueError("Площа не відповідає розмірам. Оновіть розрахунок")
            area = calculated
            dimensions = {key: format(value.normalize(), "f") for key, value in values.items()}
        extra.update(area_mode=mode, room_dimensions=dimensions)
    if "silk_color" in data:
        color = re.sub(r"\s+", "", str(data.get("silk_color") or "")).upper()
        if color and (len(color) > 64 or not re.fullmatch(r"CSK[0-9][0-9.,/-]*", color)):
            raise ValueError("Перевірте код кольору Шовку")
        if color and product not in {"sirena", "mermi"}:
            raise ValueError("Колір Шовку не відповідає обраному покриттю")
        extra["silk_color"] = color
    return area, extra


def decode_photos(items):
    if not isinstance(items, list) or len(items) > 3:
        raise ValueError("Додайте не більше трьох фото")
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Не вдалося прочитати фото")
        encoded = str(item.get("data") or "")
        if len(encoded) > 650000:
            raise ValueError("Фото завелике. Спробуйте менший файл")
        try:
            raw = base64.b64decode(encoded, validate=True)
            if not raw or len(raw) > 480000:
                raise ValueError("Фото завелике")
            with Image.open(io.BytesIO(raw)) as check:
                if check.format not in {"JPEG", "PNG", "WEBP"} or check.width * check.height > 12000000:
                    raise ValueError("Підтримуються фото JPG, PNG або WebP до 12 Мп")
                check.verify()
            with Image.open(io.BytesIO(raw)) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
                image.thumbnail((1600, 1600))
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=83)  # Re-encode: no EXIF/location or embedded payload.
            result.append((hashlib.sha256(raw).hexdigest(), output.getvalue()))
        except (UnidentifiedImageError, OSError, base64.binascii.Error, Image.DecompressionBombError):
            raise ValueError("Не вдалося прочитати фото. Виберіть JPG, PNG або WebP")
    return result


def _owner(conv, contact, funnel):
    # Existing client ownership wins: заявка старого клієнта йде його менеджеру.
    # Новий відвідувач лишається НІЧИЙ (спільна черга, рішення Олега 08.09.2026):
    # чат і угоду бачать усі менеджери, хто перший узяв — той і веде.
    ids = [contact.owner_id, conv.assigned_to_id]
    for pk in ids:
        user = User.objects.filter(pk=pk, is_active=True, account_kind="staff", employment_status="active").first()
        if user:
            return user
    return None


def _queue_recipients():
    # Кого дзвонити про нічию заявку: всі активні співробітники з правом
    # «Сповіщення про нові незакріплені чати» (inbox.notify.unassigned) + адміністратори.
    users = User.objects.filter(is_active=True, account_kind="staff", employment_status="active")
    return [u for u in users if u.is_superuser or u.has_perm_code("inbox.notify.unassigned")]


def _photos(receipt, decoded):
    existing = {row["hash"] for row in receipt.photos}
    fresh = [(key, raw) for key, raw in decoded if key not in existing]
    # A retry, including retry after timeout, doesn't add the same photo twice.
    fresh = list({key: raw for key, raw in fresh}.items())
    if len(receipt.photos) + len(fresh) > 3:
        raise ValueError("До звернення можна додати не більше трьох фото")
    for key, raw in fresh:
        file = SharedLink.objects.create(token=secrets.token_urlsafe(32), filename="room.jpg", content_type="image/jpeg", data=raw)
        receipt.photos.append({"hash": key, "file_id": file.pk})
        Message.objects.create(conversation=receipt.conversation, direction="out", internal=True,
            text="Фото кімнати до звернення #%s" % receipt.deal_id, sender_name="Лендинг",
            attachments=[{"type": "image", "url": "https://crm.wallcovdec.com.ua/api/f/%s/" % file.token, "name": "Кімната"}])
    if fresh:
        receipt.save(update_fields=["photos"])
    return len(receipt.photos)


def response_data(receipt, duplicate=False):
    q = receipt.deal.qualification
    priced = LANDINGS.get(q.get("landing_id") or LANDING_ID, {}).get("priced", True)
    return {"ok": True, "deal_id": receipt.deal_id, "duplicate": duplicate,
            "estimate_from": float(q["estimate_from"]), "estimate_to": float(q["estimate_to"]),
            "minimum_order": 220 if priced else None,
            "calculation": {k: q.get(k, "") for k in calculate("", None, "selection")},
            "photo_count": len(receipt.photos), "conversation_id": receipt.conversation_id}


@transaction.atomic
def receive(conv, data, landing_id=LANDING_ID, notify_client=True):
    """Заявка з сайту → контакт + угода у воронці сайту + задача менеджеру.
    landing_id — ключ LANDINGS (за замовчуванням wallcovdliastin, як і раніше).
    notify_client=False — підписаний запит сервер→сервер (магазин): у чат сайту нічого не пишемо."""
    from .webchat import _decimal_area
    landing = LANDINGS.get(landing_id)
    if not landing:
        raise ValueError("Невідомий сайт")
    priced = landing["priced"]
    legacy = landing_id == LANDING_ID
    if data.get("consent") is not True:
        raise ValueError("Потрібна згода на зв’язок і обробку контактних даних")
    phone = normalize_phone(data.get("phone"))
    intent = "sample" if data.get("intent") == "sample" else "selection"
    area = (_decimal_area(data["area"]) if intent != "sample" and data.get("area_mode") != "help"
            and data.get("area") not in (None, "") else None)
    product_key = str(data.get("product") or "")
    if priced:
        if product_key and product_key not in PRICES:
            raise ValueError("Невідоме покриття")
    else:
        # Без прайсу: товар — просто позначка сайту (slug), код кольору Шовку не перевіряємо.
        product_key = _slug(product_key, 64)
        data = {k: v for k, v in data.items() if k != "silk_color"}
    area, details = selection_details(data, area, product_key, intent)
    allowed_preferred = PREFERRED if legacy else PREFERRED | PREFERRED_EXTRA
    preferred = data.get("preferred") if data.get("preferred") in allowed_preferred else "phone"
    request_id = str(data.get("submission_id") or secrets.token_urlsafe(24))
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", request_id):
        raise ValueError("Некоректний номер звернення")
    snapshot = {key: str(data.get(key) or "")[:300] for key in
                ("name", "room", "velvet_color", "velvet_formula", "mood", "installer", "reference", "flow_id", "silk_base")}
    snapshot.update(phone=phone, area=str(area) if area is not None else "", product=product_key, intent=intent, preferred=preferred)
    snapshot.update(details)
    site = {}
    if not legacy:
        # Нові сайти: сайт і зміст форми входять у хеш (той самий номер звернення з іншим змістом = конфлікт).
        site = {"product_label": str(data.get("product_label") or "")[:120], "message": str(data.get("message") or "")[:1000],
                "article": _slug(data.get("article")), "form": _slug(data.get("form"), 40),
                "page_url": str(data.get("page_url") or "")[:300], "quiz": _quiz(data.get("quiz"))}
        snapshot.update(landing_id=landing_id, **{k: (json.dumps(v, sort_keys=True, ensure_ascii=False) if k == "quiz" else v)
                                                  for k, v in site.items()})
    digest = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    phone_hash = hashlib.sha256(phone.encode()).hexdigest()
    receipt, _ = LandingSubmission.objects.get_or_create(request_id=request_id,
        defaults={"phone_hash": phone_hash, "payload_hash": digest, "conversation": conv})
    receipt = LandingSubmission.objects.select_for_update(of=("self",)).select_related("deal", "conversation").get(pk=receipt.pk)
    if receipt.phone_hash != phone_hash or receipt.payload_hash != digest:
        raise SubmissionConflict("Це звернення вже має інший підбір. Почніть новий розрахунок")
    if receipt.deal_id:
        return response_data(receipt, True)
    decoded = decode_photos(data.get("photos", []))
    # Contact.phone is not unique in this CRM. Serialize new-contact creation
    # for this number without changing or merging existing client records.
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [int(phone_hash[:15], 16)])
    contact = Contact.objects.select_for_update().filter(phone__in=_phone_variants(phone)).order_by("id").first()
    if not contact:
        contact = Contact.objects.create(first_name=snapshot["name"][:120] or "Клієнт із сайту", phone=phone, source="site", channels=[] if preferred == "phone" else [preferred])
    elif preferred != "phone" and preferred not in (contact.channels or []):
        contact.channels = list(contact.channels or []) + [preferred]
        contact.save(update_fields=["channels"])
    funnel = Funnel.objects.filter(name=landing["funnel"]).first()
    stage = funnel.stages.order_by("order", "id").first() if funnel else None
    if not stage:
        raise ValueError("Не вдалося прийняти звернення. Зателефонуйте нам або спробуйте пізніше")
    owner = _owner(conv, contact, funnel)
    first = clean_touch(data.get("first_touch") or data.get("analytics"))
    last = clean_touch(data.get("last_touch"))
    if priced:
        product_label = PRICES[product_key][0] if product_key else "Підібрати з консультантом"
    else:
        product_label = site["product_label"] or product_key or "Підібрати з консультантом"
    qualification = {"landing_id": landing_id, "submission_id": request_id, "conversation_id": conv.id,
        "room": snapshot["room"], "area_m2": snapshot["area"], "product_key": product_key,
        "product": product_label,
        "velvet_color": snapshot["velvet_color"], "velvet_formula": snapshot["velvet_formula"],
        "silk_base": snapshot["silk_base"], "mood": snapshot["mood"], "installer": snapshot["installer"],
        "reference": snapshot["reference"], "flow_id": snapshot["flow_id"], "intent": intent,
        "preferred_channel": preferred, "utm": first, "first_touch": first, "last_touch": last,
        **details,
        **(calculate(product_key, area, intent) if priced else _unpriced_calc(intent))}
    if not legacy:
        qualification.update(message=site["message"], article=site["article"], form=site["form"],
                             page_url=site["page_url"], quiz=site["quiz"])
        if landing.get("attribution"):
            # Як у замовлень магазину: аналітика «Сайт · Google» читає attribution.first_touch.
            qualification["attribution"] = {"first_touch": first, "last_touch": last}
    # Old receipts created before this table still deduplicate after a move.
    deal = Deal.objects.filter(contact=contact, qualification__landing_id=landing_id,
                               qualification__submission_id=request_id).first()
    if deal:
        receipt.deal = deal
        receipt.save(update_fields=["deal"])
        return response_data(receipt, True)
    deal = Deal.objects.create(title=("Пробний набір" if intent == "sample" else "Підбір покриття") + " · " + (snapshot["name"][:80] or phone),
        contact=contact, funnel=funnel, stage=stage, owner=owner, source="site", amount=Decimal(qualification["estimate_from"]),
        area_m2=area, qualification=qualification, is_seen=False)
    receipt.deal = deal
    site_tag = "" if legacy else " (%s)" % landing_id
    receipt.task = Task.objects.create(kind="manager", title="Прийняти звернення з сайту #%s%s" % (deal.id, site_tag),
        body="Перевірити підбір і фото. Зв’язатися через %s. Після відповіді записати результат і наступний крок. Автоматичне підтвердження не є відповіддю менеджера." % preferred,
        priority="high", deal=deal, contact=contact, conversation=conv, assignee=owner,
        department=(owner.department if owner else funnel.departments.order_by("id").first()),
        status="open", created_by_agent=False)
    receipt.save(update_fields=["deal", "task"])
    note = "Нове звернення #%s · %s\nКімната: %s; площа стін: %s\nКолір: %s; нанесення: %s\nОрієнтир: %s грн (%s). Зв’язок: %s. Задача #%s." % (
        deal.id, qualification["product"], snapshot["room"] or "уточнити", snapshot["area"] or "уточнити",
        details.get("silk_color") or snapshot["velvet_color"] or snapshot["mood"] or "підібрати", snapshot["installer"] or "уточнити",
        qualification["estimate_from"], qualification["estimate_kind"], preferred, receipt.task_id)
    if details.get("area_mode") == "dimensions":
        d = details["room_dimensions"]
        note += ("\nЗа розмірами кімнати: %s × %s м; висота %s м; вікна й двері %s м². "
                 "Чотири стіни прямокутної кімнати, укоси не враховані." %
                 (d["length"], d["width"], d["height"], d["openings"]))
    elif intent == "sample":
        note += "\nПробний набір: площа всієї кімнати не потрібна."
    elif details.get("area_mode") == "help":
        note += "\nПотрібна допомога з вимірюванням площі стін."
    elif details.get("area_mode") == "known":
        note += "\nПлощу стін вказав клієнт."
    if not legacy:
        note += "\nСайт: %s%s%s" % (landing_id, "; форма: " + site["form"] if site["form"] else "",
                                     "; стаття/джерело: " + site["article"] if site["article"] else "")
        if site["page_url"]:
            note += "\nСторінка: %s" % site["page_url"]
        if site["message"]:
            note += "\nКоментар клієнта: %s" % site["message"]
        if site["quiz"]:
            note += "\nКвіз: " + "; ".join("%s — %s" % kv for kv in site["quiz"].items())
    Message.objects.create(conversation=conv, direction="out", internal=True, text=note, sender_name="Лендинг")
    type(conv).objects.filter(pk=conv.pk).update(contact=contact, title="[%s] %s" % (landing_id, str(contact)),
        status="open", assigned_to=owner, unread=F("unread") + 1, last_message_at=timezone.now())
    for _recipient in ([owner] if owner else _queue_recipients()):
        Notification.objects.create(user=_recipient, kind="system", conversation=conv, text="Нове звернення з сайту%s #%s. Прийміть задачу #%s та зв’яжіться з клієнтом." % (site_tag, deal.id, receipt.task_id))
    if notify_client and not conv.messages.filter(external_id__startswith="web-contact:").exists():
        Message.objects.create(conversation=conv, direction="out", sender_name="Wallcov",
            external_id="web-contact:%s" % deal.id, text="Звернення збережено. Менеджер уточнить підбір і спосіб зв’язку.")
    _photos(receipt, decoded)
    return response_data(receipt)


@transaction.atomic
def attach_photos(conv, data):
    receipt = LandingSubmission.objects.select_for_update().filter(request_id=str(data.get("submission_id") or ""), conversation=conv).first()
    if not receipt or not receipt.deal_id:
        raise ValueError("Не знайдено звернення для цього фото")
    previous = len(receipt.photos)
    count = _photos(receipt, decode_photos(data.get("photos", [])))
    if count > previous:
        type(conv).objects.filter(pk=conv.pk).update(status="open", unread=F("unread") + 1, last_message_at=timezone.now())
        if receipt.deal.owner_id:
            Notification.objects.create(user_id=receipt.deal.owner_id, kind="system", conversation=conv,
                text="Клієнт додав фото до звернення з сайту #%s." % receipt.deal_id)
        else:
            # нічия заявка — фото бачить уся черга (ті самі отримувачі, що й про нове звернення)
            for _recipient in _queue_recipients():
                Notification.objects.create(user=_recipient, kind="system", conversation=conv,
                    text="Клієнт додав фото до звернення з сайту #%s." % receipt.deal_id)
    return {"ok": True, "deal_id": receipt.deal_id, "photo_count": count}
