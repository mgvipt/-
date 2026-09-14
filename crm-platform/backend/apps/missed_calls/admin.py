from django.contrib import admin

from .models import MissedCallItem, MissedCallSettings


@admin.register(MissedCallItem)
class MissedCallItemAdmin(admin.ModelAdmin):
    list_display = ("id", "number", "line", "status", "assignee", "first_missed_at", "reaction_work_min", "close_reason")
    list_filter = ("status", "close_reason", "assign_reason", "backfilled")
    search_fields = ("number", "phone9")
    raw_id_fields = ("contact", "deal", "first_call", "closing_call", "task", "assignee", "closed_by")


admin.site.register(MissedCallSettings)
