"""Servicios de alertas: umbrales, evaluación de lecturas y ciclo de vida (reconocer, resolver, deduplicar)."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from accounts.models import User
from accounts.roles import CLINICAL_OR_ADMIN, THRESHOLD_MANAGERS, require_role
from audit.models import AuditAction
from audit.services import record_audit_event
from patients.locks import lock_active_patient
from patients.models import Patient
from poki_koa.exceptions import (
    ConflictDomainError,
    DomainError,
)
from vitals.models import VitalSignReading
from vitals.rules import (
    HEART_RATE_MAX,
    HEART_RATE_MIN,
    SPO2_MAX,
    SPO2_MIN,
    TEMPERATURE_MAX,
    TEMPERATURE_MIN,
)

from .models import (
    Alert,
    AlertSeverity,
    AlertStatus,
    AlertThresholdConfig,
    AlertType,
    ResolutionReason,
)
from .policies import EVALUATED_ALERT_TYPES, evaluate_vital_reading


@dataclass(frozen=True)
class AlertEvaluationSummary:
    """Resultado de evaluar una lectura: alertas creadas, deduplicadas y resueltas automáticamente."""

    created_alerts: list[Alert]
    deduplicated_alerts: list[Alert]
    auto_resolved_alerts: list[Alert]
    escalated_resolved_alerts: list[Alert]

    @property
    def active_or_updated_alerts(self) -> list[Alert]:
        """Alertas abiertas tras la evaluación (nuevas más las deduplicadas)."""
        return [*self.created_alerts, *self.deduplicated_alerts]


def get_effective_thresholds(patient: Patient | None = None) -> AlertThresholdConfig:
    """Obtiene los umbrales aplicables a un paciente, priorizando la configuración
    personalizada sobre la global o los valores por defecto.

    Args:
        patient: Instancia del paciente consultado (opcional).

    Returns:
        AlertThresholdConfig: Configuración efectiva de umbrales.
    """
    if patient is not None:
        custom = AlertThresholdConfig.objects.filter(patient=patient).first()
        if custom is not None:
            return custom
    global_default = AlertThresholdConfig.objects.filter(patient__isnull=True).first()
    if global_default is not None:
        return global_default
    return AlertThresholdConfig(patient=None)


def _validate_threshold_values(config: AlertThresholdConfig) -> None:
    """Valida que los umbrales configurados cumplan con el orden estricto y los rangos fisiológicos."""
    if not (
        HEART_RATE_MIN
        <= config.heart_rate_critical_low
        < config.heart_rate_warning_low
        < config.heart_rate_warning_high
        < config.heart_rate_critical_high
        <= HEART_RATE_MAX
    ):
        raise DomainError(
            "Los umbrales de frecuencia cardíaca deben cumplir orden estricto: "
            "critical_low < warning_low < warning_high < critical_high dentro del rango fisiológico (1..260 lpm)."
        )

    if not (SPO2_MIN < config.spo2_critical_low < config.spo2_warning_low <= SPO2_MAX):
        raise DomainError(
            "Los umbrales de SpO2 deben cumplir orden estricto: "
            "0 < critical_low < warning_low <= 100."
        )

    if not (
        TEMPERATURE_MIN
        <= config.temp_critical_low
        < config.temp_warning_low
        < config.temp_warning_high
        < config.temp_critical_high
        <= TEMPERATURE_MAX
    ):
        raise DomainError(
            "Los umbrales de temperatura deben cumplir orden estricto: "
            "critical_low < warning_low < warning_high < critical_high dentro del rango (25.0..45.0 °C)."
        )


def upsert_threshold_config(
    *,
    actor: User,
    patient: Patient | None,
    data: dict[str, Any],
    ip_address: str | None = None,
) -> AlertThresholdConfig:
    """Crea o actualiza la configuración de umbrales de alerta (global o por paciente).

    Precondiciones:
        - El `actor` debe poseer rol de Neonatólogo o Administrador (THRESHOLD_MANAGERS).
        - Si se especifica un `patient`, este no debe encontrarse egresado.
        - Los valores proporcionados deben cumplir estrictamente los rangos fisiológicos y orden lógico.
    Postcondiciones:
        - Se persiste o actualiza la instancia `AlertThresholdConfig` en la base de datos.
        - Se registra un evento de auditoría detallando los cambios realizados.
    Invariante:
        - Ninguna configuración de umbrales almacenada viola el orden estricto entre niveles críticos y de advertencia.
    """
    require_role(
        actor,
        THRESHOLD_MANAGERS,
        "Solo un Neonatólogo o Administrador puede configurar los umbrales de alerta clínica.",
    )

    with transaction.atomic():
        if patient is not None:
            locked_patient = lock_active_patient(
                patient.pk,
                discharged_message="No se pueden modificar los umbrales de un paciente egresado.",
            )
            config = (
                AlertThresholdConfig.objects.select_for_update()
                .filter(patient=locked_patient)
                .first()
            )
        else:
            locked_patient = None
            config = (
                AlertThresholdConfig.objects.select_for_update()
                .filter(patient__isnull=True)
                .first()
            )

        is_created = config is None
        if config is None:
            config = AlertThresholdConfig(patient=locked_patient)

        threshold_fields = (
            "heart_rate_critical_low",
            "heart_rate_warning_low",
            "heart_rate_warning_high",
            "heart_rate_critical_high",
            "spo2_critical_low",
            "spo2_warning_low",
            "temp_critical_low",
            "temp_warning_low",
            "temp_warning_high",
            "temp_critical_high",
        )
        changed_fields: list[str] = []
        for field_name in threshold_fields:
            if field_name in data:
                val = data[field_name]
                if field_name.startswith("temp_"):
                    val = Decimal(str(val)).quantize(Decimal("0.1"))
                else:
                    val = int(val)
                if getattr(config, field_name) != val or is_created:
                    setattr(config, field_name, val)
                    changed_fields.append(field_name)

        _validate_threshold_values(config)
        config.updated_by = actor
        config.save()

        record_audit_event(
            action=AuditAction.CREATE if is_created else AuditAction.UPDATE,
            resource_type="alert_threshold_config",
            resource_id=config.id,
            actor_user=actor,
            patient_id=locked_patient.id if locked_patient else None,
            changed_fields=changed_fields or list(threshold_fields),
            ip_address=ip_address,
        )

    assert config.id is not None, "Invariante roto: La configuración de umbrales no fue persistida."
    return config


def evaluate_reading_alerts(*, reading: VitalSignReading) -> AlertEvaluationSummary:
    """Evalúa una lectura de signos vitales y sincroniza el estado de las alertas (creación, deduplicación, escalamiento y autorresolución).

    Precondiciones:
        - La lectura `reading` debe estar asociada a una cuna válida y contener signos vitales evaluables.
    Postcondiciones:
        - Se actualizan, crean o resuelven las alertas según las anomalías detectadas en la lectura.
        - Se retorna un resumen con el desglose de alertas creadas, deduplicadas, auto-resueltas y escaladas.
    Invariante:
        - No pueden existir múltiples alertas abiertas del mismo tipo y cuna con la misma severidad.
    """
    now = timezone.now()
    thresholds = get_effective_thresholds(reading.patient)
    anomalies = evaluate_vital_reading(reading, thresholds)

    created_alerts: list[Alert] = []
    deduplicated_alerts: list[Alert] = []
    auto_resolved_alerts: list[Alert] = []
    escalated_resolved_alerts: list[Alert] = []

    with transaction.atomic():
        open_alerts_qs = Alert.objects.select_for_update().filter(
            crib=reading.crib,
            alert_type__in=EVALUATED_ALERT_TYPES,
            status__in=[AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED],
        )
        open_by_type: dict[str, list[Alert]] = {t: [] for t in EVALUATED_ALERT_TYPES}
        for open_alert in open_alerts_qs:
            open_by_type.setdefault(open_alert.alert_type, []).append(open_alert)

        for alert_type in EVALUATED_ALERT_TYPES:
            existing_open = open_by_type.get(alert_type, [])
            anomaly = anomalies.get(alert_type)

            if anomaly is None:
                for open_alert in existing_open:
                    open_alert.status = AlertStatus.RESOLVED
                    open_alert.resolution_reason = ResolutionReason.AUTO_NORMALIZED
                    open_alert.resolved_at = now
                    open_alert.last_evaluated_at = now
                    open_alert.save(
                        update_fields=[
                            "status",
                            "resolution_reason",
                            "resolved_at",
                            "last_evaluated_at",
                        ]
                    )
                    auto_resolved_alerts.append(open_alert)
                continue

            matching_open: Alert | None = None
            for open_alert in existing_open:
                if open_alert.severity == anomaly.severity and matching_open is None:
                    matching_open = open_alert
                else:
                    open_alert.status = AlertStatus.RESOLVED
                    open_alert.resolution_reason = ResolutionReason.SEVERITY_ESCALATED
                    open_alert.resolved_at = now
                    open_alert.last_evaluated_at = now
                    open_alert.save(
                        update_fields=[
                            "status",
                            "resolution_reason",
                            "resolved_at",
                            "last_evaluated_at",
                        ]
                    )
                    escalated_resolved_alerts.append(open_alert)

            if matching_open is not None:
                matching_open.patient = reading.patient
                matching_open.message = anomaly.message
                matching_open.measured_value = anomaly.measured_value
                matching_open.threshold_value = anomaly.threshold_value
                matching_open.occurrence_count += 1
                matching_open.last_evaluated_at = now
                matching_open.save(
                    update_fields=[
                        "patient",
                        "message",
                        "measured_value",
                        "threshold_value",
                        "occurrence_count",
                        "last_evaluated_at",
                    ]
                )
                deduplicated_alerts.append(matching_open)
            else:
                new_alert = Alert.objects.create(
                    crib=reading.crib,
                    patient=reading.patient,
                    alert_type=anomaly.alert_type,
                    severity=anomaly.severity,
                    status=AlertStatus.ACTIVE,
                    message=anomaly.message,
                    measured_value=anomaly.measured_value,
                    threshold_value=anomaly.threshold_value,
                    occurrence_count=1,
                    triggered_at=now,
                    last_evaluated_at=now,
                )
                created_alerts.append(new_alert)

    summary = AlertEvaluationSummary(
        created_alerts=created_alerts,
        deduplicated_alerts=deduplicated_alerts,
        auto_resolved_alerts=auto_resolved_alerts,
        escalated_resolved_alerts=escalated_resolved_alerts,
    )
    assert isinstance(summary, AlertEvaluationSummary), (
        "Invariante roto: El resumen de evaluación debe ser un objeto válido."
    )
    return summary


def acknowledge_alert(
    *,
    actor: User,
    alert: Alert,
    ip_address: str | None = None,
) -> Alert:
    """Marca una alerta activa como reconocida por el personal autorizado.

    Precondiciones:
        - El `actor` debe tener rol clínico o administrativo (CLINICAL_OR_ADMIN).
        - La alerta `alert` debe existir y encontrarse en estado activo (`ACTIVE`), sin estar ya resuelta ni reconocida.
    Postcondiciones:
        - La alerta pasa al estado `ACKNOWLEDGED`, registrando al actor y la marca de tiempo de reconocimiento.
        - Se registra el evento de auditoría y se transmite la actualización en tiempo real vía WebSocket.
    Invariante:
        - Ninguna alerta en estado `RESOLVED` puede ser reconocida.
    """
    require_role(
        actor,
        CLINICAL_OR_ADMIN,
        "Solo el personal clínico o administrativo puede reconocer alertas.",
    )

    with transaction.atomic():
        locked_alert = Alert.objects.select_for_update().get(pk=alert.pk)
        if locked_alert.status == AlertStatus.RESOLVED:
            raise ConflictDomainError(
                "No se puede reconocer una alerta que ya se encuentra resuelta."
            )
        if locked_alert.status == AlertStatus.ACKNOWLEDGED:
            raise ConflictDomainError("La alerta ya fue reconocida previamente.")

        locked_alert.status = AlertStatus.ACKNOWLEDGED
        locked_alert.acknowledged_by = actor
        locked_alert.acknowledged_at = timezone.now()
        locked_alert.save(
            update_fields=[
                "status",
                "acknowledged_by",
                "acknowledged_at",
            ]
        )

        record_audit_event(
            action=AuditAction.ACKNOWLEDGE_ALERT,
            resource_type="alert",
            resource_id=locked_alert.id,
            actor_user=actor,
            patient_id=locked_alert.patient_id,
            changed_fields=["status", "acknowledged_by_id", "acknowledged_at"],
            ip_address=ip_address,
        )

    from vitals.realtime import broadcast_alert_event

    from .serializers import AlertSerializer

    broadcast_alert_event(
        event_name="alert.acknowledged",
        alert_data=AlertSerializer(locked_alert).data,
        crib_id=locked_alert.crib_id,
        patient_id=locked_alert.patient_id,
    )

    assert locked_alert.status == AlertStatus.ACKNOWLEDGED, (
        "Invariante roto: La alerta no quedó en estado reconocido."
    )
    return locked_alert


def resolve_alert(
    *,
    actor: User,
    alert: Alert,
    ip_address: str | None = None,
) -> Alert:
    """Resuelve manualmente una alerta abierta por parte del personal autorizado.

    Precondiciones:
        - El `actor` debe tener rol clínico o administrativo (CLINICAL_OR_ADMIN).
        - La alerta seleccionada debe existir y no encontrarse ya resuelta.
    Postcondiciones:
        - La alerta pasa al estado `RESOLVED` con motivo `manual`, registrando al actor y la marca de tiempo.
        - Se registra el evento de auditoría y se transmite la notificación en tiempo real.
    Invariante:
        - Toda alerta resuelta manualmente contiene obligatoriamente la referencia al actor y el motivo de resolución.
    """
    require_role(
        actor,
        CLINICAL_OR_ADMIN,
        "Solo el personal clínico o administrativo puede resolver alertas manualmente.",
    )

    with transaction.atomic():
        locked_alert = Alert.objects.select_for_update().get(pk=alert.pk)
        if locked_alert.status == AlertStatus.RESOLVED:
            raise ConflictDomainError("La alerta ya se encuentra resuelta.")

        now = timezone.now()
        locked_alert.status = AlertStatus.RESOLVED
        locked_alert.resolved_by = actor
        locked_alert.resolved_at = now
        locked_alert.resolution_reason = ResolutionReason.MANUAL
        locked_alert.save(
            update_fields=[
                "status",
                "resolved_by",
                "resolved_at",
                "resolution_reason",
            ]
        )

        record_audit_event(
            action=AuditAction.RESOLVE_ALERT,
            resource_type="alert",
            resource_id=locked_alert.id,
            actor_user=actor,
            patient_id=locked_alert.patient_id,
            changed_fields=[
                "status",
                "resolved_by_id",
                "resolved_at",
                "resolution_reason",
            ],
            ip_address=ip_address,
        )

    from vitals.realtime import broadcast_alert_event

    from .serializers import AlertSerializer

    broadcast_alert_event(
        event_name="alert.resolved",
        alert_data=AlertSerializer(locked_alert).data,
        crib_id=locked_alert.crib_id,
        patient_id=locked_alert.patient_id,
    )

    assert locked_alert.status == AlertStatus.RESOLVED, (
        "Invariante roto: La alerta debe quedar en estado resuelto."
    )
    assert locked_alert.resolution_reason == ResolutionReason.MANUAL, (
        "Invariante roto: El motivo de resolución debe ser manual."
    )
    return locked_alert


def resolve_patient_alerts_on_discharge(*, patient: Patient, actor: User) -> int:
    """Resuelve automáticamente todas las alertas abiertas asociadas a un paciente al momento de su egreso.

    Precondiciones:
        - El paciente `patient` debe ser válido y encontrarse en proceso de egreso.
    Postcondiciones:
        - Todas las alertas activas o reconocidas del paciente pasan a estado resuelto con motivo de egreso (`patient_discharged`).
        - Retorna la cantidad total de alertas afectadas.
    Invariante:
        - Ninguna alerta abierta permanece asociada a un paciente egresado.
    """
    now = timezone.now()
    updated_count = Alert.objects.filter(
        patient=patient,
        status__in=[AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED],
    ).update(
        status=AlertStatus.RESOLVED,
        resolved_by=actor,
        resolved_at=now,
        resolution_reason=ResolutionReason.PATIENT_DISCHARGED,
        last_evaluated_at=now,
    )
    assert not Alert.objects.filter(
        patient=patient,
        status__in=[AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED],
    ).exists(), "Invariante roto: Quedaron alertas abiertas para un paciente egresado."
    return updated_count


def trigger_or_deduplicate_offline_alert(
    *,
    crib,
    patient: Patient | None,
    timeout_seconds: int,
) -> Alert:
    """Crea o deduplica una alerta de pérdida de señal (sensor_fault) para una cuna inactiva.

    Precondiciones:
        - La cuna `crib` debe existir.
        - El parámetro `timeout_seconds` debe representar un intervalo de inactividad válido.
    Postcondiciones:
        - Se crea una nueva alerta de fallo de sensor o se actualiza la existente incrementando su contador.
        - Se transmite el evento en tiempo real vía WebSocket.
    Invariante:
        - Toda alerta de pérdida de telemetría activa está debidamente vinculada a la cuna correspondiente.
    """
    now = timezone.now()
    severity = AlertSeverity.CRITICAL if patient is not None else AlertSeverity.WARNING
    message = (
        f"Pérdida de señal de telemetría en la cuna {crib.code} "
        f"(sin lecturas por más de {timeout_seconds} s)."
    )

    with transaction.atomic():
        existing_open = list(
            Alert.objects.select_for_update().filter(
                crib=crib,
                alert_type=AlertType.SENSOR_FAULT,
                status__in=[AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED],
            )
        )
        matching_open: Alert | None = None
        for open_alert in existing_open:
            if open_alert.severity == severity and matching_open is None:
                matching_open = open_alert
            else:
                open_alert.status = AlertStatus.RESOLVED
                open_alert.resolution_reason = ResolutionReason.SEVERITY_ESCALATED
                open_alert.resolved_at = now
                open_alert.last_evaluated_at = now
                open_alert.save(
                    update_fields=[
                        "status",
                        "resolution_reason",
                        "resolved_at",
                        "last_evaluated_at",
                    ]
                )

        if matching_open is not None:
            matching_open.patient = patient
            matching_open.message = message
            matching_open.threshold_value = Decimal(timeout_seconds)
            matching_open.occurrence_count += 1
            matching_open.last_evaluated_at = now
            matching_open.save(
                update_fields=[
                    "patient",
                    "message",
                    "threshold_value",
                    "occurrence_count",
                    "last_evaluated_at",
                ]
            )
            alert = matching_open
        else:
            alert = Alert.objects.create(
                crib=crib,
                patient=patient,
                alert_type=AlertType.SENSOR_FAULT,
                severity=severity,
                status=AlertStatus.ACTIVE,
                message=message,
                threshold_value=Decimal(timeout_seconds),
                occurrence_count=1,
                triggered_at=now,
                last_evaluated_at=now,
            )

    from vitals.realtime import broadcast_alert_event

    from .serializers import AlertSerializer

    broadcast_alert_event(
        event_name="alert.triggered",
        alert_data=AlertSerializer(alert).data,
        crib_id=alert.crib_id,
        patient_id=alert.patient_id,
    )

    assert alert.id is not None, (
        "Invariante roto: La alerta de sensor no fue generada correctamente."
    )
    return alert
