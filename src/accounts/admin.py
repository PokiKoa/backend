from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("id",)
    list_display = ("id", "email", "full_name", "role", "shift", "is_active", "is_two_factor_enabled")
    list_filter = ("role", "shift", "is_active", "is_two_factor_enabled")
    search_fields = ("email", "full_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Información Personal", {"fields": ("full_name", "role", "shift")}),
        (
            "Seguridad y Acceso",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "failed_login_attempts",
                    "locked_until",
                    "is_two_factor_enabled",
                )
            },
        ),
        ("Fechas", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    readonly_fields = ("created_at", "updated_at", "last_login")
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "full_name", "role", "shift", "password1", "password2", "is_active"),
            },
        ),
    )
