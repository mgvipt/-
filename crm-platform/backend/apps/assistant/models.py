"""Особистий ШІ-асистент Олега (24.09.2026).

Бот @wallcov_smm_bot, підключений Олегом у Telegram Business → Чат-боти, МОВЧКИ отримує повідомлення вибраних
особистих чатів (таргетолог, постачальники…) — сам нікому не пише. Плюс робочі групи (історія РОП-бота).
Голосові розшифровуються. ШІ витягує факти, ціни, домовленості, рішення → ПРОПОЗИЦІЇ; у базу знань CRM потрапляє
лише те, що Олег схвалив, і спершу як чернетка (агенти читають тільки затверджене). Усе бачить лише власник.
"""
from django.db import models


class AssistantChat(models.Model):
    class Kind(models.TextChoices):
        BUSINESS = "business", "Особистий чат (Telegram Business)"
        GROUP = "group", "Робоча група"
        IMPORT = "import", "Імпорт історії"

    chat_id = models.BigIntegerField(unique=True)
    title = models.CharField(max_length=200, blank=True)
    username = models.CharField(max_length=100, blank=True)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.BUSINESS)
    enabled = models.BooleanField(default=True, help_text="Вимкнений чат не зберігається й не аналізується")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title or str(self.chat_id)


class AssistantMessage(models.Model):
    class Kind(models.TextChoices):
        TEXT = "text", "Текст"
        VOICE = "voice", "Голосове"
        VIDEO_NOTE = "video_note", "Кружечок"
        PHOTO = "photo", "Фото"
        DOCUMENT = "document", "Файл"
        OTHER = "other", "Інше"

    chat = models.ForeignKey(AssistantChat, on_delete=models.CASCADE, related_name="messages")
    message_id = models.BigIntegerField()
    from_owner = models.BooleanField(default=False, help_text="Написав/сказав сам Олег")
    author = models.CharField(max_length=160, blank=True)
    sender_id = models.BigIntegerField(null=True, blank=True, db_index=True, help_text="Telegram id відправника")
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.TEXT)
    text = models.TextField(blank=True)
    transcript = models.TextField(blank=True, help_text="Розшифровка голосового")
    file_id = models.CharField(max_length=255, blank=True)
    duration = models.IntegerField(null=True, blank=True)
    sent_at = models.DateTimeField(db_index=True)
    transcribed_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True, db_index=True, help_text="Коли ШІ вже розібрав")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sent_at"]
        constraints = [models.UniqueConstraint(fields=["chat", "message_id"], name="assistant_msg_chat_mid_uniq")]

    @property
    def body(self):
        return (self.transcript or self.text or "").strip()


class AssistantProposal(models.Model):
    class Kind(models.TextChoices):
        FACT = "fact", "Факт / знання"
        PRICE = "price", "Ціна / умови постачальника"
        AGREEMENT = "agreement", "Домовленість"
        DECISION = "decision", "Рішення"
        STYLE = "style", "Мій стиль / як я кажу"

    class Status(models.TextChoices):
        NEW = "new", "Нова"
        ACCEPTED = "accepted", "Додано"
        REJECTED = "rejected", "Відхилено"

    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.FACT, db_index=True)
    title = models.CharField(max_length=200)
    text = models.TextField()
    who = models.CharField(max_length=160, blank=True, help_text="З ким / про кого")
    due = models.DateField(null=True, blank=True, help_text="Строк домовленості")
    chat = models.ForeignKey(AssistantChat, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    evidence = models.JSONField(default=list, blank=True, help_text="[{message_id, quote}] — звідки взято")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW, db_index=True)
    knowledge_item_id = models.IntegerField(null=True, blank=True, help_text="Чернетка в базі знань після «Додати»")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class AssistantSettings(models.Model):
    extraction_enabled = models.BooleanField(default=False, help_text="Щоночі розбирати нові повідомлення (платно)")
    model = models.CharField(max_length=40, default="claude-sonnet-4-6")
    monthly_budget_usd = models.DecimalField(max_digits=6, decimal_places=2, default=5)
    owner_tg_id = models.BigIntegerField(null=True, blank=True, help_text="Telegram id Олега — щоб знати, що сказав він")

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
