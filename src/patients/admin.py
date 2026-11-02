from typing import ClassVar

from django.contrib import admin

from .models import CarePlan, ClinicalObservation, Patient, WeightRecord


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = [
        "medical_record_number",
        "full_name",
        "sex",
        "gestational_age_weeks",
        "current_weight_g",
        "status",
        "crib",
        "attending_physician",
        "admitted_at",
    ]
    list_filter: ClassVar[list[str]] = ["status", "sex", "discharge_outcome"]
    search_fields: ClassVar[list[str]] = ["medical_record_number", "full_name"]


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
