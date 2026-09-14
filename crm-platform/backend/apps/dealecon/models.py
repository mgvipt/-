"""Економіка угоди (14.09.2026).

Окрема таблиця «один рядок на угоду» — НЕ поля в Deal і НЕ в np_data:
- у np_data вже були інциденти затирання;
- потрібні версія формули і «замок» закритого місяця (ЗП виплачена — цифри не пливуть);
- швидкі суми для ЗП, P&L і точки беззбитковості.
Формула — лише у services.compute(). Тут тільки зберігання.
"""
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import models

FORMULA_VERSION = 1


def default_auto_from():
    """Дата запуску економіки угоди (функція, а не константа — без попередження fields.W161 у кожній команді)."""
    return date(2026, 9, 14)


class DealEconomics(models.Model):
    deal = models.OneToOneField("crm.Deal", on_delete=models.CASCADE, primary_key=True,
                                related_name="dealecon_row")
    revenue = models.DecimalField("Виручка", max_digits=14, decimal_places=2, default=0)
    cogs = models.DecimalField("Собівартість товару", max_digits=14, decimal_places=2, default=0)
    delivery = models.DecimalField("Доставка НП за наш рахунок", max_digits=14, decimal_places=2, default=0)
    commission = models.DecimalField("Комісія оплати", max_digits=14, decimal_places=2, default=0)
    packaging = models.DecimalField("Пакування (робота + матеріали)", max_digits=14, decimal_places=2, default=0)
    master_works = models.DecimalField("Роботи майстра (+ транспорт)", max_digits=14, decimal_places=2, default=0)
    returns = models.DecimalField("Повернення", max_digits=14, decimal_places=2, default=0)
    margin = models.DecimalField("Маржа", max_digits=14, decimal_places=2, default=0)
    margin_pct = models.DecimalField("Маржа, %", max_digits=7, decimal_places=2, default=0)
    sources = models.JSONField(default=dict, blank=True,
                               help_text="По кожному компоненту: kind=fact/estimate/mixed/none + звідки взято")
    flags = models.JSONField(default=list, blank=True, help_text="Що перевірити (аномалії комісії, НП без вартості…)")
    is_estimate = models.BooleanField(default=False, help_text="Є хоч один ненульовий компонент-оцінка")
    computed_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveSmallIntegerField(default=FORMULA_VERSION, help_text="Версія формули, якою пораховано")
    locked = models.BooleanField(default=False, db_index=True,
                                 help_text="Закритий місяць: автоматичний перерахунок рядок НЕ змінює")

    class Meta:
        verbose_name = "Економіка угоди"
        verbose_name_plural = "Економіка угод"

    def __str__(self):
        return "Економіка #%s: маржа %s (%s%%)" % (self.deal_id, self.margin, self.margin_pct)


class DealEconSettings(models.Model):
    """Норми й ставки для ОЦІНОК (коли факту ще немає). Один рядок pk=1; без рядка — дефолти з коду."""
    pack_material_per_shipment = models.DecimalField(
        "Матеріали пакування, ₴ за відправлення", max_digits=8, decimal_places=2, default=Decimal("22"),
        help_text="Коробки/стрейч/скотч: 26 221 ₴ за січень–червень ÷ 6 міс ÷ ≈200 відправлень = ≈22 ₴")
    liqpay_rate_pct = models.DecimalField("LiqPay, %", max_digits=5, decimal_places=2, default=Decimal("1.30"))
    liqpay_rate_old_pct = models.DecimalField("LiqPay до дати зміни, %", max_digits=5, decimal_places=2,
                                              default=Decimal("1.50"))
    liqpay_rate_change_date = models.DateField("Дата зміни ставки LiqPay", default=date(2026, 7, 14))
    novapay_rate_pct = models.DecimalField("НоваПей, %", max_digits=5, decimal_places=2, default=Decimal("1.30"))
    fee_check_min_pct = models.DecimalField("Факт комісії нижче — перевірити, %", max_digits=5, decimal_places=2,
                                            default=Decimal("1.10"))
    fee_check_max_pct = models.DecimalField("Факт комісії вище — перевірити, %", max_digits=5, decimal_places=2,
                                            default=Decimal("3.00"))
    auto_from = models.DateField("Авто-рядки для угод, створених з", default=default_auto_from,
                                 help_text="Старіші угоди отримують рядок лише командою recompute_deal_economics")
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")

    class Meta:
        verbose_name = "Економіка угоди: норми"
        verbose_name_plural = "Економіка угоди: норми"

    def __str__(self):
        return "Норми економіки угоди"
