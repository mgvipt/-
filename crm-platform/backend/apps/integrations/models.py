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


class ShopOrderImport(models.Model):
    """Идемпотентный след заказа, принятого из собственного интернет-магазина."""

    event_uuid = models.UUIDField(unique=True)
    order_number = models.CharField(max_length=64, unique=True)
    deal = models.OneToOneField(
        "crm.Deal", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="shop_order_import",
    )
    payload = models.JSONField(default=dict)
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-imported_at"]

    def __str__(self):
        return f"{self.order_number} -> deal #{self.deal_id or '-'}"
