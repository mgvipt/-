from django.contrib import admin
from .models import Account, Category, Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("__str__", "direction", "amount", "account", "category", "deal", "created_at")
    list_filter = ("direction", "account", "category")


admin.site.register(Account)
admin.site.register(Category)
