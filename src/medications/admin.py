from typing import ClassVar

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    MedicationAdministration,
    MedicationCatalogItem,
    Prescription,
    PrescriptionStatus,
)


@admin.register(MedicationCatalogItem)
class MedicationCatalogItemAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = [
        "name",
        "active_ingredient",
        "concentration_mg",
        "unit",
        "stock_badge",
        "min_stock_alert",
        "is_active",
        "updated_at",
    ]
    list_filter: ClassVar[list[str]] = ["is_active", "unit"]
    search_fields: ClassVar[list[str]] = ["name", "active_ingredient"]

    @admin.display(description="Stock Actual")
    def stock_badge(self, obj: MedicationCatalogItem) -> str:
        if obj.stock == 0:
            bg, fg, label = "#fee2e2", "#991b1b", f"{obj.stock} (AGOTADO)"
        elif obj.is_low_stock:
            bg, fg, label = "#fef3c7", "#92400e", f"{obj.stock} (Stock bajo)"
        else:
            bg, fg, label = "#d1fae5", "#065f46", f"{obj.stock} disponibles"
        return format_html(
            '<span style="background:{};color:{};padding:3px 9px;border-radius:0.5rem;font-weight:700;font-size:0.75rem;">{}</span>',
            bg,
            fg,
            label,
        )


class MedicationAdministrationInline(admin.TabularInline):
    model = MedicationAdministration
    extra = 0
    can_delete = False
    fields: ClassVar[list[str]] = [
        "scheduled_for",
        "administered_at",
        "administered_by",
        "units_deducted",
        "notes",
    ]
    readonly_fields = fields

    def has_add_permission(self, request, obj=None) -> bool:
        # Las dosis solo se registran por el servicio para descontar stock de forma atómica
        return False


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    inlines: ClassVar[list] = [MedicationAdministrationInline]
    list_display: ClassVar[list[str]] = [
        "id",
        "patient",
        "medication",
        "dose",
        "units_per_administration",
        "route",
        "starts_at",
        "frequency_hours",
        "ends_at",
        "status_badge",
        "prescribed_by",
    ]
    list_filter: ClassVar[list[str]] = ["status", "route"]
    search_fields: ClassVar[list[str]] = [
        "patient__full_name",
        "medication__name",
        "dose",
    ]

    @admin.display(description="Estado")
    def status_badge(self, obj: Prescription) -> str:
        colors = {
            PrescriptionStatus.ACTIVE: ("#fef3c7", "#92400e"),
            PrescriptionStatus.COMPLETED: ("#d1fae5", "#065f46"),
            PrescriptionStatus.CANCELLED: ("#f1f5f9", "#475569"),
        }
        bg, fg = colors.get(obj.status, ("#f1f5f9", "#334155"))
        return format_html(
            '<span style="background:{};color:{};padding:3px 9px;border-radius:0.5rem;font-weight:700;font-size:0.75rem;">{}</span>',
            bg,
            fg,
            obj.get_status_display(),
        )
