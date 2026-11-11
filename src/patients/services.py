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

    Args:
        actor: Neonatólogo o Matrona/Enfermera que ingresa al paciente.
        medical_record_number: Ficha clínica única (se normaliza a mayúsculas).
        full_name: Nombre completo.
        sex: ``F`` o ``M``.
        birth_date: Fecha de nacimiento (no futura).
        gestational_age_weeks: Edad gestacional, entre 20 y 45 semanas.
        birth_weight_g: Peso de nacimiento, entre 200 y 8000 g.
        current_weight_g: Peso actual; por defecto el de nacimiento.
        diagnosis: Diagnóstico inicial.
        attending_physician_id: Neonatólogo a cargo.
        crib_id: Cuna a asignar.
        guardians: Datos de madre y padre (RUT y teléfono se normalizan).
        ip_address: IP de origen para la auditoría.

    Returns:
        El paciente creado.

    Raises:
        PermissionDomainError: Si el rol no puede ingresar pacientes.
        ConflictDomainError: Ficha duplicada o cuna no disponible.
        NotFoundDomainError: Si el médico o la cuna no existen.
        DomainError: Si algún dato es inválido o está fuera de rango.
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

    return patient


def _normalize_full_name(value: Any) -> str:
    new_name = str(value).strip()
    if not new_name:
        raise DomainError("El nombre completo del paciente no puede estar vacío.")
    return new_name


def _normalize_sex(value: Any) -> str:
    if value not in set(PatientSex.values):
        raise DomainError("El sexo del paciente debe ser 'F' o 'M'.")
    return value


def _normalize_birth_date(value: date) -> date:
    if value > timezone.localdate():
        raise DomainError("La fecha de nacimiento no puede ser una fecha futura.")
    return value


def _normalize_gestational_age(value: Any) -> Decimal:
    weeks = Decimal(str(value))
    if not (Decimal("20.0") <= weeks <= Decimal("45.0")):
        raise DomainError("La edad gestacional debe estar entre 20.0 y 45.0 semanas.")
    return weeks


def _normalize_current_weight(value: Any) -> int:
    weight = int(value)
    if not (200 <= weight <= 10000):
        raise DomainError("El peso actual debe estar entre 200 y 10000 gramos.")
    return weight


def _normalize_diagnosis(value: Any) -> str:
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
    if "attending_physician_id" not in data:
        return []
    new_physician = _validate_attending_physician(data["attending_physician_id"])
    new_id = new_physician.id if new_physician else None
    if new_id == patient.attending_physician_id:
        return []
    patient.attending_physician = new_physician
    return ["attending_physician_id"]


def _apply_guardian_updates(patient: Patient, data: dict[str, Any]) -> list[str]:
    changed: list[str] = []
    for field, value in _clean_guardian_data(data).items():
        if value != getattr(patient, field):
            setattr(patient, field, value)
            changed.append(field)
    return changed


def _crib_movement_kind(old_crib: Crib | None, new_crib: Crib | None) -> str:
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

    Args:
        actor: Usuario que realiza el cambio (Neonatólogo o Matrona/Enfermera).
        patient: Paciente a modificar; se vuelve a leer con bloqueo de fila.
        data: Solo los campos a cambiar. ``diagnosis`` y ``attending_physician_id``
            son exclusivos de Neonatólogo.
        ip_address: IP de origen para la auditoría.

    Returns:
        El paciente actualizado.

    Raises:
        PermissionDomainError: Si el rol no puede editar pacientes o la enfermera
            intenta cambiar campos médicos restringidos.
        ConflictDomainError: Si el paciente ya fue egresado o la cuna no está disponible.
        NotFoundDomainError: Si el médico o la cuna indicados no existen.
        DomainError: Si algún valor está fuera de rango o es inválido.
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
        locked_patient = Patient.objects.select_for_update().get(pk=patient.pk)
        if locked_patient.status != PatientStatus.ACTIVE:
            raise ConflictDomainError(
                "No se pueden modificar los datos clínicos de un paciente ya egresado."
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

    Args:
        actor: Neonatólogo que firma el egreso.
        patient: Paciente activo.
        outcome: Desenlace (``DischargeOutcome``).
        cause: Causa clínica; obligatoria si el desenlace es fallecimiento.
        notes: Observaciones de egreso.
        ip_address: IP de origen para la auditoría.

    Returns:
        El paciente egresado.

    Raises:
        PermissionDomainError: Si el actor no es Neonatólogo.
        ConflictDomainError: Si el paciente ya fue egresado.
        DomainError: Si el desenlace o la causa son inválidos.
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
        locked_patient = Patient.objects.select_for_update().get(pk=patient.pk)
        if locked_patient.status != PatientStatus.ACTIVE:
            raise ConflictDomainError("El paciente ya fue egresado previamente.")

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

    return locked_patient


def assign_patient_to_crib(
    *,
    actor: User,
    crib: Crib,
    patient_id: int,
    ip_address: str | None = None,
) -> Crib:
    """Asigna un paciente activo a una cuna disponible.

    Args:
        actor: Neonatólogo o Matrona/Enfermera.
        crib: Cuna destino; se relee con bloqueo de fila.
        patient_id: Paciente a asignar.
        ip_address: IP de origen para la auditoría.

    Returns:
        La cuna ocupada.

    Raises:
        PermissionDomainError: Si el rol no puede asignar cunas.
        NotFoundDomainError: Si el paciente no existe.
        ConflictDomainError: Cuna no disponible u ocupada, o paciente ya asignado a ella.
    """
    require_role(
        actor,
        CLINICAL_OR_ADMIN,
        "Solo el personal clínico o administrativo puede asignar pacientes a una cuna.",
    )
    with transaction.atomic():
        locked_crib = Crib.objects.select_for_update().get(pk=crib.pk)
        locked_patient = Patient.objects.select_for_update().filter(pk=patient_id).first()
        if locked_patient is None:
            raise NotFoundDomainError("El paciente indicado no existe.")
        if locked_patient.status != PatientStatus.ACTIVE:
            raise ConflictDomainError(
                "No se puede asignar una cuna a un paciente que ya fue egresado."
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
    return locked_crib


def release_patient_from_crib(
    *,
    actor: User,
    crib: Crib,
    ip_address: str | None = None,
) -> Crib:
    """Libera una cuna ocupada, desasignando a su paciente.

    Args:
        actor: Neonatólogo o Matrona/Enfermera.
        crib: Cuna a liberar.
        ip_address: IP de origen para la auditoría.

    Returns:
        La cuna disponible.

    Raises:
        PermissionDomainError: Si el rol no puede liberar cunas.
        ConflictDomainError: Si la cuna ya estaba libre.
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
    return locked_crib


def swap_patients_between_cribs(
    *,
    actor: User,
    crib: Crib,
    other_crib_id: int,
    ip_address: str | None = None,
) -> tuple[Crib, Crib]:
    """Intercambia a los pacientes de dos cunas ocupadas en una sola operación.

    Ningún paciente egresa ni queda sin cuna en el proceso; cada uno recibe un
    movimiento de tipo intercambio en su historial.
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
    return first_crib, second_crib


def delete_patient_permanently(
    *,
    actor: User,
    patient: Patient,
    confirmation: str,
    ip_address: str | None = None,
) -> None:
    """Elimina al paciente y todo su registro clínico sin posibilidad de recuperarlo.

    Pensado para ingresos creados por error. Exige escribir el número de ficha
    como confirmación; la auditoría conserva solo el identificador numérico.
    Las administraciones ya descontadas del stock no se reponen.
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

        if locked_patient.crib_id is not None:
            crib = Crib.objects.select_for_update().get(pk=locked_patient.crib_id)
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


def record_patient_weight(
    *,
    actor: User,
    patient: Patient,
    weight_g: int,
    ip_address: str | None = None,
) -> WeightRecord:
    """Registra una medición de peso y actualiza el peso actual del paciente.

    Args:
        actor: Personal clínico que mide.
        patient: Paciente activo.
        weight_g: Peso en gramos (200 a 10000).
        ip_address: IP de origen para la auditoría.

    Returns:
        El registro de peso; si el último registro tiene el mismo peso, lo devuelve sin duplicar.

    Raises:
        PermissionDomainError: Si el rol no es clínico.
        ConflictDomainError: Si el paciente ya fue egresado.
        DomainError: Si el peso está fuera de rango.
    """
    require_role(
        actor, CLINICAL_STAFF, "Solo el personal clínico puede registrar mediciones de peso."
    )
    if not (200 <= weight_g <= 10000):
        raise DomainError("El peso registrado debe estar entre 200 y 10000 gramos.")

    with transaction.atomic():
        locked_patient = Patient.objects.select_for_update().get(pk=patient.pk)
        if locked_patient.status != PatientStatus.ACTIVE:
            raise ConflictDomainError(
                "No se pueden añadir registros de peso a un paciente egresado."
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

    Args:
        actor: Personal clínico.
        patient_id: Paciente destinatario.
        care_area: Área de cuidado (obligatoria).
        intervention: Intervención (obligatoria).
        frequency: Frecuencia (obligatoria).
        status: Estado inicial del plan.
        ip_address: IP de origen para la auditoría.

    Returns:
        El plan creado.

    Raises:
        PermissionDomainError: Si el rol no es clínico.
        NotFoundDomainError: Si el paciente no existe.
        ConflictDomainError: Si el paciente ya fue egresado.
        DomainError: Si faltan campos o el estado es inválido.
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
        patient = Patient.objects.select_for_update().filter(pk=patient_id).first()
        if patient is None:
            raise NotFoundDomainError("El paciente indicado no existe.")
        if patient.status != PatientStatus.ACTIVE:
            raise ConflictDomainError(
                "No se pueden crear planes de cuidado para un paciente egresado."
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
    return plan


def update_care_plan(
    *,
    actor: User,
    care_plan: CarePlan,
    data: dict[str, Any],
    ip_address: str | None = None,
) -> CarePlan:
    """Actualiza parcialmente un plan de cuidado de un paciente activo.

    Args:
        actor: Personal clínico.
        care_plan: Plan a modificar; se relee con bloqueo de fila.
        data: Solo los campos a cambiar.
        ip_address: IP de origen para la auditoría.

    Returns:
        El plan actualizado.

    Raises:
        PermissionDomainError: Si el rol no es clínico.
        ConflictDomainError: Si el paciente ya fue egresado.
        DomainError: Si algún campo queda vacío o el estado es inválido.
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

    Args:
        actor: Personal clínico autor.
        patient_id: Paciente observado.
        content: Texto de la observación (obligatorio).
        category: Categoría (``ObservationCategory``).
        ip_address: IP de origen para la auditoría.

    Returns:
        La observación creada.

    Raises:
        PermissionDomainError: Si el rol no puede registrar observaciones.
        NotFoundDomainError: Si el paciente no existe.
        ConflictDomainError: Si el paciente ya fue egresado.
        DomainError: Si la categoría es inválida o el contenido está vacío.
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
        patient = Patient.objects.select_for_update().filter(pk=patient_id).first()
        if patient is None:
            raise NotFoundDomainError("El paciente indicado no existe.")
        if patient.status != PatientStatus.ACTIVE:
            raise ConflictDomainError(
                "No se pueden agregar observaciones a un paciente ya egresado."
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
    return observation
