"""Незалежна Meta-інтеграція CRM (БЕЗ Бітрикса): Instagram Direct + IG-коменти +
Facebook Messenger + FB-коменти напряму через Graph API.
Вмикається коли в .env задані META_PAGE_TOKEN / META_VERIFY_TOKEN / META_APP_SECRET."""
import os, json, hmac, hashlib, urllib.parse, urllib.request, urllib.error, re

GRAPH = "https://graph.facebook.com/v21.0"
# Instagram-вхід (IG-личка) шле/приймає через ОКРЕМИЙ домен + свій токен
IG_GRAPH = "https://graph.instagram.com/v21.0"
IG_TOKEN = os.environ.get("META_IG_TOKEN", "")
PAGE_TOKEN = os.environ.get("META_PAGE_TOKEN", "")
VERIFY_TOKEN = os.environ.get("META_VERIFY_TOKEN", "wallcov_crm_verify")
APP_SECRET = os.environ.get("META_APP_SECRET", "")
# Instagram-вхід (IG-личка) йде через ОКРЕМИЙ Instagram-застосунок зі СВОЇМ секретом —
# його вебхуки підписані іншим ключем, тому перевіряємо підпис проти ОБОХ секретів.
IG_APP_SECRET = os.environ.get("META_IG_APP_SECRET", "")
IG_ID = os.environ.get("META_IG_ID", "")
PAGE_ID = os.environ.get("META_PAGE_ID", "")
# Наші власні ідентифікатори — щоб відрізнити відповідь ШІ Юлі / менеджера (наш акаунт)
# від повідомлення клієнта у коментарях та Direct.
_OUR_IDS = {x for x in (IG_ID, PAGE_ID) if x}


def _is_us(author_id):
    """author_id належить нашому бізнес-акаунту (сторінка/IG) → це наша відповідь, не клієнт."""
    return bool(author_id) and str(author_id) in _OUR_IDS


def configured():
    return bool(PAGE_TOKEN)


def verify_signature(raw_body: bytes, header_sig: str) -> bool:
    secrets = [s for s in (APP_SECRET, IG_APP_SECRET) if s]
    if not secrets:
        return True  # якщо жоден секрет не заданий — не перевіряємо (dev)
    if not header_sig or not header_sig.startswith("sha256="):
        return False
    got = header_sig.split("=", 1)[1]
    for sec in secrets:  # підпис від основного АБО Instagram-застосунку
        mac = hmac.new(sec.encode(), raw_body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(mac, got):
            return True
    return False


def _graph(method, path, params=None):
    url = f"{GRAPH}/{path}"
    body = None
    if method == "POST":
        body = urllib.parse.urlencode({**(params or {}), "access_token": PAGE_TOKEN}).encode()
        req = urllib.request.Request(url, data=body)
    else:
        url += "?" + urllib.parse.urlencode({**(params or {}), "access_token": PAGE_TOKEN})
        req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            _d = e.read().decode()[:300]
        except Exception:
            _d = ""
        raise RuntimeError(_friendly_meta_err(e.code, _d))


def _friendly_meta_err(code, body):
    """Замінюємо сирий JSON/німецький текст Meta на зрозуміле пояснення.
    2534037 = наш акаунт не власник IG-треда (тредом володіє ChatPlace/Юля)."""
    b = body or ""
    if "2534037" in b or "owner of the thread" in b or "Eigent" in b:
        return ("Цей Instagram-діалог веде ChatPlace (Юля) — пряма відповідь через Meta "
                "неможлива. Відкрийте діалог цього клієнта на каналі «ChatPlace · Instagram» "
                "і відповідайте там.")
    return "Meta IG %s: %s" % (code, b or "Bad Request")


def _ig_post(path, params):
    """POST через graph.instagram.com з IG-токеном (Instagram-вхід)."""
    body = urllib.parse.urlencode({**params, "access_token": IG_TOKEN}).encode()
    req = urllib.request.Request(f"{IG_GRAPH}/{path}", data=body)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            _d = e.read().decode()[:300]
        except Exception:
            _d = ""
        raise RuntimeError(_friendly_meta_err(e.code, _d))


def send_message(recipient_id: str, text: str, platform: str = "instagram"):
    """Відповісти клієнту в Direct/Messenger. recipient_id = PSID/IGSID.
    Instagram-личка йде через graph.instagram.com + IG-токен; Facebook — через Page."""
    if platform == "instagram" and IG_TOKEN:
        return _ig_post("me/messages", {
            "recipient": json.dumps({"id": recipient_id}),
            "message": json.dumps({"text": text}),
        })
    return _graph("POST", "me/messages", {
        "recipient": json.dumps({"id": recipient_id}),
        "message": json.dumps({"text": text}),
        "messaging_type": "RESPONSE",
    })


def send_attachment(recipient_id: str, url: str, atype: str = "image", platform: str = "instagram"):
    """Надіслати клієнту медіа (фото/відео/аудіо/файл) НАТИВНО в Direct/Messenger по URL.
    atype: image|video|audio|file. Клієнт бачить картинку/відео у переписці, а не текстове посилання."""
    mtype = atype if atype in ("image", "video", "audio", "file") else "file"
    att_msg = json.dumps({"attachment": {"type": mtype, "payload": {"url": url, "is_reusable": False}}})
    if platform == "instagram" and IG_TOKEN:
        return _ig_post("me/messages", {
            "recipient": json.dumps({"id": recipient_id}),
            "message": att_msg,
        })
    return _graph("POST", "me/messages", {
        "recipient": json.dumps({"id": recipient_id}),
        "message": att_msg,
        "messaging_type": "RESPONSE",
    })


def reply_comment(comment_id: str, text: str):
    """Відповісти на коментар IG/FB (публічно)."""
    return _graph("POST", f"{comment_id}/comments", {"message": text})


def _kind(obj):
    return "instagram" if obj == "instagram" else "facebook"


def _media_card(media_id, kind):
    """Картка джерела: підтягнути дані публікації/ролика/реклами, на яку відповів клієнт.
    Повертає dict {media_type, permalink, thumbnail, caption} або порожній dict при помилці/без прав."""
    if not media_id or not PAGE_TOKEN:
        return {}
    try:
        if kind == "instagram":
            d = _graph("GET", str(media_id),
                       {"fields": "media_type,media_url,thumbnail_url,permalink,caption"})
            return {
                "media_type": (d.get("media_type") or "").upper(),  # IMAGE/VIDEO/CAROUSEL_ALBUM/REEL
                "permalink": d.get("permalink") or "",
                "thumbnail": d.get("thumbnail_url") or d.get("media_url") or "",
                "caption": (d.get("caption") or "")[:280],
            }
        # facebook post
        d = _graph("GET", str(media_id),
                   {"fields": "permalink_url,message,full_picture,attachments{media_type}"})
        att = (((d.get("attachments") or {}).get("data") or [{}])[0]) if d.get("attachments") else {}
        return {
            "media_type": (att.get("media_type") or "").upper(),
            "permalink": d.get("permalink_url") or "",
            "thumbnail": d.get("full_picture") or "",
            "caption": (d.get("message") or "")[:280],
        }
    except Exception:
        return {}


def _profile_name(sender_id):
    """Return a sender name without making it a prerequisite for ingestion."""
    if not PAGE_TOKEN:
        return ""
    try:
        profile = _graph("GET", str(sender_id), {"fields": "name"})
        name = str((profile or {}).get("name") or "").strip()
        if name:
            return name
    except Exception:
        pass
    # Meta may deny the direct PSID profile edge for a normal Page user while
    # still exposing that participant through the Page conversation itself.
    if PAGE_ID:
        try:
            result = _graph("GET", f"{PAGE_ID}/conversations", {
                "user_id": str(sender_id), "fields": "participants", "limit": 1,
            })
            for conversation in (result or {}).get("data", []):
                for participant in (conversation.get("participants") or {}).get("data", []):
                    if str(participant.get("id")) == str(sender_id):
                        return str(participant.get("name") or "").strip()
        except Exception:
            pass
    return ""


def _ig_get(path, params=None):
    """GET через graph.instagram.com з IG-токеном (Instagram-вхід)."""
    url = f"{IG_GRAPH}/{path}?" + urllib.parse.urlencode({**(params or {}), "access_token": IG_TOKEN})
    with urllib.request.urlopen(urllib.request.Request(url), timeout=15) as r:  # noqa: S310
        return json.load(r)


def _meta_profile(sender_id, kind):
    """Повертає (повне_ім'я, нік) автора Meta. Instagram → graph.instagram.com (name+username);
    Facebook → Page (тільки name)."""
    if kind == "instagram" and IG_TOKEN:
        try:
            d = _ig_get(str(sender_id), {"fields": "name,username"})
            return (str((d or {}).get("name") or "").strip(), str((d or {}).get("username") or "").strip())
        except Exception:
            pass
    return (_profile_name(sender_id), "")


_PLACEHOLDER_NAMES = {"", "instagram", "facebook", "client", "customer", "клиент", "клієнт"}


def _clean_username(value):
    """Повернути справжній username, але не платформний числовий ID/плейсхолдер."""
    username = str(value or "").strip().lstrip("@").strip()
    if not username or username.isdigit() or username.lower() in _PLACEHOLDER_NAMES:
        return ""
    return username[:150]


def _resolve_meta_identity(sender_id, kind, name="", username=""):
    """Доповнити передані ім'я/username даними профілю Meta, не замінюючи кращі значення."""
    clean_name = str(name or "").strip()
    clean_username = _clean_username(username)
    if sender_id and (not clean_name or not clean_username):
        fetched_name, fetched_username = _meta_profile(sender_id, kind)
        clean_name = clean_name or str(fetched_name or "").strip()
        clean_username = clean_username or _clean_username(fetched_username)
    return clean_name[:240], clean_username


def _contact_identity_changes(contact, kind, name="", username=""):
    """Порахувати лише безпечні дозаповнення контакту. Реальні дані менеджера не перезаписуємо."""
    name = str(name or "").strip()
    username = _clean_username(username)
    current_name = " ".join(x for x in (
        str(contact.first_name or "").strip(), str(contact.last_name or "").strip()
    ) if x)
    current_nick = _clean_username(getattr(contact, "nickname", ""))
    placeholder_name = (not current_name or current_name.lower() in _PLACEHOLDER_NAMES
                        or current_name.isdigit())
    changes = {}
    if placeholder_name and (name or username):
        parts = (name or username).split(None, 1)
        changes["first_name"] = (parts[0] if parts else username)[:120]
        changes["last_name"] = (parts[1] if len(parts) > 1 else "")[:120]
    if username and not current_nick:
        changes["nickname"] = username
    channels = list(getattr(contact, "channels", None) or [])
    if kind and kind not in channels:
        changes["channels"] = channels + [kind]
    if kind == "instagram" and username:
        link = f"https://instagram.com/{username}"
        if not str(getattr(contact, "social_link", "") or "").strip():
            changes["social_link"] = link
        messengers = list(getattr(contact, "messengers", None) or [])
        if link not in messengers:
            changes["messengers"] = messengers + [link]
    return changes


def _contact_lead_title(contact, fallback=""):
    """Назва ліда = як у картці клієнта: «Ім'я Прізвище (@нік)». Fallback — IGSID/PSID."""
    base = str(contact).strip() if contact else ""
    nick = (getattr(contact, "nickname", "") or "").strip()
    if base.lower() in ("instagram", "facebook", "tiktok"):
        base = ""  # заглушка назви каналу — це НЕ ім'я клієнта
    if nick and nick.lower() not in base.lower():
        return (f"{base} (@{nick})" if base else f"@{nick}")[:255]
    return (base or str(fallback))[:255]


def _refresh_lead_titles(contact):
    """Оновити назви лідів контакту, що лишились з голим IGSID/заглушкою «instagram/facebook»,
    на людяне «Ім'я (@нік)». Не чіпає назви, які менеджер задав вручну."""
    try:
        from apps.crm.models import Lead
        new_title = _contact_lead_title(contact)
        if not new_title:
            return
        for ld in Lead.objects.filter(contact=contact):
            old = (ld.title or "").strip()
            placeholder = (not old) or old.isdigit() or old.lower() in ("instagram", "facebook")
            if placeholder and old != new_title:
                ld.title = new_title
                ld.save(update_fields=["title"])
    except Exception:
        pass


def _enrich_contact(contact, kind, sender_id, name="", username=""):
    """Дозаповнити контакт з Meta. Повертає список реально змінених полів."""
    name, username = _resolve_meta_identity(sender_id, kind, name, username)
    changes = _contact_identity_changes(contact, kind, name, username)
    if changes:
        for field, value in changes.items():
            setattr(contact, field, value)
        contact.save(update_fields=list(changes))
        _refresh_lead_titles(contact)   # ім'я підтяглось → оновити й назву ліда
    return list(changes)


def _get_or_make_contact(kind, sender_id, name="", username=""):
    """Знайти/створити контакт для автора Meta. Тягне ім'я+нік (IG через graph.instagram.com).
    Заголовок чату = «Ім'я Прізвище (@нік)»."""
    from apps.crm.models import Contact
    name, username = _resolve_meta_identity(sender_id, kind, name, username)
    parts = (name or "").split(None, 1)
    fn = ((parts[0] if parts else "") or username or kind)[:120]
    ln = (parts[1] if len(parts) > 1 else "")[:120]
    link = f"https://instagram.com/{username}" if kind == "instagram" and username else ""
    return Contact.objects.create(
        first_name=fn, last_name=ln, nickname=username,
        channels=[kind] if kind else [], social_link=link,
        messengers=([link] if link else []), comment=f"З {kind} (Meta)",
    )


def _meta_attribution(kind, *nodes, source_context=""):
    """Витягнути лише стабільні рекламні ID, не зберігаючи сирий webhook.

    Наявність Instagram/Facebook-джерела сама по собі не є рекламою. Якщо Meta
    не передала ad/lead-form ID, запис залишається органічним і не потрапляє до
    Conversions API.
    """
    aliases = {
        "lead_id": ("lead_id", "leadgen_id"),
        "form_id": ("form_id",),
        "ad_id": ("ad_id",),
        "adset_id": ("adset_id", "ad_set_id"),
        "campaign_id": ("campaign_id",),
        "referral_id": ("referral_id",),
        "content_id": ("content_id", "post_id", "media_id"),
        # людяні дані креативу з referral.ads_context_data — щоб менеджер одразу
        # бачив, з якого оголошення прийшов клієнт (назва + мініатюра)
        "ad_ref": ("ref",),
        "ad_title": ("ad_title",),
        "ad_thumb": ("photo_url", "video_url"),
    }
    found = {}

    def walk(value):
        if isinstance(value, dict):
            for out_key, keys in aliases.items():
                if out_key in found:
                    continue
                for key in keys:
                    candidate = value.get(key)
                    if isinstance(candidate, (str, int)) and str(candidate).strip():
                        found[out_key] = str(candidate).strip()[:180]
                        break
            for child in value.values():
                if isinstance(child, (dict, list)):
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for node in nodes:
        walk(node)
    if found.get("lead_id"):
        source_kind = "lead_form"
    elif any(found.get(key) for key in ("ad_id", "campaign_id", "referral_id")):
        source_kind = "paid_ad"
    else:
        source_kind = "organic"
    return {
        "source_kind": source_kind,
        "platform": kind,
        "source_context": source_context,
        **found,
    }


def _new_meta_lead(conv, kind, sender_id, name="", username="", attribution=None):
    """Створити контакт + лід для нового вхідного чату Meta (FB/IG). Джерело = канал."""
    from apps.crm.models import Lead, Funnel
    name, username = _resolve_meta_identity(sender_id, kind, name, username)
    if not conv.contact_id:
        conv.contact = _get_or_make_contact(kind, sender_id, name, username)
        conv.save(update_fields=["contact"])
    else:
        _enrich_contact(conv.contact, kind, sender_id, name, username)
    try:
        f = Funnel.objects.filter(name="Лиды").first() or Funnel.objects.order_by("id").first()
        st = f.stages.order_by("order").first() if f else None
        if f and st:
            src = "instagram" if kind == "instagram" else "facebook"
            Lead.objects.create(title=_contact_lead_title(conv.contact, sender_id),
                                contact=conv.contact, funnel=f, stage=st, source=src, is_seen=False,
                                meta_attribution=(attribution or {}))
    except Exception:
        pass


def _extract_ad_referral(ev, msg):
    """Знайти обʼєкт переходу з реклами (referral) у Direct-події. Meta присилає його
    трьома шляхами; беремо перший знайдений:
      1) message.referral — клієнт написав перше повідомлення після кліку по рекламі;
      2) top-level referral — повторний вхід по рекламі/лінку у наявну переписку;
      3) postback.referral — перший тап по кнопці привітання/icebreaker з реклами.
    Повертає dict referral або {}."""
    return (
        (msg or {}).get("referral")
        or ev.get("referral")
        or ((ev.get("postback") or {}).get("referral"))
        or {}
    )


def _apply_ad_attribution(channel, kind, sender_id, ref_obj, ev, msg):
    """Записати рекламну атрибуцію на лід контакта по НОМЕРУ ПЕРЕПИСКИ (IGSID/PSID).

    Ключ звʼязку — sender_id: він спільний для Meta й ChatPlace, тож навіть лід, який
     веде ChatPlace-Юля, отримає мітку реклами. Ловимо навіть подію «лише referral»
    без тексту (клік по рекламі ще без повідомлення). Не перезаписуємо вже підтверджену
    рекламу.
    """
    from apps.crm.models import Lead, Deal
    from .models import Conversation
    attr = _meta_attribution(kind, ev or {}, msg or {}, ref_obj or {}, source_context="ad_referral")
    if attr.get("source_kind") != "paid_ad":
        return False  # без ad_id/campaign_id це не платний клік — не чіпаємо
    ext = str(sender_id)[:128]
    conv = (Conversation.objects.filter(channel=channel, external_chat_id=ext)
            .select_related("contact").first())
    if not conv:
        # діалогу ще нема (referral прилетів першим) — створюємо, щоб не втратити клік
        conv, _ = Conversation.objects.get_or_create(
            channel=channel, external_chat_id=ext, defaults={"title": kind})
    if not conv.contact_id:
        _new_meta_lead(conv, kind, sender_id, attribution=attr)
        return True
    contact = conv.contact
    lead = Lead.objects.filter(contact=contact).order_by("-id").first()
    if not lead:
        _new_meta_lead(conv, kind, sender_id, attribution=attr)
        return True
    if (lead.meta_attribution or {}).get("source_kind") != "paid_ad":
        lead.meta_attribution = attr
        lead.save(update_fields=["meta_attribution"])
        # перенести мітку на угоди контакта, у яких її ще немає
        for d in Deal.objects.filter(contact=contact):
            if (d.meta_attribution or {}).get("source_kind") != "paid_ad":
                d.meta_attribution = attr
                d.save(update_fields=["meta_attribution"])
    return True


def _handle_leadgen(value):
    """Заявка з лід-форми Meta (реклама з формою «Отримати пропозицію»).
    value містить leadgen_id/form_id/ad_id. Тягнемо повні відповіді форми через Graph
    і створюємо контакт + лід з атрибуцією lead_form. Дедуп по leadgen_id."""
    from apps.crm.models import Lead, Funnel, Contact
    leadgen_id = str(value.get("leadgen_id") or value.get("leadgen_id".upper()) or "")
    if not leadgen_id or not PAGE_TOKEN:
        return False
    if Lead.objects.filter(meta_attribution__lead_id=leadgen_id).exists():
        return False  # вже завели цю заявку
    try:
        data = _graph("GET", leadgen_id,
                      {"fields": "field_data,ad_id,form_id,campaign_id,adset_id,created_time"})
    except Exception:
        data = {}
    fields = {}
    for f in (data.get("field_data") or []):
        n = (f.get("name") or "").lower()
        vals = f.get("values") or []
        if vals:
            fields[n] = str(vals[0])
    full = (fields.get("full_name") or fields.get("name")
            or (fields.get("first_name", "") + " " + fields.get("last_name", "")).strip())
    phone = (fields.get("phone_number") or fields.get("phone") or "")[:32]
    email = (fields.get("email") or "")[:190]
    attr = {
        "source_kind": "lead_form", "platform": "facebook", "source_context": "leadgen",
        "lead_id": leadgen_id,
        "form_id": str(value.get("form_id") or data.get("form_id") or "")[:180],
        "ad_id": str(value.get("ad_id") or data.get("ad_id") or "")[:180],
        "campaign_id": str(value.get("campaign_id") or data.get("campaign_id") or "")[:180],
        "adset_id": str(value.get("adset_id") or data.get("adset_id") or "")[:180],
    }
    parts = (full or "").split(None, 1)
    ct = None
    if phone:
        ct = Contact.objects.filter(phone=phone).first()
    if not ct and email:
        ct = Contact.objects.filter(email__iexact=email).first()
    if not ct:
        ct = Contact.objects.create(
            first_name=((parts[0] if parts else "") or "Заявка з форми")[:120],
            last_name=(parts[1] if len(parts) > 1 else "")[:120],
            phone=phone, email=email)
    f = Funnel.objects.filter(name="Лиды").first() or Funnel.objects.order_by("id").first()
    st = f.stages.order_by("order").first() if f else None
    if f and st:
        Lead.objects.create(title=(full or phone or "Лід-форма")[:255],
                            contact=ct, funnel=f, stage=st, source="facebook", is_seen=False,
                            meta_attribution=attr)
    return True


def _story_ref(msg):
    """Витягнути посилання на історію з Direct-повідомлення (відповідь на історію / згадка в історії).
    Повертає dict для attachments або None."""
    reply_to = msg.get("reply_to") or {}
    story = reply_to.get("story") or {}
    if story.get("url") or story.get("id"):
        return {"type": "story_ref", "kind": "reply", "url": story.get("url", ""),
                "story_id": story.get("id", ""), "name": "Відповідь на історію"}
    for a in (msg.get("attachments") or []):
        if ((a or {}).get("type") or "").lower() == "story_mention":
            url = (((a or {}).get("payload") or {}).get("url") or "")
            return {"type": "story_ref", "kind": "mention", "url": url, "name": "Згадка в історії"}
    return None


def _reply_ref(msg, conv):
    """Зберегти зрозумілий preview повідомлення, на яке відповів клієнт.

    Meta передає ``reply_to.mid``. Шукаємо ціль ТІЛЬКИ у поточному діалозі,
    щоб однаковий platform ID з іншого каналу ніколи не підмінив контекст.
    Preview копіюємо у нове повідомлення: воно залишиться читабельним навіть
    якщо оригінальне медіа пізніше стане недоступним у Meta.
    """
    from .models import Message

    reply_to = msg.get("reply_to") or {}
    external_id = str(reply_to.get("mid") or reply_to.get("message_id") or "")[:128]
    if not external_id:
        return None
    target = Message.objects.filter(conversation=conv, external_id=external_id).first()
    if not target:
        return {"type": "reply_ref", "external_id": external_id, "target_id": None}

    media = next((dict(a) for a in (target.attachments or [])
                  if (a or {}).get("type") in ("photo", "video", "voice", "file")), None)
    return {
        "type": "reply_ref",
        "external_id": external_id,
        "target_id": target.id,
        "direction": target.direction,
        "sender_name": target.sender_name,
        "text": (target.text or "")[:500],
        "attachment": media,
    }


def _store_reaction(channel, event):
    """Додати/зняти реакцію Meta біля конкретного CRM-повідомлення.

    Повторна доставка webhook ідемпотентна: у одного клієнта може бути лише
    одна поточна реакція на це повідомлення. Реакція не створює окремий
    ``Message`` і тому не засмічує діалог.
    """
    from django.db import transaction
    from django.utils import timezone
    from .models import Conversation, Message

    data = event.get("reaction") or {}
    sender_id = str((event.get("sender") or {}).get("id") or "")
    recipient_id = str((event.get("recipient") or {}).get("id") or "")
    external_id = str(data.get("mid") or "")[:128]
    action = str(data.get("action") or "").lower()
    if not sender_id or not external_id or action not in ("react", "unreact"):
        return False

    ext_chat = recipient_id if _is_us(sender_id) else sender_id
    with transaction.atomic():
        conv = (Conversation.objects.select_for_update()
                .filter(channel=channel, external_chat_id=ext_chat).first())
        if not conv:
            return False
        target = (Message.objects.select_for_update()
                  .filter(conversation=conv, external_id=external_id).first())
        if not target:
            return False

        actor = "business" if _is_us(sender_id) else "customer"
        old = list(target.attachments or [])
        updated = [a for a in old if not (
            (a or {}).get("type") == "message_reaction"
            and str((a or {}).get("actor_id") or "") == sender_id
        )]
        if action == "react":
            updated.append({
                "type": "message_reaction",
                "actor_id": sender_id,
                "actor": actor,
                "reaction": str(data.get("reaction") or "other")[:32],
                "emoji": str(data.get("emoji") or "")[:16],
            })
        changed = updated != old
        if changed:
            target.attachments = updated
            target.save(update_fields=["attachments"])
            if actor == "customer" and action == "react":
                conv.unread = (conv.unread or 0) + 1
                conv.last_message_at = timezone.now()
                conv.save(update_fields=["unread", "last_message_at"])
        return True


def _event_time(value):
    """Meta timestamp (milliseconds) -> aware datetime, or ``None``."""
    from datetime import datetime, timezone as dt_timezone

    try:
        return datetime.fromtimestamp(float(value) / 1000.0, tz=dt_timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _status_rank(status):
    return {"sent": 1, "delivered": 2, "read": 3}.get(str(status or ""), 0)


def _mark_previous_outgoing_read(conversation, event_timestamp=None):
    """A fresh customer message proves that earlier outbound messages were read.

    Instagram can route the Direct conversation through ChatPlace, so the Meta
    app does not always receive a separate ``messaging_seen`` receipt.  A real
    incoming message is nevertheless an unambiguous acknowledgement for every
    successful outbound that existed before it.  Keep failed messages intact
    and use the provider timestamp to avoid marking a later reply as read when
    delivery is delayed.
    """
    from datetime import timedelta
    from django.utils import timezone
    from .models import Message

    observed_at = _event_time(event_timestamp) or timezone.now()
    # A few seconds absorb clock skew without crossing into a later manager
    # reply.  ChatPlace-synced messages that arrive much later will be covered
    # by the next customer message or an exact Meta seen receipt.
    cutoff = min(timezone.now(), observed_at + timedelta(seconds=5))
    return Message.objects.filter(
        conversation=conversation,
        direction="out",
        internal=False,
        created_at__lte=cutoff,
        status__in=("sent", "delivered", "window_risk"),
    ).update(status="read")


def _store_delivery_status(channel, event):
    """Apply Messenger delivery/read and Instagram seen receipts.

    Messenger delivery events may contain exact ``mids`` and/or a ``watermark``.
    Messenger read events use a watermark; Instagram ``messaging_seen`` gives an
    exact ``read.mid``. Statuses only move forward, so a delayed delivery event
    never changes an already-read message back to "delivered".
    """
    from .models import Conversation, Message

    delivery = event.get("delivery") or {}
    read = event.get("read") or {}
    if not delivery and not read:
        return 0

    sender_id = str((event.get("sender") or {}).get("id") or "")
    recipient_id = str((event.get("recipient") or {}).get("id") or "")
    ext_chat = recipient_id if _is_us(sender_id) else sender_id
    if not ext_chat:
        return 0
    conv = Conversation.objects.filter(channel=channel, external_chat_id=ext_chat).first()
    if not conv:
        return 0

    target_status = "read" if read else "delivered"
    data = read or delivery
    mids = [str(mid)[:128] for mid in (data.get("mids") or []) if mid]
    if data.get("mid"):
        mids.append(str(data.get("mid"))[:128])

    qs = Message.objects.filter(conversation=conv, direction="out", internal=False)
    if mids:
        from django.db.models import Q
        exact_ids = set(mids)
        qs = qs.filter(Q(external_id__in=exact_ids) | Q(meta_external_id__in=exact_ids))
    else:
        watermark = _event_time(data.get("watermark") or event.get("timestamp"))
        if not watermark:
            return 0
        qs = qs.filter(created_at__lte=watermark)

    changed = 0
    for message in qs.only("id", "status"):
        if _status_rank(target_status) <= _status_rank(message.status):
            continue
        message.status = target_status
        message.save(update_fields=["status"])
        changed += 1
    return changed


def _store_message_edit(channel, event):
    """Replace an existing Meta message with the customer's edited text.

    The former versions are kept inside a context attachment. This makes the
    visible message current while retaining an audit trail and keeps retries
    idempotent (the same edit is never appended twice).
    """
    from django.db import transaction
    from django.utils import timezone
    from .models import Conversation, Message

    edit = event.get("message_edit") or event.get("message_edits") or {}
    mid = str(edit.get("mid") or edit.get("message_id") or "")[:128]
    new_text = str(edit.get("text") or "")[:5000]
    sender_id = str((event.get("sender") or {}).get("id") or "")
    recipient_id = str((event.get("recipient") or {}).get("id") or "")
    if not mid or not new_text or not sender_id:
        return False

    ext_chat = recipient_id if _is_us(sender_id) else sender_id
    edited_at = _event_time(event.get("timestamp")) or timezone.now()
    num_edit = edit.get("num_edit")

    with transaction.atomic():
        conv = (Conversation.objects.select_for_update()
                .filter(channel=channel, external_chat_id=ext_chat).first())
        if not conv:
            return False
        target = (Message.objects.select_for_update()
                  .filter(conversation=conv, external_id=mid).first())
        if not target or target.text == new_text:
            return False

        attachments = list(target.attachments or [])
        history = next((a for a in attachments
                        if (a or {}).get("type") == "message_edit_history"), None)
        if history is None:
            history = {"type": "message_edit_history", "revisions": []}
            attachments.append(history)
        revisions = list(history.get("revisions") or [])
        revisions.append({
            "text": (target.text or "")[:5000],
            "edited_at": edited_at.isoformat(),
            "num_edit": num_edit,
        })
        history["revisions"] = revisions[-20:]
        history["last_edited_at"] = edited_at.isoformat()
        history["num_edit"] = num_edit if num_edit is not None else len(revisions)

        target.text = new_text
        target.attachments = attachments
        target.save(update_fields=["text", "attachments"])
        if target.direction == "in":
            conv.unread = (conv.unread or 0) + 1
            conv.last_message_at = timezone.now()
            conv.save(update_fields=["unread", "last_message_at"])
        return True


def _relink_manager_echo(conv, mid, text, event_timestamp=None):
    """Прив'язати Meta echo до вже записаного НАШОГО вихідного (менеджер/авто/через ChatPlace),
    щоб не задвоювати повідомлення.

    Наші вихідні Instagram ідуть через ChatPlace і пишуться локально БЕЗ Meta mid
    (external_id порожній) — а хвилину-другу потому Meta присилає echo того самого
    тексту з новим mid. Привʼязуємо цей mid до вже наявного вихідного з тим самим
    текстом у цьому діалозі (найближче за часом, у межах вікна).

    Безпека: Meta mid зберігаємо окремо від ChatPlace id. Беремо рівно одного
    кандидата з тим самим текстом у короткому вікні; якщо кандидатів кілька,
    нічого не склеюємо. Це не дає двом реальним однаковим «Готово» помінятися id.
    """
    from .models import Message
    from django.utils import timezone
    from datetime import datetime, timedelta, timezone as dt_timezone

    body = str(text or "")
    if not mid or not body:
        return False
    center = timezone.now()
    try:
        if event_timestamp:
            center = datetime.fromtimestamp(float(event_timestamp) / 1000.0, tz=dt_timezone.utc)
    except (TypeError, ValueError, OSError):
        pass
    WINDOW = 5
    candidates = list(Message.objects.filter(
            conversation=conv, direction="out", internal=False, text=body,
            meta_external_id="",
            created_at__gte=center - timedelta(seconds=WINDOW),
            created_at__lte=center + timedelta(seconds=WINDOW)).order_by("id")[:2])
    if len(candidates) != 1:
        return False
    cand = candidates[0]
    cand.meta_external_id = str(mid)[:128]
    cand.save(update_fields=["meta_external_id"])
    return True


def handle_webhook(payload: dict):
    """Розібрати вебхук Meta → створити/оновити Conversation+Message+Contact у CRM.
    Підтримує: IG/FB Direct (messaging, story reply/mention) + IG/FB коменти (changes).
    Коментарі групуються по «клієнт + публікація» (окремий чат на кожну зв'язку)."""
    from .models import Channel, Conversation, Message
    obj = payload.get("object")
    n_msg = 0
    for entry in payload.get("entry", []):
        kind = _kind(obj)
        ch, _ = Channel.objects.get_or_create(name=f"Meta · {kind}", defaults={"kind": kind, "config": {"meta": True, "platform": obj}})
        # 1) Direct / Messenger. Conversation Routing може передавати події
        # застосунку, який не володіє потоком, у верхньорівневому standby.
        # Новий Page Webhooks UI також загортає messages у changes[].value.
        changes = list(entry.get("changes") or [])
        direct_events = (list(entry.get("messaging") or [])
                         + list(entry.get("standby") or [])
                         + [(chg.get("value") or {}) for chg in changes
                            if chg.get("field") in (
                                "messages", "message_reactions", "message_deliveries",
                                "message_reads", "messaging_seen", "message_edit", "message_edits",
                            )])
        for ev in direct_events:
            sender = (ev.get("sender") or {}).get("id")
            recipient = (ev.get("recipient") or {}).get("id")
            if ev.get("delivery") or ev.get("read"):
                n_msg += _store_delivery_status(ch, ev)
                continue
            if ev.get("message_edit") or ev.get("message_edits"):
                if _store_message_edit(ch, ev):
                    n_msg += 1
                continue
            if ev.get("reaction"):
                if _store_reaction(ch, ev):
                    n_msg += 1
                continue
            msg = ev.get("message") or {}
            # Перехід з реклами: ловимо номер оголошення (referral.ad_id) навіть якщо
            # подія прийшла БЕЗ тексту (клік по рекламі ще без повідомлення). Клеїмо
            # мітку на лід по номеру переписки — навіть якщо діалог веде ChatPlace-Юля.
            ref_obj = _extract_ad_referral(ev, msg)
            if ref_obj and sender and not _is_us(sender):
                try:
                    _apply_ad_attribution(ch, kind, sender, ref_obj, ev, msg)
                except Exception:
                    pass
            if not sender or not msg:
                continue
            mid = (msg.get("mid", "") or "")[:128]  # Instagram-вхід дає ДОВГИЙ mid — поле max 128
            is_echo = msg.get("is_echo")  # надіслане нами (менеджер АБО ШІ Юля через ChatPlace)
            ext_chat = str(sender if not is_echo else recipient)[:128]
            conv, created = Conversation.objects.get_or_create(channel=ch, external_chat_id=str(ext_chat), defaults={"title": kind})
            was_closed = (not created) and conv.status == "closed"
            if not is_echo:
                if created or not conv.contact_id:
                    _new_meta_lead(
                        conv, kind, sender,
                        attribution=_meta_attribution(kind, ev, msg, source_context="direct"),
                    )
                else:
                    # Старий чат міг створитися до появи профільного lookup. Нове повідомлення
                    # повинно дозаповнити ім'я/прізвище/username, не створюючи нового контакту.
                    _enrich_contact(conv.contact, kind, sender)
            else:
                # Наша відповідь (Юля/менеджер). recipient = клієнт (IGSID/PSID).
                if not conv.contact_id:
                    # Діалог почався з НАШОГО повідомлення (Юля дожимає клієнта, який
                    # писав давно) → контакту ще нема. Створюємо контакт+лід одразу з
                    # профілем, щоб діалог не лишався безіменним «instagram».
                    try:
                        _new_meta_lead(conv, kind, recipient)
                    except Exception:
                        pass
                else:
                    # Імʼя ще заглушка (при 1-му вхідному Meta не віддала профіль) —
                    # дотягуємо профіль клієнта.
                    ct = conv.contact
                    _fn = (ct.first_name or "").strip()
                    if (not _fn) or _fn.lower() in ("instagram", "facebook") or _fn.isdigit():
                        try:
                            _enrich_contact(ct, kind, recipient)
                        except Exception:
                            pass
            if Message.objects.filter(conversation=conv, external_id=mid).exists():
                continue
            # Наше вихідне через ПРЯМИЙ Meta вже записане з Meta-mid у meta_external_id
            # (external_id порожній). Echo того самого mid НЕ має створювати дубль-«ai_assistant».
            if mid and Message.objects.filter(conversation=conv, meta_external_id=mid).exists():
                continue
            # ДОДАТКОВИЙ дедуп echo (Олег 29.08 — задвоєння IG): наше вихідне вже записане
            # (менеджер/агент відправив через CRM), АЛЕ mid не зберігся (window_risk / прямий
            # send без id). Echo того самого ТЕКСТУ за останні 10 хв — це НЕ новий дубль:
            # доклеюємо mid до наявного повідомлення і, якщо Meta підтвердив доставку, знімаємо
            # позначку window_risk. Раніше через це зʼявлявся дубль-«ai_assistant» (Юля).
            if is_echo and mid:
                _etx = (msg.get("text") or "").strip()
                if _etx:
                    from django.utils import timezone as _tzx
                    from datetime import timedelta as _tdx
                    from django.db.models import Q as _Qx
                    # ще НЕ звірене з Meta = meta_external_id порожній (ChatPlace-відправка має
                    # свій external_id, тому фільтруємо саме по meta_external_id, а не external_id).
                    _own = (Message.objects.filter(conversation=conv, direction="out", text=_etx[:5000])
                            .filter(_Qx(meta_external_id="") | _Qx(meta_external_id__isnull=True))
                            .filter(created_at__gte=_tzx.now() - _tdx(minutes=10))
                            .order_by("-created_at").first())
                    if _own:
                        _flds = ["meta_external_id"]
                        _own.meta_external_id = mid
                        if not (_own.external_id or "").strip():
                            _own.external_id = mid; _flds.append("external_id")
                        if getattr(_own, "status", "") == "window_risk":
                            _own.status = "sent"; _flds.append("status")
                        _own.save(update_fields=_flds)
                        continue
            if is_echo and _relink_manager_echo(
                    conv, mid, msg.get("text") or "", ev.get("timestamp")):
                continue
            if not is_echo:
                _mark_previous_outgoing_read(conv, ev.get("timestamp"))
            # вкладення (фото/відео/аудіо/файл) з Instagram/Messenger-вебхука
            atts = []
            for a in (msg.get("attachments") or []):
                url = (((a or {}).get("payload") or {}).get("url") or "").strip()
                if not url:
                    continue
                atyp = ((a or {}).get("type") or "").lower()
                attachment_kind = "photo" if atyp in ("image", "photo") else ("video" if atyp == "video" else ("voice" if atyp in ("audio", "voice") else "file"))
                atts.append({"type": attachment_kind, "url": url,
                             "name": ("фото" if attachment_kind == "photo" else attachment_kind)})
            # відповідь на історію / згадка в історії — картка історії в повідомленні
            sref = _story_ref(msg)
            if sref:
                atts.append(sref)
            # Звичайна відповідь на конкретне фото/текст у Direct.
            # Story reply обробляється окремою карткою вище.
            rref = _reply_ref(msg, conv)
            if rref:
                atts.insert(0, rref)
            # echo = надіслане з нашого акаунту. Якщо менеджер відповів через CRM — те саме mid
            # вже записане з sender=менеджер і дедуплікується вище. Значить echo, що дійшло сюди,
            # надіслала ШІ Юля через ChatPlace → позначаємо «ai_assistant» (щоб менеджер бачив ХТО відповів).
            Message.objects.create(conversation=conv, direction=("out" if is_echo else "in"),
                                   text=(msg.get("text") or ("📷 Фото" if atts else ""))[:5000],
                                   attachments=atts, external_id=mid,
                                   sender_name=("ai_assistant" if is_echo else ""))
            conv.unread = (conv.unread or 0) + (0 if is_echo else 1)
            if (not is_echo) and was_closed:
                # Клієнт написав у ЗАКРИТИЙ діалог → відкриваємо. В ПЕРШУ ЧЕРГУ віддаємо
                # відповідальному за клієнта менеджеру (contact.owner) — щоб чат зʼявився
                # у нього в «Мої», а не в загальному списку. Якщо власника нема (вів ІІ /
                # новий клієнт) → вільний пул (assigned_to=None).
                conv.status = "open"
                from apps.crm.models import Contact as _Ct_reopen
                _own = (_Ct_reopen.objects.filter(id=conv.contact_id, owner__is_active=True).values_list("owner_id", flat=True).first()
                        if conv.contact_id else None)
                conv.assigned_to_id = _own
                was_closed = False
                try:
                    from apps.crm.models import log_activity as _la_r
                    _la_r("contact", conv.contact_id or 0, "Повернувся з ігнору",
                          "клієнт написав у закритий діалог", None, "Система")
                except Exception:
                    pass
            from django.utils import timezone
            conv.last_message_at = timezone.now()
            conv.save()
            n_msg += 1
        # 2) Коментарі (changes → field comments/feed): чат = «клієнт + публікація»
        for chg in changes:
            field = chg.get("field")
            val = chg.get("value") or {}
            if field == "leadgen":
                try:
                    if _handle_leadgen(val):
                        n_msg += 1
                except Exception:
                    pass
                continue
            if field not in ("comments", "feed"):
                continue
            if val.get("item") and val.get("item") != "comment":
                continue
            cid = val.get("comment_id") or val.get("id")
            frm = val.get("from") or {}
            author_id = str(frm.get("id") or "")
            author_username = (frm.get("username") or "").strip()
            author_name = (frm.get("name") or frm.get("username") or "")[:160]
            text = val.get("text") or val.get("message") or ""
            if not cid or not text:
                continue
            post_id = str(val.get("post_id") or (val.get("media") or {}).get("id") or cid)
            parent_id = str((val.get("parent") or {}).get("id") or val.get("parent_id") or "")
            is_ad = bool(val.get("is_ad") or (val.get("media") or {}).get("ad_id") or val.get("ad_id"))

            # ХТО написав: наш акаунт (відповідь ШІ Юлі) чи клієнт?
            ours = _is_us(author_id)
            target = None            # знайдений чат (для нашої відповіді через parent)
            if ours:
                # відповідь Юлі — клієнт це @нік на початку тексту («@koa2108 ...»)
                mm = re.match(r"\s*@([A-Za-z0-9._]+)", text)
                client_key = (mm.group(1) if mm else "").lower()
                if not client_key and parent_id:
                    pm = Message.objects.filter(external_id=parent_id).first()
                    if pm:
                        target = pm.conversation
                direction = "out"
                sname = "ai_assistant"      # серіалізатор покаже «Юля (AI)»
                client_name = client_key or author_name
            else:
                # коментар клієнта
                client_key = (author_username or author_id).lower()
                direction = "in"
                sname = author_username or author_name  # у чаті видно НІК КЛІЄНТА, не наш канал
                client_name = author_username or author_name

            # чат = «клієнт + публікація». Шукаємо існуючий: (1) по username-ключу; (2) по ніку
            # контакту під цим постом — легасі-чати створювались по author_id, щоб клієнт не роздвоювався.
            created = False
            if target is None:
                if not client_key:
                    client_key = (author_id or cid).lower()
                ext_chat = f"comment:{kind}:{post_id}:{client_key}"[:128]
                target = Conversation.objects.filter(channel=ch, external_chat_id=str(ext_chat)).first()
                if target is None:
                    target = (Conversation.objects.filter(channel=ch, external_chat_id__startswith=f"comment:{kind}:{post_id}:")
                              .filter(contact__first_name__iexact=client_key)
                              .exclude(external_chat_id__endswith=(IG_ID or "\x00"))
                              .exclude(external_chat_id__endswith=(PAGE_ID or "\x00")).first())
                if target is None:
                    target, created = Conversation.objects.get_or_create(
                        channel=ch, external_chat_id=str(ext_chat),
                        defaults={"title": f"{kind} · коментар"})
            conv = target

            if created or (not ours and not conv.contact_id):
                # контакт = КЛІЄНТ (нік лида), НЕ наш акаунт
                _new_meta_lead(conv, kind, author_id or client_key, client_name,
                               username=author_username,
                               attribution=_meta_attribution(
                                   kind, val, source_context=("comment_ad" if is_ad else "comment"),
                               ))
            elif not ours:
                _enrich_contact(conv.contact, kind, author_id, author_name,
                                username=author_username)
            if created:
                card = _media_card((val.get("media") or {}).get("id") or val.get("post_id"), kind)
                conv.config = {**(conv.config or {}), "source_card": {
                    "type": "comment",
                    "platform": kind,
                    "media_id": post_id,
                    "media_type": card.get("media_type", "") or ("AD" if is_ad else ""),
                    "permalink": card.get("permalink", ""),
                    "thumbnail": card.get("thumbnail", ""),
                    "caption": card.get("caption", ""),
                    "is_ad": is_ad,
                    "parent_id": parent_id,
                    "ad_id": str(val.get("ad_id") or (val.get("media") or {}).get("ad_id") or ""),
                }}
                conv.save(update_fields=["config"])
            if Message.objects.filter(conversation=conv, external_id=str(cid)[:128]).exists():
                continue
            Message.objects.create(conversation=conv, direction=direction, text=text[:5000],
                                   external_id=str(cid)[:128], sender_name=sname)
            conv.unread = (conv.unread or 0) + (0 if ours else 1)  # наша відповідь не додає «непрочитане»
            from django.utils import timezone
            conv.last_message_at = timezone.now()
            conv.save()
            n_msg += 1
    return n_msg
