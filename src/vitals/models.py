from typing import ClassVar

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from .rules import (
    HEART_RATE_MAX,
    HEART_RATE_MIN,
    SPO2_MAX,
    SPO2_MIN,
    TEMPERATURE_MAX,
    TEMPERATURE_MIN,
    SleepState,
)


class VitalSignReading(models.Model):
    crib = models.ForeignKey(
        "devices.Crib",
        on_delete=models.PROTECT,
        related_name="vital_readings",
    )
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="vital_readings",
    )
    heart_rate = models.PositiveSmallIntegerField(
        validators=[
            MinValueValidator(HEART_RATE_MIN),
            MaxValueValidator(HEART_RATE_MAX),
        ]
    )
    spo2 = models.PositiveSmallIntegerField(
        validators=[
            MinValueValidator(SPO2_MIN),
            MaxValueValidator(SPO2_MAX),
        ]
    )
    temperature = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        validators=[
            MinValueValidator(TEMPERATURE_MIN),
            MaxValueValidator(TEMPERATURE_MAX),
        ],
    )
    sleep_state = models.CharField(
        max_length=16,
        choices=SleepState.choices,
    )
    cannula_connected = models.BooleanField()
    iv_line_active = models.BooleanField()

    recorded_at = models.DateTimeField(default=timezone.now, db_index=True)
    ingested_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-recorded_at", "-id"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(
                fields=["patient", "-recorded_at"], name="vitals_patient_ts_idx"
            ),
            models.Index(
                fields=["crib", "-recorded_at"], name="vitals_crib_ts_idx"
            ),
        ]
        constraints: ClassVar[list[models.CheckConstraint]] = [
            models.CheckConstraint(
                condition=models.Q(
                    heart_rate__gte=HEART_RATE_MIN,
                    heart_rate__lte=HEART_RATE_MAX,
                ),
                name="vitals_heart_rate_range",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    spo2__gte=SPO2_MIN,
                    spo2__lte=SPO2_MAX,
                ),
                name="vitals_spo2_range",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    temperature__gte=TEMPERATURE_MIN,
                    temperature__lte=TEMPERATURE_MAX,
                ),
                name="vitals_temperature_range",
            ),
        ]
        verbose_name = "Lectura de Signos Vitales"
        verbose_name_plural = "Lecturas de Signos Vitales"

    def __str__(self) -> str:
        return (
            f"[{self.crib.code}] FC={self.heart_rate} SpO2={self.spo2}% "
            f"T={self.temperature}°C ({self.recorded_at.isoformat()})"
        )
