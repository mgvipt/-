from django.conf import settings
from django.db import models


class Call(models.Model):
    DIRECTION = [("in", "Входящий"), ("out", "Исходящий"), ("missed", "Пропущенный")]
    direction = models.CharField(max_length=8, choices=DIRECTION)
    from_number = models.CharField(max_length=32, blank=True)
    to_number = models.CharField(max_length=32, blank=True)
    contact = models.ForeignKey("crm.Contact", null=True, blank=True, on_delete=models.SET_NULL, related_name="calls")
    deal = models.ForeignKey("crm.Deal", null=True, blank=True, on_delete=models.SET_NULL, related_name="calls")
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="calls")
    duration = models.PositiveIntegerField(default=0, help_text="секунды")
    recording_url = models.URLField(blank=True)
    recording_file = models.CharField(max_length=255, blank=True, help_text="імʼя файлу запису на FreePBX")
    transcript = models.TextField(blank=True, default="")
    analyzed = models.BooleanField(default=False)
    line = models.CharField(max_length=60, blank=True, help_text="SIM-лінія, напр. 803 · Салон")
    extension = models.CharField(max_length=16, blank=True, help_text="внутрішній номер менеджера")
    disposition = models.CharField(max_length=24, blank=True, help_text="ANSWERED / NO ANSWER / BUSY / FAILED")
    started_at = models.DateTimeField(null=True, blank=True)
    external_id = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_direction_display()} {self.from_number}->{self.to_number}"


class CallRequest(models.Model):
    """Заявка на дзвінок по кліку. Конектор FreePBX опитує і робить Originate."""
    number = models.CharField(max_length=32)
    extension = models.CharField(max_length=16, blank=True)
    status = models.CharField(max_length=10, default="pending")  # pending/done/failed
    error = models.CharField(max_length=200, blank=True)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class RingingCall(models.Model):
    """Дзвінок що ДЗВОНИТЬ ЗАРАЗ — для живої спливашки у CRM (real-time через AMI)."""
    uniqueid = models.CharField(max_length=64, unique=True)
    number = models.CharField(max_length=32)
    line = models.CharField(max_length=60, blank=True)
    contact = models.ForeignKey("crm.Contact", null=True, blank=True, on_delete=models.SET_NULL)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)



class PhoneLine(models.Model):
    """Лінія дзвінків (SIM): баланс для контролю оплати. Баланс вводиться вручну (перевірка *111# на телефоні)."""
    internal = models.CharField(max_length=10, unique=True, help_text="Внутрішній номер АТС: 789/788")
    name = models.CharField(max_length=60)
    number = models.CharField(max_length=30)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    balance_at = models.DateTimeField(null=True, blank=True)
    low_threshold = models.DecimalField(max_digits=10, decimal_places=2, default=50)
    note = models.CharField(max_length=200, blank=True)
    busy = models.BooleanField(default=False)
    busy_at = models.DateTimeField(null=True, blank=True)


class CallQueueMember(models.Model):
    """Учасник черги вхідних дзвінків. Порядок = position. Дзвонять лише якщо enabled
    і (за налаштуванням on_shift_only) співробітник почав робочий день."""
    user = models.OneToOneField("accounts.User", on_delete=models.CASCADE, related_name="queue_member")
    position = models.PositiveIntegerField(default=0)
    enabled = models.BooleanField(default=True)
    ring_seconds = models.PositiveIntegerField(default=20)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "id"]


class CallQueueConfig(models.Model):
    """Singleton — налаштування черги вхідних."""
    on_shift_only = models.BooleanField(default=True, help_text="Дзвонити лише тим, хто почав робочий день")
    strategy = models.CharField(max_length=12, default="sequential")  # sequential | ringall
    active = models.BooleanField(default=False, help_text="Чи керує черга маршрутизацією вхідних")

    @classmethod
    def get(cls):
        obj = cls.objects.first()
        if not obj:
            obj = cls.objects.create()
        return obj
