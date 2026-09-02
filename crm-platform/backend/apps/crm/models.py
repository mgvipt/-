from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.db import models


class Company(models.Model):
    name = models.CharField(max_length=255)
    edrpou = models.CharField("ЄДРПОУ/ИНН", max_length=32, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


CONTACT_KINDS = [
    ("client", "Клієнт"),
    ("supplier", "Постачальник"),
    ("master", "Майстер"),
    ("staff", "Співробітник"),
    ("partner", "Партнер / Дизайнер"),
]


class Contact(models.Model):
    """Карточка клиента. Каналы (Instagram/Viber/...) накапливаются по мере общения."""
    first_name = models.CharField(max_length=120, blank=True)
    last_name = models.CharField(max_length=120, blank=True)
    middle_name = models.CharField(max_length=120, blank=True, default="", help_text="По батькові")
    nickname = models.CharField(max_length=150, blank=True, default="", help_text="Нік / імʼя з месенджера (оригінал)")
    phone = models.CharField(max_length=32, blank=True, db_index=True)
    email = models.EmailField(blank=True)
    avatar_url = models.URLField("Фото профілю (з месенджера)", max_length=500, blank=True, default="",
                                 help_text="Тягнеться з Instagram/Facebook. Посилання тимчасове — оновлюється при новому повідомленні.")
    portal_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="portal_contact",
        help_text="Личный клиентский аккаунт приложения; не назначается по совпадению телефона",
    )
    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.SET_NULL, related_name="contacts")
    channels = models.JSONField(default=list, blank=True, help_text="['instagram','viber',...]")
    loyalty_tag = models.CharField(max_length=24, blank=True, default="", help_text="Новый/Активный/VIP/Спящий")
    birthday = models.DateField(null=True, blank=True)
    source = models.CharField(max_length=24, blank=True, default="", help_text="Звідки клієнт (instagram/site/...)")
    address = models.CharField(max_length=255, blank=True, default="", help_text="Адреса доставки / місто")
    comment = models.TextField(blank=True, default="", help_text="Нотатки менеджера про клієнта")
    social_link = models.CharField(max_length=300, blank=True, default="", help_text="Посилання на акаунт клієнта в месенджері (IG/TG/FB)")
    messengers = models.JSONField(default=list, blank=True, help_text="Кілька месенджерів/контактів клієнта (IG/TG/Viber/номер) — список посилань")
    edrpou = models.CharField("ЄДРПОУ / ІПН", max_length=32, blank=True, default="", db_index=True)
    iban = models.CharField("IBAN / рахунок", max_length=64, blank=True, default="")
    kinds = models.JSONField("Типи контрагента", default=list, blank=True,
                             help_text="client/supplier/master/staff/partner — контрагент може бути кількох типів одразу")
    gender = models.CharField("Стать", max_length=1, blank=True, default="",
                              choices=[("m", "Чоловіча"), ("f", "Жіноча")],
                              help_text="Визначається автоматично за по батькові/іменем; можна виправити руками")
    monitor_docs = models.BooleanField("Моніторити накладні", default=False,
                                       help_text="Забирати накладні/рахунки цього постачальника з пошти та месенджерів у «Вх. накладні»")
    doc_email = models.CharField("Пошта для накладних", max_length=190, blank=True, default="",
                                 help_text="Якщо накладні приходять з іншої адреси, ніж основний e-mail")
    default_purchase_category = models.PositiveIntegerField(
        "Категорія закупівлі за замовчуванням", null=True, blank=True,
        help_text="finance.Category — підставляється при проведенні накладної цього постачальника (фонд/напрямок тягнуться з категорії)")
    payment_purpose = models.CharField(
        "Призначення платежу (шаблон)", max_length=200, blank=True, default="",
        help_text="Своє призначення для оплати цьому постачальнику через ФОП. Плейсхолдери {номер} і {дата} підставляться з рахунку. Порожньо = «Оплата рахунку №… від …»")
    emails_extra = models.JSONField("Додаткові email", default=list, blank=True,
                                    help_text="[{label,value}] — кілька пошт з власними назвами полів")
    phones_extra = models.JSONField("Додаткові телефони", default=list, blank=True,
                                    help_text="[{label,value}] — кілька телефонів з назвами")
    links_extra = models.JSONField("Додаткові посилання на акаунти", default=list, blank=True,
                                   help_text="[{label,value}] — кілька посилань")
    accounts = models.JSONField("Рахунки (постачальник)", default=list, blank=True,
                                help_text="[{label,iban,active}] — активний рахунок = на який оплачуємо через ФОП")
    monitor_emails = models.JSONField("Пошти для моніторингу", default=list, blank=True,
                                      help_text="[email] — додаткові адреси, з яких приходять накладні цього постачальника")
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="contacts_owned", help_text="Ответственный менеджер клиента")
    shared_with = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="contacts_shared",
        help_text="Доступ к клиенту выдан этим менеджерам (шаринг). Свои клиенты видны и без этого.")

    # ── Ручна поправка авансу (обʼєктні роботи/матеріали, не оформлені сделками) ──
    # Формула авансу «заплатив − купив по сделках» не бачить робіт майстрів і закупок,
    # оформлених поза сделками, тому дає завищений залишок. Поправка ставить реальну суму.
    # Рухів грошей НЕ створює (26.08).
    advance_adjust = models.DecimalField("Коригування авансу", max_digits=14, decimal_places=2, default=0)
    advance_adjust_note = models.CharField("Причина коригування", max_length=200, blank=True, default="")
    # ── Ручна поправка ВИТРАТ по клієнту (обʼєктні закупки/роботи, проведені поза журналом) ──
    expense_adjust = models.DecimalField("Коригування витрат", max_digits=14, decimal_places=2, default=0)
    expense_adjust_note = models.CharField("Причина коригування витрат", max_length=200, blank=True, default="")
    last_touch_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [GinIndex(fields=["kinds"], name="contact_kinds_gin")]

    def __str__(self):
        _fn = (self.first_name or "").strip()
        _ln = (self.last_name or "").strip()
        _mn = (self.middle_name or "").strip()
        # постачальники (ФОП/юр.особи) — формальний порядок: Прізвище Ім'я По батькові
        if "supplier" in (self.kinds or []):
            _full = " ".join(x for x in (_ln, _fn, _mn) if x)
            if _full:
                return _full
        return f"{_fn} {_ln}".strip() or self.phone or f"Контакт #{self.pk}"


class Funnel(models.Model):
    """Воронка продаж (напр. «21 Основний продукт», «22 Тестовий набір»)."""
    name = models.CharField(max_length=160)
    is_lead_funnel = models.BooleanField(default=False, help_text="True = воронка лидов")
    is_archive = models.BooleanField(default=False, help_text="Архівна воронка — сделки для історії, НЕ вантажаться на дошку авто (тільки пошук)")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.name


class Stage(models.Model):
    funnel = models.ForeignKey(Funnel, on_delete=models.CASCADE, related_name="stages")
    name = models.CharField(max_length=160)
    color = models.CharField(max_length=9, default="#3b82f6")
    order = models.PositiveIntegerField(default=0)
    is_won = models.BooleanField(default=False)
    is_lost = models.BooleanField(default=False)
    auto_only = models.BooleanField(default=False, help_text="Статус ставиться ТІЛЬКИ автоматизацією — ручне переміщення заборонено")

    class Meta:
        ordering = ["funnel", "order"]

    def __str__(self):
        return f"{self.funnel.name} · {self.name}"


class TimestampedOwned(models.Model):
    """Базовая модель с владельцем и временем — для лидов и сделок."""
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="%(class)ss",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Lead(TimestampedOwned):
    SOURCES = [
        ("telegram", "Telegram"), ("viber", "Viber"), ("instagram", "Instagram"),
        ("facebook", "Facebook"), ("whatsapp", "WhatsApp"), ("call", "Звонок"),
        ("google_business", "Google Бизнес"), ("other", "Другое"),
        ("site", "Сайт wallcovdec"), ("wholesale", "Опт / дилери"),
        ("designers", "Дизайнери / прораби"), ("tiktok", "TikTok"),
    ]
    title = models.CharField(max_length=255)
    contact = models.ForeignKey(Contact, null=True, blank=True, on_delete=models.SET_NULL, related_name="leads")
    funnel = models.ForeignKey(Funnel, on_delete=models.PROTECT, related_name="leads")
    stage = models.ForeignKey(Stage, on_delete=models.PROTECT, related_name="leads")
    source = models.CharField(max_length=24, choices=SOURCES, default="other")
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_seen = models.BooleanField(default=False, help_text="Снимает бейдж 'НЕПЕРЕГЛЯНУТІ'")
    qualification = models.JSONField(default=dict, blank=True, help_text="Анкета виявлення потреби (тип приміщення, площа, матеріал, бюджет тощо)")
    card_fields = models.JSONField(default=list, blank=True, help_text="Кастомні поля/блоки картки (як у Бітриксі): [{label, value}]")
    meta_attribution = models.JSONField(
        default=dict, blank=True,
        help_text="Перевірена рекламна атрибуція Meta (тип джерела та стабільні ID реклами/форми)",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class Deal(TimestampedOwned):
    title = models.CharField(max_length=255)
    contact = models.ForeignKey(Contact, null=True, blank=True, on_delete=models.SET_NULL, related_name="deals")
    funnel = models.ForeignKey(Funnel, on_delete=models.PROTECT, related_name="deals")
    stage = models.ForeignKey(Stage, on_delete=models.PROTECT, related_name="deals")
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    source = models.CharField(max_length=24, choices=Lead.SOURCES, default="other")
    discount_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    pay_type = models.CharField(max_length=40, blank=True, default="", help_text="Полная/Предоплата 50%/Послеоплата НП")
    parent_deal = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="children", help_text="Батьківська сделка (дозамовлення — їде однією посилкою)")
    ttn = models.CharField("ТТН Нова Пошта", max_length=40, blank=True, default="")
    checkbox_status = models.CharField(max_length=16, blank=True, default="none", help_text="none/аванс/финальный")
    checkbox_url = models.TextField(blank=True, default="", help_text="Фіскальна ссылка на чек")
    checkbox_receipt_id = models.CharField(max_length=64, blank=True, default="")
    checkbox_relation_id = models.CharField(max_length=64, blank=True, default="", help_text="pre_payment_relation_id для звʼязку аванс→фінал")
    np_data = models.JSONField(default=dict, blank=True, help_text="Повна форма Доставка НП")
    np_delivery_date = models.DateField(null=True, blank=True, help_text="Бажана дата доставки")
    ref_photos = models.JSONField(default=list, blank=True, help_text="Скріни/фото від клієнта (data-URL) — показуються складу")
    kp_history = models.JSONField(default=list, blank=True, help_text="Історія КП/накладних: [{ts,total,subtotal,discount,note,by,items:[{name,qty,price,discount_pct,total}]}]")
    closed_at = models.DateTimeField(null=True, blank=True)
    stage_changed_at = models.DateTimeField(null=True, blank=True, help_text="Коли востаннє змінилась стадія (для днів на стадії)")
    is_seen = models.BooleanField(default=True, help_text="Бейдж непереглянуто: False=клієнт написав і не відповіли, True=відповіли")
    b24_id = models.CharField(max_length=20, blank=True, default="", db_index=True, help_text="ID угоди в Бітриксі (для токена Cashflow WC-{b24_id})")
    qualification = models.JSONField(default=dict, blank=True, help_text="Анкета виявлення потреби (переноситься з ліда)")
    card_fields = models.JSONField(default=list, blank=True, help_text="Кастомні поля картки [{label, value}]")
    meta_attribution = models.JSONField(
        default=dict, blank=True,
        help_text="Перевірена рекламна атрибуція Meta, перенесена з ліда",
    )
    area_m2 = models.DecimalField("Площа, м²", max_digits=10, decimal_places=2, null=True, blank=True,
                                  help_text="Площа стін для авто-розрахунку кількості матеріалу")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class DealRoom(models.Model):
    """Приміщення (кімната) у сделці: назва + площа. Один матеріал може рахуватись
    на РІЗНУ квадратуру по кімнатах (Олег 31.08). Позиція без кімнати = «Загальна»."""
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name="rooms")
    name = models.CharField("Приміщення", max_length=80)
    area_m2 = models.DecimalField("Площа, м²", max_digits=10, decimal_places=2, default=0)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return "%s (%s м²)" % (self.name, self.area_m2)


class DealItem(models.Model):
    """Товар в сделке. Сумма сделки = сумма строк."""
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("warehouse.Product", null=True, blank=True, on_delete=models.PROTECT, related_name="deal_items")
    custom_name = models.CharField(max_length=200, blank=True, default="",
                                   help_text="Своя позиція НЕ з номенклатури: без складського обліку і списання")
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    room = models.ForeignKey("DealRoom", null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="items", help_text="Приміщення (порожньо = загальна позиція)")
    reserved = models.BooleanField(default=False, help_text="Товар зарезервовано під цю сделку")
    discount_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Знижка на позицію, %")
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                           help_text="Знижка на позицію фіксованою сумою ₴ (якщо >0 — має пріоритет над %)")
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                               help_text="Знімок собівартості на момент продажу (для чесної маржі в історії)")

    @property
    def base_sum(self):
        """Сума позиції до знижки, з урахуванням МІНІМАЛКИ товару (min_price за рядок)."""
        gross = self.quantity * self.price
        mp = (getattr(self.product, "min_price", 0) or 0) if self.product_id else 0
        return mp if (mp and gross < mp) else gross

    @property
    def discount_sum(self):
        base = self.base_sum
        if self.discount_amount and self.discount_amount > 0:
            return min(self.discount_amount, base)   # знижка сумою ₴ (не більша за рядок)
        return base * (self.discount_pct or 0) / 100  # знижка відсотком

    @property
    def total(self):
        t = self.base_sum - self.discount_sum
        return t if t > 0 else self.base_sum - self.base_sum

    def __str__(self):
        return f"{self.product} × {self.quantity}"


class Payment(models.Model):
    """Перенос рабочих оплат: LiqPay / Checkbox / наличка. Питает финмодуль."""
    PROVIDERS = [("liqpay", "LiqPay"), ("checkbox", "Checkbox"), ("cash", "Наличные"), ("bank", "Банк"),
                 ("np_cod", "Накладений платіж НП"), ("reqs", "Реквізити")]
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name="payments")
    provider = models.CharField(max_length=16, choices=PROVIDERS)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    is_paid = models.BooleanField(default=False)
    external_id = models.CharField(max_length=128, blank=True, db_index=True)
    checkbox_receipt_id = models.CharField(max_length=64, blank=True, default="", help_text="ID чека Checkbox для цього платежу")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["external_id"], condition=~models.Q(external_id=""), name="uniq_payment_external_id"),
        ]

    def __str__(self):
        return f"{self.get_provider_display()} {self.amount} (#{self.deal_id})"


class MetaConversionEvent(models.Model):
    """Безпечна черга CRM-подій для Meta Conversions API.

    У payload зберігаються лише нормалізовані хеші контактних даних. Реальна
    відправка вимкнена за замовчуванням і запускається окремою командою.
    """

    STATUSES = [
        ("pending", "Очікує"),
        ("processing", "Відправляється"),
        ("sent", "Відправлено"),
        ("failed", "Помилка"),
        ("skipped", "Пропущено"),
    ]
    SOURCE_TYPES = [
        ("lead", "Лід"),
        ("deal", "Сделка"),
        ("payment", "Оплата"),
    ]

    event_id = models.CharField(max_length=160, unique=True, db_index=True)
    event_name = models.CharField(max_length=64, db_index=True)
    source_type = models.CharField(max_length=16, choices=SOURCE_TYPES, db_index=True)
    source_id = models.PositiveBigIntegerField(db_index=True)
    contact = models.ForeignKey(Contact, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="meta_conversion_events")
    lead = models.ForeignKey(Lead, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="meta_conversion_events")
    deal = models.ForeignKey(Deal, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="meta_conversion_events")
    payment = models.ForeignKey(Payment, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="meta_conversion_events")
    stage = models.ForeignKey(Stage, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="meta_conversion_events")
    occurred_at = models.DateTimeField(db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=STATUSES, default="pending", db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=500, blank=True, default="")
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["status", "created_at"], name="crm_meta_status_created")]

    def __str__(self):
        return f"{self.event_name} · {self.event_id}"


class MetaAdDailyStat(models.Model):
    """Щоденний read-only зріз Marketing API.

    Рядки рівня account живлять загальні KPI, а рядки рівня ad — ієрархію
    campaign → adset → ad та креативи. Токени й сирі відповіді Graph API тут
    ніколи не зберігаються.
    """

    LEVELS = [("account", "Акаунт"), ("ad", "Оголошення")]

    date = models.DateField(db_index=True)
    level = models.CharField(max_length=12, choices=LEVELS, db_index=True)
    object_id = models.CharField(max_length=64, db_index=True)
    account_id = models.CharField(max_length=64, db_index=True)
    account_name = models.CharField(max_length=255, blank=True, default="")
    currency = models.CharField(max_length=8, blank=True, default="USD")
    campaign_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    campaign_name = models.CharField(max_length=255, blank=True, default="")
    campaign_objective = models.CharField(max_length=80, blank=True, default="")
    adset_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    adset_name = models.CharField(max_length=255, blank=True, default="")
    ad_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    ad_name = models.CharField(max_length=255, blank=True, default="")
    effective_status = models.CharField(max_length=32, blank=True, default="")
    creative_id = models.CharField(max_length=64, blank=True, default="")
    media_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    thumbnail_url = models.URLField(max_length=1200, blank=True, default="")
    permalink_url = models.URLField(max_length=1200, blank=True, default="")
    spend = models.DecimalField(max_digits=16, decimal_places=4, default=0)
    fx_rate_to_uah = models.DecimalField(max_digits=14, decimal_places=6, null=True, blank=True)
    spend_uah = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    impressions = models.PositiveBigIntegerField(default=0)
    reach = models.PositiveBigIntegerField(default=0)
    clicks = models.PositiveBigIntegerField(default=0)
    outbound_clicks = models.PositiveBigIntegerField(default=0)
    messages_started = models.PositiveBigIntegerField(default=0)
    meta_leads = models.PositiveBigIntegerField(default=0)
    purchases = models.PositiveBigIntegerField(default=0)
    video_views = models.PositiveBigIntegerField(default=0)
    # «Результат» кампанії за її ціллю — як колонка «Результати» в Ads Manager
    # (Graph insights field=results). Індикатор без префіксів actions:/conversions:.
    result_indicator = models.CharField(max_length=160, blank=True, default="")
    result_value = models.PositiveBigIntegerField(default=0)
    actions = models.JSONField(default=dict, blank=True)
    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "account_id", "level", "object_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["date", "level", "account_id", "object_id"],
                name="uniq_meta_ad_daily_object",
            ),
        ]
        indexes = [
            models.Index(fields=["level", "date"], name="crm_meta_ad_level_date"),
            models.Index(fields=["campaign_id", "date"], name="crm_meta_ad_campaign_date"),
            models.Index(fields=["adset_id", "date"], name="crm_meta_ad_adset_date"),
            models.Index(fields=["ad_id", "date"], name="crm_meta_ad_ad_date"),
        ]

    def __str__(self):
        return f"{self.date} · {self.level} · {self.object_id}"


class MetaPaidFollowStat(models.Model):
    """Платні підписки Instagram із експортованого звіту Ads Manager.

    Marketing API не віддає цю метрику. CRM читає саме плановий XLSX-звіт
    Meta, тому тут зберігається тільки розріз, який фактично відображений у
    кабінеті: день → кампанія → група → оголошення.
    """

    date = models.DateField(db_index=True)
    campaign_name = models.CharField(max_length=255, blank=True, default="")
    adset_name = models.CharField(max_length=255, blank=True, default="")
    ad_name = models.CharField(max_length=255, blank=True, default="")
    follows = models.PositiveIntegerField(default=0)
    report_uid = models.CharField(max_length=64, blank=True, default="")
    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "campaign_name", "adset_name", "ad_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["date", "campaign_name", "adset_name", "ad_name"],
                name="uniq_meta_paid_follow_daily_ad",
            ),
        ]
        indexes = [
            models.Index(fields=["date", "campaign_name"], name="crm_meta_follow_campaign_day"),
            models.Index(fields=["date", "adset_name"], name="crm_meta_follow_adset_day"),
            models.Index(fields=["date", "ad_name"], name="crm_meta_follow_ad_day"),
        ]

    def __str__(self):
        return f"{self.date} · {self.ad_name or self.adset_name or self.campaign_name} · {self.follows}"


class Ga4DailyStat(models.Model):
    """Денна статистика сайту з Google Analytics 4 (Data API, runReport).

    Одна властивість (property) = один сайт Wallcov. ``sources`` — топ джерел
    трафіку дня {"source / medium": sessions} (до 10). NULL немає: день без
    трафіку просто відсутній.
    """

    property_id = models.CharField(max_length=32, db_index=True)
    site = models.CharField(max_length=120, blank=True, default="")
    date = models.DateField(db_index=True)
    sessions = models.PositiveIntegerField(default=0)
    active_users = models.PositiveIntegerField(default=0)
    new_users = models.PositiveIntegerField(default=0)
    key_events = models.PositiveIntegerField(default=0)
    sources = models.JSONField(default=dict, blank=True)
    # Канали GA (sessionDefaultChannelGroup): {"Paid Social": {"s": сесії, "k": ключові події}}
    channels = models.JSONField(default=dict, blank=True)
    engagement_rate = models.FloatField(default=0)      # % залучених сесій
    avg_duration_sec = models.PositiveIntegerField(default=0)
    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("property_id", "date"), name="uniq_ga4_property_day"),
        ]
        indexes = [models.Index(fields=["site", "date"], name="crm_ga4_site_day")]

    def __str__(self):
        return f"{self.date} · {self.site or self.property_id}"


class MetaAccountDailyStat(models.Model):
    """Щоденний зріз професійного Instagram-акаунта.

    ``followers_total`` — фактичний баланс на момент щоденного sync. Meta не
    повертає історичний баланс заднім числом, тому старі дні залишаються NULL.
    ``followers_gained`` — офіційний денний показник account insights.
    """

    date = models.DateField(db_index=True)
    ig_account_id = models.CharField(max_length=64, db_index=True)
    username = models.CharField(max_length=150, blank=True, default="")
    followers_total = models.PositiveBigIntegerField(null=True, blank=True)
    followers_gained = models.IntegerField(null=True, blank=True)
    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "ig_account_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["date", "ig_account_id"],
                name="uniq_meta_ig_account_daily",
            ),
        ]
        indexes = [
            models.Index(fields=["ig_account_id", "date"], name="crm_meta_ig_account_day"),
        ]

    def __str__(self):
        return f"{self.date} · @{self.username or self.ig_account_id}"


class MetaContentStat(models.Model):
    """Поточні lifetime-показники власного Instagram-контенту.

    Органіка зберігається окремо від реклами. Nullable-поля важливі: Meta для
    окремих типів медіа повертає відсутній показник, і це не дорівнює нулю.
    """

    ig_account_id = models.CharField(max_length=64, db_index=True)
    media_id = models.CharField(max_length=64, unique=True, db_index=True)
    caption = models.TextField(blank=True, default="")
    media_type = models.CharField(max_length=32, blank=True, default="")
    media_product_type = models.CharField(max_length=32, blank=True, default="")
    permalink = models.URLField(max_length=1200, blank=True, default="")
    thumbnail_url = models.URLField(max_length=1200, blank=True, default="")
    published_at = models.DateTimeField(db_index=True)
    like_count = models.PositiveBigIntegerField(default=0)
    comments_count = models.PositiveBigIntegerField(default=0)
    reach = models.PositiveBigIntegerField(null=True, blank=True)
    views = models.PositiveBigIntegerField(null=True, blank=True)
    saved = models.PositiveBigIntegerField(null=True, blank=True)
    shares = models.PositiveBigIntegerField(null=True, blank=True)
    total_interactions = models.PositiveBigIntegerField(null=True, blank=True)
    follows = models.PositiveBigIntegerField(null=True, blank=True)
    profile_visits = models.PositiveBigIntegerField(null=True, blank=True)
    metrics = models.JSONField(default=dict, blank=True)
    first_synced_at = models.DateTimeField(auto_now_add=True)
    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at", "-id"]
        indexes = [
            models.Index(fields=["ig_account_id", "published_at"], name="crm_meta_content_pub"),
            models.Index(fields=["media_product_type", "published_at"], name="crm_meta_content_type"),
        ]

    def __str__(self):
        return f"{self.media_product_type or self.media_type} · {self.media_id}"


# ============================================================================
# АУДИТ-ЖУРНАЛ — хто/коли/що змінив (ліди, сделки, фінанси). Незалежний від Бітрикса.
# ============================================================================
class ActivityLog(models.Model):
    KIND = [("lead", "Лід"), ("deal", "Сделка"), ("finance", "Фінанси"), ("contact", "Клієнт")]
    kind = models.CharField(max_length=12, choices=KIND, db_index=True)
    object_id = models.IntegerField(db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    actor = models.CharField(max_length=80, blank=True, default="", help_text="Хто дію зробив (менеджер / AI-агент / Система)")
    action = models.CharField(max_length=120)
    detail = models.CharField(max_length=400, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.kind}#{self.object_id}] {self.action}"


def log_activity(kind, object_id, action, detail="", user=None, actor=""):
    """Записати подію в аудит-журнал. Безпечно (не валить основну операцію)."""
    try:
        u = user if (user is not None and getattr(user, "is_authenticated", False)) else None
        who = actor or (u.get_full_name() or u.username if u else "Система")
        ActivityLog.objects.create(kind=kind, object_id=int(object_id), action=str(action)[:120],
                                   detail=str(detail)[:400], user=u, actor=str(who)[:80])
    except Exception:
        pass


# ============================================================================
# РУШІЙ АВТОМАТИЗАЦІЇ ВОРОНКИ — авто-перехід стадій (сценарій як у ChatPlace/Бітрикс,
# але незалежний, всередині CRM). Кожне правило: на стадії X за тригером T → перейти на Y.
# ============================================================================
class AutomationRule(models.Model):
    TRIGGERS = [
        ("manager_reply", "Менеджер/AI відповів"),
        ("client_reply", "Клієнт відповів"),
        ("ready_buy", "Готовність купити"),
        ("payment", "Оплата отримана"),
        ("time_in_stage", "Простій на стадії (дожим)"),
        ("field_changed", "Змінилось поле"),
        ("item_added", "Додано товар"),
    ]
    funnel = models.ForeignKey("Funnel", on_delete=models.CASCADE, related_name="automation_rules")
    from_stage = models.ForeignKey("Stage", on_delete=models.CASCADE, related_name="+")
    to_stage = models.ForeignKey("Stage", on_delete=models.CASCADE, related_name="+")
    trigger = models.CharField(max_length=20, choices=TRIGGERS)
    enabled = models.BooleanField(default=True)
    # розширення (v1): умови входу, дії при вході, людський опис, дожим-таймер
    entry_conditions = models.JSONField(default=list, blank=True, help_text="Умови входу на стадію")
    actions = models.JSONField(default=list, blank=True, help_text="Дії при потраплянні на стадію")
    description = models.TextField(blank=True, help_text="Опис правила людською мовою (для навчання)")
    delay_hours = models.IntegerField(default=0, help_text="Затримка дії, годин (дожим)")
    note_to_staff = models.TextField(blank=True, help_text="Підказка співробітнику")

    class Meta:
        unique_together = [("funnel", "from_stage", "trigger")]

    def __str__(self):
        return f"{self.from_stage} --{self.trigger}--> {self.to_stage}"



class GlobalRule(models.Model):
    """Глобальні правила роботи CRM по блоках/сутностях. Джерело правди для
    навчання співробітників ТА системний контекст вбудованого Claude-агента."""
    BLOCKS = [
        ("products", "Товари"), ("sales", "Продажі / воронки"), ("automation", "Автоматизації"),
        ("payments", "Платежі"), ("novaposhta", "Нова Пошта"), ("checkbox", "Чеки (Checkbox)"),
        ("warehouse", "Склад"), ("followup", "Дожими"), ("general", "Загальні"),
    ]
    block = models.CharField(max_length=20, choices=BLOCKS, db_index=True)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True, help_text="Markdown, редагується менеджером")
    funnel = models.ForeignKey("Funnel", null=True, blank=True, on_delete=models.SET_NULL, related_name="global_rules")
    priority = models.IntegerField(default=100)
    enabled = models.BooleanField(default=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["block", "priority", "id"]

    def __str__(self):
        return f"[{self.block}] {self.title}"


class Task(models.Model):
    """Задача співробітнику (склад/тонування/менеджер/дожим). Ставиться на ВІДДІЛ,
    стає персональною коли хтось прийняв. proposed = агент пропонує, треба апрув."""
    KINDS = [("warehouse", "Склад"), ("tinting", "Тонування"), ("manager", "Менеджер"),
             ("followup", "Дожим"), ("other", "Інше")]
    STATUS = [("proposed", "Запропоновано"), ("open", "Відкрита"), ("in_progress", "В роботі"),
              ("done", "Виконана"), ("canceled", "Скасована")]
    PRIORITIES = [("low", "Низький"), ("normal", "Звичайний"), ("high", "Високий")]
    kind = models.CharField(max_length=16, choices=KINDS, default="other")
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    priority = models.CharField(max_length=8, choices=PRIORITIES, default="normal", db_index=True)
    deal = models.ForeignKey("Deal", null=True, blank=True, on_delete=models.CASCADE, related_name="tasks")
    lead = models.ForeignKey("Lead", null=True, blank=True, on_delete=models.CASCADE, related_name="tasks")
    contact = models.ForeignKey("Contact", null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks")
    conversation = models.ForeignKey("inbox.Conversation", null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks")
    department = models.ForeignKey("accounts.Department", null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks")
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks_created")
    status = models.CharField(max_length=14, choices=STATUS, default="open", db_index=True)
    due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_by_agent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["status", "-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.title}"


class AgentConfig(models.Model):
    """Налаштування вбудованого Claude-агента (один рядок, id=1)."""
    enabled = models.BooleanField(default=True)
    autonomous = models.BooleanField(default=True, help_text="True=агент сам виконує дії; False=пропонує")
    auto_on_reply = models.BooleanField(default=True, help_text="Запускати агента на кожну відповідь клієнта")
    model = models.CharField(max_length=40, default="claude-sonnet-4-6")
    priority_enabled = models.BooleanField(default=True, help_text="ИИ-РОП авто-приоритет чатов (крон 5хв)")
    priority_model = models.CharField(max_length=40, default="claude-haiku-4-5")
    analyst_model = models.CharField(max_length=40, default="claude-sonnet-4-6")
    suggest_model = models.CharField(max_length=40, default="claude-sonnet-4-6")
    cache_enabled = models.BooleanField(default=True, help_text="Prompt caching — економія на повторному контексті")
    analyst_auto = models.BooleanField(default=False, help_text="Коуч-аналіз САМ при відкритті картки (Opus). False = тільки по кнопці")
    system_extra = models.TextField(blank=True, help_text="Додаткова інструкція агенту")

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        return obj


class AgentRun(models.Model):
    """Аудит прогонів агента: що зробив, скільки токенів, помилки."""
    kind = models.CharField(max_length=10, default="lead")  # lead / deal
    lead = models.ForeignKey("Lead", null=True, blank=True, on_delete=models.SET_NULL, related_name="agent_runs")
    deal = models.ForeignKey("Deal", null=True, blank=True, on_delete=models.SET_NULL, related_name="agent_runs")
    trigger = models.CharField(max_length=20, default="manual")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    model = models.CharField(max_length=40, blank=True)
    output = models.JSONField(default=dict, blank=True)
    tasks_created = models.IntegerField(default=0)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class PayLink(models.Model):
    """Коротке посилання на оплату → редірект на повний LiqPay URL (щоб клієнту не слати потвору)."""
    code = models.CharField(max_length=12, unique=True, db_index=True)
    deal = models.ForeignKey("Deal", null=True, blank=True, on_delete=models.CASCADE, related_name="pay_links")
    target = models.TextField()
    clicks = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)


class DialogAnalysis(models.Model):
    """Оцінка якості діалогу від Аналітика-коуча (історія для скорингу + гейміфікації)."""
    conversation = models.ForeignKey("inbox.Conversation", null=True, blank=True, on_delete=models.CASCADE, related_name="analyses")
    deal = models.ForeignKey("Deal", null=True, blank=True, on_delete=models.CASCADE, related_name="analyses")
    lead = models.ForeignKey("Lead", null=True, blank=True, on_delete=models.CASCADE, related_name="analyses")
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    kind = models.CharField(max_length=10, default="chat", help_text="chat / call")
    overall_score = models.IntegerField(default=0)
    scores = models.JSONField(default=dict)
    strengths = models.TextField(blank=True, default="")
    why_not_selling = models.TextField(blank=True, default="")
    recommended_reply = models.TextField(blank=True, default="")
    coaching = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]



class AiUsage(models.Model):
    """Лог кожного виклику Claude — для детального звіту витрат по днях/механіках."""
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    source = models.CharField(max_length=60, db_index=True)
    model = models.CharField(max_length=40)
    in_tok = models.IntegerField(default=0)
    out_tok = models.IntegerField(default=0)
    cache_read = models.IntegerField(default=0)
    cache_write = models.IntegerField(default=0)
    cost_usd = models.FloatField(default=0)
    est = models.BooleanField(default=False, help_text="True=оцінка (історія до логування), False=точно")
    note = models.CharField(max_length=200, blank=True)


class ChangeLogEntry(models.Model):
    """Історія змін CRM простою мовою — показується на сторінці «Що нового»."""
    d = models.DateField(db_index=True)
    section = models.CharField(max_length=48, blank=True, default="", db_index=True,
                               help_text="Блок-розділ для групування: Фінанси / Склад / Клієнти / Загальне")
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True, default="")
    # ── двомовність (uk/ru) + машинний ключ категорії (щоб не дублювались Фінанси/Финансы) ──
    section_key = models.CharField(max_length=24, blank=True, default="", db_index=True,
                                   help_text="Ключ категорії: finance/warehouse/clients/sales/delivery/shop/telephony/general")
    title_uk = models.CharField(max_length=200, blank=True, default="")
    title_ru = models.CharField(max_length=200, blank=True, default="")
    body_uk = models.TextField(blank=True, default="")
    body_ru = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-d", "-id"]

    def __str__(self):
        return "%s %s" % (self.d, self.title)


class ZamerProject(models.Model):
    """Проект замера из приложения «Wallcov Замер».
    Привязан к устройству (device_uuid из Keychain — переживает переустановку),
    и к пользователю если он вошёл. Хранит полный замер (payload) — чтобы
    проекты не терялись после переустановки/переделки приложения."""
    device_uuid = models.CharField(max_length=64, db_index=True)
    project_uuid = models.CharField(max_length=64, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                             on_delete=models.SET_NULL, related_name="zamer_projects")
    contact = models.ForeignKey(Contact, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="measurement_projects")
    deal = models.ForeignKey(Deal, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="measurement_projects")
    title = models.CharField(max_length=255, blank=True, default="")
    payload = models.JSONField(default=dict)
    revision = models.PositiveBigIntegerField(default=1)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["device_uuid", "project_uuid"], name="uniq_device_project"),
        ]

    def __str__(self):
        return f"ZamerProject {self.project_uuid} ({self.device_uuid[:8]})"


class ZamerStageReview(models.Model):
    """Specialist review requested by a client for one project stage."""

    STATUS = [
        ("pending", "Очікує перевірки"),
        ("accepted", "Прийнято"),
        ("rework", "Потрібно виправити"),
    ]
    project = models.ForeignKey(
        ZamerProject, on_delete=models.CASCADE, related_name="stage_reviews",
    )
    contact = models.ForeignKey(
        Contact, on_delete=models.PROTECT, related_name="zamer_stage_reviews",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="requested_zamer_stage_reviews",
    )
    stage_id = models.CharField(max_length=80)
    title = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=STATUS, default="pending", db_index=True)
    note = models.TextField(blank=True, default="")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="reviewed_zamer_stages",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "stage_id"],
                condition=models.Q(status="pending"),
                name="uniq_pending_project_stage_review",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "created_at"], name="zamer_review_queue_idx"),
        ]


def default_calc_settings():
    """Безопасные серверные значения калькулятора; внутренние ставки не попадают в публичный JS."""
    return {
        "reserve_pct": 10,
        "labor_wall_m2": 0,
        "labor_reveal_linear_m": 0,
        "material_reveal_m2": 0,
        "transport_per_km": 0,
        "transport_min": 0,
        "minimum_order": 0,
        "overhead_pct": 0,
        "max_discount_pct": 15,
        "rounding_step": 1,
        "reveal_sides": ["left", "right", "top"],
        "show_internal_rates_to_client": False,
    }


class CalcSettings(models.Model):
    """Единая административная конфигурация калькулятора Wallcov в CRM."""
    key = models.CharField(max_length=32, unique=True, default="default")
    values = models.JSONField(default=default_calc_settings)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="calc_settings_updates")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Calculator settings"


class Estimate(models.Model):
    """Смета из приложения замера; всегда привязана к одному клиенту и одной сделке."""
    STATUS = [
        ("draft", "Чернетка"),
        ("sent", "Надіслано"),
        ("accepted", "Погоджено"),
        ("archived", "Архів"),
    ]
    name = models.CharField(max_length=255)
    contact = models.ForeignKey(Contact, on_delete=models.PROTECT, related_name="estimates")
    deal = models.ForeignKey(Deal, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="estimates")
    project = models.ForeignKey(ZamerProject, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="estimates")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                              on_delete=models.SET_NULL, related_name="estimates")
    measurement_snapshot = models.JSONField(default=dict)
    lines = models.JSONField(default=list)
    totals = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=STATUS, default="draft", db_index=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["project", "deal"],
                                    condition=models.Q(project__isnull=False, deal__isnull=False),
                                    name="uniq_project_deal_estimate"),
        ]

    def __str__(self):
        return self.name


class WeeklyManagerReview(models.Model):
    """Збережений тижневий вердикт AI-РОП по роботі менеджерів (для керівника)."""
    created_at = models.DateTimeField(auto_now_add=True)
    period = models.CharField(max_length=40, blank=True, default="")
    summary = models.TextField(blank=True, default="")
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-id"]


class KpLink(models.Model):
    """Публічне посилання на документ (КП/накладну) для швидкої відправки клієнту."""
    code = models.CharField(max_length=24, unique=True)
    deal = models.ForeignKey("Deal", on_delete=models.CASCADE, related_name="kp_links")
    html = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]


class MetaSyncSettings(models.Model):
    """Настройки авто-обновления данных маркетинга: интервалы по источникам."""
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    ads_enabled = models.BooleanField(default=True)
    content_enabled = models.BooleanField(default=True)
    account_enabled = models.BooleanField(default=True)
    ads_interval_min = models.PositiveIntegerField(default=360)
    content_interval_min = models.PositiveIntegerField(default=360)
    account_interval_min = models.PositiveIntegerField(default=360)
    recent_days = models.PositiveIntegerField(default=7)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Настройки обновления маркетинга"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        return obj



class KbEntry(models.Model):
    """База знань ІІ-продавця Wallcov (незалежна від ChatPlace).
    Імпорт із ChatPlace + ручне поповнення + додавання з невідомих питань.
    ІІ-продавець підтягує сюди точні відповіді (без вигадування)."""
    SOURCE = [("chatplace", "ChatPlace-імпорт"), ("manual", "Додано вручну"), ("dialog", "З діалогу")]
    ext_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    question = models.TextField()
    answer = models.TextField(blank=True, default="")
    specific_rules = models.TextField(blank=True, default="")
    source = models.CharField(max_length=16, choices=SOURCE, default="manual")
    client_chat_count = models.IntegerField(default=0, help_text="Скільки разів клієнти про це питали (популярність)")
    tags = models.CharField(max_length=255, blank=True, default="")
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-client_chat_count", "question"]

    def __str__(self):
        return (self.question or "")[:60]


class KbUnknownQuestion(models.Model):
    """Питання, на які ІІ не знав відповіді (як «невідомі» у ChatPlace).
    На розгляд менеджера → додати відповідь у KbEntry."""
    STATUS = [("new", "Нове"), ("answered", "Додано в базу"), ("ignored", "Ігнор")]
    SOURCE = [("chatplace", "ChatPlace"), ("dialog", "З діалогу CRM")]
    ext_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    question = models.TextField()
    status = models.CharField(max_length=16, choices=STATUS, default="new", db_index=True)
    source = models.CharField(max_length=16, choices=SOURCE, default="chatplace")
    answer_entry = models.ForeignKey(KbEntry, null=True, blank=True, on_delete=models.SET_NULL, related_name="from_questions")
    times_asked = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-times_asked", "-created_at"]

    def __str__(self):
        return (self.question or "")[:60]


class DuplicateDismissal(models.Model):
    """«Це РІЗНІ люди» — рішення менеджера по групі з розділу «Дублі».

    Навіщо: у списку дублів є групи-однофамільці й люди з одним номером на двох
    (Анна Пікшрєнє / Юлия Чикаловец на +380678664328). Злити їх не можна, а без
    цієї позначки вони висіли б у списку вічно й заважали бачити справжні дублі.
    Натиснув «Це різні люди» → група зникає зі списку, рішення зберігається.
    Ключ = ID карток групи через дефіс. Якщо до групи додасться НОВА картка —
    ключ інший, і група покажеться знову (це навмисно: нові дані треба глянути).
    """
    key = models.CharField("Ключ групи", max_length=255, unique=True, db_index=True)
    contact_ids = models.JSONField("ID карток", default=list)
    reason = models.CharField("Чому не дубль", max_length=200, blank=True, default="")
    by_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="duplicate_dismissals")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Позначка «не дубль»"
        verbose_name_plural = "Позначки «не дублі»"

    def __str__(self):
        return "не дублі: %s" % self.key
