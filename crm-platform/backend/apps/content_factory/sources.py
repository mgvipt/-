"""Контент-завод: джерела контенту (24.09.2026) — Telegram-групи, канал і Google Drive (drive.py).

Файли НЕ завантажуються на сервер CRM: зберігаємо Telegram file_id, підпис, посилання на повідомлення.
Бот @wallcov_smm_bot (сервіс wallcov-content-bot на Hetzner) пересилає сюди апдейти груп і каналу
(POST /api/content-factory/sources/ingest/ з секретом CF_INGEST_SECRET). Новий чат зʼявляється ВИМКНЕНИМ —
файли з нього приймаються лише після того, як власник увімкне чат у CRM.
Теги — з підпису Олега без ШІ (назви матеріалів, кімнат, етапів, #хештеги). Превью — мініатюра Telegram
через підписане посилання на 1 годину, нічого не кешується на диску.
"""
import os
import re
import urllib.request
from datetime import datetime, timezone as dt_tz

from django.core import signing

from .models import SourceAsset, SourceChat

MATERIALS = [  # (регулярка, назва як у бібліотеці CRM)
    (r"галате|galate", "Галатея"), (r"елеганті|элеганти|elegant", "Елеганті"),
    (r"мермі|мерми|marmi", "Мермі шовк"), (r"шовк|шелк|silk", "Мокрий шовк"),
    (r"луна|luna", "Вельвет Луна"), (r"люкс|lux", "Вельвет Люкс"), (r"патер|patter", "Патера"),
    (r"піщин|піск|песк|sand", "Піски"), (r"міо|мио|mio\b", "Міо Глос"), (r"гая|gaia", "Гая Глос"),
    (r"мікроцем|микроцем|topciment|мікробет|микробет", "Мікроцемент"), (r"слейт|slate|арт-?бетон", "Слейт / Арт-бетон"),
    (r"венеці|венеци|venec", "Венеціанка"), (r"травертин|travert", "Травертин"), (r"марморин|marmorin", "Марморин"),
    (r"антикатур|antikatur", "Антикатура"),
]
TAG_WORDS = {
    "спальн": "спальня", "вітальн": "вітальня", "гостин": "вітальня", "кухн": "кухня", "коридор": "коридор",
    "передпок": "коридор", "прихож": "коридор", "дитяч": "дитяча", "детск": "дитяча", "ванн": "ванна",
    "санвуз": "ванна", "офіс": "офіс", "офис": "офіс", "фасад": "фасад", "нанес": "нанесення", "процес": "нанесення",
    "готов": "готова стіна", "до/після": "до/після", "до і після": "до/після", "до и после": "до/після",
    "викраск": "викраска", "выкраск": "викраска", "пробник": "пробник", "відгук": "відгук", "отзыв": "відгук",
}
THUMB_SALT = "cf-source-thumb"


def tags_from_caption(caption):
    low = (caption or "").lower()
    material = next((name for rx, name in MATERIALS if re.search(rx, low)), "")
    tags = sorted({v for k, v in TAG_WORDS.items() if k in low} | {h.lower() for h in re.findall(r"#(\w+)", low)})
    return material, tags


def _link(chat, message_id):
    if not message_id:
        return ""
    if chat.username:
        return f"https://t.me/{chat.username}/{message_id}"
    internal = str(chat.chat_id).removeprefix("-100").lstrip("-")
    return f"https://t.me/c/{internal}/{message_id}"


def _pick_media(msg):
    """Повертає (kind, file obj, thumb obj) або None. Фото — найбільший розмір, мініатюра — найменший."""
    if msg.get("photo"):
        sizes = msg["photo"]
        return "photo", sizes[-1], sizes[0]
    if msg.get("video"):
        return "video", msg["video"], msg["video"].get("thumbnail") or msg["video"].get("thumb")
    if msg.get("animation"):
        return "video", msg["animation"], msg["animation"].get("thumbnail")
    doc = msg.get("document")
    if doc:
        mime = doc.get("mime_type", "")
        kind = "photo" if mime.startswith("image/") else "video" if mime.startswith("video/") else "document"
        return kind, doc, doc.get("thumbnail") or doc.get("thumb")
    for k in ("audio", "voice"):
        if msg.get(k):
            return "audio", msg[k], None
    return None


def _auto_enabled(chat_id, username):
    """Наш канал (TG_CONTENT_CHANNEL_ID) вмикається сам — він і так публікується з CRM."""
    ch = os.environ.get("TG_CONTENT_CHANNEL_ID", "").strip()
    return bool(ch) and (ch == str(chat_id) or ch.lstrip("@").lower() == (username or "").lower())


def ingest(update):
    """Один апдейт Telegram → запис SourceAsset (або оновлення підпису). Повертає короткий статус."""
    msg = (update.get("message") or update.get("channel_post") or update.get("edited_message")
           or update.get("edited_channel_post"))
    if not msg or not msg.get("chat") or msg["chat"].get("type") == "private":
        return "skip"
    c = msg["chat"]
    chat, _ = SourceChat.objects.get_or_create(chat_id=c["id"], defaults={
        "title": c.get("title", "")[:200], "username": c.get("username", "") or "", "kind": c.get("type", ""),
        "enabled": _auto_enabled(c["id"], c.get("username"))})
    if chat.title != c.get("title", chat.title):
        chat.title = c.get("title", "")[:200]
        chat.save(update_fields=["title"])
    if not chat.enabled:
        return "chat-disabled"
    caption = msg.get("caption") or ""
    group = str(msg.get("media_group_id") or "")
    media = _pick_media(msg)
    if not media:
        return "no-media"
    kind, f, thumb = media
    material, tags = tags_from_caption(caption)
    posted = datetime.fromtimestamp(msg.get("date", 0), tz=dt_tz.utc) if msg.get("date") else None
    asset, created = SourceAsset.objects.update_or_create(file_unique_id=f["file_unique_id"], defaults={
        "origin": SourceAsset.Origin.TELEGRAM, "kind": kind, "chat": chat, "blog_id": chat.blog_id, "message_id": msg.get("message_id"),
        "media_group_id": group, "file_id": f["file_id"], "thumb_file_id": (thumb or {}).get("file_id", ""),
        "mime": f.get("mime_type", "image/jpeg" if kind == "photo" else ""), "size": f.get("file_size"),
        "width": f.get("width"), "height": f.get("height"), "duration": f.get("duration"),
        "file_name": f.get("file_name", "")[:255], "link": _link(chat, msg.get("message_id")), "posted_at": posted,
    })
    # Підпис: в альбомі Telegram кладе його лише в одне повідомлення — розносимо на весь альбом.
    if caption or not asset.caption:
        targets = SourceAsset.objects.filter(media_group_id=group) if group else SourceAsset.objects.filter(pk=asset.pk)
        if caption:
            targets.update(caption=caption, material=material, tags=tags)
        elif group:
            sibling = SourceAsset.objects.filter(media_group_id=group).exclude(caption="").first()
            if sibling:
                SourceAsset.objects.filter(pk=asset.pk).update(caption=sibling.caption, material=sibling.material,
                                                               tags=sibling.tags)
    return "created" if created else "updated"


def thumb_token(asset_id):
    return signing.dumps(asset_id, salt=THUMB_SALT)


def thumb_bytes(token):
    """Мініатюра з Telegram за підписаним посиланням (1 год). Повертає (bytes, content_type) або None."""
    from .telegram import PublishError, _tg, tg_config
    try:
        asset_id = signing.loads(token, salt=THUMB_SALT, max_age=3600)
    except signing.BadSignature:
        return None
    a = SourceAsset.objects.filter(pk=asset_id).first()
    if not a:
        return None
    if a.origin == SourceAsset.Origin.DRIVE:
        from .drive import DriveError, thumbnail
        try:
            return thumbnail(a.file_id)
        except DriveError:
            return None
    fid = a.thumb_file_id or (a.file_id if a.kind == "photo" else "")
    if not fid:
        return None
    try:
        path = _tg("getFile", {"file_id": fid})["file_path"]
    except PublishError:
        return None
    with urllib.request.urlopen(f"https://api.telegram.org/file/bot{tg_config()[0]}/{path}", timeout=30) as r:
        return r.read(), "image/jpeg"
