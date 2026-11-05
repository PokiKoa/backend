"""Serializers de alertas y umbrales."""

from typing import ClassVar

from rest_framework import serializers

from vitals.rules import (
    HEART_RATE_MAX,
    HEART_RATE_MIN,
    SPO2_MAX,
    SPO2_MIN,
    TEMPERATURE_MAX,
    TEMPERATURE_MIN,
)

from .models import Alert, AlertThresholdConfig


class AlertSerializer(serializers.ModelSerializer):
    """Representación de una alerta con su cuna, paciente y trazabilidad de reconocimiento y resolución."""

    crib_code = serializers.CharField(source="crib.code", read_only=True)
    patient_name = serializers.CharField(source="patient.full_name", read_only=True, default=None)
    acknowledged_by_name = serializers.CharField(
        source="acknowledged_by.full_name", read_only=True, default=None
    )
    resolved_by_name = serializers.CharField(
        source="resolved_by.full_name", read_only=True, default=None
    )

    class Meta:
        model = Alert
        fields: ClassVar[list[str]] = [
            "id",
            "crib",
            "crib_code",
            "patient",
            "patient_name",
            "alert_type",
            "severity",
            "status",
            "message",
            "measured_value",
            "threshold_value",
            "occurrence_count",
            "triggered_at",
            "last_evaluated_at",
            "acknowledged_by",
            "acknowledged_by_name",
            "acknowledged_at",
            "resolved_by",
            "resolved_by_name",
            "resolved_at",
            "resolution_reason",
        ]
        read_only_fields = fields


class AlertThresholdConfigSerializer(serializers.ModelSerializer):
    """Representación de los umbrales de alerta vigentes."""

    class Meta:
        model = AlertThresholdConfig
        fields: ClassVar[list[str]] = [
            "id",
            "patient",
            "heart_rate_critical_low",
            "heart_rate_warning_low",
            "heart_rate_warning_high",
            "heart_rate_critical_high",
            "spo2_critical_low",
            "spo2_warning_low",
            "temp_critical_low",
            "temp_warning_low",
            "temp_warning_high",
            "temp_critical_high",
            "updated_by",
            "updated_at",
        ]
        read_only_fields = fields


class AlertThresholdConfigUpdateSerializer(serializers.Serializer):
    """Entrada para actualizar umbrales; los campos omitidos conservan su valor."""

    heart_rate_critical_low = serializers.IntegerField(
        min_value=HEART_RATE_MIN, max_value=HEART_RATE_MAX, required=False
    )
    heart_rate_warning_low = serializers.IntegerField(
        min_value=HEART_RATE_MIN, max_value=HEART_RATE_MAX, required=False
    )
    heart_rate_warning_high = serializers.IntegerField(
        min_value=HEART_RATE_MIN, max_value=HEART_RATE_MAX, required=False
    )
    heart_rate_critical_high = serializers.IntegerField(
        min_value=HEART_RATE_MIN, max_value=HEART_RATE_MAX, required=False
    )
    spo2_critical_low = serializers.IntegerField(
        min_value=SPO2_MIN, max_value=SPO2_MAX, required=False
    )
    spo2_warning_low = serializers.IntegerField(
        min_value=SPO2_MIN, max_value=SPO2_MAX, required=False
    )
    temp_critical_low = serializers.DecimalField(
        max_digits=4,
        decimal_places=1,
        min_value=TEMPERATURE_MIN,
        max_value=TEMPERATURE_MAX,
        required=False,
    )
    temp_warning_low = serializers.DecimalField(
        max_digits=4,
        decimal_places=1,
        min_value=TEMPERATURE_MIN,
        max_value=TEMPERATURE_MAX,
        required=False,
    )
    temp_warning_high = serializers.DecimalField(
        max_digits=4,
        decimal_places=1,
        min_value=TEMPERATURE_MIN,
        max_value=TEMPERATURE_MAX,
        required=False,
    )
    temp_critical_high = serializers.DecimalField(
        max_digits=4,
        decimal_places=1,
        min_value=TEMPERATURE_MIN,
        max_value=TEMPERATURE_MAX,
        required=False,
    )
