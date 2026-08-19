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


import re as _re_asm


def assembly_signature(names):
    """Підпис набору компонентів: нормалізовані назви, відсортовані.
    Однаковий набір компонентів (незалежно від порядку/регістру) → однаковий підпис."""
    def _norm(x):
        return _re_asm.sub(r"[^0-9a-zа-яіїєґ]+", "", (x or "").lower())[:14]
    parts = sorted(p for p in (_norm(x) for x in (names or [])) if p)
    return "|".join(parts)[:240]


class AssemblyRecipe(models.Model):
    """Рецепт зборки: набір компонентів однієї накладної → одна позиція номенклатури.
    Напр.: силікон + контейнер + 2× крихта = «Крихта декоративна» (N відер).
    Запамʼятовується при проведенні, наступного разу CRM сама пропонує зібрати."""
    supplier_key = models.CharField(max_length=120, db_index=True, default="", blank=True)
    signature = models.CharField(max_length=240, db_index=True)
    target_product = models.ForeignKey("warehouse.Product", on_delete=models.CASCADE,
                                       related_name="assembly_recipes")
    default_qty = models.DecimalField(max_digits=12, decimal_places=3, default=1)
    components = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["supplier_key", "signature"])]

    def __str__(self):
        return "%s → #%s x%s" % (self.signature[:40], self.target_product_id, self.default_qty)
