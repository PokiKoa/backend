from datetime import date
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from accounts.models import User, UserRole
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
    DischargeCause,
    DischargeOutcome,
    ObservationCategory,
    Patient,
    PatientSex,
    PatientStatus,
    WeightRecord,
)


def _validate_attending_physician(physician_id: int | None) -> User | None:
    if physician_id is None:
        return None
    physician = User.objects.filter(pk=physician_id, is_active=True).first()
    if physician is None:
        raise NotFoundDomainError("El médico responsable indicado no existe o no está activo.")
    if physician.role != UserRole.NEONATOLOGIST:
        raise DomainError("El profesional asignado como médico a cargo debe tener rol de Neonatólogo.")
    return physician


def _validate_crib_available(crib_id: int | None, current_patient_id: int | None = None) -> Crib | None:
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
    ip_address: str | None = None,
) -> Patient:
    if actor.role not in {UserRole.NEONATOLOGIST, UserRole.NURSE}:
        raise PermissionDomainError(
            "Solo Neonatólogos o Matronas/Enfermeras pueden registrar el ingreso de un paciente."
        )

    mrn = (medical_record_number or "").strip().upper()
    cleaned_name = (full_name or "").strip()
    if not mrn:
        raise DomainError("El número de ficha clínica (medical_record_number) es obligatorio.")
    if not cleaned_name:
        raise DomainError("El nombre completo del paciente es obligatorio.")
    if sex not in set(PatientSex.values):
        raise DomainError("El sexo del paciente debe ser 'F' o 'M'.")
    if birth_date > timezone.localdate():
        raise DomainError("La fecha de nacimiento no puede ser una fecha futura.")

    gest_weeks = Decimal(str(gestational_age_weeks))
    if not (Decimal("20.0") <= gest_weeks <= Decimal("45.0")):
        raise DomainError("La edad gestacional debe estar entre 20.0 y 45.0 semanas.")
    if not (200 <= birth_weight_g <= 8000):
        raise DomainError("El peso de nacimiento debe estar entre 200 y 8000 gramos.")

    effective_current_weight = birth_weight_g if current_weight_g is None else current_weight_g
    if not (200 <= effective_current_weight <= 10000):
        raise DomainError("El peso actual debe estar entre 200 y 10000 gramos.")

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
        )

        if crib is not None:
            crib.status = CribStatus.OCCUPIED
            crib.save(update_fields=["status", "updated_at"])

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
            ],
            ip_address=ip_address,
        )

    return patient


def update_patient(
    *,
    actor: User,
    patient: Patient,
    data: dict[str, Any],
    ip_address: str | None = None,
) -> Patient:
    if actor.role not in {UserRole.NEONATOLOGIST, UserRole.NURSE}:
        raise PermissionDomainError(
            "Solo el personal clínico puede modificar datos de un paciente."
        )

    # Permiso por objeto/campo: diagnóstico y médico tratante son exclusivos de Neonatólogo
    restricted_medical_fields = {"diagnosis", "attending_physician_id"}
    if actor.role == UserRole.NURSE and restricted_medical_fields.intersection(data.keys()):
        raise PermissionDomainError(
            "Solo un Neonatólogo puede modificar el diagnóstico médico o el médico tratante."
        )

    with transaction.atomic():
        locked_patient = (
            Patient.objects.select_for_update()
            .select_related("crib", "attending_physician")
            .get(pk=patient.pk)
        )
        if locked_patient.status != PatientStatus.ACTIVE:
            raise ConflictDomainError(
                "No se pueden modificar los datos clínicos de un paciente ya egresado."
            )

        changed_fields: list[str] = []

        if "full_name" in data:
            new_name = str(data["full_name"]).strip()
            if not new_name:
                raise DomainError("El nombre completo del paciente no puede estar vacío.")
            if new_name != locked_patient.full_name:
                locked_patient.full_name = new_name
                changed_fields.append("full_name")

        if "sex" in data:
            new_sex = data["sex"]
            if new_sex not in set(PatientSex.values):
                raise DomainError("El sexo del paciente debe ser 'F' o 'M'.")
            if new_sex != locked_patient.sex:
                locked_patient.sex = new_sex
                changed_fields.append("sex")

        if "birth_date" in data:
            new_birth_date = data["birth_date"]
            if new_birth_date > timezone.localdate():
                raise DomainError("La fecha de nacimiento no puede ser una fecha futura.")
            if new_birth_date != locked_patient.birth_date:
                locked_patient.birth_date = new_birth_date
                changed_fields.append("birth_date")

        if "gestational_age_weeks" in data:
            new_gest = Decimal(str(data["gestational_age_weeks"]))
            if not (Decimal("20.0") <= new_gest <= Decimal("45.0")):
                raise DomainError(
                    "La edad gestacional debe estar entre 20.0 y 45.0 semanas."
                )
            if new_gest != locked_patient.gestational_age_weeks:
                locked_patient.gestational_age_weeks = new_gest
                changed_fields.append("gestational_age_weeks")

        if "current_weight_g" in data:
            new_weight = int(data["current_weight_g"])
            if not (200 <= new_weight <= 10000):
                raise DomainError("El peso actual debe estar entre 200 y 10000 gramos.")
            if new_weight != locked_patient.current_weight_g:
                locked_patient.current_weight_g = new_weight
                changed_fields.append("current_weight_g")
                WeightRecord.objects.create(
                    patient=locked_patient,
                    weight_g=new_weight,
                    recorded_by=actor,
                )

        if "diagnosis" in data:
            new_diag = str(data["diagnosis"] or "").strip()
            if new_diag != locked_patient.diagnosis:
                locked_patient.diagnosis = new_diag
                changed_fields.append("diagnosis")

        if "attending_physician_id" in data:
            new_physician = _validate_attending_physician(data["attending_physician_id"])
            new_phys_id = new_physician.id if new_physician else None
            if new_phys_id != locked_patient.attending_physician_id:
                locked_patient.attending_physician = new_physician
                changed_fields.append("attending_physician_id")

        if "crib_id" in data:
            new_crib_id = data["crib_id"]
            if new_crib_id != locked_patient.crib_id:
                old_crib = locked_patient.crib
                new_crib = _validate_crib_available(
                    new_crib_id, current_patient_id=locked_patient.id
                )
                locked_patient.crib = new_crib
                changed_fields.append("crib_id")
                # Liberar primero en el paciente antes de actualizar las cunas
                locked_patient.save()
                if old_crib is not None:
                    old_crib.status = CribStatus.AVAILABLE
                    old_crib.save(update_fields=["status", "updated_at"])
                if new_crib is not None:
                    new_crib.status = CribStatus.OCCUPIED
                    new_crib.save(update_fields=["status", "updated_at"])

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
    if actor.role != UserRole.NEONATOLOGIST:
        raise PermissionDomainError(
            "Solo un Neonatólogo está autorizado para firmar el egreso clínico de un paciente."
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
        locked_patient = (
            Patient.objects.select_for_update()
            .select_related("crib")
            .get(pk=patient.pk)
        )
        if locked_patient.status != PatientStatus.ACTIVE:
            raise ConflictDomainError("El paciente ya fue egresado previamente.")

        old_crib = locked_patient.crib
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
    if actor.role not in {UserRole.ADMIN, UserRole.NEONATOLOGIST, UserRole.NURSE}:
        raise PermissionDomainError(
            "Solo el personal clínico o administrativo puede asignar pacientes a una cuna."
        )
    with transaction.atomic():
        locked_crib = Crib.objects.select_for_update().get(pk=crib.pk)
        locked_patient = (
            Patient.objects.select_for_update()
            .select_related("crib")
            .filter(pk=patient_id)
            .first()
        )
        if locked_patient is None:
            raise NotFoundDomainError("El paciente indicado no existe.")
        if locked_patient.status != PatientStatus.ACTIVE:
            raise ConflictDomainError(
                "No se puede asignar una cuna a un paciente que ya fue egresado."
            )
        if locked_crib.status in {CribStatus.MAINTENANCE, CribStatus.OFFLINE}:
            raise ConflictDomainError(
                "La cuna no se encuentra disponible para asignación."
            )

        current_occupant = getattr(locked_crib, "current_patient", None)
        if current_occupant is not None and current_occupant.id != locked_patient.id:
            raise ConflictDomainError(
                "La cuna ya se encuentra ocupada por otro paciente."
            )

        previous_crib = locked_patient.crib
        if previous_crib is not None and previous_crib.id != locked_crib.id:
            locked_patient.crib = None
            locked_patient.save(update_fields=["crib", "updated_at"])
            previous_crib.status = CribStatus.AVAILABLE
            previous_crib.save(update_fields=["status", "updated_at"])

        locked_patient.crib = locked_crib
        locked_patient.save(update_fields=["crib", "updated_at"])

        locked_crib.status = CribStatus.OCCUPIED
        locked_crib.save(update_fields=["status", "updated_at"])

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
    if actor.role not in {UserRole.ADMIN, UserRole.NEONATOLOGIST, UserRole.NURSE}:
        raise PermissionDomainError(
            "Solo el personal clínico o administrativo puede liberar una cuna."
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


def record_patient_weight(
    *,
    actor: User,
    patient: Patient,
    weight_g: int,
    ip_address: str | None = None,
) -> WeightRecord:
    if actor.role not in {UserRole.NEONATOLOGIST, UserRole.NURSE}:
        raise PermissionDomainError(
            "Solo el personal clínico puede registrar mediciones de peso."
        )
    if not (200 <= weight_g <= 10000):
        raise DomainError("El peso registrado debe estar entre 200 y 10000 gramos.")

    with transaction.atomic():
        locked_patient = Patient.objects.select_for_update().get(pk=patient.pk)
        if locked_patient.status != PatientStatus.ACTIVE:
            raise ConflictDomainError(
                "No se pueden añadir registros de peso a un paciente egresado."
            )

        # Regla de deduplicación extraída de IncuNest: si el último punto tiene el mismo peso, no duplica fila
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
    if actor.role not in {UserRole.NEONATOLOGIST, UserRole.NURSE}:
        raise PermissionDomainError(
            "Solo el personal clínico puede crear planes de cuidado."
        )
    if status not in set(CarePlanStatus.values):
        raise DomainError("El estado del plan de cuidado no es válido.")

    cleaned_area = (care_area or "").strip()
    cleaned_intervention = (intervention or "").strip()
    cleaned_freq = (frequency or "").strip()
    if not cleaned_area or not cleaned_intervention or not cleaned_freq:
        raise DomainError(
            "El área de cuidado, la intervención y la frecuencia son obligatorias."
        )

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
    if actor.role not in {UserRole.NEONATOLOGIST, UserRole.NURSE}:
        raise PermissionDomainError(
            "Solo el personal clínico puede actualizar planes de cuidado."
        )

    with transaction.atomic():
        locked_plan = (
            CarePlan.objects.select_for_update()
            .select_related("patient")
            .get(pk=care_plan.pk)
        )
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
    if actor.role not in {UserRole.NEONATOLOGIST, UserRole.NURSE}:
        raise PermissionDomainError(
            "Solo el personal clínico puede registrar observaciones clínicas."
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
