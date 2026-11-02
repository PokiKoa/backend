from dataclasses import dataclass
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
    PermissionDomainError,
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
    AlertStatus,
    AlertThresholdConfig,
    ResolutionReason,
)
from .policies import EVALUATED_ALERT_TYPES, evaluate_vital_reading


@dataclass(frozen=True)
class AlertEvaluationSummary:
    created_alerts: list[Alert]
    deduplicated_alerts: list[Alert]
    auto_resolved_alerts: list[Alert]
    escalated_resolved_alerts: list[Alert]

    @property
    def active_or_updated_alerts(self) -> list[Alert]:
        return [*self.created_alerts, *self.deduplicated_alerts]


def get_effective_thresholds(patient: Patient | None = None) -> AlertThresholdConfig:
    if patient is not None:
        custom = AlertThresholdConfig.objects.filter(patient=patient).first()
        if custom is not None:
            return custom
    global_default = AlertThresholdConfig.objects.filter(patient__isnull=True).first()
    if global_default is not None:
        return global_default
    return AlertThresholdConfig(patient=None)


def _validate_threshold_values(config: AlertThresholdConfig) -> None:
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

    if not (
        SPO2_MIN
        < config.spo2_critical_low
        < config.spo2_warning_low
        <= SPO2_MAX
    ):
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
    if actor.role not in {UserRole.ADMIN, UserRole.NEONATOLOGIST}:
        raise PermissionDomainError(
            "Solo un Neonatólogo o Administrador puede configurar los umbrales de alerta clínica."
        )

    with transaction.atomic():
        if patient is not None:
            locked_patient = Patient.objects.select_for_update().get(pk=patient.pk)
            if locked_patient.status != PatientStatus.ACTIVE:
                raise ConflictDomainError(
                    "No se pueden modificar los umbrales de un paciente egresado."
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

    return config


def evaluate_reading_alerts(*, reading: VitalSignReading) -> AlertEvaluationSummary:
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
                # Autorresolución cuando la variable vuelve al rango normal
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
                    # Cambio de severidad: cierra la alerta previa y escalará a una nueva
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
                # Deduplicación: incrementa contador y actualiza lectura sin duplicar fila
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

    return AlertEvaluationSummary(
        created_alerts=created_alerts,
        deduplicated_alerts=deduplicated_alerts,
        auto_resolved_alerts=auto_resolved_alerts,
        escalated_resolved_alerts=escalated_resolved_alerts,
    )


def acknowledge_alert(
    *,
    actor: User,
    alert: Alert,
    ip_address: str | None = None,
) -> Alert:
    if actor.role not in {UserRole.ADMIN, UserRole.NEONATOLOGIST, UserRole.NURSE}:
        raise PermissionDomainError(
            "Solo el personal clínico o administrativo puede reconocer alertas."
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

    return locked_alert


def resolve_alert(
    *,
    actor: User,
    alert: Alert,
    ip_address: str | None = None,
) -> Alert:
    if actor.role not in {UserRole.ADMIN, UserRole.NEONATOLOGIST, UserRole.NURSE}:
        raise PermissionDomainError(
            "Solo el personal clínico o administrativo puede resolver alertas manualmente."
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

    return locked_alert


def resolve_patient_alerts_on_discharge(*, patient: Patient, actor: User) -> int:
    now = timezone.now()
    return Alert.objects.filter(
        patient=patient,
        status__in=[AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED],
    ).update(
        status=AlertStatus.RESOLVED,
        resolved_by=actor,
        resolved_at=now,
        resolution_reason=ResolutionReason.PATIENT_DISCHARGED,
        last_evaluated_at=now,
    )
