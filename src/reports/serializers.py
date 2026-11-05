"""Serializers de los reportes operativos."""

from rest_framework import serializers

from vitals.serializers import CribStatusCountsSerializer


class CountsByKeySerializer(serializers.DictField):
    """Mapa de conteos por clave (estado, severidad, tipo, etc.)."""

    child = serializers.IntegerField()


class PatientCountsSerializer(serializers.Serializer):
    """Conteo de pacientes: total, activos y egresados."""

    total = serializers.IntegerField()
    active = serializers.IntegerField()
    discharged = serializers.IntegerField()


class CribReportSerializer(serializers.Serializer):
    """Conteo de cunas por estado y porcentaje de ocupación."""

    total = serializers.IntegerField()
    by_status = CribStatusCountsSerializer()
    occupancy_percent = serializers.FloatField()


class PrescriptionReportSerializer(serializers.Serializer):
    """Indicaciones por estado y administraciones del día."""

    by_status = CountsByKeySerializer()
    administrations_today = serializers.IntegerField()


class AlertReportSerializer(serializers.Serializer):
    """Alertas abiertas, por severidad y por tipo."""

    open = serializers.IntegerField()
    open_by_severity = CountsByKeySerializer()
    open_by_type = CountsByKeySerializer()


class StaffReportSerializer(serializers.Serializer):
    """Personal activo, por turno y asignaciones del turno vigente."""

    active = serializers.IntegerField()
    by_shift = CountsByKeySerializer()
    assignments_current_shift_day = serializers.IntegerField()


class OperationsSummarySerializer(serializers.Serializer):
    """Respuesta del resumen operativo de la unidad."""

    generated_at = serializers.DateTimeField()
    patients = PatientCountsSerializer()
    cribs = CribReportSerializer()
    prescriptions = PrescriptionReportSerializer()
    medications_low_stock = serializers.IntegerField()
    alerts = AlertReportSerializer()
    care_plans_active = serializers.IntegerField()
    staff = StaffReportSerializer()


class ActivityPointSerializer(serializers.Serializer):
    """Punto diario de la serie de actividad: ingresos y alertas."""

    date = serializers.DateField()
    admissions = serializers.IntegerField()
    alerts = serializers.IntegerField()
