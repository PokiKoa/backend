from decimal import Decimal
from typing import ClassVar

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from . import schedule
from .models import (
    MAX_FREQUENCY_HOURS,
    AdministrationRoute,
    MedicationAdministration,
    MedicationCatalogItem,
    Prescription,
)


class MedicationCatalogItemSerializer(serializers.ModelSerializer):
    is_low_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = MedicationCatalogItem
        fields: ClassVar[list[str]] = [
            "id",
            "name",
            "active_ingredient",
            "concentration_mg",
            "unit",
            "stock",
            "min_stock_alert",
            "is_low_stock",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class MedicationCatalogCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    active_ingredient = serializers.CharField(max_length=150)
    concentration_mg = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )
    unit = serializers.CharField(max_length=30, required=False, default="ampolla")
    stock = serializers.IntegerField(min_value=0, required=False, default=0)
    min_stock_alert = serializers.IntegerField(min_value=0, required=False, default=5)
    is_active = serializers.BooleanField(required=False, default=True)


class MedicationCatalogUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150, required=False)
    active_ingredient = serializers.CharField(max_length=150, required=False)
    concentration_mg = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=False,
    )
    unit = serializers.CharField(max_length=30, required=False)
    stock = serializers.IntegerField(min_value=0, required=False)
    min_stock_alert = serializers.IntegerField(min_value=0, required=False)
    is_active = serializers.BooleanField(required=False)


class MedicationAdministrationSerializer(serializers.ModelSerializer):
    administered_by_name = serializers.CharField(
        source="administered_by.full_name", read_only=True
    )

    class Meta:
        model = MedicationAdministration
        fields: ClassVar[list[str]] = [
            "id",
            "prescription",
            "scheduled_for",
            "administered_at",
            "administered_by",
            "administered_by_name",
            "units_deducted",
            "notes",
        ]
        read_only_fields = fields


class PrescriptionSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    medication_name = serializers.CharField(source="medication.name", read_only=True)
    medication_unit = serializers.CharField(source="medication.unit", read_only=True)
    prescribed_by_name = serializers.CharField(
        source="prescribed_by.full_name", read_only=True
    )
    next_dose_at = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()
    last_administered_slot = serializers.SerializerMethodField()
    administrations_count = serializers.SerializerMethodField()

    class Meta:
        model = Prescription
        fields: ClassVar[list[str]] = [
            "id",
            "patient",
            "patient_name",
            "medication",
            "medication_name",
            "medication_unit",
            "prescribed_by",
            "prescribed_by_name",
            "dose",
            "units_per_administration",
            "route",
            "starts_at",
            "frequency_hours",
            "ends_at",
            "status",
            "next_dose_at",
            "is_overdue",
            "last_administered_slot",
            "administrations_count",
            "cancelled_at",
            "cancellation_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def _state(self, obj: Prescription) -> schedule.ScheduleState:
        cache = self.context.setdefault("_schedule_states", {})
        if obj.pk not in cache:
            now = self.context.setdefault("_now", timezone.now())
            cache[obj.pk] = schedule.schedule_state(obj, now)
        return cache[obj.pk]

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_next_dose_at(self, obj: Prescription):
        value = self._state(obj).next_dose_at
        return serializers.DateTimeField().to_representation(value) if value else None

    @extend_schema_field(serializers.BooleanField())
    def get_is_overdue(self, obj: Prescription) -> bool:
        return self._state(obj).is_overdue

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_last_administered_slot(self, obj: Prescription):
        value = self._state(obj).last_administered_slot
        return serializers.DateTimeField().to_representation(value) if value else None

    @extend_schema_field(serializers.IntegerField())
    def get_administrations_count(self, obj: Prescription) -> int:
        return self._state(obj).administrations_count


class PrescriptionCreateSerializer(serializers.Serializer):
    patient_id = serializers.IntegerField(min_value=1)
    medication_id = serializers.IntegerField(min_value=1)
    dose = serializers.CharField(max_length=100)
    units_per_administration = serializers.IntegerField(
        min_value=1, required=False, default=1
    )
    route = serializers.ChoiceField(
        choices=AdministrationRoute.choices,
        default=AdministrationRoute.IV,
    )
    starts_at = serializers.DateTimeField()
    frequency_hours = serializers.IntegerField(
        min_value=1, max_value=MAX_FREQUENCY_HOURS, required=False, allow_null=True, default=None
    )
    ends_at = serializers.DateTimeField(required=False, allow_null=True, default=None)


class PrescriptionAdministerSerializer(serializers.Serializer):
    scheduled_for = serializers.DateTimeField(required=False, allow_null=True, default=None)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class PrescriptionCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")
