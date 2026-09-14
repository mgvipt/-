from django.db import models


class MetaWebhookLog(models.Model):
    """Короткий сирий лог подій вебхука Meta з даними реклами (referral / ads_context / ad_id)
    і нових чатів «текст кнопки з реклами, але без referral». Живе 30 днів (чиститься сам),
    потрібен лише щоб знайти, чому Meta губить рекламну мітку. Нічого не відправляє."""
    REASONS = [("ads_data", "Подія з даними реклами"),
               ("phrase_no_referral", "Текст кнопки з реклами, але Meta не дала referral")]
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    platform = models.CharField(max_length=16, blank=True, default="")
    reason = models.CharField(max_length=24, blank=True, default="", choices=REASONS)
    sender_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    ad_id = models.CharField(max_length=64, blank=True, default="")
    phrase = models.CharField(max_length=120, blank=True, default="")
    event = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-id"]
        verbose_name = "Сирий вебхук Meta (реклама, 30 днів)"

    def __str__(self):
        return "%s %s %s" % (self.created_at, self.reason, self.sender_id)
