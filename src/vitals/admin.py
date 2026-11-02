from typing import ClassVar

from django.contrib import admin

from .models import VitalSignReading


@admin.register(VitalSignReading)
class VitalSignReadingAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = [
        "id",
        "crib",
        "patient",
        "heart_rate",
        "spo2",
        "temperature",
        "sleep_state",
        "cannula_connected",
        "iv_line_active",
        "recorded_at",
    ]
    list_filter: ClassVar[list[str]] = [
        "sleep_state",
        "cannula_connected",
        "iv_line_active",
    ]
    search_fields: ClassVar[list[str]] = [
        "crib__code",
        "patient__full_name",
        "patient__medical_record_number",
    ]
