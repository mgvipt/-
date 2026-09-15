"""Повернення товару від клієнта (16.09.2026, дизайн погоджено Олегом).

Одне повернення = DealReturn + рядки DealReturnLine (з позицій угоди) + фото.
Товар: «як новий» → CRM сама робить прибуткову накладну (StockDocument kind="in");
«в брак» / «списати» → на полицю не повертається (реалізація його вже списала), лише втрата в економіці угоди.
Гроші: окремий крок, лише право deal.refund (бухгалтер або власник): повернути (операція в журналі),
«вже повернуто через LiqPay» (привʼязати наявну операцію) або зарахувати в наступне замовлення (аванс клієнта).
"""
from django.conf import settings
from django.db import models


class DealReturn(models.Model):
    REASONS = [("color", "Не підійшов колір"), ("damaged", "Пошкоджено"), ("wh_error", "Помилка складу"),
               ("mgr_error", "Помилка менеджера"), ("changed_mind", "Передумав")]
    PAYERS = [("client", "Клієнт"), ("us", "Ми")]
    MONEY = [("none", "Повертати нічого"), ("pending", "Очікує рішення бухгалтера"),
             ("refund", "Гроші повернуто клієнту"), ("liqpay", "Повернуто через LiqPay"),
             ("offset", "Зараховано в наступне замовлення")]

    deal = models.ForeignKey("crm.Deal", null=True, blank=True, on_delete=models.SET_NULL, related_name="returns")
    contact = models.ForeignKey("crm.Contact", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                help_text="Клієнт угоди на момент повернення")
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="+", help_text="Відповідальний за угоду на момент повернення (для звіту)")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    client_key = models.CharField(max_length=64, blank=True, default="",
                                  help_text="Ключ форми: повторне натискання «Зберегти» не створює друге повернення")
    reason = models.CharField("Причина", max_length=16, choices=REASONS)
    delivery_payer = models.CharField("Хто платить доставку повернення", max_length=8, choices=PAYERS, default="client")
    delivery_cost = models.DecimalField("Доставка повернення, ₴", max_digits=12, decimal_places=2, default=0)
    comment = models.TextField(blank=True, default="")
    amount = models.DecimalField("На скільки зменшилась сума угоди", max_digits=12, decimal_places=2, default=0)
    cost_back = models.DecimalField("Собівартість товару, що повернувся на склад", max_digits=12, decimal_places=2, default=0)
    cost_loss = models.DecimalField("Собівартість браку / списаного", max_digits=12, decimal_places=2, default=0)
    stock_note = models.CharField(max_length=255, blank=True, default="")
    receipt_doc = models.ForeignKey("warehouse.StockDocument", null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+", help_text="Прибуткова накладна товару «як новий»")
    error = models.ForeignKey("warehouse.WarehouseError", null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="+", help_text="«Помилка співробітника» (причина — помилка складу / менеджера)")
    money_status = models.CharField(max_length=8, choices=MONEY, default="none", db_index=True)
    money_due = models.DecimalField("Скільки треба вирішити бухгалтеру", max_digits=12, decimal_places=2, default=0)
    money_amount = models.DecimalField("Повернуто / зараховано", max_digits=12, decimal_places=2, default=0)
    refund_tx = models.OneToOneField("finance.Transaction", null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="deal_return", help_text="Операція «Повернення коштів» у журналі")
    money_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    money_at = models.DateTimeField(null=True, blank=True)
    money_comment = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["client_key"], condition=~models.Q(client_key=""), name="uniq_dealreturn_client_key"),
        ]

    def __str__(self):
        return "Повернення №%s (угода #%s)" % (self.pk, self.deal_id)


class DealReturnLine(models.Model):
    DESTINATIONS = [("stock", "На склад як новий"), ("defect", "В брак"), ("writeoff", "Списати")]

    ret = models.ForeignKey(DealReturn, on_delete=models.CASCADE, related_name="lines")
    deal_item_id = models.IntegerField(null=True, blank=True, help_text="Позиція угоди (при повному поверненні позицію видалено)")
    product = models.ForeignKey("warehouse.Product", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    name = models.CharField(max_length=255)
    unit = models.CharField(max_length=16, blank=True, default="")
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    sold_quantity = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Було в позиції до повернення")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount = models.DecimalField("На скільки зменшилась сума позиції", max_digits=12, decimal_places=2, default=0)
    unit_cost = models.DecimalField("Собівартість одиниці (знімок позиції)", max_digits=12, decimal_places=2, default=0)
    destination = models.CharField(max_length=10, choices=DESTINATIONS, default="stock")

    class Meta:
        ordering = ["id"]


class DealReturnPhoto(models.Model):
    """Фото повернення. warehouse_photos/ — постійний том контейнера (як WarehousePhoto)."""
    ret = models.ForeignKey(DealReturn, on_delete=models.CASCADE, related_name="photos")
    image = models.FileField(upload_to="warehouse_photos/returns/")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
