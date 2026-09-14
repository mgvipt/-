"""Партнерська програма (14.09.2026, рішення Олега).

Рівні (Старт → Партнер → Золото → Дилер) налаштовуються; статус клієнта ТІЛЬКИ підвищується.
Знижки задаються в номенклатурі цього застосунку: на категорію (масово) і на товар (виняток).
Правило ATM: підказка = частка маржі товару; після знижки лишається ≥ 15 п.п. маржі від роздрібної ціни.
Нижче мінімуму — лише виняток на товар з правом partners.below_min і причиною.

Нічого не змінює в існуючих таблицях (Product, Contact, DealItem): лише власні таблиці partners_*.
Автоматична знижка в угодах — крок 5, ВИМКНЕНА (PartnerSettings.auto_apply=False, через API не вмикається).
"""
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

TURNOVER_FROM = date(2026, 5, 5)  # з цієї дати оплати привʼязані до угод


class PartnerLevel(models.Model):
    """Рівень партнера. Порядок (order) = старшинство: вищий order — вищий рівень."""
    name = models.CharField(max_length=40)
    order = models.PositiveSmallIntegerField(unique=True)
    threshold_uah = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                        help_text="Поріг оплаченого обороту, ₴. Старт = 0")
    margin_share = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("0"),
                                       help_text="Частка маржі для ПІДКАЗКИ знижки за правилом ATM (0.25 = 25% маржі)")
    color = models.CharField(max_length=9, default="#be185d")
    is_active = models.BooleanField(default=True, help_text="Вимкнений рівень не присвоюється (видаляти не можна)")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order"]
        verbose_name = "Рівень партнера"

    def __str__(self):
        return self.name


class PartnerSettings(models.Model):
    """Налаштування програми (один рядок, id=1). Створюється при першому зверненні (get)."""
    min_margin_pp = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("15"),
                                        help_text="Скільки п.п. маржі (від роздрібної ціни) має лишитись після знижки")
    round_step = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("5"),
                                     help_text="Підказку округлюємо ВНИЗ до цього кроку, %")
    turnover_from = models.DateField(default=TURNOVER_FROM, help_text="Оборот рахуємо з цієї дати")
    exclude_funnel_ids = models.JSONField(default=list, blank=True, help_text="Воронки, оплати яких не йдуть в оборот (тести)")
    exclude_in_category_ids = models.JSONField(default=list, blank=True,
                                               help_text="Категорії надходжень, що НЕ виручка (повернення від постачальника тощо)")
    refund_category_ids = models.JSONField(default=list, blank=True,
                                           help_text="Категорії витрат-повернень клієнту — віднімаються з обороту")
    no_discount_category_ids = models.JSONField(default=list, blank=True,
                                                help_text="Категорії без партнерської знижки взагалі (тест-набори)")
    start_fixed = models.JSONField(default=dict, blank=True,
                                   help_text="Затверджені Олегом знижки рівня «Старт» на кореневі категорії {category_id: %}")
    auto_raise = models.BooleanField(default=True, help_text="Підвищувати рівень одразу після оплати")
    auto_apply = models.BooleanField(default=False, help_text="Крок 5 (пізніше): автознижка в угодах. ВИМКНЕНО")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Налаштування партнерської програми"

    @classmethod
    def get(cls):
        obj = cls.objects.filter(pk=1).first()
        if obj:
            return obj
        return cls.objects.get_or_create(pk=1, defaults=default_settings())[0]


def default_settings():
    """Значення за замовчуванням — за назвами в базі (id не хардкодимо)."""
    from apps.crm.models import Funnel
    from apps.finance.models import Category
    from apps.warehouse.models import ProductCategory
    funnels = list(Funnel.objects.filter(name__icontains="Техническая").values_list("id", flat=True))
    exclude_in = list(Category.objects.filter(
        Q(name__istartswith="Возврат от поставщика") | Q(name__istartswith="Возврат денег")).values_list("id", flat=True))
    refunds = list(Category.objects.filter(
        Q(name__istartswith="Возврат товара") | Q(name__istartswith="Возврат денег")).values_list("id", flat=True))
    no_disc = list(ProductCategory.objects.filter(name__icontains="Тестові набори").values_list("id", flat=True))
    start = {}
    for prefix, pct in (("1.3.1", 15), ("1.2.", 10), ("1.6.", 10)):
        cat = ProductCategory.objects.filter(parent__isnull=True, name__startswith=prefix).order_by("id").first()
        if cat:
            start[str(cat.id)] = pct
    return {"exclude_funnel_ids": funnels, "exclude_in_category_ids": exclude_in, "refund_category_ids": refunds,
            "no_discount_category_ids": no_disc, "start_fixed": start}


class PartnerDiscountRule(models.Model):
    """Знижка рівня на КАТЕГОРІЮ (діє на всі товари папки й підпапок) або на ТОВАР (виняток)."""
    level = models.ForeignKey(PartnerLevel, on_delete=models.CASCADE, related_name="rules")
    category = models.ForeignKey("warehouse.ProductCategory", null=True, blank=True, on_delete=models.CASCADE,
                                 related_name="+")
    product = models.ForeignKey("warehouse.Product", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    excluded = models.BooleanField(default=False, help_text="Товар без партнерської знижки (жорсткий 0)")
    suggested_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,
                                        help_text="Що пропонувало правило ATM у момент збереження")
    below_min_reason = models.CharField(max_length=200, blank=True, default="",
                                        help_text="Виняток товару нижче мінімальної маржі: причина (право partners.below_min)")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Партнерська знижка"
        constraints = [
            models.CheckConstraint(check=(Q(category__isnull=False, product__isnull=True)
                                          | Q(category__isnull=True, product__isnull=False)),
                                   name="partners_rule_one_target"),
            models.UniqueConstraint(fields=["level", "category"], condition=Q(product__isnull=True),
                                    name="partners_rule_uniq_cat"),
            models.UniqueConstraint(fields=["level", "product"], condition=Q(category__isnull=True),
                                    name="partners_rule_uniq_prod"),
            models.CheckConstraint(check=Q(pct__gte=0, pct__lte=100), name="partners_rule_pct_range"),
        ]


class PartnerRuleLog(models.Model):
    """Історія змін знижок: хто, коли, було → стало (для відкату)."""
    level_id_ref = models.IntegerField(null=True, blank=True)
    level_name = models.CharField(max_length=40, blank=True, default="")
    category_id_ref = models.IntegerField(null=True, blank=True)
    product_id_ref = models.IntegerField(null=True, blank=True)
    target_name = models.CharField(max_length=255, blank=True, default="")
    old_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    new_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    old_excluded = models.BooleanField(null=True, blank=True)
    new_excluded = models.BooleanField(null=True, blank=True)
    source = models.CharField(max_length=16, default="manual", help_text="manual / atm / seed")
    note = models.CharField(max_length=200, blank=True, default="")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class PartnerStatus(models.Model):
    """Статус клієнта в програмі. Рівень лише зростає; зняття галочки рівень НЕ стирає."""
    contact = models.OneToOneField("crm.Contact", on_delete=models.CASCADE, related_name="partner_status")
    level = models.ForeignKey(PartnerLevel, on_delete=models.PROTECT, related_name="statuses")
    is_active = models.BooleanField(default=True, help_text="Галочка «Партнер» у картці клієнта")
    since = models.DateField(default=date.today)
    level_at = models.DateTimeField(null=True, blank=True)
    turnover_uah = models.DecimalField(max_digits=14, decimal_places=2, default=0, help_text="Кеш обороту")
    turnover_at = models.DateTimeField(null=True, blank=True)
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Статус партнера"


class PartnerStatusHistory(models.Model):
    REASONS = [("assign", "Відмічено партнером"), ("auto_raise", "Автопідвищення за оборотом"),
               ("manual", "Підвищено вручну"), ("unmark", "Галочку знято"), ("remark", "Галочку повернуто")]
    contact = models.ForeignKey("crm.Contact", on_delete=models.CASCADE, related_name="partner_history")
    old_level = models.ForeignKey(PartnerLevel, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    new_level = models.ForeignKey(PartnerLevel, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    reason = models.CharField(max_length=16, choices=REASONS)
    turnover_uah = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    note = models.CharField(max_length=200, blank=True, default="")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
