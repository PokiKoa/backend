"""Servicios de pacientes: ingreso, edición, egreso, cunas, peso, planes de cuidado y observaciones."""

from datetime import date
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from accounts.models import User, UserRole
from accounts.roles import (
    ADMIN_ONLY,
    CLINICAL_OR_ADMIN,
    CLINICAL_STAFF,
    NEONATOLOGIST_ONLY,
    require_role,
)
from audit.models import AuditAction
from audit.services import record_audit_event
from devices.models import Crib, CribStatus
from poki_koa.exceptions import (
    ConflictDomainError,
    DomainError,
    NotFoundDomainError,
    PermissionDomainError,
)

from .locks import lock_active_patient
from .models import (
    CarePlan,
    CarePlanStatus,
    ClinicalObservation,
    CribMovement,
    CribMovementKind,
    DischargeCause,
    DischargeOutcome,
    ObservationCategory,
    Patient,
    PatientSex,
    PatientStatus,
    WeightRecord,
)
from .validators import normalize_phone, normalize_rut

GUARDIAN_FIELDS: tuple[str, ...] = (
    "mother_rut",
    "mother_first_names",
    "mother_last_names",
    "mother_phone",
    "father_rut",
    "father_first_names",
    "father_last_names",
    "father_phone",
)
_GUARDIAN_LABELS = {"mother": "de la madre", "father": "del padre"}


def _clean_guardian_data(data: dict[str, Any]) -> dict[str, str]:
    """Normaliza los campos de madre/padre presentes en ``data``.

    Solo devuelve las claves informadas, para que una edición parcial no borre
    los datos que no se enviaron.
    """
    cleaned: dict[str, str] = {}
    for field in GUARDIAN_FIELDS:
        if field not in data:
            continue
        value = str(data[field] or "").strip()
        parent, _, kind = field.partition("_")
        label = _GUARDIAN_LABELS[parent]
        if kind == "rut":
            value = normalize_rut(value, label=label)
        elif kind == "phone":
            value = normalize_phone(value, label=label)
        cleaned[field] = value
    return cleaned


def _record_crib_movement(
    *,
    patient: Patient,
    kind: str,
    actor: User | None,
    from_crib: Crib | None = None,
    to_crib: Crib | None = None,
) -> CribMovement:
    """Registra una entrada inmutable en el historial de ubicaciones de cuna del paciente."""
    return CribMovement.objects.create(
        patient=patient,
        kind=kind,
        from_crib=from_crib,
        from_crib_code=from_crib.code if from_crib else "",
        to_crib=to_crib,
        to_crib_code=to_crib.code if to_crib else "",
        moved_by=actor,
    )


def _validate_attending_physician(physician_id: int | None) -> User | None:
    """Valida que el médico responsable exista, esté activo y tenga rol de Neonatólogo."""
    if physician_id is None:
        return None
    physician = User.objects.filter(pk=physician_id, is_active=True).first()
    if physician is None:
        raise NotFoundDomainError("El médico responsable indicado no existe o no está activo.")
    if physician.role != UserRole.NEONATOLOGIST:
        raise DomainError(
            "El profesional asignado como médico a cargo debe tener rol de Neonatólogo."
        )
    return physician


def _validate_crib_available(
    crib_id: int | None, current_patient_id: int | None = None
) -> Crib | None:
    """Bloquea y verifica que la cuna indicada exista, esté libre y operativa."""
    if crib_id is None:
        return None
    crib = Crib.objects.select_for_update().filter(pk=crib_id).first()
    if crib is None:
        raise NotFoundDomainError("La cuna indicada no existe.")
    occupant = getattr(crib, "current_patient", None)
    if occupant is not None and occupant.id != current_patient_id:
        raise ConflictDomainError("La cuna seleccionada ya está ocupada por otro paciente.")
    if crib.status in {CribStatus.MAINTENANCE, CribStatus.OFFLINE}:
        raise ConflictDomainError(
            "La cuna seleccionada no está disponible por encontrarse en mantenimiento o fuera de línea."
        )
    return crib


def _validate_admission_inputs(
    *,
    medical_record_number: str,
    full_name: str,
    sex: str,
    birth_date: date,
    gestational_age_weeks: Decimal | float,
    birth_weight_g: int,
    current_weight_g: int | None,
) -> tuple[str, str, Decimal, int]:
    """Valida y normaliza los datos de ingreso.

    Returns:
        Tupla ``(ficha, nombre, semanas_gestacionales, peso_actual_g)`` ya normalizada.

    Raises:
        DomainError: Si algún dato obligatorio falta o está fuera de rango.
    """
    mrn = (medical_record_number or "").strip().upper()
    cleaned_name = (full_name or "").strip()
    if not mrn:
        raise DomainError("El número de ficha clínica (medical_record_number) es obligatorio.")
    if not cleaned_name:
        raise DomainError("El nombre completo del paciente es obligatorio.")
    _normalize_sex(sex)
    _normalize_birth_date(birth_date)
    gest_weeks = _normalize_gestational_age(gestational_age_weeks)
    if not (200 <= birth_weight_g <= 8000):
        raise DomainError("El peso de nacimiento debe estar entre 200 y 8000 gramos.")
    effective_current_weight = _normalize_current_weight(
        birth_weight_g if current_weight_g is None else current_weight_g
    )
    return mrn, cleaned_name, gest_weeks, effective_current_weight


def admit_patient(
    *,
    actor: User,
    medical_record_number: str,
    full_name: str,
    sex: str,
    birth_date: date,
    gestational_age_weeks: Decimal | float,
    birth_weight_g: int,
    current_weight_g: int | None = None,
    diagnosis: str = "",
    attending_physician_id: int | None = None,
    crib_id: int | None = None,
    guardians: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> Patient:
    """Registra el ingreso de un recién nacido, con cuna y medición de peso inicial opcionales.

    Precondiciones:
        - ``actor`` posee rol en ``CLINICAL_STAFF`` (Neonatólogo o Matrona/Enfermera).
        - ``medical_record_number`` es único en el sistema y los parámetros neonatales están dentro de rango clínico.
        - Si se especifica ``crib_id``, la cuna existe, está desocupada y operativa.

    Postcondiciones:
        - Persiste un ``Patient`` en estado ``ACTIVE`` con su medición inicial en ``WeightRecord``.
        - Si se asignó cuna, esta pasa a estado ``OCCUPIED`` y se registra un ``CribMovement`` de tipo ``ASSIGN``.
        - Registra el evento de ingreso en la bitácora de auditoría.

    Invariante:
        - Todo paciente activo con cuna asignada mantiene una correspondencia biunívoca con una cuna en estado ``OCCUPIED``.
    """
    require_role(
        actor,
        CLINICAL_STAFF,
        "Solo Neonatólogos o Matronas/Enfermeras pueden registrar el ingreso de un paciente.",
    )
    guardian_data = _clean_guardian_data(guardians or {})
    mrn, cleaned_name, gest_weeks, effective_current_weight = _validate_admission_inputs(
        medical_record_number=medical_record_number,
        full_name=full_name,
        sex=sex,
        birth_date=birth_date,
        gestational_age_weeks=gestational_age_weeks,
        birth_weight_g=birth_weight_g,
        current_weight_g=current_weight_g,
    )

    with transaction.atomic():
        if Patient.objects.filter(medical_record_number=mrn).exists():
            raise ConflictDomainError(
                "Ya existe un paciente registrado con ese número de ficha clínica."
            )

        physician = _validate_attending_physician(attending_physician_id)
        crib = _validate_crib_available(crib_id)

        patient = Patient.objects.create(
            medical_record_number=mrn,
            full_name=cleaned_name,
            sex=sex,
            birth_date=birth_date,
            gestational_age_weeks=gest_weeks,
            birth_weight_g=birth_weight_g,
            current_weight_g=effective_current_weight,
            diagnosis=(diagnosis or "").strip(),
            attending_physician=physician,
            crib=crib,
            status=PatientStatus.ACTIVE,
            **guardian_data,
        )

        if crib is not None:
            crib.status = CribStatus.OCCUPIED
            crib.save(update_fields=["status", "updated_at"])
            _record_crib_movement(
                patient=patient, kind=CribMovementKind.ASSIGN, actor=actor, to_crib=crib
            )

        WeightRecord.objects.create(
            patient=patient,
            weight_g=effective_current_weight,
            recorded_by=actor,
        )

        record_audit_event(
            action=AuditAction.CREATE,
            resource_type="patient",
            resource_id=patient.id,
            actor_user=actor,
            patient_id=patient.id,
            changed_fields=[
                "medical_record_number",
                "full_name",
                "sex",
                "birth_date",
                "gestational_age_weeks",
                "birth_weight_g",
                "current_weight_g",
                "diagnosis",
                "attending_physician_id",
                "crib_id",
                *guardian_data.keys(),
            ],
            ip_address=ip_address,
        )

    assert patient.pk is not None and patient.status == PatientStatus.ACTIVE, (
        "Postcondición fallida: el paciente no quedó persistido como activo."
    )
    assert patient.crib is None or patient.crib.status == CribStatus.OCCUPIED, (
        "Invariante fallido: la cuna asignada al ingreso no quedó marcada como ocupada."
    )
    return patient


def _normalize_full_name(value: Any) -> str:
    """Normaliza y verifica que el nombre completo del paciente no esté vacío."""
    new_name = str(value).strip()
    if not new_name:
        raise DomainError("El nombre completo del paciente no puede estar vacío.")
    return new_name


def _normalize_sex(value: Any) -> str:
    """Valida que el sexo biológico corresponda a ``F`` o ``M``."""
    if value not in set(PatientSex.values):
        raise DomainError("El sexo del paciente debe ser 'F' o 'M'.")
    return value


def _normalize_birth_date(value: date) -> date:
    """Valida que la fecha de nacimiento no sea posterior a la fecha local actual."""
    if value > timezone.localdate():
        raise DomainError("La fecha de nacimiento no puede ser una fecha futura.")
    return value


def _normalize_gestational_age(value: Any) -> Decimal:
    """Convierte y valida que la edad gestacional esté entre 20.0 y 45.0 semanas."""
    weeks = Decimal(str(value))
    if not (Decimal("20.0") <= weeks <= Decimal("45.0")):
        raise DomainError("La edad gestacional debe estar entre 20.0 y 45.0 semanas.")
    return weeks


def _normalize_current_weight(value: Any) -> int:
    """Convierte y valida que el peso actual esté entre 200 y 10000 gramos."""
    weight = int(value)
    if not (200 <= weight <= 10000):
        raise DomainError("El peso actual debe estar entre 200 y 10000 gramos.")
    return weight


def _normalize_diagnosis(value: Any) -> str:
    """Limpia espacios laterales del texto de diagnóstico clínico."""
    return str(value or "").strip()


# Campos escalares editables: se validan/normalizan y se asignan solo si cambian.
# El orden define el orden de ``changed_fields`` en la auditoría.
_SCALAR_UPDATE_NORMALIZERS = {
    "full_name": _normalize_full_name,
    "sex": _normalize_sex,
    "birth_date": _normalize_birth_date,
    "gestational_age_weeks": _normalize_gestational_age,
    "current_weight_g": _normalize_current_weight,
    "diagnosis": _normalize_diagnosis,
}


def _apply_scalar_updates(patient: Patient, data: dict[str, Any], actor: User) -> list[str]:
    """Aplica en memoria los campos escalares enviados y devuelve los que cambiaron."""
    changed: list[str] = []
    for field, normalize in _SCALAR_UPDATE_NORMALIZERS.items():
        if field not in data:
            continue
        new_value = normalize(data[field])
        if new_value == getattr(patient, field):
            continue
        setattr(patient, field, new_value)
        changed.append(field)
        if field == "current_weight_g":
            WeightRecord.objects.create(patient=patient, weight_g=new_value, recorded_by=actor)
    return changed


def _apply_physician_update(patient: Patient, data: dict[str, Any]) -> list[str]:
    """Actualiza el médico tratante si fue enviado y difiere del actual."""
    if "attending_physician_id" not in data:
        return []
    new_physician = _validate_attending_physician(data["attending_physician_id"])
    new_id = new_physician.id if new_physician else None
    if new_id == patient.attending_physician_id:
        return []
    patient.attending_physician = new_physician
    return ["attending_physician_id"]


def _apply_guardian_updates(patient: Patient, data: dict[str, Any]) -> list[str]:
    """Actualiza los datos normalizados de madre/padre que hayan cambiado."""
    changed: list[str] = []
    for field, value in _clean_guardian_data(data).items():
        if value != getattr(patient, field):
            setattr(patient, field, value)
            changed.append(field)
    return changed


def _crib_movement_kind(old_crib: Crib | None, new_crib: Crib | None) -> str:
    """Determina el tipo de movimiento según la cuna de origen y destino."""
    if old_crib is None:
        return CribMovementKind.ASSIGN
    if new_crib is None:
        return CribMovementKind.RELEASE
    return CribMovementKind.MOVE


def _apply_crib_change(patient: Patient, data: dict[str, Any], actor: User) -> list[str]:
    """Reasigna la cuna del paciente, actualiza el estado de ambas cunas y registra el movimiento."""
    if "crib_id" not in data or data["crib_id"] == patient.crib_id:
        return []
    old_crib = patient.crib
    new_crib = _validate_crib_available(data["crib_id"], current_patient_id=patient.id)
    patient.crib = new_crib
    # Liberar primero en el paciente antes de actualizar las cunas
    patient.save()
    if old_crib is not None:
        old_crib.status = CribStatus.AVAILABLE
        old_crib.save(update_fields=["status", "updated_at"])
    if new_crib is not None:
        new_crib.status = CribStatus.OCCUPIED
        new_crib.save(update_fields=["status", "updated_at"])
    _record_crib_movement(
        patient=patient,
        kind=_crib_movement_kind(old_crib, new_crib),
        actor=actor,
        from_crib=old_crib,
        to_crib=new_crib,
    )
    return ["crib_id"]


def update_patient(
    *,
    actor: User,
    patient: Patient,
    data: dict[str, Any],
    ip_address: str | None = None,
) -> Patient:
    """Actualiza parcialmente los datos de un paciente activo y audita los campos modificados.

    Precondiciones:
        - ``actor`` posee rol en ``CLINICAL_STAFF``; si ``data`` incluye ``diagnosis`` o ``attending_physician_id``, ``actor`` debe ser Neonatólogo.
        - El paciente existe y permanece en estado ``ACTIVE``.

    Postcondiciones:
        - Persiste únicamente los campos validados que cambiaron y registra un evento ``UPDATE`` en auditoría si hubo modificaciones.
        - Si cambió ``current_weight_g``, crea automáticamente un ``WeightRecord`` sincronizado.

    Invariante:
        - Si el paciente queda con una cuna asignada, dicha cuna tiene estado ``OCCUPIED``.
    """
    require_role(
        actor, CLINICAL_STAFF, "Solo el personal clínico puede modificar datos de un paciente."
    )

    # Permiso por objeto/campo: diagnóstico y médico tratante son exclusivos de Neonatólogo
    restricted_medical_fields = {"diagnosis", "attending_physician_id"}
    if actor.role == UserRole.NURSE and restricted_medical_fields.intersection(data.keys()):
        raise PermissionDomainError(
            "Solo un Neonatólogo puede modificar el diagnóstico médico o el médico tratante."
        )

    with transaction.atomic():
        locked_patient = lock_active_patient(
            patient.pk,
            discharged_message="No se pueden modificar los datos clínicos de un paciente ya egresado.",
        )

        changed_fields = [
            *_apply_scalar_updates(locked_patient, data, actor),
            *_apply_physician_update(locked_patient, data),
            *_apply_guardian_updates(locked_patient, data),
            *_apply_crib_change(locked_patient, data, actor),
        ]

        if changed_fields:
            locked_patient.save()
            record_audit_event(
                action=AuditAction.UPDATE,
                resource_type="patient",
                resource_id=locked_patient.id,
                actor_user=actor,
                patient_id=locked_patient.id,
                changed_fields=changed_fields,
                ip_address=ip_address,
            )

    assert locked_patient.status == PatientStatus.ACTIVE, (
        "Invariante fallido: la edición cambió indebidamente el estado de actividad del paciente."
    )
    assert locked_patient.crib is None or locked_patient.crib.status == CribStatus.OCCUPIED, (
        "Invariante fallido: la cuna vinculada al paciente no figura como ocupada."
    )
    return locked_patient


def discharge_patient(
    *,
    actor: User,
    patient: Patient,
    outcome: str,
    cause: str | None = None,
    notes: str = "",
    ip_address: str | None = None,
) -> Patient:
    """Egresa a un paciente (alta, traslado o fallecimiento) y libera su cuna.

    Precondiciones:
        - ``actor`` posee rol en ``NEONATOLOGIST_ONLY``.
        - El paciente está en estado ``ACTIVE`` y ``outcome`` pertenece a ``DischargeOutcome``.
        - Si ``outcome == DischargeOutcome.DECEASED``, ``cause`` es obligatoria y distinta de ``DischargeCause.NONE``.

    Postcondiciones:
        - El paciente transiciona a estado terminal (``DISCHARGED``, ``TRANSFERRED`` o ``DECEASED``) con ``discharged_at`` y ``discharged_by`` poblados.
        - Se desvincula y libera la cuna ocupada (``crib is None`` y ``old_crib.status == AVAILABLE``).
        - Se finalizan sus planes de cuidado activos, se resuelven sus alertas y se cancelan sus prescripciones vigentes.

    Invariante:
        - Ningún paciente egresado puede conservar una cuna asignada ni indicaciones médicas activas.
    """
    require_role(
        actor,
        NEONATOLOGIST_ONLY,
        "Solo un Neonatólogo está autorizado para firmar el egreso clínico de un paciente.",
    )
    if outcome not in set(DischargeOutcome.values):
        raise DomainError("El desenlace clínico de egreso no es válido.")

    effective_cause = cause or DischargeCause.NONE
    if effective_cause not in set(DischargeCause.values):
        raise DomainError("La causa de egreso especificada no es válida.")
    if outcome == DischargeOutcome.DECEASED and effective_cause == DischargeCause.NONE:
        raise DomainError(
            "Cuando el desenlace es fallecimiento, debe especificarse la causa clínica neonatal."
        )

    with transaction.atomic():
        locked_patient = lock_active_patient(
            patient.pk, discharged_message="El paciente ya fue egresado previamente."
        )

        old_crib = (
            Crib.objects.select_for_update().get(pk=locked_patient.crib_id)
            if locked_patient.crib_id is not None
            else None
        )
        if outcome == DischargeOutcome.DECEASED:
            new_status = PatientStatus.DECEASED
        elif outcome == DischargeOutcome.TRANSFERRED:
            new_status = PatientStatus.TRANSFERRED
        else:
            new_status = PatientStatus.DISCHARGED

        locked_patient.status = new_status
        locked_patient.discharged_at = timezone.now()
        locked_patient.discharge_outcome = outcome
        locked_patient.discharge_cause = effective_cause
        locked_patient.discharge_notes = (notes or "").strip()
        locked_patient.discharged_by = actor
        locked_patient.crib = None
        locked_patient.save()

        if old_crib is not None:
            old_crib.status = CribStatus.AVAILABLE
            old_crib.save(update_fields=["status", "updated_at"])
            _record_crib_movement(
                patient=locked_patient,
                kind=CribMovementKind.DISCHARGE,
                actor=actor,
                from_crib=old_crib,
            )

        # Suspender planes de cuidado activos y resolver alertas pendientes al momento del egreso
        locked_patient.care_plans.filter(status=CarePlanStatus.ACTIVE).update(
            status=CarePlanStatus.COMPLETED,
            updated_at=timezone.now(),
        )
        from alerts.services import resolve_patient_alerts_on_discharge
        from medications.services import cancel_pending_prescriptions_on_discharge

        resolve_patient_alerts_on_discharge(patient=locked_patient, actor=actor)
        cancel_pending_prescriptions_on_discharge(patient=locked_patient)

        record_audit_event(
            action=AuditAction.DISCHARGE,
            resource_type="patient",
            resource_id=locked_patient.id,
            actor_user=actor,
            patient_id=locked_patient.id,
            changed_fields=[
                "status",
                "discharged_at",
                "discharge_outcome",
                "discharge_cause",
                "discharge_notes",
                "discharged_by_id",
                "crib_id",
            ],
            ip_address=ip_address,
        )

    assert (
        locked_patient.status != PatientStatus.ACTIVE
        and locked_patient.discharged_at is not None
        and locked_patient.discharged_by_id == actor.id
    ), "Postcondición fallida: el paciente no registró correctamente los metadatos de egreso."
    assert locked_patient.crib_id is None and (
        old_crib is None or old_crib.status == CribStatus.AVAILABLE
    ), "Invariante fallido: la cuna no quedó liberada tras el egreso del paciente."
    return locked_patient


def assign_patient_to_crib(
    *,
    actor: User,
    crib: Crib,
    patient_id: int,
    ip_address: str | None = None,
) -> Crib:
    """Asigna un paciente activo a una cuna disponible.

    Precondiciones:
        - ``actor`` posee rol en ``CLINICAL_OR_ADMIN``.
        - ``crib`` está operativa (no en mantenimiento ni fuera de línea) y no ocupada por otro paciente.
        - El paciente existe, está ``ACTIVE`` y no ocupa ya esa misma cuna.

    Postcondiciones:
        - Si el paciente ocupaba otra cuna, esta pasa a ``AVAILABLE``.
        - ``patient.crib`` apunta a ``crib``, ``crib.status`` pasa a ``OCCUPIED`` y se registra el movimiento (``ASSIGN`` o ``MOVE``).

    Invariante:
        - Toda cuna retornada queda en estado ``OCCUPIED`` con su ``current_patient`` vinculado.
    """
    require_role(
        actor,
        CLINICAL_OR_ADMIN,
        "Solo el personal clínico o administrativo puede asignar pacientes a una cuna.",
    )
    with transaction.atomic():
        locked_crib = Crib.objects.select_for_update().get(pk=crib.pk)
        locked_patient = lock_active_patient(
            patient_id,
            discharged_message="No se puede asignar una cuna a un paciente que ya fue egresado.",
        )
        if locked_crib.status in {CribStatus.MAINTENANCE, CribStatus.OFFLINE}:
            raise ConflictDomainError("La cuna no se encuentra disponible para asignación.")

        current_occupant = getattr(locked_crib, "current_patient", None)
        if current_occupant is not None and current_occupant.id != locked_patient.id:
            raise ConflictDomainError("La cuna ya se encuentra ocupada por otro paciente.")

        previous_crib = locked_patient.crib
        if previous_crib is not None and previous_crib.id == locked_crib.id:
            raise ConflictDomainError("El paciente ya se encuentra en esa cuna.")
        if previous_crib is not None:
            locked_patient.crib = None
            locked_patient.save(update_fields=["crib", "updated_at"])
            previous_crib.status = CribStatus.AVAILABLE
            previous_crib.save(update_fields=["status", "updated_at"])

        locked_patient.crib = locked_crib
        locked_patient.save(update_fields=["crib", "updated_at"])

        locked_crib.status = CribStatus.OCCUPIED
        locked_crib.save(update_fields=["status", "updated_at"])
        _record_crib_movement(
            patient=locked_patient,
            kind=CribMovementKind.MOVE if previous_crib else CribMovementKind.ASSIGN,
            actor=actor,
            from_crib=previous_crib,
            to_crib=locked_crib,
        )

        record_audit_event(
            action=AuditAction.ASSIGN_CRIB,
            resource_type="crib",
            resource_id=locked_crib.id,
            actor_user=actor,
            patient_id=locked_patient.id,
            changed_fields=["crib_id", "status"],
            ip_address=ip_address,
        )

    locked_crib.refresh_from_db()
    assert (
        locked_crib.status == CribStatus.OCCUPIED
        and getattr(locked_crib, "current_patient", None) is not None
        and locked_crib.current_patient.id == patient_id
    ), "Postcondición fallida: la cuna no quedó ocupada por el paciente asignado."
    return locked_crib


def release_patient_from_crib(
    *,
    actor: User,
    crib: Crib,
    ip_address: str | None = None,
) -> Crib:
    """Libera una cuna ocupada, desasignando a su paciente.

    Precondiciones:
        - ``actor`` posee rol en ``CLINICAL_OR_ADMIN``.
        - La cuna se encuentra actualmente ocupada por un paciente.

    Postcondiciones:
        - El paciente queda sin cuna asignada (``crib is None``) manteniendo su estado clínico.
        - La cuna transiciona a estado ``AVAILABLE`` y se registra un movimiento de tipo ``RELEASE``.

    Invariante:
        - La cuna retornada queda en estado ``AVAILABLE`` sin paciente asociado.
    """
    require_role(
        actor,
        CLINICAL_OR_ADMIN,
        "Solo el personal clínico o administrativo puede liberar una cuna.",
    )
    with transaction.atomic():
        locked_crib = Crib.objects.select_for_update().get(pk=crib.pk)
        occupant = getattr(locked_crib, "current_patient", None)
        if occupant is None:
            raise ConflictDomainError("La cuna ya se encuentra libre.")

        patient_id = occupant.id
        occupant.crib = None
        occupant.save(update_fields=["crib", "updated_at"])

        locked_crib.status = CribStatus.AVAILABLE
        locked_crib.save(update_fields=["status", "updated_at"])
        _record_crib_movement(
            patient=occupant,
            kind=CribMovementKind.RELEASE,
            actor=actor,
            from_crib=locked_crib,
        )

        record_audit_event(
            action=AuditAction.RELEASE_CRIB,
            resource_type="crib",
            resource_id=locked_crib.id,
            actor_user=actor,
            patient_id=patient_id,
            changed_fields=["crib_id", "status"],
            ip_address=ip_address,
        )

    locked_crib.refresh_from_db()
    assert (
        locked_crib.status == CribStatus.AVAILABLE
        and getattr(locked_crib, "current_patient", None) is None
    ), "Postcondición fallida: la cuna no quedó libre y disponible."
    return locked_crib


def swap_patients_between_cribs(
    *,
    actor: User,
    crib: Crib,
    other_crib_id: int,
    ip_address: str | None = None,
) -> tuple[Crib, Crib]:
    """Intercambia a los pacientes de dos cunas ocupadas en una sola operación.

    Precondiciones:
        - ``actor`` posee rol en ``CLINICAL_OR_ADMIN``.
        - ``crib.pk != other_crib_id`` y ambas cunas existen, están operativas y ocupadas por sendos pacientes.

    Postcondiciones:
        - El ocupante inicial de ``crib`` pasa a ocupar ``other_crib`` y viceversa.
        - Ambos pacientes registran un ``CribMovement`` de tipo ``SWAP`` y su evento de auditoría.

    Invariante:
        - Conservación de ocupación: ambas cunas permanecen ocupadas y ninguno de los dos pacientes queda sin cuna.
    """
    require_role(
        actor,
        CLINICAL_OR_ADMIN,
        "Solo el personal clínico o administrativo puede intercambiar pacientes de cuna.",
    )
    if crib.pk == other_crib_id:
        raise DomainError("Selecciona dos cunas distintas para el intercambio.")

    with transaction.atomic():
        # Bloquear siempre en el mismo orden evita interbloqueos entre intercambios simultáneos
        locked = {
            c.pk: c
            for c in Crib.objects.select_for_update()
            .filter(pk__in=[crib.pk, other_crib_id])
            .order_by("pk")
        }
        if other_crib_id not in locked:
            raise NotFoundDomainError("La cuna de destino no existe.")
        first_crib, second_crib = locked[crib.pk], locked[other_crib_id]

        for target in (first_crib, second_crib):
            if target.status in {CribStatus.MAINTENANCE, CribStatus.OFFLINE}:
                raise ConflictDomainError(
                    f"La cuna {target.code} está en mantenimiento o fuera de línea."
                )

        first_patient = Patient.objects.select_for_update().filter(crib=first_crib).first()
        second_patient = Patient.objects.select_for_update().filter(crib=second_crib).first()
        if first_patient is None or second_patient is None:
            raise ConflictDomainError(
                "Ambas cunas deben estar ocupadas para intercambiar pacientes; "
                "para una cuna libre usa la asignación."
            )

        first_patient_id = first_patient.id
        second_patient_id = second_patient.id

        # La relación uno a uno exige soltar una cuna antes de ocuparla con el otro paciente
        first_patient.crib = None
        first_patient.save(update_fields=["crib", "updated_at"])
        second_patient.crib = first_crib
        second_patient.save(update_fields=["crib", "updated_at"])
        first_patient.crib = second_crib
        first_patient.save(update_fields=["crib", "updated_at"])

        for patient, origin, destination in (
            (first_patient, first_crib, second_crib),
            (second_patient, second_crib, first_crib),
        ):
            _record_crib_movement(
                patient=patient,
                kind=CribMovementKind.SWAP,
                actor=actor,
                from_crib=origin,
                to_crib=destination,
            )
            record_audit_event(
                action=AuditAction.SWAP_CRIB,
                resource_type="crib",
                resource_id=destination.id,
                actor_user=actor,
                patient_id=patient.id,
                changed_fields=["crib_id"],
                ip_address=ip_address,
            )

    first_crib.refresh_from_db()
    second_crib.refresh_from_db()
    assert (
        getattr(first_crib, "current_patient", None) is not None
        and getattr(second_crib, "current_patient", None) is not None
        and first_crib.current_patient.id == second_patient_id
        and second_crib.current_patient.id == first_patient_id
    ), "Postcondición fallida: los ocupantes no quedaron intercambiados correctamente."
    return first_crib, second_crib


def delete_patient_permanently(
    *,
    actor: User,
    patient: Patient,
    confirmation: str,
    ip_address: str | None = None,
) -> None:
    """Elimina al paciente y todo su registro clínico sin posibilidad de recuperarlo.

    Precondiciones:
        - ``actor`` posee rol en ``ADMIN_ONLY``.
        - ``confirmation`` normalizada coincide exactamente con ``patient.medical_record_number``.

    Postcondiciones:
        - El registro del paciente y todos sus registros clínicos dependientes son eliminados de la base de datos.
        - Si el paciente ocupaba una cuna, dicha cuna queda en estado ``AVAILABLE``.
        - Se conserva el evento ``DELETE`` en la bitácora de auditoría.

    Invariante:
        - No quedan registros huérfanos del paciente ni cunas bloqueadas por el registro eliminado.
    """
    require_role(
        actor, ADMIN_ONLY, "Solo un Administrador puede eliminar definitivamente a un paciente."
    )
    if (confirmation or "").strip().upper() != patient.medical_record_number:
        raise DomainError(
            "Para confirmar, escribe exactamente el número de ficha clínica del paciente."
        )

    from alerts.models import Alert
    from medications.models import MedicationAdministration, Prescription
    from vitals.models import VitalSignReading

    with transaction.atomic():
        locked_patient = Patient.objects.select_for_update().get(pk=patient.pk)
        patient_id = locked_patient.id
        crib_id = locked_patient.crib_id

        if crib_id is not None:
            crib = Crib.objects.select_for_update().get(pk=crib_id)
            locked_patient.crib = None
            locked_patient.save(update_fields=["crib", "updated_at"])
            crib.status = CribStatus.AVAILABLE
            crib.save(update_fields=["status", "updated_at"])

        # Orden inverso a las dependencias: primero lo que apunta a otros registros del paciente
        MedicationAdministration.objects.filter(prescription__patient_id=patient_id).delete()
        Prescription.objects.filter(patient_id=patient_id).delete()
        Alert.objects.filter(patient_id=patient_id).delete()
        VitalSignReading.objects.filter(patient_id=patient_id).delete()
        WeightRecord.objects.filter(patient_id=patient_id).delete()
        CarePlan.objects.filter(patient_id=patient_id).delete()
        ClinicalObservation.objects.filter(patient_id=patient_id).delete()
        CribMovement.objects.filter(patient_id=patient_id).delete()
        locked_patient.delete()

        record_audit_event(
            action=AuditAction.DELETE,
            resource_type="patient",
            resource_id=patient_id,
            actor_user=actor,
            patient_id=patient_id,
            changed_fields=[],
            ip_address=ip_address,
        )

    assert not Patient.objects.filter(pk=patient_id).exists(), (
        "Postcondición fallida: el registro del paciente no fue eliminado."
    )
    assert (
        crib_id is None or Crib.objects.filter(pk=crib_id, status=CribStatus.AVAILABLE).exists()
    ), "Invariante fallido: la cuna ocupada no quedó liberada tras el borrado."


def record_patient_weight(
    *,
    actor: User,
    patient: Patient,
    weight_g: int,
    ip_address: str | None = None,
) -> WeightRecord:
    """Registra una medición de peso y actualiza el peso actual del paciente.

    Precondiciones:
        - ``actor`` posee rol en ``CLINICAL_STAFF``.
        - ``200 <= weight_g <= 10000`` y el paciente se encuentra en estado ``ACTIVE``.

    Postcondiciones:
        - Retorna el ``WeightRecord`` correspondiente (reutilizando el último si el valor no varió).
        - Si hubo variación, actualiza ``patient.current_weight_g == weight_g`` y audita el cambio.

    Invariante:
        - El ``current_weight_g`` del paciente coincide con el último punto de su curva ponderal.
    """
    require_role(
        actor, CLINICAL_STAFF, "Solo el personal clínico puede registrar mediciones de peso."
    )
    if not (200 <= weight_g <= 10000):
        raise DomainError("El peso registrado debe estar entre 200 y 10000 gramos.")

    with transaction.atomic():
        locked_patient = lock_active_patient(
            patient.pk,
            discharged_message="No se pueden añadir registros de peso a un paciente egresado.",
        )

        # Deduplicación: si el último punto registrado tiene el mismo peso, no duplica fila
        last_record = locked_patient.weight_records.order_by("-recorded_at", "-id").first()
        if last_record is not None and last_record.weight_g == weight_g:
            return last_record

        weight_record = WeightRecord.objects.create(
            patient=locked_patient,
            weight_g=weight_g,
            recorded_by=actor,
        )
        locked_patient.current_weight_g = weight_g
        locked_patient.save(update_fields=["current_weight_g", "updated_at"])

        record_audit_event(
            action=AuditAction.UPDATE,
            resource_type="patient",
            resource_id=locked_patient.id,
            actor_user=actor,
            patient_id=locked_patient.id,
            changed_fields=["current_weight_g"],
            ip_address=ip_address,
        )

    assert weight_record.pk is not None and weight_record.weight_g == weight_g, (
        "Postcondición fallida: la medición de peso no se registró correctamente."
    )
    assert locked_patient.current_weight_g == weight_g, (
        "Invariante fallido: el peso actual del paciente no coincide con el último registro."
    )
    return weight_record


def create_care_plan(
    *,
    actor: User,
    patient_id: int,
    care_area: str,
    intervention: str,
    frequency: str,
    status: str = CarePlanStatus.ACTIVE,
    ip_address: str | None = None,
) -> CarePlan:
    """Crea un plan de cuidado para un paciente activo.

    Precondiciones:
        - ``actor`` posee rol en ``CLINICAL_STAFF``.
        - ``care_area``, ``intervention`` y ``frequency`` son cadenas no vacías y ``status`` pertenece a ``CarePlanStatus``.
        - El paciente existe y permanece en estado ``ACTIVE``.

    Postcondiciones:
        - Persiste un ``CarePlan`` vinculado al paciente y registra la creación en auditoría.

    Invariante:
        - Todo plan de cuidado persistido tiene área, intervención y frecuencia no vacías.
    """
    require_role(actor, CLINICAL_STAFF, "Solo el personal clínico puede crear planes de cuidado.")
    if status not in set(CarePlanStatus.values):
        raise DomainError("El estado del plan de cuidado no es válido.")

    cleaned_area = (care_area or "").strip()
    cleaned_intervention = (intervention or "").strip()
    cleaned_freq = (frequency or "").strip()
    if not cleaned_area or not cleaned_intervention or not cleaned_freq:
        raise DomainError("El área de cuidado, la intervención y la frecuencia son obligatorias.")

    with transaction.atomic():
        patient = lock_active_patient(
            patient_id,
            discharged_message="No se pueden crear planes de cuidado para un paciente egresado.",
        )

        plan = CarePlan.objects.create(
            patient=patient,
            care_area=cleaned_area,
            intervention=cleaned_intervention,
            frequency=cleaned_freq,
            status=status,
            created_by=actor,
        )
        record_audit_event(
            action=AuditAction.CREATE,
            resource_type="care_plan",
            resource_id=plan.id,
            actor_user=actor,
            patient_id=patient.id,
            changed_fields=["care_area", "intervention", "frequency", "status"],
            ip_address=ip_address,
        )

    assert plan.pk is not None and plan.patient_id == patient_id, (
        "Postcondición fallida: el plan de cuidado no quedó persistido."
    )
    assert bool(plan.care_area and plan.intervention and plan.frequency), (
        "Invariante fallido: plan de cuidado con campos obligatorios vacíos."
    )
    return plan


def update_care_plan(
    *,
    actor: User,
    care_plan: CarePlan,
    data: dict[str, Any],
    ip_address: str | None = None,
) -> CarePlan:
    """Actualiza parcialmente un plan de cuidado de un paciente activo.

    Precondiciones:
        - ``actor`` posee rol en ``CLINICAL_STAFF``.
        - Los campos textuales informados no están vacíos y ``status`` (si se envía) pertenece a ``CarePlanStatus``.

    Postcondiciones:
        - Persiste únicamente los campos modificados del ``CarePlan`` y audita el cambio si hubo variación.

    Invariante:
        - Ningún plan de cuidado actualizado queda con área, intervención o frecuencia vacía.
    """
    require_role(
        actor, CLINICAL_STAFF, "Solo el personal clínico puede actualizar planes de cuidado."
    )

    with transaction.atomic():
        locked_plan = CarePlan.objects.select_for_update().get(pk=care_plan.pk)
        changed_fields: list[str] = []

        for text_field in ("care_area", "intervention", "frequency"):
            if text_field in data:
                val = str(data[text_field]).strip()
                if not val:
                    raise DomainError(f"El campo '{text_field}' no puede estar vacío.")
                if val != getattr(locked_plan, text_field):
                    setattr(locked_plan, text_field, val)
                    changed_fields.append(text_field)

        if "status" in data:
            new_status = data["status"]
            if new_status not in set(CarePlanStatus.values):
                raise DomainError("El estado del plan de cuidado no es válido.")
            if new_status != locked_plan.status:
                locked_plan.status = new_status
                changed_fields.append("status")

        if changed_fields:
            locked_plan.save()
            record_audit_event(
                action=AuditAction.UPDATE,
                resource_type="care_plan",
                resource_id=locked_plan.id,
                actor_user=actor,
                patient_id=locked_plan.patient_id,
                changed_fields=changed_fields,
                ip_address=ip_address,
            )

    assert bool(locked_plan.care_area and locked_plan.intervention and locked_plan.frequency), (
        "Invariante fallido: plan de cuidado actualizado con campos obligatorios vacíos."
    )
    return locked_plan


def create_clinical_observation(
    *,
    actor: User,
    patient_id: int,
    content: str,
    category: str = ObservationCategory.GENERAL,
    ip_address: str | None = None,
) -> ClinicalObservation:
    """Registra una observación clínica sobre un paciente activo.

    Precondiciones:
        - ``actor`` posee rol en ``CLINICAL_STAFF``.
        - ``category`` pertenece a ``ObservationCategory`` y ``content`` contiene texto no vacío.
        - El paciente existe y permanece en estado ``ACTIVE``.

    Postcondiciones:
        - Persiste una ``ClinicalObservation`` asociada al paciente y al autor, auditando su creación.

    Invariante:
        - Toda observación clínica persistida conserva contenido no vacío y autor identificado.
    """
    require_role(
        actor, CLINICAL_STAFF, "Solo el personal clínico puede registrar observaciones clínicas."
    )
    if category not in set(ObservationCategory.values):
        raise DomainError("La categoría de observación clínica no es válida.")
    cleaned_content = (content or "").strip()
    if not cleaned_content:
        raise DomainError("El contenido de la observación clínica no puede estar vacío.")

    with transaction.atomic():
        patient = lock_active_patient(
            patient_id,
            discharged_message="No se pueden agregar observaciones a un paciente ya egresado.",
        )

        observation = ClinicalObservation.objects.create(
            patient=patient,
            author=actor,
            category=category,
            content=cleaned_content,
        )
        record_audit_event(
            action=AuditAction.CREATE,
            resource_type="observation",
            resource_id=observation.id,
            actor_user=actor,
            patient_id=patient.id,
            changed_fields=["category", "content"],
            ip_address=ip_address,
        )

    assert observation.pk is not None and observation.author_id == actor.id, (
        "Postcondición fallida: la observación clínica no quedó persistida."
    )
    assert bool(observation.content), (
        "Invariante fallido: observación clínica persistida sin contenido."
    )
    return observation
