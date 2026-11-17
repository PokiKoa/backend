"""Servicios de medicación: catálogo con stock, indicaciones médicas y administración de dosis."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from accounts.models import User
from accounts.roles import CATALOG_MANAGERS, CLINICAL_STAFF, NEONATOLOGIST_ONLY, require_role
from audit.models import AuditAction
from audit.services import record_audit_event
from patients.locks import lock_active_patient
from patients.models import Patient, PatientStatus
from poki_koa.exceptions import (
    ConflictDomainError,
    DomainError,
    NotFoundDomainError,
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
    """Registra un medicamento en el catálogo.

    Precondiciones:
        - ``actor`` posee rol en ``CATALOG_MANAGERS`` (Químico Farmacéutico o Administrador).
        - ``name``, ``active_ingredient`` y ``unit`` son cadenas no vacías tras normalización.
        - ``concentration_mg > 0``, ``stock >= 0`` y ``min_stock_alert >= 0``.

    Postcondiciones:
        - Persiste un nuevo ``MedicationCatalogItem`` con identificador primario asignado y concentración positiva.
        - Registra el evento de creación en la bitácora de auditoría.

    Invariante:
        - Ningún medicamento del catálogo puede existir con stock negativo ni concentración menor o igual a cero.
    """
    require_role(
        actor,
        CATALOG_MANAGERS,
        "Solo un Químico Farmacéutico o Administrador puede registrar medicamentos en el catálogo.",
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

    conc = parse_concentration_mg(concentration_mg)
    stock = parse_stock(stock)
    min_stock_alert = parse_min_stock_alert(min_stock_alert)

    with transaction.atomic():
        if MedicationCatalogItem.objects.filter(name__iexact=cleaned_name).exists():
            raise ConflictDomainError("Ya existe un medicamento en el catálogo con ese nombre.")

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

    assert item.pk is not None, "Postcondición fallida: el medicamento no fue persistido."
    assert item.concentration_mg > Decimal("0.00") and item.stock >= 0, (
        "Invariante fallido: concentración o stock fuera de dominio."
    )
    return item


def _normalize_item_name(item: MedicationCatalogItem, value: Any) -> str:
    """Normaliza y verifica la unicidad del nombre comercial de un medicamento."""
    name = str(value).strip()
    if not name:
        raise DomainError("El nombre del medicamento no puede estar vacío.")
    if (
        name != item.name
        and MedicationCatalogItem.objects.filter(name__iexact=name).exclude(pk=item.pk).exists()
    ):
        raise ConflictDomainError("Ya existe otro medicamento en el catálogo con ese nombre.")
    return name


def _non_empty_text(field: str):
    """Construye un normalizador que exige cadenas no vacías para el campo indicado."""

    def normalize(item: MedicationCatalogItem, value: Any) -> str:
        text = str(value).strip()
        if not text:
            raise DomainError(f"El campo '{field}' no puede estar vacío.")
        return text

    return normalize


def parse_concentration_mg(value: Any) -> Decimal:
    """Normaliza una concentración a dos decimales y exige que sea mayor que cero.

    Raises:
        DomainError: Si la concentración redondeada es menor o igual a cero.
    """
    concentration = Decimal(str(value)).quantize(Decimal("0.01"))
    if concentration <= Decimal("0.00"):
        raise DomainError("La concentración en miligramos debe ser mayor que cero.")
    return concentration


def parse_stock(value: Any) -> int:
    """Convierte el stock a entero no negativo.

    Raises:
        DomainError: Si el stock es negativo.
    """
    stock = int(value)
    if stock < 0:
        raise DomainError("El stock disponible no puede ser negativo.")
    return stock


def parse_min_stock_alert(value: Any) -> int:
    """Convierte el umbral de stock mínimo a entero no negativo.

    Raises:
        DomainError: Si el umbral es negativo.
    """
    minimum = int(value)
    if minimum < 0:
        raise DomainError("El umbral de alerta de stock mínimo no puede ser negativo.")
    return minimum


# Campos editables del catálogo. El orden define ``changed_fields`` en la auditoría.
_CATALOG_EDITABLE_FIELDS = {
    "name": _normalize_item_name,
    "active_ingredient": _non_empty_text("active_ingredient"),
    "unit": _non_empty_text("unit"),
    "concentration_mg": lambda item, value: parse_concentration_mg(value),
    "stock": lambda item, value: parse_stock(value),
    "min_stock_alert": lambda item, value: parse_min_stock_alert(value),
    "is_active": lambda item, value: bool(value),
}


def update_catalog_item(
    *,
    actor: User,
    item: MedicationCatalogItem,
    data: dict[str, Any],
    ip_address: str | None = None,
) -> MedicationCatalogItem:
    """Actualiza parcialmente un medicamento del catálogo (datos y stock) y audita el cambio.

    Precondiciones:
        - ``actor`` posee rol en ``CATALOG_MANAGERS``.
        - ``item`` corresponde a un registro existente en el catálogo.

    Postcondiciones:
        - Retorna el ``MedicationCatalogItem`` actualizado con bloqueo transaccional.
        - Si hubo cambios efectivos, persiste los valores y registra el evento de auditoría.

    Invariante:
        - El stock resultante nunca es negativo y la concentración permanece mayor que cero.
    """
    require_role(
        actor,
        CATALOG_MANAGERS,
        "Solo un Químico Farmacéutico o Administrador puede actualizar el catálogo o el stock.",
    )

    with transaction.atomic():
        locked_item = MedicationCatalogItem.objects.select_for_update().get(pk=item.pk)
        changed_fields: list[str] = []

        for field, normalize in _CATALOG_EDITABLE_FIELDS.items():
            if field not in data:
                continue
            new_value = normalize(locked_item, data[field])
            if new_value != getattr(locked_item, field):
                setattr(locked_item, field, new_value)
                changed_fields.append(field)

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

    assert locked_item.stock >= 0 and locked_item.concentration_mg > Decimal("0.00"), (
        "Invariante fallido: inventario o concentración corrupta tras actualización."
    )
    return locked_item


def _validate_prescription_inputs(
    *,
    dose: str,
    route: str,
    units_per_administration: int,
    starts_at: datetime,
    ends_at: datetime | None,
    frequency_hours: int | None,
) -> tuple[str, datetime]:
    """Valida los datos de una indicación y devuelve ``(dosis_limpia, inicio_truncado_al_minuto)``.

    Raises:
        DomainError: Si la dosis, vía, unidades, fechas o frecuencia son inválidas.
    """
    cleaned_dose = (dose or "").strip()
    if not cleaned_dose:
        raise DomainError("La dosis prescrita es obligatoria.")
    if route not in set(AdministrationRoute.values):
        raise DomainError("La vía de administración indicada no es válida.")
    if units_per_administration < 1:
        raise DomainError("Las unidades a descontar por administración deben ser al menos 1.")
    if timezone.is_naive(starts_at) or (ends_at is not None and timezone.is_naive(ends_at)):
        raise DomainError("Las fechas de la indicación deben incluir zona horaria.")
    if frequency_hours is not None and not 1 <= frequency_hours <= MAX_FREQUENCY_HOURS:
        raise DomainError(f"La frecuencia debe estar entre 1 y {MAX_FREQUENCY_HOURS} horas.")
    if ends_at is not None and frequency_hours is None:
        raise DomainError("Una dosis única no admite fecha de término.")

    # Se trunca al minuto para que los horarios de dosis sean comparables de forma exacta
    starts_at = starts_at.replace(second=0, microsecond=0)
    if ends_at is not None and ends_at <= starts_at:
        raise DomainError("La fecha de término debe ser posterior a la primera dosis.")
    return cleaned_dose, starts_at


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
    """Crea una indicación médica activa para un paciente ingresado.

    Precondiciones:
        - ``actor`` posee rol en ``NEONATOLOGIST_ONLY``.
        - El paciente existe y se encuentra en estado ``ACTIVE``.
        - El medicamento existe en el catálogo y está activo (``is_active=True``).

    Postcondiciones:
        - Persiste una ``Prescription`` en estado ``ACTIVE`` con ``starts_at`` truncado al minuto.
        - Registra la prescripción en la bitácora de auditoría vinculada al paciente.

    Invariante:
        - Toda indicación creada tiene ``units_per_administration >= 1`` y, si tiene ``ends_at``, es recurrente con ``ends_at > starts_at``.
    """
    require_role(
        actor,
        NEONATOLOGIST_ONLY,
        "Solo un Neonatólogo está autorizado para prescribir indicaciones médicas.",
    )

    cleaned_dose, starts_at = _validate_prescription_inputs(
        dose=dose,
        route=route,
        units_per_administration=units_per_administration,
        starts_at=starts_at,
        ends_at=ends_at,
        frequency_hours=frequency_hours,
    )

    with transaction.atomic():
        patient = lock_active_patient(
            patient_id,
            discharged_message="No se pueden crear indicaciones médicas para un paciente ya egresado.",
        )

        medication = (
            MedicationCatalogItem.objects.select_for_update().filter(pk=medication_id).first()
        )
        if medication is None:
            raise NotFoundDomainError("El medicamento seleccionado no existe en el catálogo.")
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

    assert prescription.pk is not None and prescription.status == PrescriptionStatus.ACTIVE, (
        "Postcondición fallida: la indicación médica no quedó persistida como vigente."
    )
    assert prescription.ends_at is None or (
        prescription.frequency_hours is not None and prescription.ends_at > prescription.starts_at
    ), "Invariante fallido: pauta temporal inconsistente en la indicación médica."
    return prescription


def _format_local(when: datetime) -> str:
    """Formatea una fecha con zona horaria en formato legible local ``DD-MM-YYYY HH:MM``."""
    return timezone.localtime(when).strftime("%d-%m-%Y %H:%M")


def _resolve_dose_slot(
    prescription: Prescription, scheduled_for: datetime | None, now: datetime
) -> datetime:
    """Determina la dosis a administrar: la indicada o la última vencida.

    Raises:
        ConflictDomainError: Si aún no corresponde administrar o la dosis es demasiado anticipada.
        DomainError: Si el horario indicado no pertenece a la pauta.
    """
    if scheduled_for is None:
        slot = schedule.latest_due_slot(prescription, now)
        if slot is None:
            raise ConflictDomainError(
                "Aún no corresponde administrar esta indicación; la primera dosis es el "
                f"{_format_local(prescription.starts_at)}."
            )
        return slot
    if not schedule.is_valid_slot(prescription, scheduled_for):
        raise DomainError(
            "El horario indicado no corresponde a una dosis programada de esta indicación.",
            details={"scheduled_for": ["Horario de dosis inválido."]},
        )
    if scheduled_for > now + schedule.EARLY_ADMINISTRATION_WINDOW:
        early_minutes = int(schedule.EARLY_ADMINISTRATION_WINDOW.total_seconds() // 60)
        raise ConflictDomainError(
            f"La dosis del {_format_local(scheduled_for)} aún no puede administrarse; "
            f"se permite con hasta {early_minutes} minutos de anticipación."
        )
    return scheduled_for


def administer_prescription(
    *,
    actor: User,
    prescription: Prescription,
    scheduled_for: datetime | None = None,
    notes: str = "",
    ip_address: str | None = None,
) -> MedicationAdministration:
    """Registra la administración de una dosis y descuenta el stock de forma atómica.

    Precondiciones:
        - ``actor`` posee rol clínico autorizado (``CLINICAL_STAFF``).
        - El paciente está activo, la indicación vigente y el medicamento activo con stock suficiente.
        - La toma correspondiente a ``scheduled_for`` no ha sido administrada previamente.

    Postcondiciones:
        - Descuenta exactamente ``units_per_administration`` del inventario del medicamento.
        - Crea un ``MedicationAdministration`` vinculado al turno programado y al profesional ejecutor.
        - Si la dosis corresponde al último turno de la pauta, transiciona la indicación a ``COMPLETED``.

    Invariante:
        - Conservación de inventario: ``stock_final == stock_inicial - units_deducted`` y ``stock_final >= 0``.
    """
    require_role(
        actor,
        CLINICAL_STAFF,
        "Solo un Neonatólogo o Matrona/Enfermera puede administrar medicamentos a un paciente.",
    )

    now = timezone.now()
    with transaction.atomic():
        locked_prescription = Prescription.objects.select_for_update().get(pk=prescription.pk)
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

        slot = _resolve_dose_slot(locked_prescription, scheduled_for, now)

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

        stock_before = locked_medication.stock
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
        is_final_slot = slot == schedule.last_slot(locked_prescription)
        if is_final_slot:
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

    assert administration.pk is not None, (
        "Postcondición fallida: el registro de administración no fue persistido."
    )
    assert (
        locked_medication.stock >= 0
        and locked_medication.stock == stock_before - administration.units_deducted
    ), "Invariante fallido: inconsistencia en el descuento atómico de inventario."
    assert not is_final_slot or locked_prescription.status == PrescriptionStatus.COMPLETED, (
        "Postcondición fallida: la indicación no se marcó como completada tras su última dosis."
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
    """Cancela una indicación médica vigente.

    Precondiciones:
        - ``actor`` posee rol en ``NEONATOLOGIST_ONLY``.
        - La indicación se encuentra actualmente en estado ``ACTIVE``.

    Postcondiciones:
        - La indicación pasa a estado ``CANCELLED`` con ``cancelled_at`` poblado y evento auditado.

    Invariante:
        - Toda indicación cancelada registra una marca temporal ``cancelled_at`` no nula.
    """
    require_role(
        actor, NEONATOLOGIST_ONLY, "Solo un Neonatólogo puede cancelar una indicación médica."
    )

    with transaction.atomic():
        locked_prescription = Prescription.objects.select_for_update().get(pk=prescription.pk)
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

    assert (
        locked_prescription.status == PrescriptionStatus.CANCELLED
        and locked_prescription.cancelled_at is not None
    ), "Postcondición fallida: la indicación no quedó cancelada con fecha de cierre."
    return locked_prescription


def cancel_pending_prescriptions_on_discharge(*, patient: Patient) -> int:
    """Cancela las indicaciones vigentes de un paciente que es egresado.

    Precondiciones:
        - ``patient`` corresponde a una instancia persistida de ``Patient``.

    Postcondiciones:
        - Todas las indicaciones ``ACTIVE`` del paciente quedan en estado ``CANCELLED`` con motivo de egreso.
        - Retorna el número entero no negativo de indicaciones actualizadas.

    Invariante:
        - Tras el egreso, el paciente no conserva ninguna indicación en estado ``ACTIVE``.
    """
    assert patient.pk is not None, "Precondición fallida: el paciente debe estar persistido."

    now = timezone.now()
    cancelled_count = Prescription.objects.filter(
        patient=patient,
        status=PrescriptionStatus.ACTIVE,
    ).update(
        status=PrescriptionStatus.CANCELLED,
        cancelled_at=now,
        cancellation_reason="Egreso del paciente",
        updated_at=now,
    )

    assert cancelled_count >= 0, (
        "Postcondición fallida: el conteo de indicaciones canceladas no puede ser negativo."
    )
    assert not Prescription.objects.filter(
        patient=patient, status=PrescriptionStatus.ACTIVE
    ).exists(), "Invariante fallido: quedaron indicaciones activas tras el egreso del paciente."

    return cancelled_count
