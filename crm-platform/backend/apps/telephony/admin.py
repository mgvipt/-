from django.contrib import admin
from .models import Call


@admin.register(Call)
class CallAdmin(admin.ModelAdmin):
    list_display = ("__str__", "direction", "manager", "duration", "created_at")
    list_filter = ("direction",)
