from typing import ClassVar

from django.conf import settings
from django.db import models
from django.utils import timezone

from vitals.rules import (
    DEFAULT_HR_CRITICAL_HIGH,
    DEFAULT_HR_CRITICAL_LOW,
    DEFAULT_HR_WARNING_HIGH,
    DEFAULT_HR_WARNING_LOW,
    DEFAULT_SPO2_CRITICAL_LOW,
    DEFAULT_SPO2_WARNING_LOW,
    DEFAULT_TEMP_CRITICAL_HIGH,
    DEFAULT_TEMP_CRITICAL_LOW,
    DEFAULT_TEMP_WARNING_HIGH,
    DEFAULT_TEMP_WARNING_LOW,
)


class AlertType(models.TextChoices):
    HEART_RATE = "heart_rate", "Frecuencia Cardíaca"
    SPO2 = "spo2", "Saturación de Oxígeno (SpO2)"
    TEMPERATURE = "temperature", "Temperatura Corporal"
    CANNULA = "cannula", "Cánula de Oxígeno"
    SENSOR_FAULT = "sensor_fault", "Fallo de Sensor"
    OTHER = "other", "Otra Alerta"


class AlertSeverity(models.TextChoices):
    INFO = "info", "Informativa"
    WARNING = "warning", "Advertencia"
    CRITICAL = "critical", "Crítica"


class AlertStatus(models.TextChoices):
    ACTIVE = "active", "Activa"
    ACKNOWLEDGED = "acknowledged", "Reconocida"
    RESOLVED = "resolved", "Resuelta"


class ResolutionReason(models.TextChoices):
    AUTO_NORMALIZED = "auto_normalized", "Normalización automática"
    MANUAL = "manual", "Resolución manual"
    SEVERITY_ESCALATED = "severity_escalated", "Cambio de severidad"
    PATIENT_DISCHARGED = "patient_discharged", "Egreso del paciente"


class AlertThresholdConfig(models.Model):
    patient = models.OneToOneField(
        "patients.Patient",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="alert_threshold_config",
    )
    heart_rate_critical_low = models.PositiveSmallIntegerField(
        default=DEFAULT_HR_CRITICAL_LOW
    )
    heart_rate_warning_low = models.PositiveSmallIntegerField(
        default=DEFAULT_HR_WARNING_LOW
    )
    heart_rate_warning_high = models.PositiveSmallIntegerField(
        default=DEFAULT_HR_WARNING_HIGH
    )
    heart_rate_critical_high = models.PositiveSmallIntegerField(
        default=DEFAULT_HR_CRITICAL_HIGH
    )
    spo2_critical_low = models.PositiveSmallIntegerField(
        default=DEFAULT_SPO2_CRITICAL_LOW
    )
    spo2_warning_low = models.PositiveSmallIntegerField(
        default=DEFAULT_SPO2_WARNING_LOW
    )
    temp_critical_low = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=DEFAULT_TEMP_CRITICAL_LOW,
    )
    temp_warning_low = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=DEFAULT_TEMP_WARNING_LOW,
    )
    temp_warning_high = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=DEFAULT_TEMP_WARNING_HIGH,
    )
    temp_critical_high = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=DEFAULT_TEMP_CRITICAL_HIGH,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_threshold_configs",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["id"]
        constraints: ClassVar[list[models.CheckConstraint]] = [
            models.CheckConstraint(
                condition=models.Q(
                    heart_rate_critical_low__lt=models.F("heart_rate_warning_low"),
                    heart_rate_warning_low__lt=models.F("heart_rate_warning_high"),
                    heart_rate_warning_high__lt=models.F("heart_rate_critical_high"),
                ),
                name="threshold_hr_strict_order",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    spo2_critical_low__lt=models.F("spo2_warning_low"),
                    spo2_warning_low__lte=100,
                ),
                name="threshold_spo2_strict_order",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    temp_critical_low__lt=models.F("temp_warning_low"),
                    temp_warning_low__lt=models.F("temp_warning_high"),
                    temp_warning_high__lt=models.F("temp_critical_high"),
                ),
                name="threshold_temp_strict_order",
            ),
        ]
        verbose_name = "Configuración de Umbrales de Alerta"
        verbose_name_plural = "Configuraciones de Umbrales de Alerta"

    def __str__(self) -> str:
        if self.patient_id:
            return f"Umbrales personalizados (Paciente #{self.patient_id})"
        return "Umbrales neonatales globales por defecto"


class Alert(models.Model):
    crib = models.ForeignKey(
        "devices.Crib",
        on_delete=models.PROTECT,
        related_name="alerts",
    )
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="alerts",
    )
    alert_type = models.CharField(
        max_length=24,
        choices=AlertType.choices,
        db_index=True,
    )
    severity = models.CharField(
        max_length=16,
        choices=AlertSeverity.choices,
        db_index=True,
    )
    status = models.CharField(
        max_length=16,
        choices=AlertStatus.choices,
        default=AlertStatus.ACTIVE,
        db_index=True,
    )
    message = models.CharField(max_length=255)
    measured_value = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True,
    )
    threshold_value = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True,
    )
    occurrence_count = models.PositiveIntegerField(default=1)

    triggered_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_evaluated_at = models.DateTimeField(default=timezone.now)

    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acknowledged_alerts",
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_alerts",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_reason = models.CharField(
        max_length=30,
        choices=ResolutionReason.choices,
        null=True,
        blank=True,
    )

    class Meta:
        ordering: ClassVar[list[str]] = ["-triggered_at", "-id"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(
                fields=["crib", "status", "alert_type"],
                name="alert_crib_status_type_idx",
            ),
            models.Index(
                fields=["patient", "status", "-triggered_at"],
                name="alert_patient_status_ts_idx",
            ),
        ]
        verbose_name = "Alerta Clínica"
        verbose_name_plural = "Alertas Clínicas"

    def __str__(self) -> str:
        return f"[{self.severity.upper()}] {self.alert_type} - Cuna {self.crib.code} ({self.status})"
