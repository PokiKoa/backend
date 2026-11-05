from dataclasses import dataclass
from decimal import Decimal

from vitals.models import VitalSignReading

from .models import AlertSeverity, AlertThresholdConfig, AlertType


@dataclass(frozen=True)
class DetectedAnomaly:
    alert_type: str
    severity: str
    message: str
    measured_value: Decimal | None
    threshold_value: Decimal | None


EVALUATED_ALERT_TYPES: tuple[str, ...] = (
    AlertType.HEART_RATE,
    AlertType.SPO2,
    AlertType.TEMPERATURE,
    AlertType.CANNULA,
    AlertType.SENSOR_FAULT,
)


def _anomaly(
    alert_type: str,
    severity: str,
    message: str,
    measured: Decimal | int,
    threshold: Decimal | int,
) -> DetectedAnomaly:
    return DetectedAnomaly(
        alert_type=alert_type,
        severity=severity,
        message=message,
        measured_value=Decimal(measured) if isinstance(measured, int) else measured,
        threshold_value=Decimal(threshold) if isinstance(threshold, int) else threshold,
    )


def _evaluate_heart_rate(hr: int, t: AlertThresholdConfig) -> DetectedAnomaly | None:
    critical, warning = AlertSeverity.CRITICAL, AlertSeverity.WARNING
    if hr <= t.heart_rate_critical_low:
        severity, limit = critical, t.heart_rate_critical_low
        message = f"Bradicardia crítica neonatal: FC {hr} lpm (umbral <= {limit} lpm)."
    elif hr >= t.heart_rate_critical_high:
        severity, limit = critical, t.heart_rate_critical_high
        message = f"Taquicardia crítica neonatal: FC {hr} lpm (umbral >= {limit} lpm)."
    elif hr <= t.heart_rate_warning_low:
        severity, limit = warning, t.heart_rate_warning_low
        message = f"Alerta de bradicardia neonatal: FC {hr} lpm (umbral <= {limit} lpm)."
    elif hr >= t.heart_rate_warning_high:
        severity, limit = warning, t.heart_rate_warning_high
        message = f"Alerta de taquicardia neonatal: FC {hr} lpm (umbral >= {limit} lpm)."
    else:
        return None
    return _anomaly(AlertType.HEART_RATE, severity, message, hr, limit)


def _evaluate_spo2(spo2: int, t: AlertThresholdConfig) -> DetectedAnomaly | None:
    if spo2 < t.spo2_critical_low:
        limit = t.spo2_critical_low
        message = f"Hipoxemia crítica: SpO2 {spo2}% (umbral < {limit}%)."
        severity = AlertSeverity.CRITICAL
    elif spo2 < t.spo2_warning_low:
        limit = t.spo2_warning_low
        message = f"Saturación de oxígeno baja: SpO2 {spo2}% (umbral < {limit}%)."
        severity = AlertSeverity.WARNING
    else:
        return None
    return _anomaly(AlertType.SPO2, severity, message, spo2, limit)


def _evaluate_temperature(temp: Decimal, t: AlertThresholdConfig) -> DetectedAnomaly | None:
    critical, warning = AlertSeverity.CRITICAL, AlertSeverity.WARNING
    if temp <= t.temp_critical_low:
        severity, limit = critical, t.temp_critical_low
        message = f"Hipotermia crítica: temperatura {temp} °C (umbral <= {limit} °C)."
    elif temp >= t.temp_critical_high:
        severity, limit = critical, t.temp_critical_high
        message = f"Hipertermia crítica: temperatura {temp} °C (umbral >= {limit} °C)."
    elif temp <= t.temp_warning_low:
        severity, limit = warning, t.temp_warning_low
        message = f"Riesgo de hipotermia: temperatura {temp} °C (umbral <= {limit} °C)."
    elif temp >= t.temp_warning_high:
        severity, limit = warning, t.temp_warning_high
        message = f"Temperatura elevada: {temp} °C (umbral >= {limit} °C)."
    else:
        return None
    return _anomaly(AlertType.TEMPERATURE, severity, message, temp, limit)


def evaluate_vital_reading(
    reading: VitalSignReading,
    thresholds: AlertThresholdConfig,
) -> dict[str, DetectedAnomaly]:
    """Evalúa una lectura de signos vitales frente a los umbrales configurados.

    Args:
        reading: Lectura recién ingerida (con su cuna cargada).
        thresholds: Umbrales vigentes de frecuencia cardíaca, SpO2 y temperatura.

    Returns:
        Anomalías detectadas indexadas por tipo de alerta; vacío si todo está en rango.
    """
    anomalies: dict[str, DetectedAnomaly] = {}
    detected = (
        _evaluate_heart_rate(reading.heart_rate, thresholds),
        _evaluate_spo2(reading.spo2, thresholds),
        _evaluate_temperature(reading.temperature, thresholds),
    )
    for anomaly in detected:
        if anomaly is not None:
            anomalies[anomaly.alert_type] = anomaly

    if not reading.cannula_connected:
        anomalies[AlertType.CANNULA] = DetectedAnomaly(
            alert_type=AlertType.CANNULA,
            severity=AlertSeverity.CRITICAL,
            message=f"Desconexión de cánula de oxígeno detectada en la cuna {reading.crib.code}.",
            measured_value=Decimal("0.0"),
            threshold_value=Decimal("1.0"),
        )

    return anomalies
