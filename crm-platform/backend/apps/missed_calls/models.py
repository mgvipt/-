"""Черга «Пропущені дзвінки» (14.09.2026). Окремий застосунок — моделі телефонії не чіпаємо."""
from datetime import time

from django.conf import settings
from django.db import models


class MissedCallSettings(models.Model):
    """Налаштування черги (один рядок). Змінює власник / хто керує чергою вхідних."""
    work_start = models.TimeField(default=time(9, 0), help_text="Початок робочого дня (для 15 робочих хвилин)")
    work_end = models.TimeField(default=time(18, 0), help_text="Кінець робочого дня")
    work_days = models.JSONField(default=list, blank=True, help_text="Робочі дні 0=Пн…6=Нд; порожньо = щодня")
    sla_minutes = models.PositiveIntegerField(default=15, help_text="За скільки робочих хвилин треба передзвонити")
    escalate_minutes = models.PositiveIntegerField(default=60, help_text="Через скільки робочих хвилин сказати керівнику")
    escalate_user_ids = models.JSONField(default=list, blank=True, help_text="Кому ескалація; порожньо = власник (суперадмін)")
    auto_task = models.BooleanField(default=True, help_text="Ставити задачу «Передзвонити» відповідальному")
    ignore_numbers = models.JSONField(default=list, blank=True, help_text="Номери, які НЕ потрапляють у чергу (внутрішні)")
    ignore_staff_numbers = models.BooleanField(default=True, help_text="Не рахувати дзвінки з номерів співробітників")
    active_since = models.DateTimeField(null=True, blank=True, help_text="З цього моменту пропущені йдуть у чергу")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Налаштування пропущених"

    @classmethod
    def get(cls):
        obj = cls.objects.order_by("id").first()
        if not obj:
            from django.utils import timezone
            obj = cls.objects.create(active_since=timezone.now(), work_days=[0, 1, 2, 3, 4, 5, 6])
        return obj


class MissedCallItem(models.Model):
    """Пункт черги: пропущений вхідний, якому ще треба передзвонити (або вже оброблений)."""
    STATUS = [("open", "Треба передзвонити"), ("closed", "Оброблено")]
    REASONS = [
        ("callback", "Передзвонили"),
        ("client_called", "Клієнт додзвонився сам"),
        ("other_channel", "Оброблено іншим каналом"),
        ("not_relevant", "Клієнт не актуальний"),
        ("task_closed", "Задачу закрили вручну"),
    ]
    ASSIGN_REASONS = [
        ("owner", "Власник клієнта"),
        ("last_manager", "Останній менеджер клієнта"),
        ("on_duty", "Черговий на зміні"),
        ("transfer", "Передано колегою"),
    ]

    phone9 = models.CharField(max_length=12, db_index=True, help_text="Останні 9 цифр номера клієнта")
    number = models.CharField(max_length=32, blank=True)
    line = models.CharField(max_length=60, blank=True)
    line_key = models.CharField(max_length=64, blank=True, db_index=True)
    contact = models.ForeignKey("crm.Contact", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    deal = models.ForeignKey("crm.Deal", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    first_call = models.ForeignKey("telephony.Call", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    call_ids = models.JSONField(default=list, blank=True)
    calls_count = models.PositiveIntegerField(default=1)
    first_missed_at = models.DateTimeField(db_index=True)
    last_missed_at = models.DateTimeField()
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="missed_call_items")
    assign_reason = models.CharField(max_length=16, blank=True, choices=ASSIGN_REASONS)
    task = models.ForeignKey("crm.Task", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    due_at = models.DateTimeField(null=True, blank=True)
    first_attempt_at = models.DateTimeField(null=True, blank=True, help_text="Перший вихідний на номер після пропуску")
    reaction_work_min = models.IntegerField(null=True, blank=True, help_text="Реакція, робочих хвилин")
    status = models.CharField(max_length=8, choices=STATUS, default="open", db_index=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    close_reason = models.CharField(max_length=16, blank=True, choices=REASONS)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    closing_call = models.ForeignKey("telephony.Call", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    close_note = models.CharField(max_length=300, blank=True)
    escalated_at = models.DateTimeField(null=True, blank=True)
    history = models.JSONField(default=list, blank=True)
    backfilled = models.BooleanField(default=False, help_text="Створено з історії (без задачі і сповіщень)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-first_missed_at", "-id"]
        indexes = [models.Index(fields=["status", "assignee"], name="missed_status_assignee")]

    def __str__(self):
        return f"{self.number} · {self.line} · {self.status}"
