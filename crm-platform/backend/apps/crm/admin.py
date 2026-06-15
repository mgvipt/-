from django.contrib import admin
from .models import Company, Contact, Funnel, Stage, Lead, Deal, Payment


class StageInline(admin.TabularInline):
    model = Stage
    extra = 0


@admin.register(Funnel)
class FunnelAdmin(admin.ModelAdmin):
    list_display = ("name", "is_lead_funnel", "order")
    inlines = [StageInline]


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("title", "funnel", "stage", "source", "owner", "amount", "is_seen")
    list_filter = ("funnel", "stage", "source", "is_seen")


@admin.register(Deal)
class DealAdmin(admin.ModelAdmin):
    list_display = ("title", "funnel", "stage", "owner", "amount")
    list_filter = ("funnel", "stage", "source")


admin.site.register(Company)
admin.site.register(Contact)
admin.site.register(Payment)
