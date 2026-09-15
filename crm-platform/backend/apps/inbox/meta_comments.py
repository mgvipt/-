"""Відповіді в КОМЕНТАРЯХ Meta (Facebook / Instagram) з CRM: куди саме піде відповідь менеджера.

fbcomment 15.09.2026, скарга Олега: чат «Івана Забурко» (FB-коментар), друга відповідь Лаптева червона ✕.
Що перевірено на живих даних (Graph API лише на читання):
  * CRM відповідає в коментарях ПУБЛІЧНО: POST /{comment-id}/comments. Обидві відповіді Лаптева
    опубліковані в гілці. Другу (msg 101573) Facebook ОПУБЛІКУВАВ о 15:19:31 UTC (коментар …_1063598253156583),
    але CRM записала «не доставлено»: помилка сталася вже після публікації, а її текст ніде не зберігся.
  * Instagram: у коментаря IG немає ребра /comments (Meta #100 «nonexisting field (comments)»). Відповідають через
    /{ig-comment-id}/replies і лише на коментар ВЕРХНЬОГО рівня. Тому 40 з 40 відповідей менеджерів
    в IG-коментарях з 31.08 не пішли.
Що тут:
  * reply_target: останній коментар клієнта в чаті (для IG — верхній коментар його гілки);
  * plan/deliver: публічно в гілку (типово, як і раніше) або приватно в Messenger (лише FB, лише коли менеджер
    сам обрав). Meta дозволяє ОДНУ приватну відповідь на коментар і лише 7 днів;
  * після помилки/таймауту перевіряємо гілку: якщо Meta все ж опублікувала — це «надіслано», а не ✕;
  * людський текст помилки + прапорець «можна відповісти публічно» (кнопка «Відповісти в гілці коментаря»).
Мережа — лише через _call(); у тестах вона підміняється (жодних реальних викликів).
"""
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from django.utils import timezone

log = logging.getLogger(__name__)

PRIVATE_DAYS = 7          # Meta: приватна відповідь на коментар — не пізніше 7 днів від коментаря
RECHECK_WINDOW_MIN = 3    # звірка «чи Meta все ж опублікувала»: наш коментар з тим самим текстом за останні N хв
MODES = ("public", "private")

NO_TARGET_TEXT = "У цьому чаті немає коментаря клієнта, на який можна відповісти."
GONE_TEXT = ("Коментар клієнта видалено або приховано — відповісти на нього неможливо. "
             "Відкрийте публікацію і перевірте, або напишіть клієнту в Direct/Messenger.")
PRIVATE_USED_TEXT = ("Приватну відповідь на цей коментар уже надіслано — Meta дозволяє лише ОДНУ на коментар. "
                     "Напишіть публічно в гілці або дочекайтесь, поки клієнт напише в Messenger (тоді це буде звичайний чат).")
PRIVATE_EXPIRED_TEXT = ("Коментарю більше %d днів — Meta вже не дозволяє приватну відповідь на нього. "
                        "Напишіть публічно в гілці." % PRIVATE_DAYS)
PRIVATE_NOT_ALLOWED_TEXT = ("Meta не дозволяє приватну відповідь на цей коментар (на нього вже відповідали приватно, "
                            "минуло більше %d днів або клієнт обмежив повідомлення). Напишіть публічно в гілці." % PRIVATE_DAYS)
PRIVATE_IG_TEXT = ("Для Instagram-коментарів приватна відповідь з CRM не підключена — відповідь піде публічно в гілку. "
                   "Написати клієнту в Direct можна з його чату Instagram.")


class CommentReplyError(RuntimeError):
    """Помилка відповіді в коментарі з людським текстом.
    code: no_target | comment_gone | private_used | private_expired | private_not_allowed | private_unsupported |
          meta_error | timeout
    can_public: показати кнопку «Відповісти в гілці коментаря».
    blocked: True = нічого не відправляли й не записували (перевірка ДО відправки)."""

    def __init__(self, text, code="meta_error", can_public=False, blocked=False):
        super().__init__(text)
        self.code = code
        self.can_public = can_public
        self.blocked = blocked


class GraphError(RuntimeError):
    def __init__(self, http_status=None, code=None, subcode=None, message="", raw=""):
        super().__init__("Meta %s: %s" % (code or http_status, message or raw))
        self.http_status = http_status
        self.code = code
        self.subcode = subcode
        self.message = message or ""
        self.raw = raw or ""


def _meta():
    from . import meta
    return meta


def _call(method, path, params=None, timeout=20):
    """Єдина точка мережі (Graph API сторінки). У тестах підміняється."""
    m = _meta()
    data = {**(params or {}), "access_token": m.PAGE_TOKEN}
    url = "%s/%s" % (m.GRAPH, path)
    if method == "POST":
        req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode())
    else:
        req = urllib.request.Request(url + "?" + urllib.parse.urlencode(data))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
            return json.load(r)
    except urllib.error.HTTPError as e:
        raw = ""
        try:
            raw = e.read().decode()[:800]
        except Exception:
            pass
        err = {}
        try:
            err = (json.loads(raw) or {}).get("error") or {}
        except Exception:
            pass
        raise GraphError(e.code, err.get("code"), err.get("error_subcode"), err.get("message") or "", raw)


# ───────────────────────── що це за чат і куди відповідати ─────────────────────────

def is_meta_comment(conv):
    return bool(conv is not None and (conv.channel.config or {}).get("meta")
                and str(conv.external_chat_id or "").startswith("comment:"))


def platform_of(conv):
    parts = str(conv.external_chat_id or "").split(":")
    if len(parts) > 1 and parts[1] in ("instagram", "facebook"):
        return parts[1]
    return "instagram" if "instagram" in str((conv.channel.config or {}).get("platform") or "") else "facebook"


def _page_id(conv):
    return str(_meta().PAGE_ID or (conv.channel.config or {}).get("page_id") or "")


def _ours(author_id, conv):
    a = str(author_id or "")
    return bool(a) and (_meta()._is_us(a) or a == _page_id(conv))


def _is_gone(e):
    msg = (e.message or e.raw or "").lower()
    return (e.code == 100 and ("does not exist" in msg or "cannot be loaded" in msg or e.subcode == 33)) or e.code == 803


def _last_client_comment(conv):
    from .models import Message
    return (Message.objects.filter(conversation=conv, direction="in", internal=False)
            .exclude(external_id="").order_by("-id").first())


def _ig_top_level(comment_id):
    """IG дозволяє відповідати лише на коментар верхнього рівня: якщо клієнт писав у гілці — беремо її верхній."""
    try:
        d = _call("GET", comment_id, {"fields": "id,parent_id"}, timeout=8)
    except GraphError as e:
        if _is_gone(e):
            raise CommentReplyError(GONE_TEXT, code="comment_gone", blocked=True)
        return comment_id  # не змогли уточнити — пробуємо як є; якщо не можна, відправка покаже причину
    except Exception:
        return comment_id
    return str((d or {}).get("parent_id") or comment_id)


def reply_target(conv):
    """Останній коментар клієнта: {platform, comment_id, reply_to, message_id, text, at} або None."""
    last = _last_client_comment(conv)
    if not last:
        return None
    plat = platform_of(conv)
    t = {"platform": plat, "comment_id": str(last.external_id), "reply_to": str(last.external_id),
         "message_id": last.id, "text": (last.text or "")[:200], "at": last.created_at}
    if plat == "instagram":
        t["reply_to"] = _ig_top_level(t["comment_id"])
    return t


def _private_used(conv, comment_id):
    from .models import Message
    for atts in (Message.objects.filter(conversation=conv, direction="out", internal=False)
                 .exclude(status="failed").values_list("attachments", flat=True)):
        for a in atts or []:
            if (isinstance(a, dict) and a.get("type") == "comment_reply" and a.get("mode") == "private"
                    and str(a.get("comment_id")) == str(comment_id)):
                return True
    return False


def private_status(conv, target, ask_meta=True):
    """(можна?, код, пояснення). Приватна відповідь — лише Facebook, одна на коментар, до 7 днів."""
    if not target:
        return False, "no_target", NO_TARGET_TEXT
    if target["platform"] != "facebook":
        return False, "private_unsupported", PRIVATE_IG_TEXT
    if _private_used(conv, target["comment_id"]):
        return False, "private_used", PRIVATE_USED_TEXT
    if target.get("at") and timezone.now() - target["at"] > timedelta(days=PRIVATE_DAYS):
        return False, "private_expired", PRIVATE_EXPIRED_TEXT
    if ask_meta:
        try:
            d = _call("GET", target["comment_id"], {"fields": "can_reply_privately"}, timeout=8)
            if (d or {}).get("can_reply_privately") is False:
                return False, "private_not_allowed", PRIVATE_NOT_ALLOWED_TEXT
        except Exception:
            pass  # Meta не відповіла — не блокуємо; якщо не можна, Meta відмовить і менеджер побачить причину
    return True, "", ""


def describe(conv):
    """Для підказки НАД полем вводу (GET …/comment_target/). Нічого не відправляє."""
    if not is_meta_comment(conv):
        return {"is_comment": False}
    out = {"is_comment": True, "platform": platform_of(conv), "default_mode": "public", "private_days": PRIVATE_DAYS}
    try:
        t = reply_target(conv)
    except CommentReplyError as e:
        out.update({"target": None, "problem": str(e), "can_private": False, "private_code": e.code,
                    "private_reason": str(e)})
        return out
    if not t:
        out.update({"target": None, "problem": NO_TARGET_TEXT, "can_private": False, "private_code": "no_target",
                    "private_reason": NO_TARGET_TEXT})
        return out
    ok, code, why = private_status(conv, t)
    out.update({
        "target": {"comment_id": t["comment_id"], "message_id": t["message_id"], "text": t["text"],
                   "at": t["at"].isoformat() if t.get("at") else None,
                   "nested_to_top": t["reply_to"] != t["comment_id"]},
        "can_private": ok, "private_code": code, "private_reason": why,
    })
    return out


# ───────────────────────── відправка ─────────────────────────

def plan(conv, mode=None):
    """Перевірка ДО відправки: нічого не відправляє і не записує. План або CommentReplyError(blocked=True)."""
    mode = mode if mode in MODES else "public"
    t = reply_target(conv)
    if not t:
        raise CommentReplyError(NO_TARGET_TEXT, code="no_target", blocked=True)
    if mode == "private":
        ok, code, why = private_status(conv, t)
        if not ok:
            raise CommentReplyError(why, code=code, can_public=True, blocked=True)
    return {**t, "mode": mode}


def _marker(p):
    return {"type": "comment_reply", "mode": p["mode"], "platform": p["platform"],
            "comment_id": p["comment_id"], "reply_to": p["reply_to"]}


def _parse_ts(s):
    try:
        return datetime.strptime(str(s), "%Y-%m-%dT%H:%M:%S%z")
    except (TypeError, ValueError):
        return None


def _find_published(conv, plat, reply_to, text, since):
    """Meta повернула помилку/таймаут — чи наш коментар з цим текстом усе ж зʼявився в гілці? (лише читання)"""
    body = (text or "").strip()
    if not body or not reply_to:
        return ""
    if plat == "instagram":
        path, key, tkey = "%s/replies" % reply_to, "text", "timestamp"
        params = {"fields": "id,text,timestamp,from", "limit": 50}
    else:
        path, key, tkey = "%s/comments" % reply_to, "message", "created_time"
        params = {"fields": "id,message,created_time,from", "limit": 50, "filter": "stream",
                  "order": "reverse_chronological"}
    try:
        d = _call("GET", path, params, timeout=10)
    except Exception:
        return ""
    lo = (since or timezone.now()) - timedelta(minutes=RECHECK_WINDOW_MIN)
    for c in (d or {}).get("data") or []:
        if (c.get(key) or "").strip() != body:
            continue
        fid = (c.get("from") or {}).get("id")
        if fid and not _ours(fid, conv):
            continue
        ts = _parse_ts(c.get(tkey))
        if ts and ts < lo:
            continue
        if c.get("id"):
            return str(c["id"])
    return ""


def _human(e, mode, plat):
    """Помилка Meta/мережі → CommentReplyError з поясненням для менеджера."""
    if isinstance(e, CommentReplyError):
        return e
    where = "Instagram" if plat == "instagram" else "Facebook"
    if isinstance(e, GraphError):
        code, msg = e.code, (e.message or "")
        low = msg.lower()
        if _is_gone(e):
            return CommentReplyError(GONE_TEXT, code="comment_gone")
        if mode == "private":
            if code == 10900 or "already replied" in low:
                return CommentReplyError(PRIVATE_USED_TEXT, code="private_used", can_public=True)
            return CommentReplyError("Meta не прийняла приватну відповідь (код %s: %s). Можна відповісти публічно "
                                     "в гілці коментаря." % (code or e.http_status, msg[:160]), code="meta_error",
                                     can_public=True)
        if code == 368:
            return CommentReplyError("Meta тимчасово обмежила публікацію від сторінки (антиспам, код 368). Спробуйте "
                                     "пізніше або напишіть клієнту в Direct/Messenger.", code="meta_error")
        if code in (10, 190, 200) or "permission" in low:
            return CommentReplyError("Немає дозволу Meta на відповідь у коментарях %s (код %s). Потрібно перевірити "
                                     "доступи застосунку Meta — повідомте Олега." % (where, code), code="meta_error")
        if code in (1, 2, 4, 17, 32, 613) or (e.http_status or 0) >= 500:
            return CommentReplyError("%s тимчасово не відповідає (код %s). Ми перевірили гілку — відповіді там немає. "
                                     "Спробуйте ще раз за хвилину." % (where, code or e.http_status), code="meta_error")
        return CommentReplyError("%s не прийняв відповідь (код %s): %s" % (where, code or e.http_status, msg[:200]),
                                 code="meta_error")
    return CommentReplyError("%s не відповів вчасно (%s). Ми перевірили гілку — відповіді там немає. Спробуйте ще раз."
                             % (where, str(e)[:80] or e.__class__.__name__), code="timeout")


def deliver(conv, text, p, since=None):
    """Відправка за планом. (external_id, marker) або CommentReplyError з людським текстом."""
    since = since or timezone.now()
    plat = p["platform"]
    try:
        if p["mode"] == "private":
            r = _call("POST", "%s/messages" % (_page_id(conv) or "me"), {
                "recipient": json.dumps({"comment_id": p["comment_id"]}),
                "message": json.dumps({"text": text}),
            })
            ext = str((r or {}).get("message_id") or "")
        else:
            edge = "replies" if plat == "instagram" else "comments"
            r = _call("POST", "%s/%s" % (p["reply_to"], edge), {"message": text})
            ext = str((r or {}).get("id") or "")
    except Exception as e:  # noqa: BLE001 — будь-яка помилка → звірка + людський текст
        err = _human(e, p["mode"], plat)
        if p["mode"] == "public" and err.code != "comment_gone":
            found = _find_published(conv, plat, p["reply_to"], text, since)
            if found:
                log.warning("comment reply conv=%s: Meta повернула %r, але відповідь опублікована (%s) — надіслано",
                            conv.id, e, found)
                return _free_ext(conv, found), _marker(p)
        log.warning("comment reply conv=%s mode=%s target=%s failed: %r", conv.id, p["mode"], p["reply_to"], e)
        raise err from e
    return _free_ext(conv, ext), _marker(p)


def _free_ext(conv, ext):
    """id уже записаний вебхуком в іншому повідомленні цього чату → не дублюємо (унікальність conv+external_id)."""
    from .models import Message
    return "" if ext and Message.objects.filter(conversation=conv, external_id=ext).exists() else ext


def adapter_send(conv, text):
    """Для прямих викликів MetaAdapter.send (публічно, на останній коментар клієнта)."""
    ext, _m = deliver(conv, text, plan(conv, "public"))
    return ext
