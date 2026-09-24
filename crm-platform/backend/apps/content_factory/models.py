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


# ── Етап 2 (24.09.2026): Telegram-автопілот ────────────────────────────────────────────────────

class TgSettings(models.Model):
    """Налаштування автопілота каналу. Публікації з CRM поки немає — лише чернетки на схвалення."""
    daily_drafts = models.BooleanField(default=False, help_text="Щоранку чернетка з найчастішого питання (платно, в межах ліміту)")
    model = models.CharField(max_length=40, choices=QuestionSettings.MODELS, default="claude-sonnet-4-6")
    monthly_budget_usd = models.DecimalField(max_digits=6, decimal_places=2, default=2)
    channel = models.CharField(max_length=64, default="@wallcovpro")

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class TgPost(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Чернетка"
        APPROVED = "approved", "Схвалено"
        REJECTED = "rejected", "Відхилено"
        PUBLISHED = "published", "Опубліковано"

    topic = models.ForeignKey(QuestionTopic, null=True, blank=True, on_delete=models.SET_NULL, related_name="tg_posts")
    title = models.CharField(max_length=200)
    text = models.TextField()
    material = models.CharField(max_length=80, blank=True)
    photo_ids = models.JSONField(default=list, blank=True, help_text="inbox.MediaLibraryItem — лише реальні фото обʼєктів")
    video_ids = models.JSONField(default=list, blank=True, help_text="inbox.MediaLibraryItem kind=video (24.09, публікація)")
    scheduled_at = models.DateTimeField(null=True, blank=True, db_index=True,
                                        help_text="Коли опублікувати (лише схвалені). Порожньо — вручну")
    publish_error = models.CharField(max_length=300, blank=True)
    source_ids = models.JSONField(default=list, blank=True, help_text="SourceAsset з TG — шлються за file_id, без завантаження")
    views = models.IntegerField(null=True, blank=True, help_text="Перегляди з публічного віджета каналу")
    reactions = models.IntegerField(null=True, blank=True)
    reactions_detail = models.JSONField(default=dict, blank=True, help_text="{емодзі: кількість}")
    stats_at = models.DateTimeField(null=True, blank=True)
    facts = models.JSONField(default=list, blank=True, help_text="Назви записів бази знань, з яких узято факти")
    checks = models.JSONField(default=list, blank=True, help_text="Що перевірити людині перед публікацією")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    model = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    tg_message_id = models.CharField(max_length=40, blank=True)

    class Meta:
        ordering = ["-created_at"]

# ── Джерела контенту (24.09.2026): TG-групи/канал і Google Drive — лише посилання, без завантаження ──

class SourceChat(models.Model):
    """Чат Telegram, звідки бот пересилає файли. Новий чат зʼявляється вимкненим — вмикає власник."""
    chat_id = models.BigIntegerField(unique=True)
    title = models.CharField(max_length=200, blank=True)
    username = models.CharField(max_length=100, blank=True)
    kind = models.CharField(max_length=20, blank=True, help_text="group / supergroup / channel")
    enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title or str(self.chat_id)


class SourceAsset(models.Model):
    """Файл у джерелі. Зберігаємо file_id, підпис і посилання; сам файл лишається в Telegram/Drive."""
    class Origin(models.TextChoices):
        TELEGRAM = "telegram", "Telegram"
        DRIVE = "drive", "Google Drive"

    class Kind(models.TextChoices):
        PHOTO = "photo", "Фото"
        VIDEO = "video", "Відео"
        DOCUMENT = "document", "Файл"
        AUDIO = "audio", "Аудіо"

    origin = models.CharField(max_length=12, choices=Origin.choices, default=Origin.TELEGRAM)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    chat = models.ForeignKey(SourceChat, null=True, blank=True, on_delete=models.SET_NULL, related_name="assets")
    message_id = models.BigIntegerField(null=True, blank=True)
    media_group_id = models.CharField(max_length=40, blank=True, db_index=True)
    file_id = models.CharField(max_length=255, help_text="Telegram file_id або Drive fileId")
    file_unique_id = models.CharField(max_length=128, unique=True)
    thumb_file_id = models.CharField(max_length=255, blank=True)
    mime = models.CharField(max_length=100, blank=True)
    size = models.BigIntegerField(null=True, blank=True)
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    duration = models.IntegerField(null=True, blank=True)
    file_name = models.CharField(max_length=255, blank=True)
    caption = models.TextField(blank=True, help_text="Підпис під файлом — з нього беремо теги")
    link = models.URLField(max_length=500, blank=True)
    material = models.CharField(max_length=80, blank=True, db_index=True)
    tags = models.JSONField(default=list, blank=True)
    hidden = models.BooleanField(default=False, help_text="Не показувати в добірках (сміття, дубль)")
    markup_at = models.DateTimeField(null=True, blank=True, help_text="Коли ШІ розмітив сцени (лише відео)")
    posted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-posted_at", "-id"]


class DriveFolder(models.Model):
    """Папка Google Drive, яку CRM раз на добу обходить і заносить у «Джерела» лише посилання й назви файлів.
    Доступ — сервісний акаунт GA4 (ads-bot@…): папка має бути відкрита йому або «всім, у кого є посилання»."""
    folder_id = models.CharField(max_length=80, unique=True)
    title = models.CharField(max_length=200, blank=True)
    enabled = models.BooleanField(default=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    files_count = models.IntegerField(default=0)
    last_error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title or self.folder_id


class TgPostStat(models.Model):
    """Знімок переглядів/реакцій опублікованого поста — щоб бачити ріст (1 год, доба, 3 дні, тиждень)."""
    post = models.ForeignKey(TgPost, on_delete=models.CASCADE, related_name="stats")
    views = models.IntegerField(null=True, blank=True)
    reactions = models.IntegerField(null=True, blank=True)
    taken_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["taken_at"]


# ── Етап 3 (24.09.2026): стрічка рекомендацій і аналітик ─────────────────────────────────────────

class FeedItem(models.Model):
    """Ролик/карусель зі сторінок, які відстежує Virale (ChatPlace). Лише метадані й посилання."""
    class Status(models.TextChoices):
        NEW = "new", "Нове"
        SAVED = "saved", "В ідеях"
        USED = "used", "Зроблено з наших"
        HIDDEN = "hidden", "Сховано"

    external_id = models.CharField(max_length=64, unique=True)
    username = models.CharField(max_length=100, db_index=True)
    platform = models.CharField(max_length=20, blank=True)
    url = models.URLField(max_length=2000)
    preview_url = models.URLField(max_length=2000, blank=True, help_text="Підписані посилання Virale бувають довгими")
    caption = models.TextField(blank=True)
    media_type = models.CharField(max_length=20, blank=True)
    duration = models.FloatField(null=True, blank=True)
    views = models.BigIntegerField(null=True, blank=True)
    likes = models.IntegerField(null=True, blank=True)
    comments = models.IntegerField(null=True, blank=True)
    engagement = models.FloatField(null=True, blank=True)
    viral_score = models.FloatField(null=True, blank=True)
    is_own = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at"]


class AnalystSettings(models.Model):
    weekly_enabled = models.BooleanField(default=False, help_text="Щопонеділка звіт (платно, в межах ліміту)")
    model = models.CharField(max_length=40, choices=QuestionSettings.MODELS, default="claude-sonnet-4-6")
    monthly_budget_usd = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    last_feed_sync_at = models.DateTimeField(null=True, blank=True)
    last_feed_note = models.CharField(max_length=300, blank=True)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class AnalystReport(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    period_days = models.PositiveSmallIntegerField(default=7)
    summary = models.TextField(help_text="Звіт простими словами")
    ideas = models.JSONField(default=list, blank=True, help_text="[{title, hook, why, format, material}]")
    inputs = models.JSONField(default=dict, blank=True, help_text="Цифри, на яких зроблено звіт")
    model = models.CharField(max_length=40, blank=True)

    class Meta:
        ordering = ["-created_at"]


# ── Етап 4–5 (24.09.2026): розмітка сцен відео і генератор рилсів ────────────────────────────────

class VideoScene(models.Model):
    """Сцена у відео-джерелі: що відбувається з такої-то до такої-то секунди. Розмічає ШІ один раз."""
    asset = models.ForeignKey(SourceAsset, on_delete=models.CASCADE, related_name="scenes")
    start = models.FloatField()
    end = models.FloatField()
    shot = models.CharField(max_length=40, blank=True, help_text="крупно / загальний план / процес / результат / людина")
    what = models.CharField(max_length=300)
    quality = models.PositiveSmallIntegerField(default=3, help_text="1–5: різкість, світло, чи видно фактуру")
    tags = models.JSONField(default=list, blank=True)
    thumb = models.ForeignKey("inbox.SharedLink", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                              help_text="Кадр із середини сцени (240px) — для вибору при заміні")

    class Meta:
        ordering = ["asset_id", "start"]


class ReelDraft(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Чернетка"
        APPROVED = "approved", "Схвалено"
        REJECTED = "rejected", "Відхилено"

    title = models.CharField(max_length=200)
    topic = models.CharField(max_length=300, blank=True)
    material = models.CharField(max_length=80, blank=True)
    caption = models.TextField(blank=True, help_text="Підпис до рилса")
    beats = models.JSONField(default=list, blank=True, help_text="[{text, scene_id, seconds}] — сценарій по кадрах")
    facts = models.JSONField(default=list, blank=True)
    file = models.ForeignKey("inbox.SharedLink", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    duration = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    error = models.CharField(max_length=300, blank=True)
    style = models.ForeignKey("ReelStyle", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class ReelStyle(models.Model):
    """Стиль тексту на рилсі: пресет, знятий з референсу (обкладинка/відео) або «наш блог»."""
    class Origin(models.TextChoices):
        PRESET = "preset", "Пресет"
        REFERENCE = "reference", "З референсу"
        BLOG = "blog", "Наш блог"

    name = models.CharField(max_length=120)
    origin = models.CharField(max_length=12, choices=Origin.choices, default=Origin.PRESET)
    source_url = models.URLField(max_length=2000, blank=True)
    font = models.CharField(max_length=40, default="DejaVu Sans")
    weight = models.CharField(max_length=20, default="Bold")
    size = models.PositiveSmallIntegerField(default=68, help_text="px при ширині 1080")
    color = models.CharField(max_length=9, default="#FFFFFF")
    stroke_color = models.CharField(max_length=9, default="#000000")
    stroke = models.PositiveSmallIntegerField(default=0)
    box = models.BooleanField(default=True)
    box_color = models.CharField(max_length=9, default="#000000")
    box_opacity = models.FloatField(default=0.45)
    position = models.FloatField(default=0.70, help_text="Вертикаль центру тексту: 0 — верх, 1 — низ")
    upper = models.BooleanField(default=False)
    notes = models.CharField(max_length=300, blank=True)
    structure = models.JSONField(default=dict, blank=True, help_text="Темп і будова ролика-референсу (якщо було відео)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["origin", "name"]
