from django.contrib import admin
from .models import Company, Contact, Funnel, Stage, Lead, Deal, Payment, MetaConversionEvent


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


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("__str__", "phone", "owner", "loyalty_tag")
    search_fields = ("first_name", "last_name", "phone", "email")
    list_filter = ("loyalty_tag",)
    filter_horizontal = ("shared_with",)  # админ выдаёт доступ менеджерам к клиенту


admin.site.register(Payment)


@admin.register(MetaConversionEvent)
class MetaConversionEventAdmin(admin.ModelAdmin):
    list_display = ("event_name", "source_type", "source_id", "status", "attempts", "occurred_at")
    list_filter = ("event_name", "source_type", "status")
    search_fields = ("event_id",)
    readonly_fields = (
        "event_id", "event_name", "source_type", "source_id", "contact", "lead", "deal",
        "payment", "stage", "occurred_at", "payload", "status", "attempts", "last_error",
        "sent_at", "created_at", "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
