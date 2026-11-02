from typing import Any

from django.db import transaction

from accounts.models import User, UserRole
from alerts.services import AlertEvaluationSummary, evaluate_reading_alerts
from devices.models import Crib, CribStatus
from poki_koa.exceptions import ConflictDomainError, PermissionDomainError

from .models import VitalSignReading
from .rules import validate_telemetry_payload


def ingest_telemetry(
    *,
    crib: Crib,
    payload: dict[str, Any],
    actor_user: User | None = None,
    is_device_authenticated: bool = False,
) -> tuple[VitalSignReading, AlertEvaluationSummary]:
    if not is_device_authenticated and (
        actor_user is None
        or actor_user.role
        not in {
            UserRole.ADMIN,
            UserRole.NEONATOLOGIST,
            UserRole.NURSE,
        }
    ):
        raise PermissionDomainError(
            "Solo un dispositivo autenticado o personal clínico/administrativo puede enviar telemetría."
        )

    validated = validate_telemetry_payload(payload)

    with transaction.atomic():
        locked_crib = (
            Crib.objects.select_for_update()
            .select_related("current_patient")
            .get(pk=crib.pk)
        )
        if locked_crib.status == CribStatus.MAINTENANCE:
            raise ConflictDomainError(
                "No se puede ingerir telemetría en una cuna en estado de mantenimiento."
            )
        if not locked_crib.is_device_active:
            raise ConflictDomainError(
                "El dispositivo asociado a esta cuna se encuentra deshabilitado."
            )

        current_patient = getattr(locked_crib, "current_patient", None)

        reading = VitalSignReading.objects.create(
            crib=locked_crib,
            patient=current_patient,
            heart_rate=validated.heart_rate,
            spo2=validated.spo2,
            temperature=validated.temperature,
            sleep_state=validated.sleep_state,
            cannula_connected=validated.cannula_connected,
            iv_line_active=validated.iv_line_active,
            recorded_at=validated.recorded_at,
        )

        locked_crib.last_telemetry_at = reading.recorded_at
        update_fields = ["last_telemetry_at", "updated_at"]
        if locked_crib.status == CribStatus.OFFLINE:
            locked_crib.status = (
                CribStatus.OCCUPIED
                if current_patient is not None
                else CribStatus.AVAILABLE
            )
            update_fields.append("status")
        locked_crib.save(update_fields=update_fields)

        evaluation = evaluate_reading_alerts(reading=reading)

    return reading, evaluation
