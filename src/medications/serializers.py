from decimal import Decimal
from typing import ClassVar

from rest_framework import serializers

from .models import AdministrationRoute, MedicationCatalogItem, Prescription


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


class PrescriptionSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    medication_name = serializers.CharField(source="medication.name", read_only=True)
    medication_unit = serializers.CharField(source="medication.unit", read_only=True)
    prescribed_by_name = serializers.CharField(
        source="prescribed_by.full_name", read_only=True
    )
    administered_by_name = serializers.CharField(
        source="administered_by.full_name", read_only=True, default=None
    )

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
            "scheduled_time",
            "status",
            "administered_by",
            "administered_by_name",
            "administered_at",
            "administration_notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


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
    scheduled_time = serializers.TimeField()


class PrescriptionAdministerSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class PrescriptionCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")
