"""Transactional landing intake. No messages are sent to external channels here."""
import base64
import hashlib
import io
import json
import re
import secrets
from decimal import Decimal, ROUND_HALF_UP

from django.db import connection, transaction
from django.db.models import F
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError

from apps.accounts.models import User
from apps.crm.models import Contact, Deal, Funnel, Task
from .models import LandingSubmission, Message, Notification, SharedLink
from .services import _phone_variants

LANDING_ID = "wallcovdliastin.com.ua"
PRICES = {"sirena": ("Шовк · Сирена", "0.15", "1265"),
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
    # Existing client ownership wins. Unknown visitors go to the responsible
    # department head, or the active administrator as a visible intake queue.
    ids = [contact.owner_id, conv.assigned_to_id]
    ids += list(funnel.departments.exclude(head=None).order_by("id").values_list("head_id", flat=True))
    for pk in ids:
        user = User.objects.filter(pk=pk, is_active=True, account_kind="staff", employment_status="active").first()
        if user:
            return user
    return User.objects.filter(is_active=True, is_superuser=True, account_kind="staff").order_by("id").first()


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
    return {"ok": True, "deal_id": receipt.deal_id, "duplicate": duplicate,
            "estimate_from": float(q["estimate_from"]), "estimate_to": float(q["estimate_to"]),
            "minimum_order": 220, "calculation": {k: q.get(k, "") for k in calculate("", None, "selection")},
            "photo_count": len(receipt.photos), "conversation_id": receipt.conversation_id}


@transaction.atomic
def receive(conv, data):
    from .webchat import _decimal_area
    if data.get("consent") is not True:
        raise ValueError("Потрібна згода на зв’язок і обробку контактних даних")
    phone = normalize_phone(data.get("phone"))
    area = _decimal_area(data["area"]) if data.get("area") not in (None, "") else None
    product_key = str(data.get("product") or "")
    if product_key and product_key not in PRICES:
        raise ValueError("Невідоме покриття")
    intent = "sample" if data.get("intent") == "sample" else "selection"
    preferred = data.get("preferred") if data.get("preferred") in {"phone", "telegram", "viber"} else "phone"
    request_id = str(data.get("submission_id") or secrets.token_urlsafe(24))
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", request_id):
        raise ValueError("Некоректний номер звернення")
    snapshot = {key: str(data.get(key) or "")[:300] for key in
                ("name", "room", "velvet_color", "velvet_formula", "mood", "installer", "reference", "flow_id", "silk_base")}
    snapshot.update(phone=phone, area=str(area) if area is not None else "", product=product_key, intent=intent, preferred=preferred)
    digest = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    phone_hash = hashlib.sha256(phone.encode()).hexdigest()
    receipt, _ = LandingSubmission.objects.get_or_create(request_id=request_id,
        defaults={"phone_hash": phone_hash, "payload_hash": digest, "conversation": conv})
    receipt = LandingSubmission.objects.select_for_update(of=("self",)).select_related("deal", "conversation").get(pk=receipt.pk)
    if receipt.phone_hash != phone_hash or receipt.payload_hash != digest:
        raise ValueError("Це звернення вже має інший підбір. Почніть новий розрахунок")
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
    funnel = Funnel.objects.filter(name="Лендинг · wallcovdliastin.com.ua").first()
    stage = funnel.stages.order_by("order", "id").first() if funnel else None
    if not stage:
        raise ValueError("Не вдалося прийняти звернення. Зателефонуйте нам або спробуйте пізніше")
    owner = _owner(conv, contact, funnel)
    if owner is None:
        raise ValueError("Черга звернень недоступна. Зателефонуйте нам або спробуйте пізніше")
    first = clean_touch(data.get("first_touch") or data.get("analytics"))
    last = clean_touch(data.get("last_touch"))
    qualification = {"landing_id": LANDING_ID, "submission_id": request_id, "conversation_id": conv.id,
        "room": snapshot["room"], "area_m2": snapshot["area"], "product_key": product_key,
        "product": PRICES[product_key][0] if product_key else "Підібрати з консультантом",
        "velvet_color": snapshot["velvet_color"], "velvet_formula": snapshot["velvet_formula"],
        "silk_base": snapshot["silk_base"], "mood": snapshot["mood"], "installer": snapshot["installer"],
        "reference": snapshot["reference"], "flow_id": snapshot["flow_id"], "intent": intent,
        "preferred_channel": preferred, "utm": first, "first_touch": first, "last_touch": last,
        **calculate(product_key, area, intent)}
    # Old receipts created before this table still deduplicate after a move.
    deal = Deal.objects.filter(contact=contact, qualification__landing_id=LANDING_ID,
                               qualification__submission_id=request_id).first()
    if deal:
        receipt.deal = deal
        receipt.save(update_fields=["deal"])
        return response_data(receipt, True)
    deal = Deal.objects.create(title=("Пробний набір" if intent == "sample" else "Підбір покриття") + " · " + (snapshot["name"][:80] or phone),
        contact=contact, funnel=funnel, stage=stage, owner=owner, source="site", amount=Decimal(qualification["estimate_from"]),
        area_m2=area, qualification=qualification, is_seen=False)
    receipt.deal = deal
    receipt.task = Task.objects.create(kind="manager", title="Прийняти звернення з сайту #%s" % deal.id,
        body="Перевірити підбір і фото. Зв’язатися через %s. Після відповіді записати результат і наступний крок. Автоматичне підтвердження не є відповіддю менеджера." % preferred,
        priority="high", deal=deal, contact=contact, conversation=conv, assignee=owner,
        department=owner.department, status="open", created_by_agent=False)
    receipt.save(update_fields=["deal", "task"])
    note = "Нове звернення #%s · %s\nКімната: %s; площа стін: %s\nКолір: %s; нанесення: %s\nОрієнтир: %s грн (%s). Зв’язок: %s. Задача #%s." % (
        deal.id, qualification["product"], snapshot["room"] or "уточнити", snapshot["area"] or "уточнити",
        snapshot["velvet_color"] or snapshot["mood"] or "підібрати", snapshot["installer"] or "уточнити",
        qualification["estimate_from"], qualification["estimate_kind"], preferred, receipt.task_id)
    Message.objects.create(conversation=conv, direction="out", internal=True, text=note, sender_name="Лендинг")
    type(conv).objects.filter(pk=conv.pk).update(contact=contact, title="[%s] %s" % (LANDING_ID, str(contact)),
        status="open", assigned_to=owner, unread=F("unread") + 1, last_message_at=timezone.now())
    Notification.objects.create(user=owner, kind="system", conversation=conv, text="Нове звернення з сайту #%s. Прийміть задачу #%s та зв’яжіться з клієнтом." % (deal.id, receipt.task_id))
    if not conv.messages.filter(external_id__startswith="web-contact:").exists():
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
    return {"ok": True, "deal_id": receipt.deal_id, "photo_count": count}
