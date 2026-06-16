from django.db import models


class IntegrationSettings(models.Model):
    """Единственная запись с ключами интеграций. Заполняется на экране «Интеграции».
    Ключи сюда переносятся из Битрикса (вставляются вручную)."""
    provider = models.CharField(max_length=32, unique=True)  # liqpay/checkbox/novaposhta
    config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.provider
