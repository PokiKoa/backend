from typing import ClassVar

from rest_framework import serializers

from .models import VitalSignReading
from .rules import (
    HEART_RATE_MAX,
    HEART_RATE_MIN,
    SPO2_MAX,
    SPO2_MIN,
    TEMPERATURE_MAX,
    TEMPERATURE_MIN,
    SleepState,
)


class VitalSignReadingSerializer(serializers.ModelSerializer):
    crib_code = serializers.CharField(source="crib.code", read_only=True)
    patient_name = serializers.CharField(
        source="patient.full_name", read_only=True, default=None
    )

    class Meta:
        model = VitalSignReading
        fields: ClassVar[list[str]] = [
            "id",
            "crib",
            "crib_code",
            "patient",
            "patient_name",
            "heart_rate",
            "spo2",
            "temperature",
            "sleep_state",
            "cannula_connected",
            "iv_line_active",
            "recorded_at",
            "ingested_at",
        ]
        read_only_fields = fields


class TelemetryIngestSerializer(serializers.Serializer):
    heart_rate = serializers.IntegerField(
        min_value=HEART_RATE_MIN, max_value=HEART_RATE_MAX
    )
    spo2 = serializers.IntegerField(min_value=SPO2_MIN, max_value=SPO2_MAX)
    temperature = serializers.DecimalField(
        max_digits=4,
        decimal_places=1,
        min_value=TEMPERATURE_MIN,
        max_value=TEMPERATURE_MAX,
    )
    sleep_state = serializers.ChoiceField(choices=SleepState.choices)
    cannula_connected = serializers.BooleanField()
    iv_line_active = serializers.BooleanField()
    recorded_at = serializers.DateTimeField(required=False, allow_null=True)
