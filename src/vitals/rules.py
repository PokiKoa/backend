from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import models
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from poki_koa.exceptions import DomainError

# Fuente única de verdad para límites físicos de aceptación de telemetría neonatal
HEART_RATE_MIN = 1
HEART_RATE_MAX = 260

SPO2_MIN = 0
SPO2_MAX = 100

TEMPERATURE_MIN = Decimal("25.0")
TEMPERATURE_MAX = Decimal("45.0")

# Fuente única de verdad para umbrales clínicos neonatales por defecto
DEFAULT_HR_CRITICAL_LOW = 80
DEFAULT_HR_WARNING_LOW = 100
DEFAULT_HR_WARNING_HIGH = 160
DEFAULT_HR_CRITICAL_HIGH = 180

DEFAULT_SPO2_CRITICAL_LOW = 90
DEFAULT_SPO2_WARNING_LOW = 95

DEFAULT_TEMP_CRITICAL_LOW = Decimal("36.0")
DEFAULT_TEMP_WARNING_LOW = Decimal("36.5")
DEFAULT_TEMP_WARNING_HIGH = Decimal("37.5")
DEFAULT_TEMP_CRITICAL_HIGH = Decimal("38.5")


class SleepState(models.TextChoices):
    ASLEEP = "asleep", "Dormido"
    AWAKE = "awake", "Despierto"


@dataclass(frozen=True)
class ValidatedTelemetryPayload:
    heart_rate: int
    spo2: int
    temperature: Decimal
    sleep_state: str
    cannula_connected: bool
    iv_line_active: bool
    recorded_at: datetime


def _parse_strict_int(value: Any, field_name: str, label: str) -> int:
    if isinstance(value, bool) or value is None:
        raise DomainError(
            "Los datos de telemetría enviados no son válidos.",
            details={field_name: [f"El campo {label} debe ser un número entero."]},
        )
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    raise DomainError(
        "Los datos de telemetría enviados no son válidos.",
        details={field_name: [f"El campo {label} debe ser un número entero."]},
    )


def _parse_strict_bool(value: Any, field_name: str, label: str) -> bool:
    if isinstance(value, bool):
        return value
    raise DomainError(
        "Los datos de telemetría enviados no son válidos.",
        details={
            field_name: [f"El campo {label} debe ser un valor booleano estricto (true/false)."]
        },
    )


_REQUIRED_TELEMETRY_FIELDS = (
    "heart_rate",
    "spo2",
    "temperature",
    "sleep_state",
    "cannula_connected",
    "iv_line_active",
)


def _read_ranged_int(
    payload: dict[str, Any],
    errors: dict[str, list[str]],
    *,
    field: str,
    label: str,
    minimum: int,
    maximum: int,
    range_message: str,
) -> int:
    """Lee un entero estricto dentro de rango; acumula el error en ``errors`` y devuelve 0 si falla."""
    try:
        value = _parse_strict_int(payload[field], field, label)
    except DomainError as exc:
        errors.update(exc.details)
        return 0
    if not (minimum <= value <= maximum):
        errors[field] = [range_message]
    return value


def _read_bool(
    payload: dict[str, Any], errors: dict[str, list[str]], *, field: str, label: str
) -> bool:
    try:
        return _parse_strict_bool(payload[field], field, label)
    except DomainError as exc:
        errors.update(exc.details)
        return False


def _read_temperature(payload: dict[str, Any], errors: dict[str, list[str]]) -> Decimal:
    invalid = ["La temperatura debe ser un número decimal válido."]
    raw = payload["temperature"]
    if isinstance(raw, bool) or raw is None:
        errors["temperature"] = invalid
        return Decimal("0.0")
    try:
        temperature = Decimal(str(raw)).quantize(Decimal("0.1"))
    except (InvalidOperation, ValueError):
        errors["temperature"] = invalid
        return Decimal("0.0")
    if not (TEMPERATURE_MIN <= temperature <= TEMPERATURE_MAX):
        errors["temperature"] = [
            f"La temperatura corporal debe estar entre {TEMPERATURE_MIN} y {TEMPERATURE_MAX} °C."
        ]
    return temperature


def _read_recorded_at(payload: dict[str, Any], errors: dict[str, list[str]]) -> datetime:
    """Interpreta ``recorded_at`` (opcional); si falta usa la hora actual."""
    raw = payload.get("recorded_at")
    if raw is None:
        return timezone.now()
    parsed = raw if isinstance(raw, datetime) else None
    if isinstance(raw, str):
        parsed = parse_datetime(raw)
    if parsed is None:
        errors["recorded_at"] = ["El formato de fecha y hora (recorded_at) no es válido."]
        return timezone.now()
    return timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed


def validate_telemetry_payload(payload: dict[str, Any]) -> ValidatedTelemetryPayload:
    """Valida estrictamente una lectura de telemetría contra los rangos fisiológicos.

    Args:
        payload: Cuerpo JSON enviado por el dispositivo.

    Returns:
        La lectura tipada y normalizada.

    Raises:
        DomainError: Si el cuerpo no es un objeto, faltan campos obligatorios o algún
            valor es inválido o está fuera de rango (``details`` indica cada campo).
    """
    if not isinstance(payload, dict):
        raise DomainError("El cuerpo de telemetría debe ser un objeto JSON válido.")

    missing = {
        field: ["Este campo es obligatorio en cada lectura de telemetría."]
        for field in _REQUIRED_TELEMETRY_FIELDS
        if field not in payload
    }
    if missing:
        raise DomainError(
            "Faltan campos obligatorios en la lectura de telemetría.", details=missing
        )

    errors: dict[str, list[str]] = {}
    heart_rate = _read_ranged_int(
        payload,
        errors,
        field="heart_rate",
        label="frecuencia cardíaca",
        minimum=HEART_RATE_MIN,
        maximum=HEART_RATE_MAX,
        range_message=(
            f"La frecuencia cardíaca debe estar entre {HEART_RATE_MIN} y {HEART_RATE_MAX} lpm."
        ),
    )
    spo2 = _read_ranged_int(
        payload,
        errors,
        field="spo2",
        label="SpO2",
        minimum=SPO2_MIN,
        maximum=SPO2_MAX,
        range_message=(
            f"La saturación de oxígeno (SpO2) debe estar entre {SPO2_MIN}% y {SPO2_MAX}%."
        ),
    )
    temperature = _read_temperature(payload, errors)

    sleep_state = payload["sleep_state"]
    if not isinstance(sleep_state, str) or sleep_state not in set(SleepState.values):
        errors["sleep_state"] = ["El estado de sueño debe ser 'asleep' o 'awake'."]

    cannula_connected = _read_bool(
        payload, errors, field="cannula_connected", label="conexión de cánula"
    )
    iv_line_active = _read_bool(
        payload, errors, field="iv_line_active", label="vía intravenosa activa"
    )
    recorded_at = _read_recorded_at(payload, errors)

    if errors:
        raise DomainError(
            "Los datos de telemetría enviados no superaron la validación fisiológica.",
            details=errors,
        )

    return ValidatedTelemetryPayload(
        heart_rate=heart_rate,
        spo2=spo2,
        temperature=temperature,
        sleep_state=sleep_state,
        cannula_connected=cannula_connected,
        iv_line_active=iv_line_active,
        recorded_at=recorded_at,
    )
