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
    date = models.DateField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.direction}] {self.amount}"
