"""Контент-завод (24.09.2026, етап 0): сторінки у соцмережах, які аналізуємо.

Наші сторінки, конкуренти й джерела натхнення в Instagram / TikTok / YouTube / Telegram.
Далі (етапи 1–7) сюди додаються питання клієнтів, стрічка рекомендацій, аналітик, рилси, каруселі
та TG-автопілот. Доступ — лише власник або право content_factory.access.
"""
import re
from urllib.parse import urlparse

from django.conf import settings
from django.db import models


class ContentChannel(models.Model):
    class Platform(models.TextChoices):
        INSTAGRAM = "instagram", "Instagram"
        TIKTOK = "tiktok", "TikTok"
        YOUTUBE = "youtube", "YouTube"
        TELEGRAM = "telegram", "Telegram"

    class Role(models.TextChoices):
        OWN = "own", "Наша сторінка"
        COMPETITOR = "competitor", "Конкурент"
        INSPIRATION = "inspiration", "Натхнення"

    platform = models.CharField(max_length=16, choices=Platform.choices)
    handle = models.CharField(max_length=150, help_text="Імʼя сторінки без @, у нижньому регістрі (для YouTube channel/ID)")
    url = models.URLField(max_length=500)
    title = models.CharField(max_length=200, blank=True)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.COMPETITOR)
    note = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, help_text="Вимкнена сторінка не аналізується, але історія лишається")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["role", "platform", "handle"]
        constraints = [models.UniqueConstraint(fields=["platform", "handle"], name="cf_channel_platform_handle_uniq")]

    def __str__(self):
        return f"{self.get_platform_display()} @{self.handle}"


class ChannelLinkError(ValueError):
    """Посилання не схоже на сторінку — текст помилки показуємо користувачу як є."""


_HANDLE_RX = re.compile(r"^[A-Za-z0-9._-]{1,150}$")
# шляхи, які є постом / сервісною сторінкою, а не профілем
_IG_NOT_PROFILE = {"p", "reel", "reels", "stories", "explore", "tv", "accounts", "direct", "s"}
_TG_NOT_PROFILE = {"joinchat", "addstickers", "share", "proxy", "iv"}


def _clean(handle):
    handle = (handle or "").strip().lstrip("@").strip("/")
    if not _HANDLE_RX.match(handle):
        raise ChannelLinkError("Не бачу імені сторінки в посиланні.")
    return handle


def parse_channel_link(text, platform_hint=""):
    """Посилання або @імʼя → (platform, handle, canonical_url). Піднімає ChannelLinkError з людським текстом."""
    raw = (text or "").strip()
    if not raw:
        raise ChannelLinkError("Вставте посилання на сторінку.")
    if raw.startswith("@") and " " not in raw:
        if platform_hint not in ContentChannel.Platform.values:
            raise ChannelLinkError("Для @імені оберіть соцмережу або вставте повне посилання.")
        return _build(platform_hint, _clean(raw))

    if "://" not in raw:
        raw = "https://" + raw
    u = urlparse(raw)
    host = (u.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    parts = [p for p in u.path.split("/") if p]

    if host in ("instagram.com", "instagr.am"):
        if not parts or parts[0].lower() in _IG_NOT_PROFILE:
            raise ChannelLinkError("Це посилання на пост або рилс. Потрібне посилання на сторінку: instagram.com/імʼя")
        return _build("instagram", _clean(parts[0]))
    if host.endswith("tiktok.com"):
        if host.startswith("vm.") or host.startswith("vt.") or not parts or not parts[0].startswith("@"):
            raise ChannelLinkError("Потрібне посилання на профіль: tiktok.com/@імʼя (не на окреме відео)")
        return _build("tiktok", _clean(parts[0]))
    if host in ("youtube.com", "music.youtube.com"):
        if parts and parts[0].startswith("@"):
            return _build("youtube", _clean(parts[0]))
        if len(parts) >= 2 and parts[0] in ("channel", "c", "user"):
            return _build("youtube", _clean(parts[1]), kind=parts[0])
        raise ChannelLinkError("Потрібне посилання на канал: youtube.com/@імʼя (не на окреме відео)")
    if host == "youtu.be":
        raise ChannelLinkError("Це посилання на відео. Потрібне посилання на канал: youtube.com/@імʼя")
    if host in ("t.me", "telegram.me", "telegram.dog"):
        if parts and parts[0] == "s":
            parts = parts[1:]
        if not parts or parts[0].startswith("+") or parts[0].lower() in _TG_NOT_PROFILE:
            raise ChannelLinkError("Потрібне публічне посилання на канал: t.me/імʼя (закриті запрошення не підходять)")
        return _build("telegram", _clean(parts[0]))
    raise ChannelLinkError("Підтримуються Instagram, TikTok, YouTube і Telegram.")


def _build(platform, handle, kind=""):
    if platform == "instagram":
        handle = handle.lower()
        return platform, handle, f"https://www.instagram.com/{handle}/"
    if platform == "tiktok":
        handle = handle.lower()
        return platform, handle, f"https://www.tiktok.com/@{handle}"
    if platform == "youtube":
        if kind in ("channel", "c", "user"):
            return platform, f"{kind}/{handle}", f"https://www.youtube.com/{kind}/{handle}"
        handle = handle.lower()
        return platform, handle, f"https://www.youtube.com/@{handle}"
    handle = handle.lower()
    return platform, handle, f"https://t.me/{handle}"


# ── Етап 1 (24.09.2026): питання клієнтів → теми ──────────────────────────────────────────────

class QuestionSettings(models.Model):
    """Один рядок налаштувань нічного розбору питань. За замовчуванням ВИМКНЕНО — вмикає власник."""
    MODELS = [("claude-sonnet-4-6", "Sonnet 4.6 — точніше групує"), ("claude-haiku-4-5", "Haiku 4.5 — найдешевше")]
    enabled = models.BooleanField(default=False)
    model = models.CharField(max_length=40, choices=MODELS, default="claude-sonnet-4-6")
    monthly_budget_usd = models.DecimalField(max_digits=6, decimal_places=2, default=2,
                                             help_text="Ліміт на місяць. Досягнуто — розбір зупиняється до 1-го числа")
    min_new = models.PositiveSmallIntegerField(default=5, help_text="Менше нових питань — ШІ не викликаємо")
    backfill_days = models.PositiveSmallIntegerField(default=7, help_text="Перший запуск бере питання за стільки днів")
    last_message_id = models.BigIntegerField(default=0, help_text="До якого повідомлення вже розібрано")
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_run_note = models.CharField(max_length=300, blank=True)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class QuestionTopic(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Нова"
        PLANNED = "planned", "У плані контенту"
        DONE = "done", "Контент зроблено"
        IGNORED = "ignored", "Не для контенту"

    title = models.CharField(max_length=200, help_text="Питання словами клієнта, українською")
    material = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW, db_index=True)
    examples = models.JSONField(default=list, blank=True, help_text="До 5 останніх формулювань, без телефонів і пошти")
    kb_item_id = models.IntegerField(null=True, blank=True, help_text="Схожий затверджений запис бази знань (пошук за словами)")
    kb_item_title = models.CharField(max_length=200, blank=True)
    first_seen = models.DateTimeField(null=True, blank=True)
    last_seen = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-last_seen"]

    def __str__(self):
        return self.title


class QuestionMention(models.Model):
    """Одне повідомлення клієнта, віднесене до теми. Одне повідомлення — одна тема (розбирається раз)."""
    topic = models.ForeignKey(QuestionTopic, on_delete=models.CASCADE, related_name="mentions")
    message_id = models.BigIntegerField(unique=True, help_text="inbox.Message.id (без FK — історію не чіпаємо)")
    channel = models.CharField(max_length=24, blank=True)
    asked_at = models.DateTimeField(db_index=True)
