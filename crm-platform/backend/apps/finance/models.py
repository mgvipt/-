from datetime import date as _date
from django.db import models
from django.db.models import Sum


class Account(models.Model):
    """Счёт/касса (ФОП карта, наличка, LiqPay-эквайринг и т.д.)."""
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=24, default="bank")  # bank/cash/acquiring
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0, help_text="Порядок у списках (менше — вище)")

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name

    def balance(self):
        inc = self.transactions.filter(direction="in").aggregate(s=Sum("amount"))["s"] or 0
        exp = self.transactions.filter(direction="out").aggregate(s=Sum("amount"))["s"] or 0
        tr_out = self.transactions.filter(direction="transfer").aggregate(s=Sum("amount"))["s"] or 0
        tr_in = self.incoming_transfers.aggregate(s=Sum("amount"))["s"] or 0
        return inc + tr_in - exp - tr_out


class Category(models.Model):
    DIRECTION = [("in", "Доход"), ("out", "Расход")]
    name = models.CharField(max_length=120)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="children", help_text="Батьківська категорія (підкатегорії ФінМапа)")
    direction = models.CharField(max_length=3, choices=DIRECTION)

    class Meta:
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Transaction(models.Model):
    DIRECTION = [("in", "Доход"), ("out", "Расход"), ("transfer", "Переказ")]
    direction = models.CharField(max_length=10, choices=DIRECTION)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="transactions")
    transfer_account = models.ForeignKey(Account, null=True, blank=True, on_delete=models.PROTECT, related_name="incoming_transfers", help_text="Рахунок-отримувач (для переказу)")
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions")
    comment = models.CharField(max_length=255, blank=True)
    deal = models.ForeignKey("crm.Deal", null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions")
    payment = models.OneToOneField("crm.Payment", null=True, blank=True, on_delete=models.SET_NULL, related_name="transaction")
    fin_direction = models.ForeignKey("FinDirection", null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions")
    fin_article = models.ForeignKey("FinModelArticle", null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions", help_text="Фонд (стаття финмоделі)")
    channel = models.CharField(max_length=24, blank=True, default="", help_text="Канал/джерело надходження")
    counterparty = models.CharField(max_length=160, blank=True, default="", help_text="Контрагент (від кого/кому)")
    currency = models.CharField(max_length=3, default="UAH", help_text="Валюта операції")
    rate = models.DecimalField(max_digits=12, decimal_places=4, default=1, help_text="Курс до гривні (1 одиниця валюти = N грн)")
    amount_uah = models.DecimalField(max_digits=14, decimal_places=2, default=0, help_text="Сума у гривні (amount × rate) — для аналітики")
    date = models.DateField(default=_date.today, db_index=True)
    op_time = models.TimeField(null=True, blank=True, help_text="Час операції (з банку або момент внесення)")
    import_batch = models.CharField(max_length=48, blank=True, default="", db_index=True,
                                    help_text="Партія імпорту (банк/виписка) — для відкату помилкового завантаження")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "id"]

    def save(self, *args, **kwargs):
        self.amount_uah = (self.amount or 0) * (self.rate or 1)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.direction}] {self.amount} {self.currency}"


class FinModelArticle(models.Model):
    """Справочник финмодели (ATM): статьи для расчёта P&L и точки безубыточности.
    Редактирует владелец в разделе Финансы → Налаштування фінмоделі."""
    CATEGORY = [
        ("revenue_fund", "Фонди виручки (% з виручки)"),
        ("payment_fee", "Комісія еквайрингу (₴/угода)"),
        ("variable", "Перемінні витрати (% від маржі)"),
        ("fixed", "Постійні витрати (₴/міс)"),
        ("upr_cat2", "УПР обов'язкові (₴/міс, у ТБ)"),
        ("upr_cat3", "УПР відмовні (₴/міс)"),
        ("warehouse_rate", "Ставки складу"),
        ("skd", "Фонд СКД / розвитку (грн/міс)"),
        ("config", "Конфіг / ліміти"),
        ("salary", "ЗП менеджера (ставки)"),
    ]
    VALUE_TYPE = [
        ("percent", "%"),
        ("fixed_sum_per_month", "₴/місяць"),
        ("fixed_per_deal", "₴/угода"),
        ("auto_meta_ads", "Авто Meta-ads"),
    ]
    category = models.CharField(max_length=24, choices=CATEGORY)
    name = models.CharField(max_length=160)
    value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    value_type = models.CharField(max_length=24, choices=VALUE_TYPE, default="percent")
    unit = models.CharField(max_length=24, blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE,
        related_name="subfunds", help_text="Батьківський фонд (для підфондів)")
    is_envelope = models.BooleanField(default=False,
        help_text="Конверт: тримає гроші, отримує розподіл і робить з нього розхід")
    code = models.CharField(max_length=40, blank=True, default="", help_text="Машинний код для службових параметрів (salary_base тощо)")

    # Групи фондів у логіці Finmap: ФВ → ФМ → ФСКД
    FUND_GROUP = {
        "revenue_fund": "revenue",
        "variable": "margin", "fixed": "margin",
        "skd": "skd",
        "upr_cat2": "upr", "upr_cat3": "upr",
    }

    class Meta:
        ordering = ["category", "sort_order", "id"]

    @property
    def fund_group(self):
        """revenue=Фонди виручки, margin=Фонди маржі, skd=Фонди СКД, upr, other."""
        return self.FUND_GROUP.get(self.category, "other")

    @property
    def margin_kind(self):
        """Для фондів маржі: variable=змінні, fixed=постійні."""
        return {"variable": "variable", "fixed": "fixed"}.get(self.category, "")

    def __str__(self):
        return f"{self.get_category_display()}: {self.name}"


class FinDirection(models.Model):
    """Напрямок бізнесу (проект Finmap): ДЕКОР Товари / Об'єкти / Hardwork / Маркетинг.
    Дозволяє рахувати доходи/витрати/прибуток/рентабельність по кожному напрямку + план."""
    name = models.CharField(max_length=160)
    plan_income = models.DecimalField(max_digits=14, decimal_places=2, default=0, help_text="План доходу (рік/період)")
    plan_expense = models.DecimalField(max_digits=14, decimal_places=2, default=0, help_text="План витрат")
    sort_order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name


class ChannelSpend(models.Model):
    """Рекламні витрати по каналу за місяць (для ROAS). Авто з Meta-ads або вручну."""
    channel = models.CharField(max_length=24)
    period = models.CharField(max_length=7, help_text="YYYY-MM")
    spend = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    src = models.CharField(max_length=10, default="manual", help_text="meta / manual")

    class Meta:
        unique_together = [("channel", "period")]

    def __str__(self):
        return f"{self.channel} {self.period}: {self.spend}"


class FundAllocation(models.Model):
    """Розподіл грошей у фонд-конверт (планування за логікою Finmap).
    Гроші приходять на рахунок → розподіляються по фондах. Залишок фонду =
    сума розподілів − витрати з цього фонду (Transaction out з fin_article=fund)."""
    fund = models.ForeignKey(FinModelArticle, on_delete=models.CASCADE, related_name="allocations")
    account = models.ForeignKey(Account, null=True, blank=True, on_delete=models.SET_NULL, related_name="fund_allocations")
    fin_direction = models.ForeignKey(FinDirection, null=True, blank=True, on_delete=models.SET_NULL, related_name="fund_allocations")
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    period = models.CharField(max_length=7, help_text="YYYY-MM")
    comment = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.fund.name} +{self.amount} ({self.period})"


class ManagerPlan(models.Model):
    """Персональний план менеджера на місяць (3 рівні). Замінює хардкод 400К.
    Норма ≈ факт × 1.2 (rolling). Амбіція ≈ факт × 1.5."""
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="kpi_plans")
    period = models.CharField(max_length=7, help_text="YYYY-MM")
    min_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0, help_text="Мінімум (поріг)")
    target_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0, help_text="Норма / ціль")
    ambition_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0, help_text="Амбіція (stretch)")

    class Meta:
        unique_together = [("user", "period")]
        ordering = ["-period"]

    def __str__(self):
        return f"{self.user} {self.period}: ціль {self.target_revenue}"


class AdvisoryReport(models.Model):
    """Звіт радчої системи (бізнес-аналітик/фінаналітик/РОП/коуч/маркетолог + конкуренти).
    Показується у CRM у вкладці «Зростання» як план дій для власника."""
    kind = models.CharField(max_length=32, default="profit_x2")
    title = models.CharField(max_length=200, default="План зростання прибутку")
    body = models.TextField(help_text="Markdown")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.created_at:%Y-%m-%d})"


class PlannedPayment(models.Model):
    """Дебіторка/Кредиторка: заплановані платежі ОКРЕМО від факту (журналу).
    Кредиторка = ми винні (майбутня витрата), Дебіторка = нам винні (майбутній дохід).
    «Оплачено» → створюється фактична операція в журналі."""
    KIND = [("payable", "Кредиторка (ми винні)"), ("receivable", "Дебіторка (нам винні)")]
    STATUS = [("planned", "Заплановано"), ("paid", "Оплачено"), ("canceled", "Скасовано")]
    kind = models.CharField(max_length=12, choices=KIND, db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    due_date = models.DateField(db_index=True)
    counterparty = models.CharField(max_length=160, blank=True)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="planned_payments")
    account = models.ForeignKey(Account, null=True, blank=True, on_delete=models.SET_NULL, related_name="planned_payments")
    deal = models.ForeignKey("crm.Deal", null=True, blank=True, on_delete=models.SET_NULL, related_name="planned_payments")
    comment = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="planned", db_index=True)
    paid_tx = models.ForeignKey("Transaction", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date", "id"]


class BankRule(models.Model):
    """Правило авторозноски банківських операцій: якщо поле містить текст →
    проставити категорію / напрямок / фонд / контрагента. Застосовується при
    синку Приват/Моно та імпорті виписок (перше правило за пріоритетом)."""
    FIELDS = [("osnd", "Призначення платежу"), ("counterparty", "Контрагент")]
    field = models.CharField(max_length=16, choices=FIELDS, default="osnd")
    contains = models.CharField("Містить текст", max_length=160, blank=True, default="")
    direction = models.CharField(max_length=10, blank=True, default="", help_text="Порожньо = будь-який; in/out")
    set_category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    set_fin_direction = models.ForeignKey("FinDirection", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    set_fin_article = models.ForeignKey("FinModelArticle", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    set_counterparty = models.CharField(max_length=160, blank=True, default="")
    priority = models.IntegerField(default=100)
    active = models.BooleanField(default=True)
    # ── v2 (як у ФінМап): імʼя, умови І/АБО, дії, лічильник ──
    name = models.CharField(max_length=160, blank=True, default="")
    logic = models.CharField(max_length=3, default="or", help_text="and | or — як поєднувати умови")
    conditions = models.JSONField(default=list, blank=True, help_text="[{field: osnd|counterparty|account, op: contains|not_contains|equals, text}]")
    actions = models.JSONField(default=dict, blank=True, help_text="{category, fin_direction, fin_article, counterparty, channel}")
    hits = models.IntegerField(default=0, help_text="скільки разів правило спрацювало")

    class Meta:
        ordering = ["priority", "id"]


class TransactionAttachment(models.Model):
    """Фото/скан чека або документа до операції. Зберігаємо у БД (до 10 МБ),
    щоб не залежати від файлового тому. Віддаємо через авторизований API."""
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="attachments")
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, default="application/octet-stream")
    size = models.PositiveIntegerField(default=0)
    data = models.BinaryField()
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.filename} ({self.size} b)"


class WorkDay(models.Model):
    """Табель робочого часу менеджера (як Бітрикс timeman). Впливає на оклад
    (пропорційно відпрацьованим дням) і перевиконання (вихід у вихідний = +денна ставка)."""
    STATUS = [
        ("worked", "Робочий день"),
        ("overtime", "Перевиконання (вихід у вихідний)"),
        ("dayoff", "Вихідний"),
        ("sick", "Лікарняний"),
        ("vacation", "Відпустка"),
        ("absent", "Прогул"),
    ]
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="workdays")
    date = models.DateField()
    status = models.CharField(max_length=12, choices=STATUS, default="worked")
    note = models.CharField(max_length=160, blank=True, default="")

    class Meta:
        unique_together = [("user", "date")]
        ordering = ["-date"]

    def __str__(self):
        return f"{self.user_id} {self.date} {self.status}"


class WorkSession(models.Model):
    """Робоча зміна (як Бітрикс timeman): старт дня, пауза (обід), завершення.
    При старті автоматично відмічає WorkDay(worked) → табель заповнюється сам."""
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="work_sessions")
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    paused_seconds = models.PositiveIntegerField(default=0)
    paused_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def worked_seconds(self):
        from django.utils import timezone
        end = self.ended_at or timezone.now()
        total = (end - self.started_at).total_seconds() - self.paused_seconds
        if self.paused_at:
            total -= (timezone.now() - self.paused_at).total_seconds()
        return max(0, int(total))
