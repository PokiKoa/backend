from typing import ClassVar

from rest_framework import serializers

from .models import Crib, CribStatus


class CribSerializer(serializers.ModelSerializer):
    current_patient_id = serializers.IntegerField(
        source="current_patient.id", read_only=True, default=None, allow_null=True
    )
    current_patient_name = serializers.CharField(
        source="current_patient.full_name", read_only=True, default=None, allow_null=True
    )
    current_patient_mrn = serializers.CharField(
        source="current_patient.medical_record_number",
        read_only=True,
        default=None,
        allow_null=True,
    )

    class Meta:
        model = Crib
        fields: ClassVar[list[str]] = [
            "id",
            "code",
            "name",
            "location",
            "status",
            "api_key_prefix",
            "is_device_active",
            "last_telemetry_at",
            "current_patient_id",
            "current_patient_name",
            "current_patient_mrn",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class CribCreateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=20)
    name = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    location = serializers.CharField(
        max_length=100, required=False, allow_blank=True, default=""
    )
    status = serializers.ChoiceField(
        choices=CribStatus.choices, default=CribStatus.AVAILABLE
    )
    is_device_active = serializers.BooleanField(default=True)


class CribUpdateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=20, required=False)
    name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    location = serializers.CharField(max_length=100, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=CribStatus.choices, required=False)
    is_device_active = serializers.BooleanField(required=False)


class CribAssignPatientSerializer(serializers.Serializer):
    patient_id = serializers.IntegerField(min_value=1)


class CribSwapSerializer(serializers.Serializer):
    other_crib_id = serializers.IntegerField(min_value=1)
