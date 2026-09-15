from django.db import models
from django.conf import settings


class XPEvent(models.Model):
    """Один рядок нарахування балів (аудит + ідемпотентність по ref).
    Розвиток v2 (16.09.2026): archived=True — бал за старими правилами (60 за виграну угоду + сума/1000, розбір чату
    «вручну»); більше ніде не рахується, рядок лишається для історії і відкату (gamify_rules_v2 --restore)."""
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="xp_events")
    kind = models.CharField(max_length=32)
    xp = models.IntegerField(default=0)
    ref_type = models.CharField(max_length=24, blank=True, default="")
    ref_id = models.CharField(max_length=40, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    meta = models.JSONField(default=dict, blank=True)
    archived = models.BooleanField(default=False, db_index=True,
                                   help_text="Старі правила (до 16.09.2026) — не рахується, лишається для історії")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["kind", "ref_type", "ref_id"],
                                               condition=~models.Q(ref_id=""), name="uniq_xp_ref")]
        indexes = [models.Index(fields=["manager", "created_at"], name="gam_xp_mgr_idx")]


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


class GamSettings(models.Model):
    """Налаштування «Розвитку» — один рядок (pk=1). Усе, що коштує грошей або платить призи, ВИМКНЕНО за замовчуванням.
    Читання без запису: GamSettings.get() повертає незбережений рядок зі значеннями за замовчуванням, якщо його ще немає."""
    chat_sampling = models.BooleanField(default=False,
                                        help_text="Раз на тиждень ІІ розбирає випадкову вибірку чатів кожного менеджера (коштує грошей)")
    chat_sample_per_week = models.PositiveSmallIntegerField(default=3, help_text="Скільки чатів одного менеджера за тиждень")
    contests = models.JSONField(default=dict, blank=True,
                                help_text="Змагання тижня: {код: {offer_id, enabled}} — заводить команда rozvytok_contests_seed")
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    @classmethod
    def get(cls):
        return cls.objects.filter(pk=1).first() or cls(pk=1)


class PracticeMark(models.Model):
    """Відмітка «маленької справи на тиждень» (Розвиток → Що робити далі). Тиждень = дата понеділка."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    week = models.DateField()
    key = models.CharField(max_length=60)
    text = models.CharField(max_length=300, blank=True, default="")
    done = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "week", "key")]
