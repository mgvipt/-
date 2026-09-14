"""Мітки «з реклами Meta» (14.09.2026, meta-attr).

Класи живуть усередині ВЖЕ ІСНУЮЧОГО JSON meta_attribution ліда/угоди (нових полів у crm немає):
  class="meta_ad"         — точна мітка від Meta (referral / коментар під рекламою / лід-форма);
  class="meta_ad_likely"  — «ймовірно з реклами»: перше повідомлення = текст кнопки з оголошення
                            (source_kind="likely_ad", method, phrase, attributed_at).
Точна мітка завжди важливіша; «ймовірно» підвищується до точної, коли Meta пришле referral.
У Meta CAPI йде лише точна: has_verified_meta_attribution() вимагає paid_ad/lead_form + ID,
а "likely_ad" туди не проходить.

Контактний рівень без нових полів: останній точний клік пишемо в
Conversation.config["ad_referral"] (JSON, вже є) — з нього угоди успадковують мітку.
"""
import json
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone as dt_timezone

from django.db import transaction
from django.utils import timezone

CLASS_EXACT = "meta_ad"
CLASS_LIKELY = "meta_ad_likely"
EXACT_KINDS = ("paid_ad", "lead_form")
LIKELY_KIND = "likely_ad"
# лід/угода можуть бути створені трохи РАНІШЕ за клік (лід від першого повідомлення,
# referral прилетів наступною подією) — допуск 1 день; старіші записи не чіпаємо.
CLICK_BEFORE_TOLERANCE = timedelta(days=1)
# нова угода бере мітку з ліда/чату клієнта, якщо клік був не раніше ніж 30 днів тому
INHERIT_WINDOW = timedelta(days=30)
PHRASES_PROVIDER = "meta_ad_phrases"      # IntegrationSettings.provider
LOG_KEEP_DAYS = 30

# Дані 01.07–13.09 (перше повідомлення IG/FB-чатів): тексти кнопок з оголошень.
#  A «слово+емодзі»: Galatea🔥, Сирена💎, Патера💎, Galatea🌼/🎨/🧵, Luna🎨, Pattera🌿 …
#    (+ варіант «Прорахунок на об`єм та консультація Galatea🌼»);
#  C «Розрахунок на обʼєм».
#  B просте слово («Галатея», «Сирена») і «/start» — НЕ рахуємо (точність ~47% = фон).
DEFAULT_PHRASES = {
    "enabled": True,
    "emoji_words": ["Galatea", "Галатея", "Сирена", "Siren", "Патера", "Pattera", "Luna", "Луна", "Стіни"],
    "prefixes": ["Прорахунок на обʼєм та консультація", "Консультація та прорахунок обʼєму"],
    "phrases": ["Розрахунок на обʼєм"],
}

_APOS = str.maketrans({"ʼ": "'", "’": "'", "`": "'", "‘": "'", "´": "'", "ʹ": "'"})
_CACHE = {"at": 0.0, "cfg": None}
_PURGE = {"at": 0.0}


# ─────────────────────────── фрази ───────────────────────────

def _norm(text):
    s = unicodedata.normalize("NFC", str(text or "")).translate(_APOS).casefold()
    return re.sub(r"\s+", " ", s).strip()


def _is_emoji_char(ch):
    if ch in ("\ufe0f", "\u200d", "\u20e3"):   # variation selector, ZWJ, keycap
        return True
    return unicodedata.category(ch) in ("So", "Sk", "Me", "Mn")


def clear_phrase_cache():
    _CACHE.update(at=0.0, cfg=None)


def get_phrase_config(use_cache=True):
    """Список рекламних фраз: IntegrationSettings(provider="meta_ad_phrases").config поверх
    DEFAULT_PHRASES. Лише читання (рядок у базі створює тільки PUT /api/meta-attr/phrases/)."""
    now = time.monotonic()
    if use_cache and _CACHE["cfg"] is not None and now - _CACHE["at"] < 60:
        return _CACHE["cfg"]
    cfg = {k: (list(v) if isinstance(v, list) else v) for k, v in DEFAULT_PHRASES.items()}
    try:
        from apps.integrations.models import IntegrationSettings
        row = IntegrationSettings.objects.filter(provider=PHRASES_PROVIDER).first()
        if row and isinstance(row.config, dict):
            for key in DEFAULT_PHRASES:
                if key in row.config:
                    cfg[key] = row.config[key]
    except Exception:
        pass
    _CACHE.update(at=now, cfg=cfg)
    return cfg


def match_ad_phrase_group(text, cfg=None):
    """→ (фраза, "A"|"C") якщо перше повідомлення схоже на текст кнопки з реклами, інакше ("", "")."""
    cfg = cfg or get_phrase_config()
    raw = str(text or "").strip()
    t = _norm(raw)
    if not t or t.startswith("/") or not cfg.get("enabled", True):
        return "", ""
    bare = t.rstrip(" .!?,;:…")
    for phrase in cfg.get("phrases") or []:
        p = _norm(phrase).rstrip(" .!?,;:…")
        if p and bare == p:
            return raw[:120], "C"
    body = t
    for prefix in sorted((_norm(x) for x in (cfg.get("prefixes") or [])), key=len, reverse=True):
        if prefix and body.startswith(prefix):
            body = body[len(prefix):].strip()
            break
    m = re.match(r"^([^\W\d_]+)\s*(.*)$", body)
    if not m:
        return "", ""
    word, tail = m.group(1), m.group(2)
    words = {_norm(w) for w in (cfg.get("emoji_words") or []) if w}
    if word in words and tail and all(_is_emoji_char(c) or c.isspace() for c in tail) \
            and any(unicodedata.category(c) == "So" for c in tail):
        return raw[:120], "A"
    return "", ""


def match_ad_phrase(text, cfg=None):
    return match_ad_phrase_group(text, cfg)[0]


# ─────────────────────────── класи ───────────────────────────

def is_exact(attr):
    return isinstance(attr, dict) and attr.get("source_kind") in EXACT_KINDS


def is_likely(attr):
    return (isinstance(attr, dict) and not is_exact(attr)
            and (attr.get("class") == CLASS_LIKELY or attr.get("source_kind") == LIKELY_KIND))


def classify(attr):
    if is_exact(attr):
        return CLASS_EXACT
    if is_likely(attr):
        return CLASS_LIKELY
    if isinstance(attr, dict) and attr.get("source_kind") == "organic":
        return "organic"
    return "unknown"


def _parse_dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if timezone.is_naive(dt):
        dt = dt.replace(tzinfo=dt_timezone.utc)
    return dt


def click_time(attr, fallback=None):
    return _parse_dt((attr or {}).get("attributed_at")) or fallback


def _event_time(ev):
    now = timezone.now()
    try:
        ts = float((ev or {}).get("timestamp") or 0)
    except (TypeError, ValueError):
        ts = 0
    if ts <= 0:
        return now
    if ts > 1e11:            # Meta присилає мілісекунди
        ts = ts / 1000.0
    try:
        dt = datetime.fromtimestamp(ts, tz=dt_timezone.utc)
    except (OverflowError, OSError, ValueError):
        return now
    if dt > now + timedelta(hours=1) or dt < now - timedelta(days=365):
        return now
    return dt


def stamp_exact(attr, method="referral", ev=None, at=None):
    out = dict(attr or {})
    out["class"] = CLASS_EXACT
    out.setdefault("method", method)
    if not out.get("attributed_at"):
        out["attributed_at"] = (at or _event_time(ev)).isoformat()
    return out


def stamp_new(attr):
    """Для нового ліда з Meta: точній мітці додаємо class/method/attributed_at. Інше — як є."""
    try:
        attr = dict(attr or {})
        if not is_exact(attr) or attr.get("class"):
            return attr
        if attr.get("source_kind") == "lead_form":
            method = "lead_form"
        elif attr.get("source_context") == "comment_ad":
            method = "comment_ad"
        else:
            method = "referral"
        return stamp_exact(attr, method=method)
    except Exception:
        return attr or {}


def likely_attr(phrase, platform="instagram", method="first_text", at=None, **extra):
    out = {
        "source_kind": LIKELY_KIND, "class": CLASS_LIKELY, "method": method,
        "phrase": str(phrase or "")[:120], "platform": platform or "instagram",
        "source_context": "first_text_keyword",
        "attributed_at": (at or timezone.now()).isoformat(),
    }
    out.update({k: v for k, v in extra.items() if v not in (None, "")})
    return out


def _is_open(obj):
    stage = getattr(obj, "stage", None)
    if stage is not None and (stage.is_won or stage.is_lost):
        return False
    return getattr(obj, "closed_at", None) is None


def _write_exact(obj, attr):
    cur = obj.meta_attribution or {}
    if is_exact(cur):
        return False                      # точну мітку ніколи не перезаписуємо
    new = dict(attr)
    if is_likely(cur):
        new["upgraded_from_likely"] = cur.get("phrase") or "так"
    obj.meta_attribution = new
    obj.save(update_fields=["meta_attribution"])
    return True


# ─────────────────────── живий вебхук Meta ───────────────────────

def first_text_guess(attr, kind, ev, msg):
    """Новий Meta-чат без referral: перше повідомлення = текст кнопки з реклами → «ймовірно»."""
    try:
        if is_exact(attr):
            return attr
        phrase = match_ad_phrase((msg or {}).get("text") or "")
        if not phrase:
            return attr
        _log_event(kind, ev, "phrase_no_referral", phrase=phrase)
        return likely_attr(phrase, platform=kind, method="first_text", at=_event_time(ev))
    except Exception:
        return attr


def remember_click(conv, attr):
    """Точний клік → Conversation.config["ad_referral"] (контактний рівень для успадкування)."""
    try:
        keep = ("source_kind", "platform", "class", "method", "attributed_at", "ad_id", "adset_id",
                "campaign_id", "referral_id", "content_id", "ad_title", "ad_thumb", "ad_ref", "source_context")
        with transaction.atomic():
            cfg = dict(conv.config or {})
            cfg["ad_referral"] = {k: attr[k] for k in keep if attr.get(k)}
            conv.config = cfg
            conv.save(update_fields=["config"])
    except Exception:
        pass


def apply_exact_click(contact, attr):
    """Точний клік Meta для відомого клієнта. Баги A–E (14.09.2026):
      • мітимо лише ВІДКРИТІ ліди/угоди, створені не раніше ніж за 1 день до кліку;
      • закриті угоди не чіпаємо (не буде «реклами заднім числом» у ROAS);
      • є відкритий лід/угода → новий лід НЕ створюємо (мітка лишається на чаті).
    → "marked" | "kept" | "need_lead" (клієнт без відкритих справ → новий лід)."""
    from apps.crm.models import Deal, Lead
    click = click_time(attr) or timezone.now()
    since = click - CLICK_BEFORE_TOLERANCE
    open_leads = [x for x in Lead.objects.filter(contact=contact).select_related("stage") if _is_open(x)]
    open_deals = [x for x in Deal.objects.filter(contact=contact).select_related("stage") if _is_open(x)]
    targets = [x for x in open_leads + open_deals if x.created_at and x.created_at >= since]
    for obj in targets:
        _write_exact(obj, attr)
    if targets:
        return "marked"
    if open_leads or open_deals:
        return "kept"
    return "need_lead"


# ─────────────────────── успадкування угодою ───────────────────────

def inherit_meta_attribution(deal):
    """Нова угода без точної мітки → беремо мітку з ліда/чату того ж клієнта, якщо клік
    був не раніше ніж 30 днів тому. Точну не перезаписуємо; «ймовірно» → точна, якщо є.
    Ніколи не ламає створення угоди (свій savepoint + try)."""
    try:
        with transaction.atomic():
            return _inherit(deal)
    except Exception:
        return False


def _inherit(deal):
    from apps.crm.models import Lead
    from apps.inbox.models import Conversation
    if deal is None or not deal.pk or not deal.contact_id:
        return False
    cur = deal.meta_attribution or {}
    if is_exact(cur):
        return False
    created = deal.created_at or timezone.now()
    lo, hi = created - INHERIT_WINDOW, created + timedelta(hours=1)
    cands = []
    for lead in (Lead.objects.filter(contact_id=deal.contact_id).exclude(meta_attribution={})
                 .only("id", "created_at", "meta_attribution")):
        a = lead.meta_attribution or {}
        if not (is_exact(a) or is_likely(a)):
            continue
        t = click_time(a, fallback=lead.created_at)
        if t and lo <= t <= hi:
            cands.append((is_exact(a), t, a, "lead:%s" % lead.id))
    for conv in Conversation.objects.filter(contact_id=deal.contact_id).only("id", "config"):
        a = (conv.config or {}).get("ad_referral") or {}
        t = click_time(a)
        if is_exact(a) and t and lo <= t <= hi:
            cands.append((True, t, a, "conversation:%s" % conv.id))
    if not cands:
        return False
    cands.sort(key=lambda row: (row[0], row[1]), reverse=True)
    exact, _t, attr, where = cands[0]
    if is_likely(cur) and not exact:
        return False
    new = dict(attr)
    new["inherited_from"] = where
    new["inherited_at"] = timezone.now().isoformat()
    if is_likely(cur):
        new["upgraded_from_likely"] = cur.get("phrase") or "так"
    deal.meta_attribution = new
    deal.save(update_fields=["meta_attribution"])
    return True


# ─────────────────────── нічна «підмітальна» команда ───────────────────────

def attr_with_click_time(lead):
    a = dict(lead.meta_attribution or {})
    if not a.get("attributed_at") and getattr(lead, "created_at", None):
        a["attributed_at"] = lead.created_at.isoformat()
    return a


def deal_accepts_click(deal, attr):
    """Угода може отримати мітку кліку: відкрита і створена не раніше ніж за 1 день до кліку."""
    if not _is_open(deal):
        return False
    click = click_time(attr)
    return click is None or (deal.created_at is not None and deal.created_at >= click - CLICK_BEFORE_TOLERANCE)


# ─────────────────────── бейдж (API) ───────────────────────

_RANK = {CLASS_EXACT: 3, CLASS_LIKELY: 2, "organic": 1, "unknown": 0}


def _ad_card(attr):
    try:
        from apps.crm.serializers import _resolve_meta_ad
        card = _resolve_meta_ad(attr)
        if card:
            return card
    except Exception:
        pass
    if (attr or {}).get("source_kind") == "lead_form":
        return {"title": "Лід-форма", "ad_id": attr.get("ad_id", ""), "campaign": "", "ad_name": ""}
    return {"title": (attr or {}).get("ad_title", ""), "ad_id": (attr or {}).get("ad_id", ""), "campaign": "", "ad_name": ""}


def summarize(contact_id=None, conversation=None):
    """Одна відповідь для бейджа клієнта/чату: ліди + угоди + чати (сконвертовані ліди видалені,
    тому угоди обовʼязково). class: meta_ad | meta_ad_likely | organic | unknown | none."""
    from apps.crm.models import Deal, Lead
    from apps.inbox.models import Conversation
    items, footprint = [], False
    if contact_id:
        for model, kind in ((Lead, "lead"), (Deal, "deal")):
            for obj in (model.objects.filter(contact_id=contact_id)
                        .only("id", "created_at", "source", "meta_attribution").order_by("-id")[:50]):
                a = obj.meta_attribution or {}
                if obj.source in ("instagram", "facebook") or a:
                    footprint = True
                if a:
                    items.append((_RANK[classify(a)], click_time(a, obj.created_at), a, "%s:%s" % (kind, obj.id)))
    convs = list(Conversation.objects.filter(contact_id=contact_id).select_related("channel")[:50]) if contact_id else []
    if conversation is not None and all(c.pk != conversation.pk for c in convs):
        convs.append(conversation)
    for conv in convs:
        if conv.channel_id and conv.channel.kind in ("instagram", "facebook"):
            footprint = True
        cfg = conv.config or {}
        a = cfg.get("ad_referral") or {}
        if is_exact(a):
            items.append((3, click_time(a, conv.created_at), a, "conversation:%s" % conv.id))
        card = cfg.get("source_card") or {}
        if card.get("is_ad") and card.get("ad_id"):
            a2 = {"source_kind": "paid_ad", "platform": card.get("platform") or "instagram",
                  "ad_id": str(card.get("ad_id")), "content_id": str(card.get("media_id") or ""),
                  "source_context": "comment_ad", "class": CLASS_EXACT, "method": "comment_ad"}
            items.append((3, conv.created_at, a2, "conversation:%s" % conv.id))
    if not items:
        return {"class": "unknown" if footprint else "none"}
    epoch = datetime(1970, 1, 1, tzinfo=dt_timezone.utc)
    items.sort(key=lambda row: (row[0], row[1] or epoch), reverse=True)
    _rank, t, attr, where = items[0]
    cls = classify(attr)
    out = {"class": cls, "method": attr.get("method") or attr.get("source_context") or "",
           "phrase": attr.get("phrase", ""), "attributed_at": t.isoformat() if t else "", "where": where}
    if cls == CLASS_EXACT:
        out["ad"] = _ad_card(attr)
    return out


# ─────────────────────── сирий лог вебхуків (30 днів) ───────────────────────

_ADS_KEYS = {"referral", "ads_context_data", "ad_id", "ad_title", "ctwa_clid"}


def _deep_find(value, keys, depth=0, found=None):
    found = {} if found is None else found
    if depth > 7:
        return found
    if isinstance(value, dict):
        for k, v in value.items():
            if k in keys and k not in found and v not in (None, "", {}, []):
                found[k] = v
            if isinstance(v, (dict, list)):
                _deep_find(v, keys, depth + 1, found)
    elif isinstance(value, list):
        for v in value:
            _deep_find(v, keys, depth + 1, found)
    return found


def _log_event(kind, ev, reason, phrase=""):
    try:
        from .models import MetaWebhookLog
        ev = ev or {}
        val = ev.get("value") if isinstance(ev.get("value"), dict) else {}
        sender = ((ev.get("sender") or {}).get("id") or ((val or {}).get("from") or {}).get("id") or "")
        found = _deep_find(ev, {"ad_id"})
        payload = ev
        try:
            dumped = json.dumps(ev, ensure_ascii=False, default=str)
            if len(dumped) > 20000:
                payload = {"truncated": dumped[:20000]}
        except Exception:
            payload = {"unserializable": str(ev)[:20000]}
        with transaction.atomic():
            MetaWebhookLog.objects.create(
                platform=str(kind or "")[:16], reason=reason[:24], sender_id=str(sender)[:64],
                ad_id=str(found.get("ad_id") or "")[:64], phrase=str(phrase or "")[:120], event=payload)
        _maybe_purge()
    except Exception:
        pass


def _maybe_purge():
    now = time.monotonic()
    if _PURGE["at"] and now - _PURGE["at"] < 3600:
        return
    _PURGE["at"] = now
    try:
        from .models import MetaWebhookLog
        with transaction.atomic():
            MetaWebhookLog.objects.filter(created_at__lt=timezone.now() - timedelta(days=LOG_KEEP_DAYS)).delete()
    except Exception:
        pass


def log_webhook_entry(obj, kind, entry):
    """Зберегти (на 30 днів) сирі події вебхука, у яких є дані реклами (referral/ads_context/ad_id),
    щоб потім побачити, чому Meta губить мітку. Ніколи не ламає вебхук."""
    try:
        events = list((entry or {}).get("messaging") or []) + list((entry or {}).get("standby") or [])
        events += list((entry or {}).get("changes") or [])
        for ev in events:
            if not isinstance(ev, dict):
                continue
            val = ev.get("value") if isinstance(ev.get("value"), dict) else {}
            if _deep_find(ev, _ADS_KEYS) or (val or {}).get("is_ad"):
                _log_event(kind, ev, "ads_data")
    except Exception:
        pass
