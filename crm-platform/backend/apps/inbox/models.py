from django.conf import settings
from django.db import models
from apps.crm.models import Contact


class Channel(models.Model):
    """Открытая линия — подключённый канал (Telegram-бот, Instagram и т.д.)."""
    KINDS = [
        ("telegram", "Telegram"), ("viber", "Viber"), ("instagram", "Instagram"),
        ("facebook", "Facebook"), ("whatsapp", "WhatsApp"), ("google_business", "Google Бизнес"),
        ("echat_whatsapp", "WhatsApp (e-chat)"),
        ("web", "Web Chat"),
    ]
    kind = models.CharField(max_length=24, choices=KINDS)
    name = models.CharField(max_length=120)
    # секреты/настройки канала (для Telegram: {"bot_token": "..."}). Не отдаётся в API.
    config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_kind_display()} · {self.name}"


class Conversation(models.Model):
    """Диалог с клиентом в рамках канала."""
    STATUS = [("open", "Открыт"), ("closed", "Закрыт")]
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name="conversations")
    contact = models.ForeignKey(Contact, null=True, blank=True, on_delete=models.SET_NULL, related_name="conversations")
    external_chat_id = models.CharField(max_length=128, db_index=True)
    title = models.CharField(max_length=160, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="open")
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="conversations")
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="participating_conversations")
    unread = models.PositiveIntegerField(default=0)
    priority = models.CharField(max_length=20, blank=True, default="")
    priority_reason = models.CharField(max_length=200, blank=True, default="")
    priority_at = models.DateTimeField(null=True, blank=True)
    priority_seen_count = models.PositiveIntegerField(default=0)
    last_message_at = models.DateTimeField(null=True, blank=True)
    config = models.JSONField(default=dict, blank=True)  # source_card тощо (Meta комент-чати)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-last_message_at", "-created_at"]

    def __str__(self):
        return self.title or f"Диалог #{self.pk}"


class Message(models.Model):
    DIRECTION = [("in", "Входящее"), ("out", "Исходящее")]
    STATUS = [
        ("sent", "Надіслано"),
        ("delivered", "Доставлено"),
        ("read", "Прочитано"),
        ("failed", "Не доставлено"),
        ("window_risk", "Вікно закрите — міг не дійти"),
    ]
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    direction = models.CharField(max_length=3, choices=DIRECTION)
    internal = models.BooleanField(default=False, help_text="Внутрішня нотатка — видно лише менеджерам, клієнту НЕ йде")
    is_followup = models.BooleanField(default=False, help_text="Дожим — повідомлення-нагадування клієнту, який замовк")
    text = models.TextField(blank=True)
    # вложения: [{"type":"photo|voice|file","url":..., "size":...}]
    attachments = models.JSONField(default=list, blank=True)
    external_id = models.CharField(max_length=128, blank=True)
    # Instagram-відповідь менеджера може піти через ChatPlace (external_id =
    # ChatPlace id), а квитанції delivery/read повертаються з окремим Meta mid.
    # Зберігаємо обидва значення, не перезаписуючи ідентифікатор провайдера відправки.
    meta_external_id = models.CharField(max_length=128, blank=True, db_index=True)
    sender_name = models.CharField(max_length=160, blank=True)
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="sent_messages")
    status = models.CharField(max_length=12, choices=STATUS, default="sent", help_text="Статус доставки вихідного")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["conversation", "external_id"],
                                    condition=~models.Q(external_id=""),
                                    name="uniq_conv_extid"),  # #16 без дублів повідомлень
        ]

    def __str__(self):
        return f"[{self.direction}] {self.text[:40]}"


class Notification(models.Model):
    """Персональне сповіщення співробітнику (напр. «вас додали до чату»)."""
    KIND = [("added_chat", "Додано до чату"), ("system", "Система")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=16, choices=KIND, default="system")
    text = models.CharField(max_length=300)
    conversation = models.ForeignKey(Conversation, null=True, blank=True, on_delete=models.CASCADE)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]



class SharedLink(models.Model):
    """Файл/фото для відправки клієнту ПОСИЛАННЯМ (обхід обмеження IG на медіа)."""
    token = models.CharField(max_length=48, unique=True, db_index=True)
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, default="application/octet-stream")
    data = models.BinaryField()
    created_at = models.DateTimeField(auto_now_add=True)


class MediaLibraryItem(models.Model):
    """Reusable asset for Open Lines. The bytes live in one SharedLink and are never copied per send."""
    KIND = [("image", "Фото"), ("video", "Відео"), ("catalog", "Каталог")]
    SECTION = [("colors", "Кольори"), ("quick", "Швидкі відповіді")]
    title = models.CharField(max_length=160)
    kind = models.CharField(max_length=16, choices=KIND, default="image")
    section = models.CharField(max_length=16, choices=SECTION, default="quick")
    material = models.CharField(max_length=100, default="Мокрий шовк", db_index=True)
    color_code = models.CharField(max_length=48, blank=True, db_index=True)
    tags = models.CharField(max_length=240, blank=True)
    file = models.ForeignKey(SharedLink, null=True, blank=True, on_delete=models.SET_NULL, related_name="library_items")
    public_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    sort = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["section", "sort", "title"]


class QuickReply(models.Model):
    title = models.CharField(max_length=120)
    text = models.TextField(blank=True)
    assets = models.ManyToManyField(MediaLibraryItem, blank=True, related_name="quick_replies")
    is_active = models.BooleanField(default=True)
    sort = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort", "title"]



class TeamMessage(models.Model):
    """Внутрішній чат між співробітниками (DM). Текст + файли + згадки (@)."""
    from django.conf import settings as _s
    sender = models.ForeignKey(_s.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="team_sent")
    recipient = models.ForeignKey(_s.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE,
                                  related_name="team_received", help_text="NULL = загальний чат (усім)")
    text = models.TextField(blank=True)
    attachments = models.JSONField(default=list, blank=True)
    mentions = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]


class SoundLibrary(models.Model):
    """Спільна бібліотека завантажених звуків сповіщень. Вибирати може будь-хто;
    завантажувати/видаляти — лише з правом settings.sounds.upload. Дедуп по sha256 (без дублів)."""
    from django.conf import settings as _s3
    name = models.CharField(max_length=160)
    sha256 = models.CharField(max_length=64, unique=True, db_index=True)
    mime = models.CharField(max_length=60, default="audio/mpeg")
    data = models.BinaryField()
    size = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(_s3.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
