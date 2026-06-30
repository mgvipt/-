from django.db import models
from django.conf import settings


class XPEvent(models.Model):
    """Один рядок нарахування XP (аудит + ідемпотентність по ref)."""
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="xp_events")
    kind = models.CharField(max_length=32)
    xp = models.IntegerField(default=0)
    ref_type = models.CharField(max_length=24, blank=True, default="")
    ref_id = models.CharField(max_length=40, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["kind", "ref_type", "ref_id"],
                                               condition=~models.Q(ref_id=""), name="uniq_xp_ref")]
        indexes = [models.Index(fields=["manager", "created_at"])]


class ManagerLevel(models.Model):
    manager = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="gam_level")
    total_xp = models.IntegerField(default=0)
    level = models.IntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)


class BadgeAward(models.Model):
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="gam_badges")
    badge_code = models.CharField(max_length=32)
    awarded_at = models.DateTimeField(auto_now_add=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = [("manager", "badge_code")]
