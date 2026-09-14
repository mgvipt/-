from django.contrib import admin

from .models import DealEconomics, DealEconSettings


@admin.register(DealEconomics)
class DealEconomicsAdmin(admin.ModelAdmin):
    list_display = ("deal_id", "revenue", "margin", "margin_pct", "is_estimate", "locked", "computed_at")
    list_filter = ("locked", "is_estimate")
    search_fields = ("deal__id",)
    readonly_fields = ("deal", "revenue", "cogs", "delivery", "commission", "packaging", "master_works", "returns",
                       "margin", "margin_pct", "sources", "flags", "is_estimate", "computed_at", "version")


@admin.register(DealEconSettings)
class DealEconSettingsAdmin(admin.ModelAdmin):
    list_display = ("pack_material_per_shipment", "liqpay_rate_pct", "novapay_rate_pct", "updated_at")
