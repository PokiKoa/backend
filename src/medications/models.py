from decimal import Decimal
from typing import ClassVar

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class AdministrationRoute(models.TextChoices):
    IV = "IV", "Intravenosa (IV)"
    IM = "IM", "Intramuscular (IM)"
    ET = "ET", "Endotraqueal (ET)"
    PO = "PO", "Vía Oral / Sonda (PO)"
    SC = "SC", "Subcutánea (SC)"


class PrescriptionStatus(models.TextChoices):
    PENDING = "pending", "Pendiente"
    ADMINISTERED = "administered", "Administrado"
    CANCELLED = "cancelled", "Cancelado"


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
    scheduled_time = models.TimeField()
    status = models.CharField(
        max_length=16,
        choices=PrescriptionStatus.choices,
        default=PrescriptionStatus.PENDING,
        db_index=True,
    )

    administered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="administered_prescriptions",
    )
    administered_at = models.DateTimeField(null=True, blank=True)
    administration_notes = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["scheduled_time", "-id"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(
                fields=["patient", "status", "scheduled_time"],
                name="presc_patient_status_time_idx",
            ),
        ]
        constraints: ClassVar[list[models.CheckConstraint]] = [
            models.CheckConstraint(
                condition=models.Q(units_per_administration__gte=1),
                name="prescription_units_positive",
            ),
        ]
        verbose_name = "Indicación Médica"
        verbose_name_plural = "Indicaciones Médicas"

    def __str__(self) -> str:
        return f"{self.medication.name} ({self.dose}) -> {self.patient.full_name} [{self.status}]"
