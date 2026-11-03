from decimal import Decimal
from typing import ClassVar

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class AdministrationRoute(models.TextChoices):
    IV = "IV", "Intravenosa (IV)"
    IM = "IM", "Intramuscular (IM)"
    ET = "ET", "Endotraqueal (ET)"
    PO = "PO", "Vía Oral / Sonda (PO)"
    SC = "SC", "Subcutánea (SC)"


class PrescriptionStatus(models.TextChoices):
    ACTIVE = "active", "Vigente"
    COMPLETED = "completed", "Completada"
    CANCELLED = "cancelled", "Cancelada"


MAX_FREQUENCY_HOURS = 168


class MedicationCatalogItem(models.Model):
    name = models.CharField(max_length=150, unique=True)
    active_ingredient = models.CharField(max_length=150)
    concentration_mg = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    unit = models.CharField(max_length=30, default="ampolla")
    stock = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
    )
    min_stock_alert = models.PositiveIntegerField(default=5)
    is_active = models.BooleanField(default=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["name"]
        constraints: ClassVar[list[models.CheckConstraint]] = [
            models.CheckConstraint(
                condition=models.Q(concentration_mg__gt=Decimal("0.00")),
                name="catalog_concentration_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(stock__gte=0),
                name="catalog_stock_non_negative",
            ),
        ]
        verbose_name = "Medicamento de Catálogo"
        verbose_name_plural = "Catálogo de Medicamentos"

    def __str__(self) -> str:
        return f"{self.name} ({self.concentration_mg} mg - stock: {self.stock})"

    @property
    def is_low_stock(self) -> bool:
        return self.stock <= self.min_stock_alert


class Prescription(models.Model):
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="prescriptions",
    )
    medication = models.ForeignKey(
        MedicationCatalogItem,
        on_delete=models.PROTECT,
        related_name="prescriptions",
    )
    prescribed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_prescriptions",
    )
    dose = models.CharField(max_length=100)
    units_per_administration = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
    )
    route = models.CharField(
        max_length=8,
        choices=AdministrationRoute.choices,
        default=AdministrationRoute.IV,
    )
    starts_at = models.DateTimeField()
    # Nulo = dosis única; con valor, las dosis se programan cada N horas desde starts_at
    frequency_hours = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_FREQUENCY_HOURS)],
    )
    ends_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=16,
        choices=PrescriptionStatus.choices,
        default=PrescriptionStatus.ACTIVE,
        db_index=True,
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["starts_at", "-id"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(
                fields=["patient", "status", "starts_at"],
                name="presc_patient_status_start_idx",
            ),
        ]
        constraints: ClassVar[list[models.CheckConstraint]] = [
            models.CheckConstraint(
                condition=models.Q(units_per_administration__gte=1),
                name="prescription_units_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(frequency_hours__isnull=True)
                | models.Q(frequency_hours__gte=1, frequency_hours__lte=MAX_FREQUENCY_HOURS),
                name="prescription_frequency_range",
            ),
            models.CheckConstraint(
                condition=models.Q(ends_at__isnull=True)
                | models.Q(frequency_hours__isnull=False, ends_at__gt=models.F("starts_at")),
                name="prescription_end_after_start_for_recurring",
            ),
        ]
        verbose_name = "Indicación Médica"
        verbose_name_plural = "Indicaciones Médicas"

    def __str__(self) -> str:
        return f"{self.medication.name} {self.dose} ({self.get_status_display()})"


class MedicationAdministration(models.Model):
    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.PROTECT,
        related_name="administrations",
    )
    scheduled_for = models.DateTimeField()
    administered_at = models.DateTimeField()
    administered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="medication_administrations",
    )
    units_deducted = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-scheduled_for", "-id"]
        constraints: ClassVar[list[models.UniqueConstraint]] = [
            # Garantía a nivel de base de datos contra la doble administración de una misma dosis
            models.UniqueConstraint(
                fields=["prescription", "scheduled_for"],
                name="administration_unique_dose_slot",
            ),
        ]
        verbose_name = "Administración de Medicamento"
        verbose_name_plural = "Administraciones de Medicamentos"

    def __str__(self) -> str:
        return f"Dosis {self.scheduled_for:%Y-%m-%d %H:%M} de indicación #{self.prescription_id}"
