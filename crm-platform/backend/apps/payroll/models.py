"""Ставки співробітників — ЄДИНЕ місце (рішення Олега 14.09.2026).

Звідси беруть: ЗП (Фінанси → ЗП/KPI), точка беззбитковості за ATM (Фінанси → Точка беззбитковості),
бонус у картці угоди, «що якщо» для вакансій. Змінюється в Налаштування → Ставки співробітників.
Правило: нова ставка = нова версія з місяця; старі версії й минулі місяці не переписуються.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class PayScheme(models.Model):
    """Схема оплати = версія «договору» співробітника, посади без акаунта (бухгалтер) або вакансії."""
    PURPOSE = [("official", "По ній платимо"), ("legacy", "Як платили раніше (для порівняння)")]
    STATUS = [("active", "Діє"), ("draft", "Чернетка"), ("archived", "Архів")]
    EMPLOYMENT = [("labor", "Трудовий договір"), ("fop", "ФОП"), ("none", "Без оформлення")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                             related_name="pay_schemes")
    position = models.CharField(max_length=120, help_text="Посада: «Менеджер з продажу», «Комірник», «SMM»…")
    department = models.CharField(max_length=60, blank=True, default="", help_text="Продажі / Склад / Маркетинг / Офіс")
    title = models.CharField(max_length=160, blank=True, default="")
    purpose = models.CharField(max_length=10, choices=PURPOSE, default="official")
    status = models.CharField(max_length=10, choices=STATUS, default="active")
    employment = models.CharField(max_length=6, choices=EMPLOYMENT, default="none",
                                  help_text="Від оформлення залежить, скільки людина коштує компанії (податки)")
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True, help_text="Включно; порожньо — діє зараз")
    is_vacancy = models.BooleanField(default=False)
    in_plan = models.BooleanField(default=True, help_text="Враховувати в точці беззбитковості (для вакансії — «що якщо»)")
    planned_start = models.DateField(null=True, blank=True)
    options = models.JSONField(default=dict, blank=True, help_text='{"insurance_first_month": true}')
    note = models.TextField(blank=True, default="")
    based_on = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["department", "position", "-valid_from", "id"]

    def __str__(self):
        who = self.user.get_full_name() if self.user_id else ("вакансія" if self.is_vacancy else "посада")
        return f"{self.position} · {who} · з {self.valid_from}"


class PayComponent(models.Model):
    KIND = [
        ("base_by_days", "За вихід / ставка (по табелю)"),
        ("fixed_monthly", "Фіксовано на місяць"),
        ("standard", "Стандарт роботи (премія до …)"),
        ("margin_share", "% з маржі продажів"),
        ("revenue_share", "% з обороту / суми акту"),
        ("event_bonus", "Бонус «тест-набір → основне»"),
        ("guarantee", "Гарантія новачку"),
        ("piece_rate", "Відрядно (склад)"),
    ]
    scheme = models.ForeignKey(PayScheme, on_delete=models.CASCADE, related_name="components")
    kind = models.CharField(max_length=16, choices=KIND)
    title = models.CharField(max_length=160, blank=True, default="")
    params = models.JSONField(default=dict, blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]


class PayPolicy(models.Model):
    """Правила компанії для всіх схем (один рядок id=1): податки, дивіденди, які статті фінмоделі замінені ставками…"""
    params = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")


class PayRateLog(models.Model):
    """Хто, коли, що змінив у ставках (було → стало)."""
    scheme = models.ForeignKey(PayScheme, null=True, blank=True, on_delete=models.SET_NULL, related_name="log")
    action = models.CharField(max_length=24)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True, default="")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-at", "-id"]


class ObjectAct(models.Model):
    """Акт обʼєкта. 2% від УСІЄЇ суми акту — менеджеру обʼєкта (рішення Олега 14.09),
    нараховується в місяць закриття. Закриває лише Олег (право objects.act.close)."""
    STATUS = [("draft", "Внесено"), ("closed", "Закрито (підтверджено)")]
    contact = models.ForeignKey("crm.Contact", null=True, blank=True, on_delete=models.PROTECT, related_name="object_acts")
    title = models.CharField(max_length=200)
    number = models.CharField(max_length=40, blank=True, default="")
    act_date = models.DateField()
    amount_total = models.DecimalField(max_digits=14, decimal_places=2)
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="object_acts")
    status = models.CharField(max_length=8, choices=STATUS, default="draft")
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="+")
    commission_pct_applied = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    payroll_period = models.CharField(max_length=7, blank=True, default="")
    note = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-act_date", "-id"]


class PayrollRun(models.Model):
    """Відомість місяця на людину — «знімок», як «Знімок дня». Затверджений місяць не змінюється,
    навіть якщо потім поміняти ставки: CRM лише покаже «зараз вийшло б …»."""
    STATUS = [("approved", "Затверджено"), ("reopened", "Перевідкрито")]
    period = models.CharField(max_length=7, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payroll_runs")
    scheme = models.ForeignKey(PayScheme, null=True, blank=True, on_delete=models.SET_NULL, related_name="runs")
    version = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=10, choices=STATUS, default="approved")
    lines = models.JSONField(default=list, blank=True)
    inputs = models.JSONField(default=dict, blank=True)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    company_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    note = models.CharField(max_length=255, blank=True, default="")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    approved_at = models.DateTimeField(default=timezone.now)
    reopened_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reopened_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-period", "user_id", "-version"]
        unique_together = [("period", "user", "version")]


class PayrollPayout(models.Model):
    """Звʼязок відомості з фактичною виплатою в журналі. Гроші не переносимо і не створюємо — лише привʼязка."""
    run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name="payouts")
    transaction = models.ForeignKey("finance.Transaction", on_delete=models.PROTECT, related_name="payroll_payouts")
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    linked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    linked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("run", "transaction")]
