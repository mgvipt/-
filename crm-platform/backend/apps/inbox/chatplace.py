"""Незалежна інтеграція з ChatPlace через MCP-протокол (https://mcp.chatplace.io/).
БЕЗ Бітрикса. Тягне живі IG-чати (Direct) у inbox CRM і вміє відповідати.
Ключ у .env: CHATPLACE_API_KEY (cpk_...)."""
import os, json, datetime, urllib.request

MCP_URL = os.environ.get("CHATPLACE_MCP_URL", "https://mcp.chatplace.io/")
# 2026-07-31: ChatPlace flip-flop між /mcp і / (обидва можуть 404). Тримаємо ОБИДВА
# і при 404 з активного — перемикаємось на альтернативний.
def _mcp_url_alternates():
    from urllib.parse import urlparse, urlunparse
    p = urlparse(MCP_URL)
    paths = ("/", "/mcp")
    primary = p.path.rstrip("/") + "/" if p.path.rstrip("/") == "" else p.path
    if primary not in paths:
        primary = "/"
    order = [primary] + [x for x in paths if x != primary]
    return [urlunparse(p._replace(path=pth)) for pth in order]
_MCP_ALT = _mcp_url_alternates()
_WORKING_URL = [_MCP_ALT[0]]  # список щоб мутувати всередині _mcp
API_KEY = (os.environ.get("CHATPLACE_API_KEY", "") or "").strip()

# сторони повідомлення, які вважаємо ВИХІДНИМИ (ми/AI/оператор). Решта = вхідне (клієнт).
_STAFF_SIDES = {"ai_assistant", "operator", "manager", "bot", "system", "admin", "out"}


def _relink_echo(conv, ext, text, direction):
    """Канал повертає НАШЕ вихідне повідомлення з іншим id (ехо «operator»).
    Якщо знаходимо свіже власне вихідне з тим же текстом — привʼязуємо до нього
    цей id і НЕ створюємо дубль. Повертає True якщо це ехо (пропустити)."""
    if direction != "out":
        return False
    from .models import Message
    from django.utils import timezone as _tz
    from datetime import timedelta
    own = (Message.objects.filter(conversation=conv, direction="out", text=text)
           .filter(created_at__gte=_tz.now() - timedelta(minutes=30))
           .exclude(external_id=ext).order_by("-id").first())
    if own:
        own.external_id = ext
        own.save(update_fields=["external_id"])
        return True
    return False
# службові маркери ChatPlace (не реальні повідомлення)
import re as _re
_SYS_LABEL = _re.compile(r"^[A-Za-z]{3,}Label$")
_SYSTEM_MARKERS = {"ActiveStatusLabel", "InactiveStatusLabel", "ReadStatusLabel"}


def configured():
    return bool(API_KEY)


def _mcp(name, arguments=None):
    """Викликати інструмент ChatPlace MCP (JSON-RPC tools/call)."""
    if not API_KEY:
        raise RuntimeError("CHATPLACE_API_KEY не налаштовано")
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": name, "arguments": arguments or {}}}
    import urllib.error, time as _t
    # Circuit-breaker: якщо Cloudflare нас щойно забанив (429/1015) — не довбимо далі,
    # інакше бан лише продовжується. Повертаємо зрозумілу помилку одразу.
    _BLOCK_FILE = "/tmp/cp_block"
    try:
        with open(_BLOCK_FILE) as _bf:
            _bu = float(_bf.read().strip() or 0)
    except Exception:
        _bu = 0
    if _bu and _bu > _t.time():
        raise RuntimeError("ChatPlace тимчасово обмежив запити. Автовідновлення за ~%d хв." % (int(_bu - _t.time()) // 60 + 1))
    body = json.dumps(payload).encode()
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": "wallcov-crm/1.0",
    }
    # ChatPlace MCP нестабільний → до 4 спроб з наростаючою паузою.
    # Ретраїмо ЛИШЕ мережеві/5xx/429 (запит не дійшов). НА відмову самого ChatPlace
    # (JSON-RPC error, напр. вікно закрите) — НЕ ретраїмо, щоб не задвоїти повідомлення.
    last = None
    for _i in range(4):
        try:
            req = urllib.request.Request(_WORKING_URL[0], data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
                resp = json.load(r)
            if resp.get("error"):
                raise RuntimeError(f"ChatPlace MCP error: {resp['error']}")
            content = (resp.get("result") or {}).get("content") or []
            text = content[0].get("text") if content else "null"
            try:
                return json.loads(text)
            except (ValueError, TypeError):
                return text
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429:
                ra = e.headers.get("Retry-After") if e.headers else None
                secs = min(float(ra), 2000) if ra and str(ra).replace(".", "", 1).isdigit() else 120
                try:
                    with open(_BLOCK_FILE, "w") as _bf:
                        _bf.write(str(_t.time() + secs))
                except Exception:
                    pass
                raise RuntimeError("ChatPlace обмежив запити (забагато звернень). Автовідновлення за ~%d хв." % (int(secs) // 60 + 1))
            if e.code in (500, 502, 503, 504) and _i < 3:
                _t.sleep(0.6 * (2 ** _i)); continue
            # 2026-07-31 flip-flop: 404 → спробуй альтернативний endpoint і закріпи його
            if e.code == 404:
                other = next((u for u in _MCP_ALT if u != _WORKING_URL[0]), None)
                if other:
                    try:
                        req2 = urllib.request.Request(other, data=body, headers=headers)
                        with urllib.request.urlopen(req2, timeout=30) as r2:
                            resp2 = json.load(r2)
                        _WORKING_URL[0] = other  # switch and remember
                        if resp2.get("error"):
                            raise RuntimeError(f"ChatPlace MCP error: {resp2['error']}")
                        content2 = (resp2.get("result") or {}).get("content") or []
                        text2 = content2[0].get("text") if content2 else "null"
                        try:
                            return json.loads(text2)
                        except (ValueError, TypeError):
                            return text2
                    except Exception:
                        pass
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            last = e
            if _i < 3:
                _t.sleep(0.6 * (2 ** _i)); continue
            raise
    if last:
        raise last


def send(chat_id, text):
    """Відповісти клієнту в IG Direct через ChatPlace (чат має бути open/оператор)."""
    return _mcp("chats_send_message", {"chatId": chat_id, "text": text})


def sync_one_chat(conv, per_chat=40):
    """Підтягнути свіжі повідомлення ОДНОГО чату (live-оновлення відкритого діалогу)."""
    from .models import Message
    msgs = _mcp("chats_messages", {"chatId": conv.external_chat_id, "limit": per_chat})
    if isinstance(msgs, dict):
        msgs = msgs.get("items") or msgs.get("messages") or []
    new = 0
    _had_in = [False]; _had_out = [False]
    for m in reversed(msgs or []):
        ext = str(m.get("id"))
        raw = str(m.get("message") or m.get("text") or "").strip()
        if raw and (raw in _SYSTEM_MARKERS or "StatusLabel" in raw or _SYS_LABEL.match(raw)):
            continue
        if Message.objects.filter(conversation=conv, external_id=ext).exists():
            continue
        side = (m.get("side") or "").lower()
        direction = "out" if side in _STAFF_SIDES else "in"
        # ChatPlace через MCP віддає медіа як ПОРОЖНЄ повідомлення без URL → плейсхолдер (лише вхідні)
        if not raw:
            if direction != "in":
                continue
            body = "📷 Клієнт надіслав фото/файл (відкрийте Instagram/TikTok, щоб побачити)"
        else:
            body = raw
        if _relink_echo(conv, ext, str(body)[:5000], direction):
            continue
        Message.objects.create(conversation=conv, direction=direction, text=str(body)[:5000],
                               external_id=ext, sender_name=("" if direction == "in" else side))
        new += 1
        if direction == "in":
            _had_in[0] = True
            if conv.contact_id:
                try:
                    from apps.crm.automation import capture_phone as _cp
                    _cp(conv.contact, body)
                except Exception:
                    pass
        else:
            _had_out[0] = True
    if new:
        # СИНК ОДНОГО ЧАТУ теж мусить рухати чат угору списку (сортування за last_message_at)
        _lm = conv.messages.order_by("-created_at").values_list("created_at", flat=True).first()
        if _lm and (conv.last_message_at is None or _lm > conv.last_message_at):
            conv.last_message_at = _lm
            conv.save(update_fields=["last_message_at"])
    if conv.contact_id:
        try:
            from apps.crm.automation import on_incoming, on_outgoing
            if _had_in[0]:
                on_incoming(conv.contact, "")
            if _had_out[0]:
                on_outgoing(conv.contact)
        except Exception:
            pass
    return new



_TT_CACHE = {}
def _tt_exists(username):
    """Чи існує реальний TikTok-акаунт (oembed). Кеш у памʼяті. Мережева помилка → None (не чіпати)."""
    if not username:
        return False
    if username in _TT_CACHE:
        return _TT_CACHE[username]
    import urllib.request, urllib.error
    try:
        req = urllib.request.Request("https://www.tiktok.com/oembed?url=https://www.tiktok.com/@%s" % username,
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            ok = (r.status == 200)
    except urllib.error.HTTPError:
        ok = False
    except Exception:
        ok = None
    _TT_CACHE[username] = ok
    return ok


def sync_chats(max_chats=40, per_chat=40):
    """Підтягнути останні чати + повідомлення з ChatPlace у inbox CRM."""
    from .models import Channel, Conversation, Message
    from apps.crm.models import Contact, Lead, Funnel
    ig_ch, _ = Channel.objects.get_or_create(name="ChatPlace · Instagram",
                                             defaults={"kind": "instagram", "config": {"chatplace": True}})
    tt_ch, _ = Channel.objects.get_or_create(name="ChatPlace · TikTok",
                                             defaults={"kind": "tiktok", "config": {"chatplace": True}})
    for _c in (ig_ch, tt_ch):
        if not (_c.config or {}).get("chatplace"):
            _c.config = {**(_c.config or {}), "chatplace": True}; _c.save(update_fields=["config"])
    data = _mcp("chats_list", {"limit": max_chats})
    items = data.get("items", []) if isinstance(data, dict) else (data or [])
    new_conv = new_msg = 0
    errors = []
    for it in items:
        cid = it.get("id")
        raw_name = (it.get("clientName") or "").strip()
        # TikTok визначаємо НАДІЙНО: імʼя-@username І реальний TikTok-акаунт існує (oembed).
        # Раніше брали лише '@' — але у частини IG-клієнтів теж імена з '@' (хибний TikTok).
        _cand = raw_name.lstrip("@").strip() if raw_name.startswith("@") else ""
        is_tt = bool(_cand) and (_tt_exists(_cand) is True)
        platform = "tiktok" if is_tt else "instagram"
        ch = tt_ch if is_tt else ig_ch
        name = raw_name or "Instagram"
        if not cid:
            continue
        # шукаємо діалог в ОБОХ ChatPlace-каналах: визначення платформи (oembed) інколи
        # «фліпає» IG<->TikTok і той самий клієнт дублювався у два чати/контакти
        _both = [c for c in (ig_ch, tt_ch) if c is not None]
        conv = (Conversation.objects.filter(channel__in=_both, external_chat_id=str(cid), status="open")
                .order_by("-created_at").first())
        was_closed = False
        if conv is None:
            conv = (Conversation.objects.filter(channel__in=_both, external_chat_id=str(cid), status="closed")
                    .order_by("-created_at").first())
            was_closed = conv is not None
        if conv is not None and conv.channel_id != ch.id:
            ch = conv.channel            # канал існуючого діалогу — авторитетний
            is_tt = (ch.kind == "tiktok")
            platform = ch.kind
        created = conv is None
        if created:
            conv = Conversation.objects.create(channel=ch, external_chat_id=str(cid), title=name[:160])
        if created:
            new_conv += 1
            # ЗАВЖДИ створюємо/лінкуємо контакт (раніше @username-клієнти лишались без контакту → лід без чату)
            nm = (name or "Instagram").lstrip("@").strip() or "Instagram"
            link = ((("https://www.tiktok.com/@" if is_tt else "https://instagram.com/") + nm) if name.startswith("@") else "")
            existing = Contact.objects.filter(social_link=link).first() if link else None
            contact_created = False
            if existing:
                conv.contact = existing
            elif name.startswith("@"):
                conv.contact = Contact.objects.create(first_name=nm[:120], nickname=name[:150], channels=[platform],
                                                      social_link=link, comment="З ChatPlace " + platform.upper())
                contact_created = True
            else:
                # БЕЗ матчингу по голому імені (зливав різних клієнтів в один контакт).
                # IG-клієнт без @username → завжди новий контакт (external_chat_id унікальний per-діалог).
                parts = name.split(" ", 1)
                conv.contact = Contact.objects.create(first_name=parts[0][:120],
                                                      last_name=(parts[1] if len(parts) > 1 else "")[:120],
                                                      nickname=name[:150], channels=[platform], comment="З ChatPlace " + platform.upper())
                contact_created = True
            conv.save(update_fields=["contact"])
            # посилання на IG-акаунт (username з chats_get)
            try:
                if conv.contact and not conv.contact.social_link:
                    g = _mcp("chats_get", {"chatId": cid})
                    un = (g or {}).get("username") if isinstance(g, dict) else None
                    if un:
                        conv.contact.social_link = (("https://www.tiktok.com/@" + un) if is_tt else ("https://instagram.com/" + un))
                        conv.contact.save(update_fields=["social_link"])
            except Exception:
                pass
            # авто-лід у воронці "Лиды" на кожен новий вхідний IG-чат
            try:
                f = Funnel.objects.filter(name="Лиды").first() or Funnel.objects.order_by("id").first()
                st = f.stages.order_by("order").first() if f else None
                if f and st and contact_created:
                    from apps.crm.lead_routing import make_lead_for_contact
                    make_lead_for_contact(conv.contact, f, platform)
            except Exception:
                pass
        # Економія rate-limit: не смикати chats_messages, якщо з останньої синхронізації
        # НЕ було нових повідомлень (lastMessageAt чату <= збережений last_message_at).
        _clast = it.get("lastMessageAt")
        if (not created) and (not was_closed) and _clast and conv.last_message_at:
            try:
                if int(_clast) <= int(conv.last_message_at.timestamp()):
                    continue
            except (TypeError, ValueError):
                pass
        chad_in = chad_out = False
        try:
            msgs = _mcp("chats_messages", {"chatId": cid, "limit": per_chat})
            if isinstance(msgs, dict):
                msgs = msgs.get("items") or msgs.get("messages") or []
            for m in reversed(msgs or []):
                ext = str(m.get("id"))
                raw = str(m.get("message") or m.get("text") or "").strip()
                if raw and (raw in _SYSTEM_MARKERS or "StatusLabel" in raw or _SYS_LABEL.match(raw)):
                    continue
                if Message.objects.filter(conversation=conv, external_id=ext).exists():
                    continue
                side = (m.get("side") or "").lower()
                direction = "out" if side in _STAFF_SIDES else "in"
                # ChatPlace через MCP віддає медіа як ПОРОЖНЄ повідомлення без URL → плейсхолдер (лише вхідні)
                if not raw:
                    if direction != "in":
                        continue
                    body = "📷 Клієнт надіслав фото/файл (відкрийте Instagram/TikTok, щоб побачити)"
                else:
                    body = raw
                if _relink_echo(conv, ext, str(body)[:5000], direction):
                    continue
                Message.objects.create(conversation=conv, direction=direction, text=str(body)[:5000],
                                       external_id=ext, sender_name=("" if direction == "in" else side))
                new_msg += 1
                if direction == "in":
                    chad_in = True
                    if conv.contact_id:
                        try:
                            from apps.crm.automation import capture_phone as _cp
                            _cp(conv.contact, body)
                        except Exception:
                            pass
                else:
                    chad_out = True
        except Exception as e:
            errors.append(str(cid))
        if was_closed:
            if chad_in:
                conv.status = "open"; conv.assigned_to = None
                conv.save(update_fields=["status", "assigned_to"])  # клієнт написав → відкрити у вільний пул
                # Повернення відкриває діалог того самого контакту, але не створює новий лід.
            # інакше лишаємо закритим — у списку не зʼявиться (status-фільтр)
        if conv.contact_id:
            try:
                from apps.crm.automation import on_incoming, on_outgoing
                if chad_in:
                    on_incoming(conv.contact, "")
                if chad_out:
                    on_outgoing(conv.contact)
            except Exception:
                pass
        ts = it.get("lastMessageAt")
        if ts:
            try:
                conv.last_message_at = datetime.datetime.fromtimestamp(int(ts), tz=datetime.timezone.utc)
            except (ValueError, OSError):
                pass
        conv.title = name[:160]
        conv.save()
        # контакт створився ДО того як ChatPlace віддав імʼя (лаг 1-2 хв) → у ньому плейсхолдер.
        # Дозаповнюємо реальним імʼям (тільки плейсхолдери, справжні імена не чіпаємо).
        try:
            c = conv.contact
            if (c and raw_name and not raw_name.startswith("@")
                    and (c.first_name or "").strip() in ("Instagram", "TikTok", "Клієнт")
                    and not (c.last_name or "").strip()):
                parts = raw_name.split(" ", 1)
                c.first_name = parts[0][:120]
                c.last_name = (parts[1] if len(parts) > 1 else "")[:120]
                if (c.nickname or "").strip() in ("", "Instagram", "TikTok"):
                    c.nickname = raw_name[:150]
                c.save(update_fields=["first_name", "last_name", "nickname"])
                for dl in c.deals.filter(title__in=("Instagram", "TikTok", "Клієнт", "Сделка з чату")):
                    dl.title = raw_name[:200]
                    dl.save(update_fields=["title"])
        except Exception:
            pass
    return {"chats": len(items), "new_conversations": new_conv, "new_messages": new_msg, "errors": len(errors)}
