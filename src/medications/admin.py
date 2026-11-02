from typing import ClassVar

from django.contrib import admin

from .models import MedicationCatalogItem, Prescription


@admin.register(MedicationCatalogItem)
class MedicationCatalogItemAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = [
        "name",
        "active_ingredient",
        "concentration_mg",
        "unit",
        "stock",
        "min_stock_alert",
        "is_active",
        "updated_at",
    ]
    list_filter: ClassVar[list[str]] = ["is_active", "unit"]
    search_fields: ClassVar[list[str]] = ["name", "active_ingredient"]


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = [
        "id",
        "patient",
        "medication",
        "dose",
        "units_per_administration",
        "route",
        "scheduled_time",
        "status",
        "prescribed_by",
        "administered_by",
        "administered_at",
    ]
    list_filter: ClassVar[list[str]] = ["status", "route"]
    search_fields: ClassVar[list[str]] = [
        "patient__full_name",
        "medication__name",
        "dose",
    ]
