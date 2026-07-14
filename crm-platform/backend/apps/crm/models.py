from django.conf import settings
from django.db import models


class Company(models.Model):
    name = models.CharField(max_length=255)
    edrpou = models.CharField("ЄДРПОУ/ИНН", max_length=32, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Contact(models.Model):
    """Карточка клиента. Каналы (Instagram/Viber/...) накапливаются по мере общения."""
    first_name = models.CharField(max_length=120, blank=True)
    last_name = models.CharField(max_length=120, blank=True)
    middle_name = models.CharField(max_length=120, blank=True, default="", help_text="По батькові")
    nickname = models.CharField(max_length=150, blank=True, default="", help_text="Нік / імʼя з месенджера (оригінал)")
    phone = models.CharField(max_length=32, blank=True, db_index=True)
    email = models.EmailField(blank=True)
    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.SET_NULL, related_name="contacts")
    channels = models.JSONField(default=list, blank=True, help_text="['instagram','viber',...]")
    loyalty_tag = models.CharField(max_length=24, blank=True, default="", help_text="Новый/Активный/VIP/Спящий")
    birthday = models.DateField(null=True, blank=True)
    source = models.CharField(max_length=24, blank=True, default="", help_text="Звідки клієнт (instagram/site/...)")
    address = models.CharField(max_length=255, blank=True, default="", help_text="Адреса доставки / місто")
    comment = models.TextField(blank=True, default="", help_text="Нотатки менеджера про клієнта")
    social_link = models.CharField(max_length=300, blank=True, default="", help_text="Посилання на акаунт клієнта в месенджері (IG/TG/FB)")
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="contacts_owned", help_text="Ответственный менеджер клиента")
    shared_with = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="contacts_shared",
        help_text="Доступ к клиенту выдан этим менеджерам (шаринг). Свои клиенты видны и без этого.")
    last_touch_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}".strip() or self.phone or f"Контакт #{self.pk}"


class Funnel(models.Model):
    """Воронка продаж (напр. «21 Основний продукт», «22 Тестовий набір»)."""
    name = models.CharField(max_length=160)
    is_lead_funnel = models.BooleanField(default=False, help_text="True = воронка лидов")
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

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class DealItem(models.Model):
    """Товар в сделке. Сумма сделки = сумма строк."""
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("warehouse.Product", null=True, blank=True, on_delete=models.PROTECT, related_name="deal_items")
    custom_name = models.CharField(max_length=200, blank=True, default="",
                                   help_text="Своя позиція НЕ з номенклатури: без складського обліку і списання")
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
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
    kind = models.CharField(max_length=16, choices=KINDS, default="other")
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    deal = models.ForeignKey("Deal", null=True, blank=True, on_delete=models.CASCADE, related_name="tasks")
    lead = models.ForeignKey("Lead", null=True, blank=True, on_delete=models.CASCADE, related_name="tasks")
    department = models.ForeignKey("accounts.Department", null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks")
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks")
    status = models.CharField(max_length=14, choices=STATUS, default="open", db_index=True)
    due_at = models.DateTimeField(null=True, blank=True)
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-d", "-id"]

    def __str__(self):
        return "%s %s" % (self.d, self.title)
