from django.contrib import admin

from .models import Crib


@admin.register(Crib)
class CribAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "name", "location", "status", "is_device_active", "last_telemetry_at")
    list_filter = ("status", "is_device_active")
    search_fields = ("code", "name", "location")
    readonly_fields = ("api_key_prefix", "api_key_hash", "last_telemetry_at", "created_at", "updated_at")
