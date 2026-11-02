from typing import ClassVar

from django.contrib import admin
from django.utils.html import format_html

from .models import CarePlan, ClinicalObservation, Patient, PatientStatus, WeightRecord


class WeightRecordInline(admin.TabularInline):
    model = WeightRecord
    extra = 0
    fields = ("weight_g", "recorded_by", "recorded_at")
    readonly_fields = ("recorded_at",)


class CarePlanInline(admin.TabularInline):
    model = CarePlan
    extra = 0
    fields = ("care_area", "intervention", "frequency", "status", "created_by")


class ClinicalObservationInline(admin.TabularInline):
    model = ClinicalObservation
    extra = 0
    fields = ("category", "content", "author", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = [
        "medical_record_number",
        "full_name",
        "sex",
        "gestational_age_weeks",
        "current_weight_g",
        "status_badge",
        "crib",
        "attending_physician",
        "admitted_at",
    ]
    list_filter: ClassVar[list[str]] = ["status", "sex", "discharge_outcome"]
    search_fields: ClassVar[list[str]] = ["medical_record_number", "full_name"]
    inlines: ClassVar[list] = [
        CarePlanInline,
        WeightRecordInline,
        ClinicalObservationInline,
    ]
    fieldsets = (
        (
            "Identificación y Datos Neonatales",
            {
                "fields": (
                    "medical_record_number",
                    "full_name",
                    "sex",
                    "birth_date",
                    "gestational_age_weeks",
                    "birth_weight_g",
                    "current_weight_g",
                )
            },
        ),
        (
            "Asignación Clínica en Unidad",
            {
                "fields": (
                    "status",
                    "crib",
                    "attending_physician",
                    "diagnosis",
                    "admitted_at",
                )
            },
        ),
        (
            "Datos de Egreso (Baja Lógica)",
            {
                "classes": ("collapse",),
                "fields": (
                    "discharged_at",
                    "discharge_outcome",
                    "discharge_cause",
                    "discharge_notes",
                    "discharged_by",
                ),
            },
        ),
    )

    @admin.display(description="Estado")
    def status_badge(self, obj: Patient) -> str:
        colors = {
            PatientStatus.ACTIVE: ("#d1fae5", "#065f46"),
            PatientStatus.DISCHARGED: ("#e0f2fe", "#075985"),
            PatientStatus.TRANSFERRED: ("#fef3c7", "#92400e"),
            PatientStatus.DECEASED: ("#fee2e2", "#991b1b"),
        }
        bg, fg = colors.get(obj.status, ("#f1f5f9", "#334155"))
        return format_html(
            '<span style="background:{};color:{};padding:3px 9px;border-radius:999px;font-weight:700;font-size:0.76rem;">{}</span>',
            bg,
            fg,
            obj.get_status_display(),
        )


@admin.register(WeightRecord)
class WeightRecordAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = [
        "patient",
        "weight_g",
        "recorded_by",
        "recorded_at",
    ]
    list_filter: ClassVar[list[str]] = ["recorded_at"]


@admin.register(CarePlan)
class CarePlanAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = [
        "patient",
        "care_area",
        "intervention",
        "frequency",
        "status",
        "created_by",
        "created_at",
    ]
    list_filter: ClassVar[list[str]] = ["status", "care_area"]


@admin.register(ClinicalObservation)
class ClinicalObservationAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = [
        "patient",
        "category",
        "author",
        "created_at",
    ]
    list_filter: ClassVar[list[str]] = ["category"]
