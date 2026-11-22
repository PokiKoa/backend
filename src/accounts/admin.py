from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import ShiftAssignment, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Configuración de la interfaz de administración para el modelo de usuarios del sistema.
    Define las columnas visibles, filtros de búsqueda y la agrupación de campos (fieldsets)
    para la gestión del personal clínico.
    """

    ordering = ("id",)
    list_display = (
        "id",
        "username",
        "full_name",
        "email",
        "role",
        "shift",
        "is_active",
        "is_two_factor_enabled",
    )
    list_filter = ("role", "shift", "is_active", "is_two_factor_enabled")
    search_fields = ("username", "full_name", "email")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Información Personal", {"fields": ("full_name", "email", "role", "shift")}),
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
                "fields": (
                    "username",
                    "full_name",
                    "email",
                    "role",
                    "shift",
                    "password1",
                    "password2",
                    "is_active",
                ),
            },
        ),
    )


@admin.register(ShiftAssignment)
class ShiftAssignmentAdmin(admin.ModelAdmin):
    """
    Configuración de la interfaz de administración para la asignación de turnos.
    Permite visualizar y filtrar fácilmente qué usuario está a cargo de qué cuna
    en una fecha determinada.
    """

    list_display = ("date", "shift", "user", "crib", "created_by")
    list_filter = ("shift", "date")
    search_fields = ("user__full_name", "crib__code")
