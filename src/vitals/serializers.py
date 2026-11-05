"""Serializers de lecturas de signos vitales y del resumen de la unidad."""

from typing import ClassVar

from rest_framework import serializers

from alerts.models import AlertSeverity
from devices.serializers import CribSerializer
from patients.models import Patient

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
    """Representación de solo lectura de una lectura de signos vitales."""

    crib_code = serializers.CharField(source="crib.code", read_only=True)
    patient_name = serializers.CharField(source="patient.full_name", read_only=True, default=None)

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
    """Entrada de telemetría con los rangos fisiológicos aceptados por cada signo vital."""

    heart_rate = serializers.IntegerField(min_value=HEART_RATE_MIN, max_value=HEART_RATE_MAX)
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


class OverviewAlertCountsSerializer(serializers.Serializer):
    """Alertas abiertas de una cuna por severidad."""

    total = serializers.IntegerField()
    critical = serializers.IntegerField()
    warning = serializers.IntegerField()
    info = serializers.IntegerField()


class OverviewPatientSerializer(serializers.ModelSerializer):
    """Datos mínimos del paciente que se muestran en el resumen de la unidad."""

    age_days = serializers.IntegerField(read_only=True)

    class Meta:
        model = Patient
        fields: ClassVar[list[str]] = [
            "id",
            "medical_record_number",
            "full_name",
            "sex",
            "age_days",
            "gestational_age_weeks",
            "current_weight_g",
        ]
        read_only_fields = fields


class CribOverviewSerializer(CribSerializer):
    """Cuna con su paciente, última lectura, alertas abiertas y severidad máxima."""

    patient = OverviewPatientSerializer(source="current_patient", read_only=True, allow_null=True)
    latest_reading = VitalSignReadingSerializer(read_only=True, allow_null=True)
    open_alerts = OverviewAlertCountsSerializer(read_only=True)
    highest_open_severity = serializers.ChoiceField(
        choices=AlertSeverity.choices, read_only=True, allow_null=True
    )

    class Meta(CribSerializer.Meta):
        fields: ClassVar[list[str]] = [
            *CribSerializer.Meta.fields,
            "patient",
            "latest_reading",
            "open_alerts",
            "highest_open_severity",
        ]
        read_only_fields = fields


class CribStatusCountsSerializer(serializers.Serializer):
    """Cantidad de cunas por estado operativo."""

    available = serializers.IntegerField()
    occupied = serializers.IntegerField()
    maintenance = serializers.IntegerField()
    offline = serializers.IntegerField()


class UnitSummarySerializer(serializers.Serializer):
    """Totales de la unidad: cunas por estado y alertas abiertas."""

    cribs_total = serializers.IntegerField()
    cribs_by_status = CribStatusCountsSerializer()
    patients_monitored = serializers.IntegerField()
    open_alerts = OverviewAlertCountsSerializer()


class UnitOverviewSerializer(serializers.Serializer):
    """Respuesta del resumen de la unidad: fecha de generación, totales y cunas."""

    generated_at = serializers.DateTimeField()
    summary = UnitSummarySerializer()
    cribs = CribOverviewSerializer(many=True)
