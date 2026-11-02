from decimal import Decimal
from typing import ClassVar

from rest_framework import serializers

from .models import (
    CarePlan,
    CarePlanStatus,
    ClinicalObservation,
    DischargeCause,
    DischargeOutcome,
    ObservationCategory,
    Patient,
    PatientSex,
    WeightRecord,
)


class PatientSerializer(serializers.ModelSerializer):
    age_days = serializers.IntegerField(read_only=True)
    attending_physician_name = serializers.CharField(
        source="attending_physician.full_name", read_only=True, default=None
    )
    crib_code = serializers.CharField(
        source="crib.code", read_only=True, default=None
    )

    class Meta:
        model = Patient
        fields: ClassVar[list[str]] = [
            "id",
            "medical_record_number",
            "full_name",
            "sex",
            "birth_date",
            "age_days",
            "gestational_age_weeks",
            "birth_weight_g",
            "current_weight_g",
            "admitted_at",
            "diagnosis",
            "attending_physician",
            "attending_physician_name",
            "crib",
            "crib_code",
            "status",
            "discharged_at",
            "discharge_outcome",
            "discharge_cause",
            "discharge_notes",
            "discharged_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PatientCreateSerializer(serializers.Serializer):
    medical_record_number = serializers.CharField(max_length=30)
    full_name = serializers.CharField(max_length=200)
    sex = serializers.ChoiceField(choices=PatientSex.choices)
    birth_date = serializers.DateField()
    gestational_age_weeks = serializers.DecimalField(
        max_digits=4,
        decimal_places=1,
        min_value=Decimal("20.0"),
        max_value=Decimal("45.0"),
    )
    birth_weight_g = serializers.IntegerField(min_value=200, max_value=8000)
    current_weight_g = serializers.IntegerField(
        min_value=200, max_value=10000, required=False, allow_null=True, default=None
    )
    diagnosis = serializers.CharField(required=False, allow_blank=True, default="")
    attending_physician_id = serializers.IntegerField(
        required=False, allow_null=True, default=None
    )
    crib_id = serializers.IntegerField(required=False, allow_null=True, default=None)


class PatientUpdateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=200, required=False)
    sex = serializers.ChoiceField(choices=PatientSex.choices, required=False)
    birth_date = serializers.DateField(required=False)
    gestational_age_weeks = serializers.DecimalField(
        max_digits=4,
        decimal_places=1,
        min_value=Decimal("20.0"),
        max_value=Decimal("45.0"),
        required=False,
    )
    current_weight_g = serializers.IntegerField(
        min_value=200, max_value=10000, required=False
    )
    diagnosis = serializers.CharField(required=False, allow_blank=True)
    attending_physician_id = serializers.IntegerField(
        required=False, allow_null=True
    )
    crib_id = serializers.IntegerField(required=False, allow_null=True)


class PatientDischargeSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=DischargeOutcome.choices)
    cause = serializers.ChoiceField(
        choices=DischargeCause.choices, required=False, allow_null=True, default=None
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class WeightRecordSerializer(serializers.ModelSerializer):
    recorded_by_name = serializers.CharField(
        source="recorded_by.full_name", read_only=True, default=None
    )

    class Meta:
        model = WeightRecord
        fields: ClassVar[list[str]] = [
            "id",
            "patient",
            "weight_g",
            "recorded_by",
            "recorded_by_name",
            "recorded_at",
        ]
        read_only_fields = fields


class WeightRecordCreateSerializer(serializers.Serializer):
    weight_g = serializers.IntegerField(min_value=200, max_value=10000)


class CarePlanSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    created_by_name = serializers.CharField(
        source="created_by.full_name", read_only=True
    )

    class Meta:
        model = CarePlan
        fields: ClassVar[list[str]] = [
            "id",
            "patient",
            "patient_name",
            "care_area",
            "intervention",
            "frequency",
            "status",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class CarePlanCreateSerializer(serializers.Serializer):
    patient_id = serializers.IntegerField(min_value=1)
    care_area = serializers.CharField(max_length=100)
    intervention = serializers.CharField(max_length=255)
    frequency = serializers.CharField(max_length=50)
    status = serializers.ChoiceField(
        choices=CarePlanStatus.choices, default=CarePlanStatus.ACTIVE
    )


class CarePlanUpdateSerializer(serializers.Serializer):
    care_area = serializers.CharField(max_length=100, required=False)
    intervention = serializers.CharField(max_length=255, required=False)
    frequency = serializers.CharField(max_length=50, required=False)
    status = serializers.ChoiceField(choices=CarePlanStatus.choices, required=False)


class ClinicalObservationSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    author_name = serializers.CharField(source="author.full_name", read_only=True)

    class Meta:
        model = ClinicalObservation
        fields: ClassVar[list[str]] = [
            "id",
            "patient",
            "patient_name",
            "author",
            "author_name",
            "category",
            "content",
            "created_at",
        ]
        read_only_fields = fields


class ClinicalObservationCreateSerializer(serializers.Serializer):
    patient_id = serializers.IntegerField(min_value=1)
    category = serializers.ChoiceField(
        choices=ObservationCategory.choices, default=ObservationCategory.GENERAL
    )
    content = serializers.CharField()
