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

# 19.09.2026 (Олег: «зробив прихід Prana — товар не підставився, хоча приходи вже були»).
# Причина: для ручного завантаження ключем постачальника ставало ІМʼЯ ФАЙЛУ рахунку («ручне завантаження ·
# рахунок_№_555…pdf») — у кожного рахунку воно своє, тож правило більше ніколи не знаходилось.
# Тепер ключ — сам постачальник (contact:<id>), а пошук іде: цей постачальник → старий ключ (пошта) →
# та сама назва в будь-якого постачальника. Назви порівнюються без регістру, зайвих пробілів і лапок.
SKIP_CROSS_KEYS = ("grafio-catalog-source-id",)   # службові правила іншого імпорту — у загальний пошук не беремо


def supplier_key_for(contact):
    return "contact:%s" % contact.id if contact is not None else ""


def norm_name(s):
    s = (s or "").lower().replace("«", "\"").replace("»", "\"").replace("“", "\"").replace("”", "\"")
    s = _re_asm.sub(r"\s+", " ", s).strip(" .,;:\"'")
    return s


def find_rules(names, contact=None, legacy_key=""):
    """{назва постачальника: правило} для рядків накладної. Порядок: постачальник → старий ключ → будь-хто."""
    keys = [k for k in (supplier_key_for(contact), legacy_key) if k]
    wanted = {norm_name(n): n for n in names if (n or "").strip()}
    out = {}
    if not wanted:
        return out
    rules = list(SupplierProductMap.objects.select_related("product").order_by("-id"))
    for key in keys:
        for r in rules:
            if r.supplier_key == key:
                orig = wanted.get(norm_name(r.their_name))
                if orig and orig not in out and r.product.is_active:
                    out[orig] = r
    for r in rules:   # та сама назва в іншого постачальника / ручне завантаження — найсвіжіше правило
        if r.supplier_key in SKIP_CROSS_KEYS:
            continue
        orig = wanted.get(norm_name(r.their_name))
        if orig and orig not in out and r.product.is_active:
            out[orig] = r
    return out


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
