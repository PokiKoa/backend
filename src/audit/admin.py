"""Configuración del panel de administración para los registros de auditoría forense."""

from typing import ClassVar

from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """
    Administración de solo lectura para los registros de auditoría (`AuditLog`),
    protegiendo la trazabilidad clínica y bloqueando cualquier alteración o borrado manual.
    """

    list_display: ClassVar[list[str]] = [
        "id",
        "timestamp",
        "action",
        "resource_type",
        "resource_id",
        "patient_id",
        "actor_user",
    ]
    list_filter: ClassVar[list[str]] = ["action", "resource_type"]
    readonly_fields: ClassVar[list[str]] = [
        "actor_user",
        "actor_device_code",
        "patient_id",
        "action",
        "resource_type",
        "resource_id",
        "changed_fields",
        "ip_address",
        "timestamp",
    ]

    def has_add_permission(self, request) -> bool:
        """Deniega el permiso para crear nuevos registros de auditoría manualmente desde el admin."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """Deniega el permiso para modificar registros de auditoría existentes."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """Deniega el permiso para eliminar registros de auditoría, garantizando inmutabilidad."""
        return False
