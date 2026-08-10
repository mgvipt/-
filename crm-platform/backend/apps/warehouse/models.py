from django.db import models
from django.db.models import Sum
from django.conf import settings
import uuid


class Warehouse(models.Model):
    name = models.CharField(max_length=120)
    is_default = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class ProductComponent(models.Model):
    """Склад набору (комплекту): набір = звичайний Product, склад = рядки компонентів.
    Глибина рівно 1: компонент не може сам бути набором (валідація в сериалізаторі).
    Продаж набору списує КОМПОНЕНТИ; cost набору = Σ(component.cost × quantity) — авто."""
    bundle = models.ForeignKey("Product", on_delete=models.CASCADE, related_name="components")
    component = models.ForeignKey("Product", on_delete=models.PROTECT, related_name="used_in_bundles")
    quantity = models.DecimalField("Кількість", max_digits=10, decimal_places=3, default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["bundle", "component"], name="uniq_bundle_component"),
            models.CheckConstraint(check=~models.Q(bundle=models.F("component")), name="bundle_not_self"),
        ]


class ProductImage(models.Model):
    """Картинка товара (галерея). Файлы в warehouse_photos/products/ (постоянный том)."""
    product = models.ForeignKey("Product", on_delete=models.CASCADE, related_name="images")
    file_path = models.CharField(max_length=255)
    b24_file_id = models.IntegerField(null=True, blank=True, db_index=True)
    order = models.IntegerField(default=0)
    alt_text = models.CharField(max_length=255, blank=True, default="")
    is_primary = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False)
    variant_key = models.CharField(max_length=40, blank=True, default="")

    class Meta:
        ordering = ["order", "id"]


class ProductCategory(models.Model):
    """Категория каталога (дерево папок). Перенос из Bitrix iblock 24."""
    name = models.CharField(max_length=255)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    bitrix_id = models.IntegerField(null=True, blank=True, unique=True, db_index=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Product categories"

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=255)
    sku = models.CharField("Артикул", max_length=64, blank=True, db_index=True)
    unit = models.CharField("Ед. изм.", max_length=16, default="шт")
    price = models.DecimalField("Цена продажи", max_digits=12, decimal_places=2, default=0)
    cost = models.DecimalField("Себестоимость", max_digits=12, decimal_places=2, default=0)
    pack_factor = models.DecimalField("Коеф. закупівлі→одиниця", max_digits=12, decimal_places=4, default=1,
                                      help_text="Скільки одиниць номенклатури (кг/л/шт) в 1 закупівельній одиниці (відро/мішок). 1 = однакові")
    cost_pct = models.DecimalField("Себестоимость, % от цены", max_digits=5, decimal_places=2, default=0,
        help_text="Для услуг/работ, где мастеру платим долю: себестоимость = цена × этот %. 0 = использовать фиксированную Себестоимость. Пример: монтаж, мастер получает 80% → впиши 80.")
    min_price = models.DecimalField("Минимальная цена за позицию", max_digits=12, decimal_places=2, default=0,
        help_text="Минимум за строку в сделке: если цена×кол-во меньше — берётся этот минимум. 0 = без минимума. Пример: сверление 17/см, но минимум 1500.")
    weight_kg = models.DecimalField("Вага нетто, кг", max_digits=8, decimal_places=3, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    category = models.ForeignKey("ProductCategory", null=True, blank=True, on_delete=models.SET_NULL, related_name="products")
    currency = models.CharField(max_length=8, default="UAH")
    bitrix_id = models.IntegerField("ID в Bitrix", null=True, blank=True, unique=True, db_index=True)
    description = models.TextField("Опис", blank=True, default="")
    track_stock = models.BooleanField("Кількісний облік", default=True,
        help_text="Вимкни для послуг/робіт/номенклатури без залишку — не списується зі складу, залишок не рахується")
    is_drop = models.BooleanField("Дроп (докупаємо під замовлення)", default=False,
        help_text="Товар, який ми продаємо ПІД замовлення і закуповуємо ПІСЛЯ продажу. Коли робиш прихід — закупівельна ціна автоматично оновлюється в УСІХ угодах з цим товаром (навіть у закритих) і в русі товару. Для звичайних складських товарів вимкнено — там історія собівартості на момент продажу не змінюється.")
    SHOP_STATUSES = [
        ("draft", "Чернетка"), ("ready", "Готовий"),
        ("published", "Опублікований"), ("hidden", "Прихований"),
        ("error", "Помилка"),
    ]
    shop_managed = models.BooleanField(default=False, db_index=True)
    shop_enabled = models.BooleanField("Показувати на сайті", default=False)
    shop_category_path = models.JSONField("Категорія на сайті", default=list, blank=True)
    shop_status = models.CharField(max_length=16, choices=SHOP_STATUSES, default="draft", db_index=True)
    shop_group_key = models.CharField(max_length=96, blank=True, default="", db_index=True)
    shop_parent_name = models.CharField("Назва покриття на сайті", max_length=255, blank=True, default="")
    shop_slug = models.SlugField(max_length=160, blank=True, default="")
    shop_short_description = models.TextField(blank=True, default="")
    shop_full_description = models.TextField(blank=True, default="")
    shop_benefits = models.JSONField(default=list, blank=True)
    shop_effect = models.CharField(max_length=120, blank=True, default="")
    shop_rooms = models.JSONField(default=list, blank=True)
    shop_beginner = models.BooleanField(default=False)
    shop_video_url = models.URLField(max_length=500, blank=True, default="")
    shop_instruction_url = models.URLField(max_length=500, blank=True, default="")
    shop_sort = models.PositiveIntegerField(default=0)
    shop_badges = models.JSONField(default=list, blank=True)
    shop_variant_type = models.CharField(max_length=32, blank=True, default="sample")
    shop_has_board = models.BooleanField(null=True, blank=True)
    shop_is_tinted = models.BooleanField(null=True, blank=True)
    shop_variant_order = models.PositiveSmallIntegerField(default=0)
    shop_variant_name = models.CharField(max_length=255, blank=True, default="")
    shop_contents = models.TextField(blank=True, default="")
    shop_specs = models.JSONField(default=dict, blank=True)
    seo_title = models.CharField(max_length=255, blank=True, default="")
    seo_description = models.TextField(blank=True, default="")
    seo_h1 = models.CharField(max_length=255, blank=True, default="")
    seo_categories = models.JSONField(default=list, blank=True)
    seo_faqs = models.JSONField(default=list, blank=True)
    seo_index = models.BooleanField(default=False)
    shop_last_sync_at = models.DateTimeField(null=True, blank=True)
    shop_sync_error = models.TextField(blank=True, default="")
    shop_remote_url = models.URLField(max_length=500, blank=True, default="")
    b24_created_by = models.CharField("Хто створив (Б24)", max_length=120, blank=True, default="")
    b24_modified_by = models.CharField("Хто змінив (Б24)", max_length=120, blank=True, default="")
    b24_created_at = models.DateTimeField(null=True, blank=True)
    b24_modified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def stock(self, warehouse=None):
        """Текущий остаток = сумма движений (приход +, расход -)."""
        qs = self.movements.filter(document__posted=True)  # чернетки не рахуються
        if warehouse:
            qs = qs.filter(document__warehouse=warehouse)
        return qs.aggregate(s=Sum("quantity"))["s"] or 0


class ShopSyncEvent(models.Model):
    STATUSES = [
        ("pending", "Очікує"), ("processing", "Передається"),
        ("processed", "Готово"), ("failed", "Помилка"),
        ("superseded", "Замінено новішою подією"),
    ]
    event_uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="shop_sync_events")
    action = models.CharField(max_length=16, default="upsert")
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=STATUSES, default="pending", db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]


class ShopCatalogImportBatch(models.Model):
    STATUSES = [("review", "На перевірці"), ("partially_applied", "Частково збережено"), ("applied", "Збережено")]
    source_name = models.CharField(max_length=255)
    source_hash = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=24, choices=STATUSES, default="review", db_index=True)
    summary = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class ShopCatalogImportRow(models.Model):
    batch = models.ForeignKey(ShopCatalogImportBatch, on_delete=models.CASCADE, related_name="rows")
    sheet_name = models.CharField(max_length=80)
    source_row = models.PositiveIntegerField()
    external_id = models.CharField(max_length=80, db_index=True)
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL, related_name="shop_import_rows")
    source_data = models.JSONField(default=dict)
    proposed_data = models.JSONField(default=dict)
    warnings = models.JSONField(default=list, blank=True)
    errors = models.JSONField(default=list, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sheet_name", "source_row", "id"]
        constraints = [
            models.UniqueConstraint(fields=["batch", "sheet_name", "source_row"], name="uniq_shop_import_source_row"),
        ]


class ShopSiteSettings(models.Model):
    """Черновик и опубликованная версия текстов/фото витрины."""
    key = models.CharField(max_length=80, unique=True, default="home")
    draft = models.JSONField(default=dict, blank=True)
    published = models.JSONField(default=dict, blank=True)
    last_published_at = models.DateTimeField(null=True, blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ShopSiteMedia(models.Model):
    file = models.FileField(upload_to="shop_site_content/")
    alt = models.CharField(max_length=255, blank=True, default="")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)


class StockDocument(models.Model):
    """Складской документ: приход / расход / инвентаризация."""
    KINDS = [("in", "Приход"), ("out", "Расход"), ("inv", "Инвентаризация"), ("writeoff", "Списание")]
    kind = models.CharField(max_length=8, choices=KINDS)
    number = models.CharField(max_length=40, blank=True)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="documents")
    comment = models.CharField(max_length=255, blank=True)
    deal = models.ForeignKey("crm.Deal", null=True, blank=True, on_delete=models.SET_NULL, related_name="stock_documents")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    posted = models.BooleanField("Проведено", default=True)  # чернетка (False) не впливає на залишок/COGS
    close_stage = models.CharField("Стадія закриття", max_length=120, blank=True, default="")  # на якій стадії створено реалізацію
    supplier = models.ForeignKey("crm.Contact", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="supplied_documents", help_text="Постачальник (контрагент)")
    supplier_invoice = models.CharField("№ накладної постачальника", max_length=80, blank=True, default="")
    source_invoice_doc = models.IntegerField("ID вхідної накладної-джерела", null=True, blank=True,
                                             help_text="IncomingDoc, з якого створено прихід — щоб відкрити оригінал накладної")
    doc_date = models.DateField("Дата документа", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} {self.number or self.pk}"

    @property
    def total(self):
        return sum(i.quantity * i.price for i in self.items.all())


class StockMovement(models.Model):
    """Строка документа = движение товара. Приход +qty, расход -qty."""
    document = models.ForeignKey(StockDocument, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="movements")
    quantity = models.DecimalField(max_digits=12, decimal_places=2)  # знак уже учтён
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.product} × {self.quantity}"


# ═══════════════════════════════ СКЛАД — робота кладовщиків (Фаза 1) ═══════════════════════════════
class TareType(models.Model):
    """Тип тари — визначає рівень упаковки (до 5/10/20 кг) за вмістимістю."""
    name = models.CharField("Назва", max_length=80)
    tare_weight_kg = models.DecimalField("Вага порожньої тари, кг", max_digits=6, decimal_places=3, default=0)
    max_fill_kg = models.DecimalField("Вмістимість, кг", max_digits=6, decimal_places=3, default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["max_fill_kg"]

    def __str__(self):
        return self.name


class WarehouseJob(models.Model):
    """Картка виконання задачі складу (1↔1 з crm.Task). Джерело правди для ЗП."""
    STATUS = [("queued", "У черзі"), ("taken", "Взято"), ("tinting", "Тонується"),
              ("packing", "Пакування"), ("awaiting_photos", "Потрібні фото"),
              ("shipped", "Відвантажено"), ("partial", "Часткове"), ("cancelled", "Скасовано")]
    task = models.OneToOneField("crm.Task", null=True, blank=True, on_delete=models.SET_NULL, related_name="warehouse_job")
    deal = models.ForeignKey("crm.Deal", on_delete=models.CASCADE, related_name="warehouse_jobs")
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="warehouse_jobs")
    status = models.CharField(max_length=16, choices=STATUS, default="queued", db_index=True)
    is_shipment = models.BooleanField(default=True)
    tinted_kits = models.JSONField(default=list, blank=True)
    tintings_count = models.PositiveIntegerField(default=0)
    tintings_base = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    shipped_weight_kg = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    pack_le5_count = models.PositiveIntegerField(default=0)
    pack_le10_count = models.PositiveIntegerField(default=0)
    pack_le20_count = models.PositiveIntegerField(default=0)
    packed = models.BooleanField(default=True, help_text="Чи самі пакували (ні = >4 місць, контейнер НП)")
    np_ttn = models.CharField(max_length=40, blank=True, default="")
    done_snapshot = models.JSONField(default=dict, blank=True)
    taken_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return "Job#%s deal=%s %s" % (self.pk, self.deal_id, self.status)


class WarehousePayrollEntry(models.Model):
    """Аудит-рядок ЗП: одна дія = один рядок зі снімком ставки. ЗП = SUM(amount)."""
    OP = [("shipment_weight", "Вага відвантаження"), ("packing", "Упаковка"), ("tinting", "Тонування"),
          ("workday", "Робочий день"), ("error", "Помилка"), ("wrong_material", "Невірний матеріал"),
          ("bonus_initiative", "Бонус-ідея"), ("bonus_cleanliness", "Бонус-чистота")]
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wh_payroll")
    work_date = models.DateField(db_index=True)
    job = models.ForeignKey(WarehouseJob, null=True, blank=True, on_delete=models.SET_NULL, related_name="payroll")
    deal = models.ForeignKey("crm.Deal", null=True, blank=True, on_delete=models.SET_NULL)
    op_type = models.CharField(max_length=20, choices=OP)
    quantity_kg = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    pack_tier = models.CharField(max_length=4, blank=True, default="")
    base_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    rate_applied = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=10, default="confirmed")
    source = models.CharField(max_length=10, default="system")
    note = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class WarehousePhoto(models.Model):
    """Фото регламенту (відерця/посилка/чистота/доказ). FileField — Pillow не потрібен."""
    KIND = [("buckets", "Відерця"), ("parcel", "Посилка"), ("cleanliness", "Чистота"), ("error_proof", "Доказ помилки")]
    job = models.ForeignKey(WarehouseJob, null=True, blank=True, on_delete=models.CASCADE, related_name="photos")
    deal = models.ForeignKey("crm.Deal", null=True, blank=True, on_delete=models.SET_NULL)
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    kind = models.CharField(max_length=16, choices=KIND)
    image = models.FileField(upload_to="warehouse_photos/")
    uploaded_at = models.DateTimeField(auto_now_add=True)


class WarehouseError(models.Model):
    """Помилка/удержання (Ф2). Удержання в ЗП лише після confirmed власником/РОПом."""
    SOURCE = [("manual_staff", "Сам визнав"), ("manager", "Менеджер/РОП"), ("ai_suggested", "AI")]
    KIND = [("wrong_material", "Невірний матеріал"), ("wrong_tint", "Невірна тонировка"),
            ("wrong_qty", "Невірна кількість"), ("damaged", "Пошкоджено"),
            ("lost_np", "Втрачено в НП"), ("other", "Інше")]
    STATUS = [("suggested", "На розгляді"), ("confirmed", "Підтверджено"), ("rejected", "Відхилено")]
    job = models.ForeignKey(WarehouseJob, null=True, blank=True, on_delete=models.SET_NULL, related_name="errors")
    deal = models.ForeignKey("crm.Deal", null=True, blank=True, on_delete=models.SET_NULL)
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="wh_errors_reported")
    blamed_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="wh_errors_blamed")
    source = models.CharField(max_length=16, choices=SOURCE, default="manual_staff")
    kind = models.CharField(max_length=16, choices=KIND, default="other")
    description = models.TextField(blank=True, default="")
    deduction_uah = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=STATUS, default="suggested")
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class InitiativeIdea(models.Model):
    """Ідея співробітника (Ф3). Бонус за прийняту/впроваджену."""
    STATUS = [("new", "Нова"), ("accepted", "Прийнято"), ("implemented", "Впроваджено"), ("declined", "Відхилено")]
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wh_ideas")
    text = models.TextField()
    status = models.CharField(max_length=12, choices=STATUS, default="new")
    award_uah = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    awarded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class InventoryFactDraft(models.Model):
    """Спільний чернетковий «Факт» інвентаризації (щоб Олег і кладовщик бачили ОДНЕ, а не
    локально в браузері). Один запис на товар — останнє введене значення."""
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="inv_fact_draft")
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)
