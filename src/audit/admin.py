from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "timestamp",
        "action",
        "resource_type",
        "resource_id",
        "patient_id",
        "actor_user",
    )
    list_filter = ("action", "resource_type")
    readonly_fields = (
        "actor_user",
        "actor_device_code",
        "patient_id",
        "action",
        "resource_type",
        "resource_id",
        "changed_fields",
        "ip_address",
        "timestamp",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
