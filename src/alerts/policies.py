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
)


def evaluate_vital_reading(
    reading: VitalSignReading,
    thresholds: AlertThresholdConfig,
) -> dict[str, DetectedAnomaly]:
    """Evalúa una lectura de signos vitales frente a los umbrales configurados."""
    anomalies: dict[str, DetectedAnomaly] = {}

    hr = reading.heart_rate
    if hr <= thresholds.heart_rate_critical_low:
        anomalies[AlertType.HEART_RATE] = DetectedAnomaly(
            alert_type=AlertType.HEART_RATE,
            severity=AlertSeverity.CRITICAL,
            message=(
                f"Bradicardia crítica neonatal: FC {hr} lpm "
                f"(umbral <= {thresholds.heart_rate_critical_low} lpm)."
            ),
            measured_value=Decimal(hr),
            threshold_value=Decimal(thresholds.heart_rate_critical_low),
        )
    elif hr >= thresholds.heart_rate_critical_high:
        anomalies[AlertType.HEART_RATE] = DetectedAnomaly(
            alert_type=AlertType.HEART_RATE,
            severity=AlertSeverity.CRITICAL,
            message=(
                f"Taquicardia crítica neonatal: FC {hr} lpm "
                f"(umbral >= {thresholds.heart_rate_critical_high} lpm)."
            ),
            measured_value=Decimal(hr),
            threshold_value=Decimal(thresholds.heart_rate_critical_high),
        )
    elif hr <= thresholds.heart_rate_warning_low:
        anomalies[AlertType.HEART_RATE] = DetectedAnomaly(
            alert_type=AlertType.HEART_RATE,
            severity=AlertSeverity.WARNING,
            message=(
                f"Alerta de bradicardia neonatal: FC {hr} lpm "
                f"(umbral <= {thresholds.heart_rate_warning_low} lpm)."
            ),
            measured_value=Decimal(hr),
            threshold_value=Decimal(thresholds.heart_rate_warning_low),
        )
    elif hr >= thresholds.heart_rate_warning_high:
        anomalies[AlertType.HEART_RATE] = DetectedAnomaly(
            alert_type=AlertType.HEART_RATE,
            severity=AlertSeverity.WARNING,
            message=(
                f"Alerta de taquicardia neonatal: FC {hr} lpm "
                f"(umbral >= {thresholds.heart_rate_warning_high} lpm)."
            ),
            measured_value=Decimal(hr),
            threshold_value=Decimal(thresholds.heart_rate_warning_high),
        )

    spo2 = reading.spo2
    if spo2 < thresholds.spo2_critical_low:
        anomalies[AlertType.SPO2] = DetectedAnomaly(
            alert_type=AlertType.SPO2,
            severity=AlertSeverity.CRITICAL,
            message=(
                f"Hipoxemia crítica: SpO2 {spo2}% "
                f"(umbral < {thresholds.spo2_critical_low}%)."
            ),
            measured_value=Decimal(spo2),
            threshold_value=Decimal(thresholds.spo2_critical_low),
        )
    elif spo2 < thresholds.spo2_warning_low:
        anomalies[AlertType.SPO2] = DetectedAnomaly(
            alert_type=AlertType.SPO2,
            severity=AlertSeverity.WARNING,
            message=(
                f"Saturación de oxígeno baja: SpO2 {spo2}% "
                f"(umbral < {thresholds.spo2_warning_low}%)."
            ),
            measured_value=Decimal(spo2),
            threshold_value=Decimal(thresholds.spo2_warning_low),
        )

    temp = reading.temperature
    if temp <= thresholds.temp_critical_low:
        anomalies[AlertType.TEMPERATURE] = DetectedAnomaly(
            alert_type=AlertType.TEMPERATURE,
            severity=AlertSeverity.CRITICAL,
            message=(
                f"Hipotermia crítica: temperatura {temp} °C "
                f"(umbral <= {thresholds.temp_critical_low} °C)."
            ),
            measured_value=temp,
            threshold_value=thresholds.temp_critical_low,
        )
    elif temp >= thresholds.temp_critical_high:
        anomalies[AlertType.TEMPERATURE] = DetectedAnomaly(
            alert_type=AlertType.TEMPERATURE,
            severity=AlertSeverity.CRITICAL,
            message=(
                f"Hipertermia crítica: temperatura {temp} °C "
                f"(umbral >= {thresholds.temp_critical_high} °C)."
            ),
            measured_value=temp,
            threshold_value=thresholds.temp_critical_high,
        )
    elif temp <= thresholds.temp_warning_low:
        anomalies[AlertType.TEMPERATURE] = DetectedAnomaly(
            alert_type=AlertType.TEMPERATURE,
            severity=AlertSeverity.WARNING,
            message=(
                f"Riesgo de hipotermia: temperatura {temp} °C "
                f"(umbral <= {thresholds.temp_warning_low} °C)."
            ),
            measured_value=temp,
            threshold_value=thresholds.temp_warning_low,
        )
    elif temp >= thresholds.temp_warning_high:
        anomalies[AlertType.TEMPERATURE] = DetectedAnomaly(
            alert_type=AlertType.TEMPERATURE,
            severity=AlertSeverity.WARNING,
            message=(
                f"Temperatura elevada: {temp} °C "
                f"(umbral >= {thresholds.temp_warning_high} °C)."
            ),
            measured_value=temp,
            threshold_value=thresholds.temp_warning_high,
        )

    if not reading.cannula_connected:
        anomalies[AlertType.CANNULA] = DetectedAnomaly(
            alert_type=AlertType.CANNULA,
            severity=AlertSeverity.CRITICAL,
            message=f"Desconexión de cánula de oxígeno detectada en la cuna {reading.crib.code}.",
            measured_value=Decimal("0.0"),
            threshold_value=Decimal("1.0"),
        )

    return anomalies
