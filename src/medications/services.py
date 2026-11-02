from datetime import time
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

from .models import (
    AdministrationRoute,
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
    scheduled_time: time,
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
            scheduled_time=scheduled_time,
            status=PrescriptionStatus.PENDING,
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
                "scheduled_time",
                "status",
            ],
            ip_address=ip_address,
        )

    return prescription


def administer_prescription(
    *,
    actor: User,
    prescription: Prescription,
    notes: str = "",
    ip_address: str | None = None,
) -> Prescription:
    if actor.role not in {UserRole.NEONATOLOGIST, UserRole.NURSE}:
        raise PermissionDomainError(
            "Solo un Neonatólogo o Matrona/Enfermera puede administrar medicamentos a un paciente."
        )

    with transaction.atomic():
        locked_prescription = Prescription.objects.select_for_update().get(
            pk=prescription.pk
        )
        locked_medication = MedicationCatalogItem.objects.select_for_update().get(
            pk=locked_prescription.medication_id
        )

        if locked_prescription.patient.status != PatientStatus.ACTIVE:
            raise ConflictDomainError(
                "No se puede administrar medicación a un paciente ya egresado."
            )
        if locked_prescription.status != PrescriptionStatus.PENDING:
            raise ConflictDomainError(
                "La indicación médica ya fue administrada o cancelada previamente."
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

        locked_prescription.status = PrescriptionStatus.ADMINISTERED
        locked_prescription.administered_by = actor
        locked_prescription.administered_at = timezone.now()
        locked_prescription.administration_notes = (notes or "").strip()
        locked_prescription.save(
            update_fields=[
                "status",
                "administered_by",
                "administered_at",
                "administration_notes",
                "updated_at",
            ]
        )

        record_audit_event(
            action=AuditAction.ADMINISTER_MEDICATION,
            resource_type="prescription",
            resource_id=locked_prescription.id,
            actor_user=actor,
            patient_id=locked_prescription.patient_id,
            changed_fields=[
                "status",
                "administered_by_id",
                "administered_at",
                "administration_notes",
                "stock",
            ],
            ip_address=ip_address,
        )

    locked_prescription.medication = locked_medication
    return locked_prescription


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
        if locked_prescription.status != PrescriptionStatus.PENDING:
            raise ConflictDomainError(
                "Solo se pueden cancelar indicaciones que aún se encuentren pendientes."
            )

        locked_prescription.status = PrescriptionStatus.CANCELLED
        if reason and reason.strip():
            locked_prescription.administration_notes = reason.strip()
        locked_prescription.save(
            update_fields=["status", "administration_notes", "updated_at"]
        )

        record_audit_event(
            action=AuditAction.UPDATE,
            resource_type="prescription",
            resource_id=locked_prescription.id,
            actor_user=actor,
            patient_id=locked_prescription.patient_id,
            changed_fields=["status", "administration_notes"],
            ip_address=ip_address,
        )

    return locked_prescription


def cancel_pending_prescriptions_on_discharge(*, patient: Patient) -> int:
    return Prescription.objects.filter(
        patient=patient,
        status=PrescriptionStatus.PENDING,
    ).update(
        status=PrescriptionStatus.CANCELLED,
        updated_at=timezone.now(),
    )
