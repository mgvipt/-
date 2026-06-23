"""Адаптеры каналов. Ядро не зависит от конкретного мессенджера —
каждый канал реализует один интерфейс. Так Viber/Instagram/WhatsApp
добавляются позже без переписывания инбокса.
"""
from __future__ import annotations
import json
import urllib.request
from dataclasses import dataclass, field


@dataclass
class IncomingMessage:
    external_chat_id: str
    text: str
    sender_name: str = ""
    external_id: str = ""
    attachments: list = field(default_factory=list)


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
        chat = msg.get("chat", {})
        frm = msg.get("from", {})
        name = " ".join(x for x in [frm.get("first_name"), frm.get("last_name")] if x) \
            or frm.get("username") or str(chat.get("id"))
        attachments = []
        if "photo" in msg:
            attachments.append({"type": "photo", "file_id": msg["photo"][-1]["file_id"]})
        if "voice" in msg:
            attachments.append({"type": "voice", "file_id": msg["voice"]["file_id"],
                                "duration": msg["voice"].get("duration")})
        return IncomingMessage(
            external_chat_id=str(chat.get("id")),
            text=msg.get("text") or msg.get("caption") or "",
            sender_name=name,
            external_id=str(msg.get("message_id", "")),
            attachments=attachments,
        )

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
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
            resp = json.loads(r.read().decode())
        return str(resp.get("result", {}).get("message_id", ""))

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
        body += b"--" + b + b'\r\nContent-Disposition: form-data; name="' + field.encode() + b'"; filename="' + filename.encode() + b'"\r\nContent-Type: application/octet-stream\r\n\r\n' + content + b"\r\n"
        body += b"--" + b + b"--\r\n"
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
        with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310
            resp = json.loads(r.read().decode())
        return str(resp.get("result", {}).get("message_id", ""))


class MetaAdapter(ChannelAdapter):
    """Instagram/Facebook напряму через Graph API (незалежно від Бітрикса)."""
    kind = "meta"

    def send(self, external_chat_id: str, text: str) -> str:
        from .meta import send_message, reply_comment
        if str(external_chat_id).startswith("comment:"):
            r = reply_comment(str(external_chat_id).split(":", 1)[1], text)
            return str(r.get("id", ""))
        platform = "instagram" if "instagram" in (self.config or {}).get("platform", "instagram") else "facebook"
        r = send_message(external_chat_id, text, platform=platform)
        return str(r.get("message_id", ""))


class ChatPlaceAdapter(ChannelAdapter):
    """IG/Telegram через ChatPlace MCP (незалежно від Бітрикса)."""
    kind = "chatplace"

    def send(self, external_chat_id: str, text: str) -> str:
        from .chatplace import send as cp_send
        r = cp_send(external_chat_id, text)
        return str(r.get("id", "")) if isinstance(r, dict) else ""


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


ADAPTERS = {TelegramAdapter.kind: TelegramAdapter, ViberAdapter.kind: ViberAdapter}


def get_adapter(channel) -> ChannelAdapter:
    if (channel.config or {}).get("chatplace"):
        return ChatPlaceAdapter(channel)
    if (channel.config or {}).get("meta"):
        return MetaAdapter(channel)
    cls = ADAPTERS.get(channel.kind)
    if not cls:
        raise NotImplementedError(f"Адаптер для канала '{channel.kind}' ещё не реализован")
    return cls(channel)
