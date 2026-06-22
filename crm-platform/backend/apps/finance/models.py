from django.db import models
from django.db.models import Sum


class Account(models.Model):
    """Счёт/касса (ФОП карта, наличка, LiqPay-эквайринг и т.д.)."""
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=24, default="bank")  # bank/cash/acquiring
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    def balance(self):
        agg = self.transactions.aggregate(
            income=Sum("amount", filter=models.Q(direction="in")),
            expense=Sum("amount", filter=models.Q(direction="out")),
        )
        return (agg["income"] or 0) - (agg["expense"] or 0)


class Category(models.Model):
    DIRECTION = [("in", "Доход"), ("out", "Расход")]
    name = models.CharField(max_length=120)
    direction = models.CharField(max_length=3, choices=DIRECTION)

    class Meta:
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Transaction(models.Model):
    DIRECTION = [("in", "Доход"), ("out", "Расход")]
    direction = models.CharField(max_length=3, choices=DIRECTION)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="transactions")
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
    date = models.DateField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

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
