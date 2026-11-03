from datetime import datetime
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from accounts.models import User, UserRole
from audit.models import AuditAction
from audit.services import record_audit_event
from patients.models import Patient, PatientStatus
from poki_koa.exceptions import (
    ConflictDomainError,
    DomainError,
    NotFoundDomainError,
    PermissionDomainError,
)

from . import schedule
from .models import (
    MAX_FREQUENCY_HOURS,
    AdministrationRoute,
    MedicationAdministration,
    MedicationCatalogItem,
    Prescription,
    PrescriptionStatus,
)


def create_catalog_item(
    *,
    actor: User,
    name: str,
    active_ingredient: str,
    concentration_mg: Decimal | float | str,
    unit: str = "ampolla",
    stock: int = 0,
    min_stock_alert: int = 5,
    is_active: bool = True,
    ip_address: str | None = None,
) -> MedicationCatalogItem:
    if actor.role not in {UserRole.ADMIN, UserRole.PHARMACIST}:
        raise PermissionDomainError(
            "Solo un Químico Farmacéutico o Administrador puede registrar medicamentos en el catálogo."
        )

    cleaned_name = (name or "").strip()
    cleaned_ingredient = (active_ingredient or "").strip()
    cleaned_unit = (unit or "ampolla").strip()
    if not cleaned_name:
        raise DomainError("El nombre del medicamento es obligatorio.")
    if not cleaned_ingredient:
        raise DomainError("El principio activo del medicamento es obligatorio.")
    if not cleaned_unit:
        raise DomainError("La unidad de dispensación es obligatoria.")

    conc = Decimal(str(concentration_mg)).quantize(Decimal("0.01"))
    if conc <= Decimal("0.00"):
        raise DomainError("La concentración en miligramos debe ser mayor que cero.")
    if stock < 0:
        raise DomainError("El stock disponible no puede ser negativo.")
    if min_stock_alert < 0:
        raise DomainError("El umbral de alerta de stock mínimo no puede ser negativo.")

    with transaction.atomic():
        if MedicationCatalogItem.objects.filter(name__iexact=cleaned_name).exists():
            raise ConflictDomainError(
                "Ya existe un medicamento en el catálogo con ese nombre."
            )

        item = MedicationCatalogItem.objects.create(
            name=cleaned_name,
            active_ingredient=cleaned_ingredient,
            concentration_mg=conc,
            unit=cleaned_unit,
            stock=stock,
            min_stock_alert=min_stock_alert,
            is_active=is_active,
        )
        record_audit_event(
            action=AuditAction.CREATE,
            resource_type="medication_catalog",
            resource_id=item.id,
            actor_user=actor,
            changed_fields=[
                "name",
                "active_ingredient",
                "concentration_mg",
                "unit",
                "stock",
                "min_stock_alert",
                "is_active",
            ],
            ip_address=ip_address,
        )
    return item


def update_catalog_item(
    *,
    actor: User,
    item: MedicationCatalogItem,
    data: dict[str, Any],
    ip_address: str | None = None,
) -> MedicationCatalogItem:
    if actor.role not in {UserRole.ADMIN, UserRole.PHARMACIST}:
        raise PermissionDomainError(
            "Solo un Químico Farmacéutico o Administrador puede actualizar el catálogo o el stock."
        )

    with transaction.atomic():
        locked_item = MedicationCatalogItem.objects.select_for_update().get(pk=item.pk)
        changed_fields: list[str] = []

        if "name" in data:
            new_name = str(data["name"]).strip()
            if not new_name:
                raise DomainError("El nombre del medicamento no puede estar vacío.")
            if new_name != locked_item.name:
                if (
                    MedicationCatalogItem.objects.filter(name__iexact=new_name)
                    .exclude(pk=locked_item.pk)
                    .exists()
                ):
                    raise ConflictDomainError(
                        "Ya existe otro medicamento en el catálogo con ese nombre."
                    )
                locked_item.name = new_name
                changed_fields.append("name")

        for text_field in ("active_ingredient", "unit"):
            if text_field in data:
                val = str(data[text_field]).strip()
                if not val:
                    raise DomainError(f"El campo '{text_field}' no puede estar vacío.")
                if val != getattr(locked_item, text_field):
                    setattr(locked_item, text_field, val)
                    changed_fields.append(text_field)

        if "concentration_mg" in data:
            new_conc = Decimal(str(data["concentration_mg"])).quantize(Decimal("0.01"))
            if new_conc <= Decimal("0.00"):
                raise DomainError(
                    "La concentración en miligramos debe ser mayor que cero."
                )
            if new_conc != locked_item.concentration_mg:
                locked_item.concentration_mg = new_conc
                changed_fields.append("concentration_mg")

        if "stock" in data:
            new_stock = int(data["stock"])
            if new_stock < 0:
                raise DomainError("El stock disponible no puede ser negativo.")
            if new_stock != locked_item.stock:
                locked_item.stock = new_stock
                changed_fields.append("stock")

        if "min_stock_alert" in data:
            new_min = int(data["min_stock_alert"])
            if new_min < 0:
                raise DomainError(
                    "El umbral de alerta de stock mínimo no puede ser negativo."
                )
            if new_min != locked_item.min_stock_alert:
                locked_item.min_stock_alert = new_min
                changed_fields.append("min_stock_alert")

        if "is_active" in data:
            new_active = bool(data["is_active"])
            if new_active != locked_item.is_active:
                locked_item.is_active = new_active
                changed_fields.append("is_active")

        if changed_fields:
            locked_item.save()
            record_audit_event(
                action=AuditAction.UPDATE,
                resource_type="medication_catalog",
                resource_id=locked_item.id,
                actor_user=actor,
                changed_fields=changed_fields,
                ip_address=ip_address,
            )

    return locked_item


def create_prescription(
    *,
    actor: User,
    patient_id: int,
    medication_id: int,
    dose: str,
    starts_at: datetime,
    frequency_hours: int | None = None,
    ends_at: datetime | None = None,
    route: str = AdministrationRoute.IV,
    units_per_administration: int = 1,
    ip_address: str | None = None,
) -> Prescription:
    if actor.role != UserRole.NEONATOLOGIST:
        raise PermissionDomainError(
            "Solo un Neonatólogo está autorizado para prescribir indicaciones médicas."
        )

    cleaned_dose = (dose or "").strip()
    if not cleaned_dose:
        raise DomainError("La dosis prescrita es obligatoria.")
    if route not in set(AdministrationRoute.values):
        raise DomainError("La vía de administración indicada no es válida.")
    if units_per_administration < 1:
        raise DomainError(
            "Las unidades a descontar por administración deben ser al menos 1."
        )
    if timezone.is_naive(starts_at) or (ends_at is not None and timezone.is_naive(ends_at)):
        raise DomainError("Las fechas de la indicación deben incluir zona horaria.")
    if frequency_hours is not None and not 1 <= frequency_hours <= MAX_FREQUENCY_HOURS:
        raise DomainError(
            f"La frecuencia debe estar entre 1 y {MAX_FREQUENCY_HOURS} horas."
        )
    if ends_at is not None and frequency_hours is None:
        raise DomainError("Una dosis única no admite fecha de término.")

    # Se trunca al minuto para que los horarios de dosis sean comparables de forma exacta
    starts_at = starts_at.replace(second=0, microsecond=0)
    if ends_at is not None and ends_at <= starts_at:
        raise DomainError("La fecha de término debe ser posterior a la primera dosis.")

    with transaction.atomic():
        patient = Patient.objects.select_for_update().filter(pk=patient_id).first()
        if patient is None:
            raise NotFoundDomainError("El paciente indicado no existe.")
        if patient.status != PatientStatus.ACTIVE:
            raise ConflictDomainError(
                "No se pueden crear indicaciones médicas para un paciente ya egresado."
            )

        medication = (
            MedicationCatalogItem.objects.select_for_update()
            .filter(pk=medication_id)
            .first()
        )
        if medication is None:
            raise NotFoundDomainError(
                "El medicamento seleccionado no existe en el catálogo."
            )
        if not medication.is_active:
            raise ConflictDomainError(
                "El medicamento seleccionado se encuentra inactivo en el catálogo."
            )

        prescription = Prescription.objects.create(
            patient=patient,
            medication=medication,
            prescribed_by=actor,
            dose=cleaned_dose,
            units_per_administration=units_per_administration,
            route=route,
            starts_at=starts_at,
            frequency_hours=frequency_hours,
            ends_at=ends_at,
            status=PrescriptionStatus.ACTIVE,
        )

        record_audit_event(
            action=AuditAction.CREATE,
            resource_type="prescription",
            resource_id=prescription.id,
            actor_user=actor,
            patient_id=patient.id,
            changed_fields=[
                "medication_id",
                "dose",
                "units_per_administration",
                "route",
                "starts_at",
                "frequency_hours",
                "ends_at",
                "status",
            ],
            ip_address=ip_address,
        )

    return prescription


def _format_local(when: datetime) -> str:
    return timezone.localtime(when).strftime("%d-%m-%Y %H:%M")


def administer_prescription(
    *,
    actor: User,
    prescription: Prescription,
    scheduled_for: datetime | None = None,
    notes: str = "",
    ip_address: str | None = None,
) -> MedicationAdministration:
    if actor.role not in {UserRole.NEONATOLOGIST, UserRole.NURSE}:
        raise PermissionDomainError(
            "Solo un Neonatólogo o Matrona/Enfermera puede administrar medicamentos a un paciente."
        )

    now = timezone.now()
    with transaction.atomic():
        locked_prescription = Prescription.objects.select_for_update().get(
            pk=prescription.pk
        )
        locked_medication = MedicationCatalogItem.objects.select_for_update().get(
            pk=locked_prescription.medication_id
        )
        patient_status = Patient.objects.values_list("status", flat=True).get(
            pk=locked_prescription.patient_id
        )

        if patient_status != PatientStatus.ACTIVE:
            raise ConflictDomainError(
                "No se puede administrar medicación a un paciente ya egresado."
            )
        if locked_prescription.status != PrescriptionStatus.ACTIVE:
            raise ConflictDomainError(
                "La indicación médica ya fue completada o cancelada previamente."
            )

        if scheduled_for is None:
            slot = schedule.latest_due_slot(locked_prescription, now)
            if slot is None:
                raise ConflictDomainError(
                    "Aún no corresponde administrar esta indicación; la primera dosis es el "
                    f"{_format_local(locked_prescription.starts_at)}."
                )
        else:
            slot = scheduled_for
            if not schedule.is_valid_slot(locked_prescription, slot):
                raise DomainError(
                    "El horario indicado no corresponde a una dosis programada de esta indicación.",
                    details={"scheduled_for": ["Horario de dosis inválido."]},
                )
            if slot > now + schedule.EARLY_ADMINISTRATION_WINDOW:
                early_minutes = int(schedule.EARLY_ADMINISTRATION_WINDOW.total_seconds() // 60)
                raise ConflictDomainError(
                    f"La dosis del {_format_local(slot)} aún no puede administrarse; "
                    f"se permite con hasta {early_minutes} minutos de anticipación."
                )

        if locked_prescription.administrations.filter(scheduled_for=slot).exists():
            raise ConflictDomainError(
                f"La dosis programada para el {_format_local(slot)} ya fue administrada."
            )
        if not locked_medication.is_active:
            raise ConflictDomainError(
                "El medicamento asociado se encuentra inactivo en el catálogo."
            )
        if locked_medication.stock < locked_prescription.units_per_administration:
            raise ConflictDomainError(
                "Stock insuficiente en el catálogo para administrar la dosis indicada."
            )

        locked_medication.stock -= locked_prescription.units_per_administration
        locked_medication.save(update_fields=["stock", "updated_at"])

        administration = MedicationAdministration.objects.create(
            prescription=locked_prescription,
            scheduled_for=slot,
            administered_at=now,
            administered_by=actor,
            units_deducted=locked_prescription.units_per_administration,
            notes=(notes or "").strip(),
        )

        changed_fields = ["administrations", "stock"]
        if slot == schedule.last_slot(locked_prescription):
            locked_prescription.status = PrescriptionStatus.COMPLETED
            locked_prescription.save(update_fields=["status", "updated_at"])
            changed_fields.append("status")

        record_audit_event(
            action=AuditAction.ADMINISTER_MEDICATION,
            resource_type="prescription",
            resource_id=locked_prescription.id,
            actor_user=actor,
            patient_id=locked_prescription.patient_id,
            changed_fields=changed_fields,
            ip_address=ip_address,
        )

    administration.prescription = locked_prescription
    return administration


def cancel_prescription(
    *,
    actor: User,
    prescription: Prescription,
    reason: str = "",
    ip_address: str | None = None,
) -> Prescription:
    if actor.role != UserRole.NEONATOLOGIST:
        raise PermissionDomainError(
            "Solo un Neonatólogo puede cancelar una indicación médica."
        )

    with transaction.atomic():
        locked_prescription = Prescription.objects.select_for_update().get(
            pk=prescription.pk
        )
        if locked_prescription.status != PrescriptionStatus.ACTIVE:
            raise ConflictDomainError(
                "Solo se pueden cancelar indicaciones que aún se encuentren vigentes."
            )

        locked_prescription.status = PrescriptionStatus.CANCELLED
        locked_prescription.cancelled_at = timezone.now()
        locked_prescription.cancellation_reason = (reason or "").strip()
        locked_prescription.save(
            update_fields=["status", "cancelled_at", "cancellation_reason", "updated_at"]
        )

        record_audit_event(
            action=AuditAction.UPDATE,
            resource_type="prescription",
            resource_id=locked_prescription.id,
            actor_user=actor,
            patient_id=locked_prescription.patient_id,
            changed_fields=["status", "cancelled_at", "cancellation_reason"],
            ip_address=ip_address,
        )

    return locked_prescription


def cancel_pending_prescriptions_on_discharge(*, patient: Patient) -> int:
    now = timezone.now()
    return Prescription.objects.filter(
        patient=patient,
        status=PrescriptionStatus.ACTIVE,
    ).update(
        status=PrescriptionStatus.CANCELLED,
        cancelled_at=now,
        cancellation_reason="Egreso del paciente",
        updated_at=now,
    )
