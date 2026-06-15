from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Role, Department

admin.site.register(Role)
admin.site.register(Department)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("CRM", {"fields": ("role", "department", "phone", "theme")}),
    )
