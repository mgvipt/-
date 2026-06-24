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
    extension = models.CharField(max_length=16, blank=True, help_text="внутрішній номер менеджера")
    disposition = models.CharField(max_length=24, blank=True, help_text="ANSWERED / NO ANSWER / BUSY / FAILED")
    started_at = models.DateTimeField(null=True, blank=True)
    external_id = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_direction_display()} {self.from_number}->{self.to_number}"
