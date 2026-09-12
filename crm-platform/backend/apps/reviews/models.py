"""Відгуки покупців (12.09.2026, рішення Олега).

Головна копія — CRM: просьба (ReviewRequest) → відгук з форми магазину (Review + фото) →
модерація Олегом → публікація на wallcov.com.ua (магазин забирає стрічку опублікованих).
Відправка просьб клієнтам ВИМКНЕНА (ReviewSettings.send_enabled=False), доки Олег не затвердить тексти.
"""
from datetime import date, time

from django.conf import settings
from django.db import models
from django.db.models import Q

GOOGLE_REVIEW_URL = "https://g.page/r/CVZX_3B9PYFbEBM/review"


class ReviewSettings(models.Model):
    """Налаштування відгуків (один рядок, id=1)."""
    send_enabled = models.BooleanField(default=False, help_text="Надсилати просьби клієнтам. Вмикається лише після затвердження текстів")
    texts_approved = models.BooleanField(default=False, help_text="Олег затвердив тексти просьби/нагадування")
    start_date = models.DateField(null=True, blank=True, help_text="Беремо лише посилки, отримані з цієї дати")
    delay_main_days = models.PositiveSmallIntegerField(default=10)
    delay_test_days = models.PositiveSmallIntegerField(default=5)
    remind_after_days = models.PositiveSmallIntegerField(default=5)
    repeat_block_days = models.PositiveSmallIntegerField(default=60)
    expire_days = models.PositiveSmallIntegerField(default=60)
    window_wait_days = models.PositiveSmallIntegerField(default=21, help_text="Скільки днів чекати можливості написати")
    manager_quiet_hours = models.PositiveSmallIntegerField(default=48, help_text="Тест-набір: не писати, якщо менеджер писав клієнту за стільки годин")
    send_from = models.TimeField(default=time(10, 0))
    send_to = models.TimeField(default=time(19, 30))
    per_run_cap = models.PositiveSmallIntegerField(default=20)
    test_funnel_ids = models.JSONField(default=list, blank=True, help_text="Воронки тест-наборів")
    excluded_funnel_ids = models.JSONField(default=list, blank=True, help_text="Воронки, де не просимо (тести, найм, ліди)")
    allowlist_contact_ids = models.JSONField(default=list, blank=True, help_text="Якщо не порожньо — надсилати лише цим контактам (тест)")
    text_main = models.TextField(blank=True, default="")
    text_test = models.TextField(blank=True, default="")
    text_remind = models.TextField(blank=True, default="")
    google_review_url = models.URLField(max_length=300, default=GOOGLE_REVIEW_URL)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Налаштування відгуків"

    @classmethod
    def get(cls):
        obj = cls.objects.filter(pk=1).first()
        if obj:
            return obj
        from apps.crm.models import Funnel
        test_ids = list(Funnel.objects.filter(name__icontains="Тестовий набір").values_list("id", flat=True))
        excluded = list(Funnel.objects.filter(
            Q(name__icontains="Техническая") | Q(name__icontains="Найм") | Q(is_lead_funnel=True)
        ).values_list("id", flat=True))
        obj, _ = cls.objects.get_or_create(pk=1, defaults={
            "test_funnel_ids": test_ids, "excluded_funnel_ids": excluded, "start_date": date(2026, 9, 1)})
        return obj


class ReviewRequest(models.Model):
    """Просьба залишити відгук по угоді: коли, яким каналом, що сталося (журнал)."""
    KIND = [("main", "Основне замовлення"), ("test", "Тест-набір"), ("manual", "Вручну")]
    STATUS = [
        ("scheduled", "Заплановано"),
        ("waiting", "Чекаємо"),
        ("would_send", "Відправили б (відправка вимкнена)"),
        ("sent", "Надіслано"),
        ("reminded", "Нагадали"),
        ("submitted", "Відгук отримано"),
        ("skipped", "Пропущено"),
        ("cancelled", "Скасовано"),
        ("opted_out", "Клієнт відписався"),
        ("expired", "Минув термін"),
        ("test", "Тестове посилання"),
    ]
    deal = models.ForeignKey("crm.Deal", null=True, blank=True, on_delete=models.SET_NULL, related_name="review_requests")
    contact = models.ForeignKey("crm.Contact", null=True, blank=True, on_delete=models.SET_NULL, related_name="review_requests")
    kind = models.CharField(max_length=12, choices=KIND, default="main")
    code = models.CharField(max_length=16, unique=True)
    status = models.CharField(max_length=12, choices=STATUS, default="scheduled", db_index=True)
    reason = models.CharField(max_length=300, blank=True, default="")
    is_test = models.BooleanField(default=False)
    received_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    channel_plan = models.CharField(max_length=20, blank=True, default="")
    channel_label = models.CharField(max_length=120, blank=True, default="")
    channel = models.ForeignKey("inbox.Channel", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    conversation = models.ForeignKey("inbox.Conversation", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    message = models.ForeignKey("inbox.Message", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reminder_message = models.ForeignKey("inbox.Message", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    checked_at = models.DateTimeField(null=True, blank=True)
    journal_at = models.DateTimeField(null=True, blank=True, help_text="Коли потрапило в журнал «відправили б»")
    sent_at = models.DateTimeField(null=True, blank=True)
    reminded_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=300, blank=True, default="")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["deal"], condition=Q(deal__isnull=False) & ~Q(kind="manual"),
                                    name="reviews_one_auto_request_per_deal"),
        ]

    def __str__(self):
        return "Просьба #%s (угода %s, %s)" % (self.pk, self.deal_id, self.status)


class Review(models.Model):
    """Відгук покупця з форми на сайті. text — для показу (модератор може приховати особисті дані),
    text_original — як написав клієнт, не змінюється."""
    STATUS = [("pending", "На перевірці"), ("published", "Опубліковано"), ("hidden", "Приховано")]
    request = models.OneToOneField(ReviewRequest, null=True, blank=True, on_delete=models.SET_NULL, related_name="review")
    deal = models.ForeignKey("crm.Deal", null=True, blank=True, on_delete=models.SET_NULL, related_name="reviews")
    contact = models.ForeignKey("crm.Contact", null=True, blank=True, on_delete=models.SET_NULL, related_name="reviews")
    event_uuid = models.UUIDField(unique=True)
    rating = models.PositiveSmallIntegerField()
    text = models.TextField(blank=True, default="")
    text_original = models.TextField(blank=True, default="")
    room = models.CharField(max_length=20, blank=True, default="")
    applied_by = models.CharField(max_length=10, blank=True, default="unknown")
    display_name = models.CharField(max_length=60, blank=True, default="")
    anonymous = models.BooleanField(default=False)
    city = models.CharField(max_length=60, blank=True, default="")
    consent_site = models.BooleanField(default=False)
    consent_social = models.BooleanField(default=False)
    consent_version = models.CharField(max_length=40, blank=True, default="")
    consent_at = models.DateTimeField(null=True, blank=True)
    products = models.JSONField(default=list, blank=True)
    kind = models.CharField(max_length=12, default="main")
    is_test = models.BooleanField(default=False)
    status = models.CharField(max_length=12, choices=STATUS, default="pending", db_index=True)
    hidden_reason = models.CharField(max_length=200, blank=True, default="")
    reply_text = models.TextField(blank=True, default="")
    replied_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    replied_at = models.DateTimeField(null=True, blank=True)
    featured = models.BooleanField(default=False)
    moderated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    moderated_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    task = models.ForeignKey("crm.Task", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return "Відгук #%s %s★" % (self.pk, self.rating)


class ReviewPhoto(models.Model):
    """Фото до відгуку: пересохранене CRM без EXIF/геолокації (≤1600 px) + превʼю ≤480 px."""
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="photos")
    token = models.CharField(max_length=40, unique=True)
    data = models.BinaryField()
    thumb = models.BinaryField()
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True, default="")
    sort = models.PositiveSmallIntegerField(default=0)
    is_public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort", "id"]


class ReviewOptOut(models.Model):
    """Клієнт не хоче просьб про відгук («стоп» або вручну) — більше ніколи не просимо."""
    REASON = [("keyword", "Відповів «стоп»"), ("manual", "Вручну"), ("form", "Через форму")]
    contact = models.OneToOneField("crm.Contact", on_delete=models.CASCADE, related_name="review_opt_out")
    reason = models.CharField(max_length=10, choices=REASON, default="manual")
    note = models.CharField(max_length=200, blank=True, default="")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
