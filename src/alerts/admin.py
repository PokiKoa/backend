from typing import ClassVar

from django.contrib import admin

from .models import Alert, AlertThresholdConfig


@admin.register(AlertThresholdConfig)
class AlertThresholdConfigAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = [
        "id",
        "patient",
        "heart_rate_critical_low",
        "heart_rate_warning_low",
        "heart_rate_warning_high",
        "heart_rate_critical_high",
        "spo2_critical_low",
        "spo2_warning_low",
        "temp_critical_low",
        "temp_critical_high",
        "updated_at",
    ]


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = [
        "id",
        "crib",
        "patient",
        "alert_type",
        "severity",
        "status",
        "occurrence_count",
        "triggered_at",
        "acknowledged_by",
        "resolved_by",
        "resolution_reason",
    ]
    list_filter: ClassVar[list[str]] = [
        "status",
        "severity",
        "alert_type",
        "resolution_reason",
    ]
    search_fields: ClassVar[list[str]] = [
        "message",
        "crib__code",
        "patient__full_name",
    ]
