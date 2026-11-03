from decimal import Decimal
from typing import ClassVar

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class PatientSex(models.TextChoices):
    FEMALE = "F", "Femenino"
    MALE = "M", "Masculino"


class PatientStatus(models.TextChoices):
    ACTIVE = "active", "Activo en unidad"
    DISCHARGED = "discharged", "Egresado (alta)"
    TRANSFERRED = "transferred", "Trasladado"
    DECEASED = "deceased", "Fallecido"


class DischargeOutcome(models.TextChoices):
    SURVIVED = "survived", "Sobrevivió / Alta domiciliaria"
    TRANSFERRED = "transferred", "Trasladado a otra unidad"
    DECEASED = "deceased", "Fallecido"
    UNKNOWN = "unknown", "Desconocido"


class DischargeCause(models.TextChoices):
    NONE = "none", "No aplica"
    PREMATURITY = "prematurity", "Prematuridad"
    PERINATAL_ASPHYXIA = "perinatal_asphyxia", "Asfixia perinatal"
    SEPSIS = "sepsis", "Sepsis / Infección"
    CONGENITAL_MALFORMATION = "congenital_malformation", "Malformación congénita"
    HYPOTHERMIA = "hypothermia", "Hipotermia"
    OTHER = "other", "Otra causa"


class CarePlanStatus(models.TextChoices):
    ACTIVE = "active", "Activo"
    SUSPENDED = "suspended", "Suspendido"
    COMPLETED = "completed", "Finalizado"


class ObservationCategory(models.TextChoices):
    GENERAL = "general", "General"
    NURSING = "nursing", "Enfermería / Matronería"
    MEDICAL = "medical", "Evolución Médica"
    KANGAROO_CARE = "kangaroo_care", "Método Canguro"
    PHOTOTHERAPY = "phototherapy", "Fototerapia"


class Patient(models.Model):
    medical_record_number = models.CharField(max_length=30, unique=True)
    full_name = models.CharField(max_length=200)
    sex = models.CharField(max_length=1, choices=PatientSex.choices)
    birth_date = models.DateField()
    gestational_age_weeks = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        validators=[
            MinValueValidator(Decimal("20.0")),
            MaxValueValidator(Decimal("45.0")),
        ],
    )
    birth_weight_g = models.PositiveIntegerField(
        validators=[MinValueValidator(200), MaxValueValidator(8000)]
    )
    current_weight_g = models.PositiveIntegerField(
        validators=[MinValueValidator(200), MaxValueValidator(10000)]
    )
    admitted_at = models.DateTimeField(default=timezone.now, db_index=True)
    diagnosis = models.TextField(blank=True, default="")

    # Datos de contacto de los padres; el RUT se guarda normalizado (12345678-5)
    # y el teléfono como +56XXXXXXXXX
    mother_rut = models.CharField(max_length=12, blank=True, default="", db_index=True)
    mother_first_names = models.CharField(max_length=100, blank=True, default="")
    mother_last_names = models.CharField(max_length=100, blank=True, default="")
    mother_phone = models.CharField(max_length=16, blank=True, default="")
    father_rut = models.CharField(max_length=12, blank=True, default="", db_index=True)
    father_first_names = models.CharField(max_length=100, blank=True, default="")
    father_last_names = models.CharField(max_length=100, blank=True, default="")
    father_phone = models.CharField(max_length=16, blank=True, default="")

    attending_physician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assigned_patients",
    )
    crib = models.OneToOneField(
        "devices.Crib",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_patient",
    )

    status = models.CharField(
        max_length=20,
        choices=PatientStatus.choices,
        default=PatientStatus.ACTIVE,
        db_index=True,
    )
    discharged_at = models.DateTimeField(null=True, blank=True)
    discharge_outcome = models.CharField(
        max_length=20,
        choices=DischargeOutcome.choices,
        null=True,
        blank=True,
    )
    discharge_cause = models.CharField(
        max_length=30,
        choices=DischargeCause.choices,
        null=True,
        blank=True,
    )
    discharge_notes = models.TextField(blank=True, default="")
    discharged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="discharged_patients",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-admitted_at", "-id"]
        constraints: ClassVar[list[models.CheckConstraint]] = [
            models.CheckConstraint(
                condition=models.Q(
                    gestational_age_weeks__gte=Decimal("20.0"),
                    gestational_age_weeks__lte=Decimal("45.0"),
                ),
                name="patient_gestational_age_range",
            ),
            models.CheckConstraint(
                condition=models.Q(birth_weight_g__gte=200, birth_weight_g__lte=8000),
                name="patient_birth_weight_range",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    current_weight_g__gte=200, current_weight_g__lte=10000
                ),
                name="patient_current_weight_range",
            ),
        ]
        verbose_name = "Paciente"
        verbose_name_plural = "Pacientes"

    def __str__(self) -> str:
        return f"{self.full_name} ({self.medical_record_number})"

    @property
    def age_days(self) -> int:
        reference_date = (
            self.discharged_at.date() if self.discharged_at else timezone.localdate()
        )
        return max(0, (reference_date - self.birth_date).days)


class CribMovementKind(models.TextChoices):
    ASSIGN = "assign", "Asignación de cuna"
    MOVE = "move", "Traslado entre cunas"
    SWAP = "swap", "Intercambio de cunas"
    RELEASE = "release", "Liberación de cuna (sigue activo)"
    DISCHARGE = "discharge", "Liberación por egreso"


class CribMovement(models.Model):
    """Historial de ubicaciones del paciente dentro de la unidad.

    Guarda una copia del código de cada cuna para que el historial siga
    legible aunque la cuna se renombre o se elimine.
    """

    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        related_name="crib_movements",
    )
    kind = models.CharField(max_length=20, choices=CribMovementKind.choices)
    from_crib = models.ForeignKey(
        "devices.Crib",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    from_crib_code = models.CharField(max_length=20, blank=True, default="")
    to_crib = models.ForeignKey(
        "devices.Crib",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    to_crib_code = models.CharField(max_length=20, blank=True, default="")
    moved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="crib_movements",
    )
    moved_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-moved_at", "-id"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["patient", "-moved_at"], name="crib_move_patient_ts_idx"),
        ]
        verbose_name = "Movimiento de cuna"
        verbose_name_plural = "Movimientos de cuna"

    def __str__(self) -> str:
        origin = self.from_crib_code or "—"
        destination = self.to_crib_code or "—"
        return f"{self.patient_id}: {origin} → {destination} ({self.kind})"


class WeightRecord(models.Model):
    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        related_name="weight_records",
    )
    weight_g = models.PositiveIntegerField(
        validators=[MinValueValidator(200), MaxValueValidator(10000)]
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_weights",
    )
    recorded_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-recorded_at", "-id"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(
                fields=["patient", "-recorded_at"], name="weight_patient_ts_idx"
            ),
        ]
        constraints: ClassVar[list[models.CheckConstraint]] = [
            models.CheckConstraint(
                condition=models.Q(weight_g__gte=200, weight_g__lte=10000),
                name="weight_record_positive_range",
            ),
        ]
        verbose_name = "Registro de Peso"
        verbose_name_plural = "Registros de Peso"

    def __str__(self) -> str:
        return f"{self.patient.medical_record_number}: {self.weight_g} g"


class CarePlan(models.Model):
    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        related_name="care_plans",
    )
    care_area = models.CharField(max_length=100)
    intervention = models.CharField(max_length=255)
    frequency = models.CharField(max_length=50)
    status = models.CharField(
        max_length=20,
        choices=CarePlanStatus.choices,
        default=CarePlanStatus.ACTIVE,
        db_index=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_care_plans",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at", "-id"]
        verbose_name = "Plan de Cuidado"
        verbose_name_plural = "Planes de Cuidado"

    def __str__(self) -> str:
        return f"{self.care_area} - {self.patient.full_name} ({self.status})"


class ClinicalObservation(models.Model):
    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        related_name="observations",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="clinical_observations",
    )
    category = models.CharField(
        max_length=30,
        choices=ObservationCategory.choices,
        default=ObservationCategory.GENERAL,
        db_index=True,
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at", "-id"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(
                fields=["patient", "-created_at"], name="obs_patient_ts_idx"
            ),
        ]
        verbose_name = "Observación Clínica"
        verbose_name_plural = "Observaciones Clínicas"

    def __str__(self) -> str:
        return f"[{self.category}] {self.patient.full_name}"
