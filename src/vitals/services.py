"""Servicios de signos vitales: ingesta de telemetría y resumen operativo de la unidad."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from django.db import transaction
from django.db.models import Count, OuterRef, Subquery
from django.utils import timezone

from accounts.models import User, UserRole
from alerts.models import Alert, AlertSeverity, AlertStatus
from alerts.serializers import AlertSerializer
from alerts.services import AlertEvaluationSummary, evaluate_reading_alerts
from devices.models import Crib, CribStatus
from poki_koa.exceptions import ConflictDomainError, PermissionDomainError

from .models import VitalSignReading
from .realtime import broadcast_telemetry_reading
from .rules import validate_telemetry_payload
from .serializers import VitalSignReadingSerializer


def ingest_telemetry(
    *,
    crib: Crib,
    payload: dict[str, Any],
    actor_user: User | None = None,
    is_device_authenticated: bool = False,
) -> tuple[VitalSignReading, AlertEvaluationSummary]:
    """Valida y persiste una lectura de telemetría, evalúa alertas y la difunde en tiempo real.

    Args:
        crib: Cuna de origen.
        payload: Cuerpo JSON de la lectura.
        actor_user: Usuario que envía la lectura (alternativa al dispositivo).
        is_device_authenticated: Si la petición se autenticó con la API Key de la cuna.

    Returns:
        Tupla ``(lectura, resumen_de_alertas)``.

    Raises:
        PermissionDomainError: Si no es un dispositivo autenticado ni personal autorizado.
        DomainError: Si el payload no supera la validación fisiológica.
    """
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
        locked_crib = Crib.objects.select_for_update().get(pk=crib.pk)
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
                CribStatus.OCCUPIED if current_patient is not None else CribStatus.AVAILABLE
            )
            update_fields.append("status")
        locked_crib.save(update_fields=update_fields)

        evaluation = evaluate_reading_alerts(reading=reading)

    broadcast_telemetry_reading(
        reading_data=VitalSignReadingSerializer(reading).data,
        active_alerts_data=AlertSerializer(evaluation.active_or_updated_alerts, many=True).data,
        auto_resolved_alerts_data=AlertSerializer(evaluation.auto_resolved_alerts, many=True).data,
        crib_id=reading.crib_id,
        patient_id=reading.patient_id,
    )

    return reading, evaluation


OPEN_ALERT_STATUSES = (AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED)
SEVERITY_ORDER = (AlertSeverity.CRITICAL, AlertSeverity.WARNING, AlertSeverity.INFO)


def _empty_alert_counts() -> dict[str, int]:
    return {"total": 0, **{severity: 0 for severity in SEVERITY_ORDER}}


@dataclass
class UnitOverview:
    """Foto de la unidad: cunas con su última lectura y contadores de alertas."""

    generated_at: datetime
    cribs: list[Crib]
    summary: dict[str, Any] = field(default_factory=dict)


def build_unit_overview(crib_ids: list[int] | None = None) -> UnitOverview:
    """Arma el panel principal de la unidad con consultas acotadas.

    Args:
        crib_ids: Limita el resumen a estas cunas; ``None`` incluye todas.

    Returns:
        Cunas ordenadas por código, con su última lectura y alertas abiertas.
    """
    # Consultas acotadas e independientes del número de cunas para el panel principal
    latest_reading_id = (
        VitalSignReading.objects.filter(crib=OuterRef("pk"))
        .order_by("-recorded_at", "-id")
        .values("id")[:1]
    )
    crib_qs = Crib.objects.select_related("current_patient")
    open_alerts = Alert.objects.filter(status__in=OPEN_ALERT_STATUSES)
    if crib_ids is not None:
        crib_qs = crib_qs.filter(pk__in=crib_ids)
        open_alerts = open_alerts.filter(crib_id__in=crib_ids)
    cribs = list(crib_qs.annotate(latest_reading_id=Subquery(latest_reading_id)).order_by("code"))

    readings = VitalSignReading.objects.select_related("crib", "patient").in_bulk(
        [c.latest_reading_id for c in cribs if c.latest_reading_id is not None]
    )

    alert_counts: dict[int, dict[str, int]] = {}
    unit_alerts = _empty_alert_counts()
    grouped = open_alerts.values("crib_id", "severity").annotate(n=Count("id"))
    for row in grouped:
        counts = alert_counts.setdefault(row["crib_id"], _empty_alert_counts())
        counts[row["severity"]] += row["n"]
        counts["total"] += row["n"]
        unit_alerts[row["severity"]] += row["n"]
        unit_alerts["total"] += row["n"]

    cribs_by_status = {status: 0 for status in CribStatus.values}
    for crib in cribs:
        crib.latest_reading = readings.get(crib.latest_reading_id)
        crib.open_alerts = alert_counts.get(crib.id, _empty_alert_counts())
        crib.highest_open_severity = next(
            (sev for sev in SEVERITY_ORDER if crib.open_alerts[sev]), None
        )
        cribs_by_status[crib.status] += 1

    return UnitOverview(
        generated_at=timezone.now(),
        cribs=cribs,
        summary={
            "cribs_total": len(cribs),
            "cribs_by_status": cribs_by_status,
            "patients_monitored": sum(
                1 for c in cribs if getattr(c, "current_patient", None) is not None
            ),
            "open_alerts": unit_alerts,
        },
    )
