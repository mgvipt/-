from django.contrib import admin
from .models import Warehouse, Product, StockDocument, StockMovement


class MovementInline(admin.TabularInline):
    model = StockMovement
    extra = 0


@admin.register(StockDocument)
class StockDocumentAdmin(admin.ModelAdmin):
    list_display = ("__str__", "kind", "warehouse", "created_at")
    list_filter = ("kind", "warehouse")
    inlines = [MovementInline]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "price", "cost", "unit", "is_active")
    search_fields = ("name", "sku")


admin.site.register(Warehouse)
