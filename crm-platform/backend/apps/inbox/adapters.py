"""Адаптеры каналов. Ядро не зависит от конкретного мессенджера —
каждый канал реализует один интерфейс. Так Viber/Instagram/WhatsApp
добавляются позже без переписывания инбокса.
"""
from __future__ import annotations
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field


@dataclass
class IncomingMessage:
    external_chat_id: str
    text: str
    sender_name: str = ""
    external_id: str = ""
    attachments: list = field(default_factory=list)
    direction: str = "in"
    social_link: str = ""
    phone: str = ""


class ChannelAdapter:
    kind = ""

    def __init__(self, channel):
        self.channel = channel
        self.config = channel.config or {}

    def parse_webhook(self, payload: dict) -> IncomingMessage | None:
        raise NotImplementedError

    def send(self, external_chat_id: str, text: str) -> str:
        raise NotImplementedError

    def send_media(self, external_chat_id: str, content: bytes, filename: str, kind: str) -> str:
        """Надіслати фото/відео/документ. kind: photo|video|document."""
        raise NotImplementedError


class TelegramAdapter(ChannelAdapter):
    kind = "telegram"
    API = "https://api.telegram.org/bot{token}/{method}"

    def parse_webhook(self, payload: dict) -> IncomingMessage | None:
        msg = (payload.get("message") or payload.get("edited_message")
               or payload.get("business_message") or payload.get("edited_business_message"))
        if not msg:
            return None
        chat = msg.get("chat", {}) or {}
        frm = msg.get("from", {}) or {}
        chat_id = str(chat.get("id") or "")
        from_id = str(frm.get("id") or "")
        owner_id = str(self.config.get("owner_id") or "")
        # КЛІЄНТ = співрозмовник (chat). НАПРЯМ: у приватному чаті клієнт має from.id==chat.id;
        # якщо відправник інший (ми пишемо з бізнес-акаунту) → from.id!=chat.id → це наше вихідне.
        is_out = bool(from_id and chat_id and from_id != chat_id) or bool(owner_id and from_id == owner_id)
        direction = "out" if is_out else "in"
        party = chat  # ідентичність клієнта завжди беремо з chat, а не з відправника
        name = " ".join(x for x in [party.get("first_name"), party.get("last_name")] if x) \
            or party.get("username") or party.get("title") or chat_id
        uname = party.get("username")
        link = ("https://t.me/" + uname) if uname else (("tg://user?id=" + chat_id) if chat_id else "")
        attachments = []
        if "photo" in msg:
            attachments.append({"type": "photo", "file_id": msg["photo"][-1]["file_id"]})
        if "document" in msg:
            _doc = msg["document"]
            attachments.append({"type": "document", "file_id": _doc["file_id"], "name": _doc.get("file_name") or "файл", "mime": _doc.get("mime_type") or "application/octet-stream"})
        if "video" in msg:
            attachments.append({"type": "video", "file_id": msg["video"]["file_id"], "mime": "video/mp4"})
        if "voice" in msg:
            attachments.append({"type": "voice", "file_id": msg["voice"]["file_id"],
                                "duration": msg["voice"].get("duration")})
        shared = msg.get("contact") or {}
        shared_phone = str(shared.get("phone_number") or "")
        body_text = msg.get("text") or msg.get("caption") or ""
        if shared_phone and not body_text:
            body_text = "☎️ Клієнт надіслав номер: " + shared_phone
        return IncomingMessage(
            external_chat_id=chat_id,
            text=body_text,
            sender_name=name,
            external_id=str(msg.get("message_id", "")),
            attachments=attachments,
            direction=direction,
            social_link=link,
            phone=shared_phone,
        )

    def request_phone(self, external_chat_id: str) -> str:
        """Надіслати клієнту кнопку "Поділитися номером" (request_contact)."""
        token = self.config.get("bot_token")
        if not token:
            return ""
        url = self.API.format(token=token, method="sendMessage")
        body = {
            "chat_id": external_chat_id,
            "text": "Щоб ми швидше зв’язалися — натисніть кнопку нижче 📱",
            "reply_markup": {
                "keyboard": [[{"text": "📱 Поділитися номером", "request_contact": True}]],
                "resize_keyboard": True, "one_time_keyboard": True,
            },
        }
        bcid = (self.config.get("business_chats") or {}).get(str(external_chat_id))
        if bcid:
            body["business_connection_id"] = bcid
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
                resp = json.loads(r.read().decode())
            return str(resp.get("result", {}).get("message_id", ""))
        except Exception as e:
            return "ERR:" + str(e)[:80]

    def send(self, external_chat_id: str, text: str) -> str:
        token = self.config.get("bot_token")
        if not token:
            raise RuntimeError("В канале не задан bot_token")
        url = self.API.format(token=token, method="sendMessage")
        body = {"chat_id": external_chat_id, "text": text}
        bcid = (self.config.get("business_chats") or {}).get(str(external_chat_id))
        if bcid:
            body["business_connection_id"] = bcid  # відповідь від імені особистого акаунту
        data = json.dumps(body).encode()
        import time, urllib.error
        last_err = "Telegram: не вдалося відправити"
        for attempt in range(3):  # ретрай на лимит/таймаут/мережу
            try:
                req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
                    resp = json.loads(r.read().decode())
                return str(resp.get("result", {}).get("message_id", ""))
            except urllib.error.HTTPError as e:
                try:
                    ed = json.loads(e.read().decode())
                except Exception:
                    ed = {}
                desc = ed.get("description", "") or str(e)
                ra = (ed.get("parameters") or {}).get("retry_after")
                last_err = "Telegram: %s" % desc
                if e.code == 429:  # перевищено ліміт частоти — чекаємо і повторюємо
                    time.sleep(min(int(ra) + 1, 10) if ra else 2); continue
                if e.code in (500, 502, 503):  # тимчасова помилка Telegram
                    time.sleep(2); continue
                raise RuntimeError(last_err)  # 400/403 — постійна (заблокований/невірний chat) — не повторюємо
            except (urllib.error.URLError, TimeoutError, OSError) as e:  # мережа/таймаут
                last_err = "Мережа/таймаут: %s" % e
                time.sleep(2); continue
        raise RuntimeError(last_err)

    def send_media(self, external_chat_id: str, content: bytes, filename: str, kind: str) -> str:
        token = self.config.get("bot_token")
        if not token:
            raise RuntimeError("В канале не задан bot_token")
        method = {"video": "sendVideo", "photo": "sendPhoto"}.get(kind, "sendDocument")
        field = {"video": "video", "photo": "photo"}.get(kind, "document")
        url = self.API.format(token=token, method=method)
        boundary = "----wallcovmedia" + str(len(content))
        b = boundary.encode()
        body = b"--" + b + b'\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n' + str(external_chat_id).encode() + b"\r\n"
        bcid = (self.config.get("business_chats") or {}).get(str(external_chat_id))
        if bcid:
            body += b"--" + b + b'\r\nContent-Disposition: form-data; name="business_connection_id"\r\n\r\n' + str(bcid).encode() + b"\r\n"
        body += b"--" + b + b'\r\nContent-Disposition: form-data; name="' + field.encode() + b'"; filename="' + filename.encode() + b'"\r\nContent-Type: application/octet-stream\r\n\r\n' + content + b"\r\n"
        body += b"--" + b + b"--\r\n"
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
        with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310
            resp = json.loads(r.read().decode())
        return str(resp.get("result", {}).get("message_id", ""))


class MetaAdapter(ChannelAdapter):
    """Instagram/Facebook напряму через Graph API (незалежно від Бітрикса)."""
    kind = "meta"

    def _platform(self) -> str:
        return "instagram" if "instagram" in (self.config or {}).get("platform", "instagram") else "facebook"

    def send(self, external_chat_id: str, text: str) -> str:
        from .meta import send_message, reply_comment
        if str(external_chat_id).startswith("comment:"):
            # Відповідь на коментар — публічно, на ОСТАННІЙ коментар клієнта у цій зв'язці «клієнт+публікація»
            from .models import Conversation, Message
            conv = Conversation.objects.filter(channel=self.channel, external_chat_id=external_chat_id).first()
            last_in = (Message.objects.filter(conversation=conv, direction="in").order_by("-id").first()
                       if conv else None)
            comment_id = (last_in.external_id if last_in else "")
            if not comment_id:
                return ""
            r = reply_comment(comment_id, text)
            return str(r.get("id", ""))
        r = send_message(external_chat_id, text, platform=self._platform())
        return str(r.get("message_id", ""))

    def send_media(self, external_chat_id: str, content: bytes, filename: str, kind: str) -> str:
        """Meta приймає медіа лише по ПУБЛІЧНОМУ URL, не сирі байти. Тому реальну
        відправку робить views.send_media (Meta-гілка з публічним посиланням SharedLink)."""
        raise NotImplementedError


class ChatPlaceAdapter(ChannelAdapter):
    """IG/Telegram через ChatPlace MCP (незалежно від Бітрикса)."""
    kind = "chatplace"

    def send(self, external_chat_id: str, text: str) -> str:
        from .chatplace import send as cp_send
        r = cp_send(external_chat_id, text)
        import logging
        logging.getLogger(__name__).info("ChatPlace send resp [%s]: %r", external_chat_id, r)
        if isinstance(r, dict):
            mid = str(r.get("id") or r.get("messageId") or r.get("message_id")
                      or (r.get("data") or {}).get("id") or "")
            if mid:
                return mid
            # ChatPlace MCP chats_send_message при УСПІХУ повертає {'success': True} БЕЗ
            # message-id — повідомлення РЕАЛЬНО доставляється в IG (перевірено з Олегом 22.08).
            # Тому success/ok/status=sent = надіслано; повертаємо "" (порожній external_id
            # дозволений — unique-constraint має condition ~Q(external_id="")). Раніше це
            # помилково червонилось банером «ChatPlace не прийняв», хоча лист доходив.
            if (r.get("success") or r.get("ok")
                    or str(r.get("status") or "").lower() in ("ok", "success", "sent", "true")):
                return ""
            # dict без id і без ознаки успіху — реальна відмова каналу
            raise RuntimeError("ChatPlace не прийняв повідомлення: %s" % (str(r.get("error") or r)[:200]))
        # НЕ-dict відповідь = текст помилки ChatPlace (напр. «Failed to send message»
        # для TikTok, коли їхня інтеграція не доставляє). НЕ пишемо цей текст як id
        # (це давало сміттєвий external_id і duplicate key) — кидаємо чесну помилку,
        # менеджер бачить «не надіслано», а не фейковий «відправлено».
        # ЧОМУ не надіслалось: питаємо ChatPlace статус чату — ТІЛЬКИ при помилці,
        # щоб не сповільнювати робочі відправки (Олег 05.09: у TikTok сипались
        # незрозумілі «Failed to send message», а причина — клієнт зупинив бота).
        # ChatPlace status: 1=active, 2=stopped, 3=unsubscribe.
        _why = ""
        try:
            from .chatplace import _mcp as _cp_mcp
            _st = (_cp_mcp("chats_get", {"chatId": str(external_chat_id)}) or {})
            _code = _st.get("status")
            if _code == 2:
                _why = ("Клієнт зупинив бота в цьому чаті — платформа не приймає від нас повідомлення. "
                        "Напишіть йому з іншого каналу або дочекайтесь, поки він відповість сам.")
            elif _code == 3:
                _why = "Клієнт відписався від чату — відправка неможлива."
        except Exception:
            pass
        if _why:
            raise RuntimeError(_why)
        raise RuntimeError("ChatPlace не зміг надіслати: %s" % (str(r or "порожня відповідь")[:200]))


class ViberAdapter(ChannelAdapter):
    """Viber-бот (public account). Приём через webhook, отправка через chatapi.viber.com."""
    kind = "viber"
    API = "https://chatapi.viber.com/pa"

    def parse_webhook(self, payload: dict):
        if payload.get("event") != "message":
            return None
        sender = payload.get("sender", {}) or {}
        msg = payload.get("message", {}) or {}
        return IncomingMessage(
            external_chat_id=str(sender.get("id", "")),
            text=msg.get("text") or "",
            sender_name=sender.get("name") or "",
            external_id=str(payload.get("message_token", "")),
        )

    def send(self, external_chat_id: str, text: str) -> str:
        token = self.config.get("auth_token")
        if not token:
            raise RuntimeError("В канале не задан auth_token Viber")
        body = json.dumps({"receiver": external_chat_id, "type": "text", "text": text,
                           "sender": {"name": "Wallcov"}}).encode()
        req = urllib.request.Request(self.API + "/send_message", data=body,
                                     headers={"Content-Type": "application/json", "X-Viber-Auth-Token": token})
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
            resp = json.loads(r.read().decode())
        return str(resp.get("message_token", ""))


class EchatViberAdapter(ChannelAdapter):
    """Viber через агрегатор e-chat.tech. config: {echat:True, api_key, number}.
    Вхідні — webhook у форматі e-chat; вихідні — POST /messages/send (header Api-Key)."""
    kind = "echat"
    BASE = "https://e-chat.tech/api/viber/v2"

    def parse_webhook(self, payload: dict):
        contact = payload.get("contact", {}) or {}
        msg = payload.get("message", {}) or {}
        att = []
        if msg.get("file"):
            att.append({"type": msg.get("type", "file"), "url": msg["file"]})
        num = str(contact.get("number", "") or "")
        if not num:
            return None
        return IncomingMessage(
            external_chat_id=num,
            text=msg.get("text") or "",
            sender_name=(contact.get("name") or num),
            external_id=str(msg.get("message_id", "")),
            attachments=att,
            phone=num,
            social_link=("viber://chat?number=%2B" + num.lstrip("+")),
        )

    def _post(self, path, body):
        req = urllib.request.Request(self.BASE + path, data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Api-Key": self.config.get("api_key", ""),
                # Без явного User-Agent Cloudflare E-chat відхиляє urllib як error 1010.
                "User-Agent": "WallcovCRM/1.0 (+https://crm.wallcovdec.com.ua)",
            })
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
            return json.loads((r.read().decode() or "{}") or "{}")

    def send(self, external_chat_id: str, text: str) -> str:
        if not self.config.get("api_key"):
            raise RuntimeError("В каналі e-chat не задано api_key")
        import time
        ext = "wcv-%d" % int(time.time() * 1000)
        resp = self._post("/messages/send", {
            "number": self.config.get("number", ""),
            "message": {"id": ext, "text": text},
            "contact": {"number": external_chat_id},
        })
        return str((resp.get("message") or {}).get("message_id") or ext)

    def connect(self):
        try:
            return self._post("/channel/connect", {"number": self.config.get("number", "")})
        except urllib.error.HTTPError as exc:
            # Повторне підключення вже активної лінії — штатний idempotent результат E-chat.
            if exc.code == 409:
                return {"status": "Success", "description": "Integration already exists"}
            raise


class EchatTelegramAdapter(ChannelAdapter):
    """Telegram особистого номера через e-chat.tech.

    config: {echat_telegram: True, api_key, number}. API-ключ Telegram E-chat
    окремий від ключа Viber, навіть якщо обидві лінії працюють на одному номері.
    """
    kind = "echat_telegram"
    BASE = "https://telegram.e-chat.tech/api"

    def parse_webhook(self, payload: dict):
        sender = payload.get("sender", {}) or {}
        msg = payload.get("message", {}) or {}
        sender_id = str(sender.get("id") or sender.get("username") or sender.get("phone") or "")
        if not sender_id:
            return None
        username = str(sender.get("username") or "").lstrip("@")
        attachments = []
        if msg.get("media"):
            attachments.append({
                "type": "document" if msg.get("type") == "media" else (msg.get("type") or "file"),
                "url": msg.get("media"),
                "name": msg.get("file_name") or "файл",
                "size": msg.get("file_size"),
            })
        return IncomingMessage(
            external_chat_id=sender_id,
            text=msg.get("text") or "",
            sender_name=sender.get("name") or ("@" + username if username else sender_id),
            external_id=str(msg.get("id") or msg.get("telegram_id") or ""),
            attachments=attachments,
            phone=str(sender.get("phone") or ""),
            social_link=("https://t.me/" + username) if username else "",
        )

    def _post(self, path, body):
        req = urllib.request.Request(self.BASE + path, data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "API": self.config.get("api_key", ""),
                "User-Agent": "WallcovCRM/1.0 (+https://crm.wallcovdec.com.ua)",
            })
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
            return json.loads((r.read().decode() or "{}") or "{}")

    def send(self, external_chat_id: str, text: str) -> str:
        if not self.config.get("api_key"):
            raise RuntimeError("В каналі Telegram E-chat не задано api_key")
        import re
        import time
        ext = "wcv-tg-%d" % int(time.time() * 1000)
        address = str(external_chat_id or "")
        if address.startswith("@"):
            receiver = {"username": address}
        elif re.fullmatch(r"380\d{9}", address):
            receiver = {"phone": address}
        else:
            receiver = {"id": address}
        resp = self._post("/SendMessage.php", {
            "user": {"number": self.config.get("number", "")},
            "message": {"id": ext, "text": text},
            "receiver": receiver,
        })
        if str(resp.get("status") or "").upper() == "ERROR":
            raise RuntimeError("Telegram E-chat: " + str(resp.get("description") or "помилка відправки"))
        return str(resp.get("message_id") or ext)

    def connect(self):
        resp = self._post("/CreateChannel.php", {"number": self.config.get("number", "")})
        if str(resp.get("status") or "").upper() == "ERROR":
            raise RuntimeError(str(resp.get("description") or "Telegram E-chat: помилка підключення"))
        return resp


class WebChatAdapter(ChannelAdapter):
    """Відповідь менеджера зберігається у CRM; браузер клієнта забирає її polling-запитом."""
    kind = "web"

    def send(self, external_chat_id: str, text: str) -> str:
        import secrets
        return "web-out-" + secrets.token_urlsafe(10)


class EchatWhatsappAdapter(ChannelAdapter):
    """WhatsApp через агрегатор e-chat.tech. config: {echat_whatsapp:True, api_key, number}.
    API ідентичне Viber e-chat: POST /messages/send, header Api-Key. База whatsapp/v1."""
    kind = "echat_whatsapp"
    BASE = "https://e-chat.tech/api/whatsapp/v1"

    def parse_webhook(self, payload: dict):
        contact = payload.get("contact", {}) or {}
        msg = payload.get("message", {}) or {}
        att = []
        if msg.get("file"):
            att.append({"type": msg.get("type", "file"), "url": msg["file"]})
        num = str(contact.get("number", "") or "")
        if not num:
            return None
        return IncomingMessage(
            external_chat_id=num,
            text=msg.get("text") or "",
            sender_name=(contact.get("name") or num),
            external_id=str(msg.get("message_id", "")),
            attachments=att,
            phone=num,
            social_link=("https://wa.me/" + num.lstrip("+")),
        )

    def _post(self, path, body):
        req = urllib.request.Request(self.BASE + path, data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Api-Key": self.config.get("api_key", ""),
                "User-Agent": "WallcovCRM/1.0 (+https://crm.wallcovdec.com.ua)",
            })
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
            return json.loads((r.read().decode() or "{}") or "{}")

    def send(self, external_chat_id: str, text: str) -> str:
        if not self.config.get("api_key"):
            raise RuntimeError("В каналі WhatsApp e-chat не задано api_key")
        import time
        ext = "wcw-%d" % int(time.time() * 1000)
        resp = self._post("/messages/send", {
            "number": self.config.get("number", ""),
            "message": {"id": ext, "text": text},
            "contact": {"number": external_chat_id},
        })
        if str(resp.get("status") or "").upper() == "ERROR":
            raise RuntimeError("WhatsApp e-chat: " + str(resp.get("description") or "помилка відправки"))
        return str((resp.get("message") or {}).get("message_id") or ext)

    def send_media(self, external_chat_id: str, content: bytes, filename: str, kind: str) -> str:
        """WhatsApp e-chat приймає файл як публічний URL у message.file — надсилаємо
        нативним вкладенням (фото/відео/документ), а не текстовим посиланням."""
        if not self.config.get("api_key"):
            raise RuntimeError("В каналі WhatsApp e-chat не задано api_key")
        from .models import SharedLink
        import secrets, mimetypes, time
        tok = secrets.token_urlsafe(16)
        ct = mimetypes.guess_type(filename)[0] or ("image/jpeg" if kind in ("photo", "image") else "application/octet-stream")
        SharedLink.objects.create(token=tok, filename=(filename or "file")[:255], content_type=ct, data=content)
        import re as _re
        safe = _re.sub(r"[^A-Za-z0-9._-]", "_", (filename or "file"))[:80] or "file"
        url = "https://crm.wallcovdec.com.ua/api/f/%s/%s" % (tok, safe)
        ext = "wcw-%d" % int(time.time() * 1000)
        resp = self._post("/messages/send", {
            "number": self.config.get("number", ""),
            "message": {"id": ext, "text": "", "file": url},
            "contact": {"number": external_chat_id},
        })
        if str(resp.get("status") or "").upper() == "ERROR":
            raise RuntimeError("WhatsApp e-chat (файл): " + str(resp.get("description") or "помилка"))
        return str((resp.get("message") or {}).get("message_id") or ext)

    def connect(self):
        try:
            return self._post("/channel/connect", {"number": self.config.get("number", "")})
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                return {"status": "Success", "description": "Integration already exists"}
            raise


ADAPTERS = {TelegramAdapter.kind: TelegramAdapter, ViberAdapter.kind: ViberAdapter,
            EchatViberAdapter.kind: EchatViberAdapter,
            EchatTelegramAdapter.kind: EchatTelegramAdapter,
            EchatWhatsappAdapter.kind: EchatWhatsappAdapter,
            WebChatAdapter.kind: WebChatAdapter}


def get_adapter(channel) -> ChannelAdapter:
    if (channel.config or {}).get("echat_whatsapp"):
        return EchatWhatsappAdapter(channel)
    if (channel.config or {}).get("echat_telegram"):
        return EchatTelegramAdapter(channel)
    if (channel.config or {}).get("echat"):
        return EchatViberAdapter(channel)
    if (channel.config or {}).get("chatplace"):
        return ChatPlaceAdapter(channel)
    if (channel.config or {}).get("meta"):
        return MetaAdapter(channel)
    cls = ADAPTERS.get(channel.kind)
    if not cls:
        raise NotImplementedError(f"Адаптер для канала '{channel.kind}' ещё не реализован")
    return cls(channel)
