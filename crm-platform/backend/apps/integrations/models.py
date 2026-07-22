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


class IncomingDoc(models.Model):
    """Вхідний документ з пошти накладних (акт НП / накладна постачальника). Чернетка → підтвердження."""
    DOC_TYPES = [("np_act", "Акт Нової Пошти"), ("supplier", "Накладна постачальника"), ("unknown", "Інше")]
    STATUSES = [("draft", "Чернетка"), ("confirmed", "Проведено"), ("rejected", "Відхилено")]
    mailbox = models.CharField(max_length=120, blank=True, default="")
    sender = models.CharField(max_length=200, blank=True, default="")
    subject = models.CharField(max_length=300, blank=True, default="")
    message_uid = models.CharField(max_length=64, db_index=True)
    received_at = models.DateTimeField(null=True, blank=True)
    doc_type = models.CharField(max_length=12, choices=DOC_TYPES, default="unknown")
    status = models.CharField(max_length=10, choices=STATUSES, default="draft", db_index=True)
    parsed = models.JSONField(default=dict, blank=True)
    attachments_b64 = models.JSONField(default=list, blank=True)
    note = models.CharField(max_length=255, blank=True, default="")
    created_payable = models.ForeignKey("finance.PlannedPayment", null=True, blank=True,
                                        on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("mailbox", "message_uid")]
        ordering = ["-id"]

    def __str__(self):
        return "IncomingDoc#%s %s %s" % (self.pk, self.doc_type, self.status)


class SupplierProductMap(models.Model):
    """Правило: назва товару постачальника → наш склад-товар. Налаштував раз — далі авто-підстановка."""
    supplier_key = models.CharField(max_length=120, db_index=True, default="")  # e-mail відправника
    their_name = models.CharField(max_length=300)
    product = models.ForeignKey("warehouse.Product", on_delete=models.CASCADE, related_name="+")
    qty_factor = models.DecimalField("Коеф. одиниць складу за 1 одиницю постачальника", max_digits=12, decimal_places=4, default=1,
                                     help_text="Скільки НАШИХ одиниць (напр. кг) в 1 одиниці постачальника (напр. відро). 1 = однакові одиниці")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("supplier_key", "their_name")]

    def __str__(self):
        return "%s → #%s" % (self.their_name[:40], self.product_id)
