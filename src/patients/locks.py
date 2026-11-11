"""Bloqueo transaccional de pacientes activos, compartido por los servicios de dominio."""

from poki_koa.exceptions import ConflictDomainError, NotFoundDomainError

from .models import Patient, PatientStatus


def lock_active_patient(patient_id: int, *, discharged_message: str) -> Patient:
    """Bloquea con ``SELECT ... FOR UPDATE`` un paciente y exige que siga ingresado.

    Debe llamarse dentro de ``transaction.atomic()``.

    Args:
        patient_id: Identificador del paciente.
        discharged_message: Mensaje propio de la operación si el paciente ya egresó.

    Returns:
        El paciente bloqueado.

    Raises:
        NotFoundDomainError: Si el paciente no existe (HTTP 404).
        ConflictDomainError: Si el paciente ya fue egresado (HTTP 409).
    """
    patient = Patient.objects.select_for_update().filter(pk=patient_id).first()
    if patient is None:
        raise NotFoundDomainError("El paciente indicado no existe.")
    if patient.status != PatientStatus.ACTIVE:
        raise ConflictDomainError(discharged_message)
    return patient
