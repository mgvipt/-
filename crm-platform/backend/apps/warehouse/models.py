from django.db import models
from django.db.models import Sum
from django.conf import settings


class Warehouse(models.Model):
    name = models.CharField(max_length=120)
    is_default = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=255)
    sku = models.CharField("Артикул", max_length=64, blank=True, db_index=True)
    unit = models.CharField("Ед. изм.", max_length=16, default="шт")
    price = models.DecimalField("Цена продажи", max_digits=12, decimal_places=2, default=0)
    cost = models.DecimalField("Себестоимость", max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def stock(self, warehouse=None):
        """Текущий остаток = сумма движений (приход +, расход -)."""
        qs = self.movements.all()
        if warehouse:
            qs = qs.filter(document__warehouse=warehouse)
        return qs.aggregate(s=Sum("quantity"))["s"] or 0


class StockDocument(models.Model):
    """Складской документ: приход / расход / инвентаризация."""
    KINDS = [("in", "Приход"), ("out", "Расход"), ("inv", "Инвентаризация")]
    kind = models.CharField(max_length=4, choices=KINDS)
    number = models.CharField(max_length=40, blank=True)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="documents")
    comment = models.CharField(max_length=255, blank=True)
    deal = models.ForeignKey("crm.Deal", null=True, blank=True, on_delete=models.SET_NULL, related_name="stock_documents")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

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
