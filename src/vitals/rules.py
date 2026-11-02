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
        details={field_name: [f"El campo {label} debe ser un valor booleano estricto (true/false)."]},
    )


def validate_telemetry_payload(payload: dict[str, Any]) -> ValidatedTelemetryPayload:
    if not isinstance(payload, dict):
        raise DomainError("El cuerpo de telemetría debe ser un objeto JSON válido.")

    errors: dict[str, list[str]] = {}

    required_fields = (
        "heart_rate",
        "spo2",
        "temperature",
        "sleep_state",
        "cannula_connected",
        "iv_line_active",
    )
    for req_field in required_fields:
        if req_field not in payload:
            errors[req_field] = ["Este campo es obligatorio en cada lectura de telemetría."]

    if errors:
        raise DomainError(
            "Faltan campos obligatorios en la lectura de telemetría.",
            details=errors,
        )

    heart_rate = 0
    try:
        heart_rate = _parse_strict_int(payload["heart_rate"], "heart_rate", "frecuencia cardíaca")
        if not (HEART_RATE_MIN <= heart_rate <= HEART_RATE_MAX):
            errors["heart_rate"] = [
                f"La frecuencia cardíaca debe estar entre {HEART_RATE_MIN} y {HEART_RATE_MAX} lpm."
            ]
    except DomainError as exc:
        errors.update(exc.details)

    spo2 = 0
    try:
        spo2 = _parse_strict_int(payload["spo2"], "spo2", "SpO2")
        if not (SPO2_MIN <= spo2 <= SPO2_MAX):
            errors["spo2"] = [
                f"La saturación de oxígeno (SpO2) debe estar entre {SPO2_MIN}% y {SPO2_MAX}%."
            ]
    except DomainError as exc:
        errors.update(exc.details)

    temperature = Decimal("0.0")
    raw_temp = payload["temperature"]
    if isinstance(raw_temp, bool) or raw_temp is None:
        errors["temperature"] = ["La temperatura debe ser un número decimal válido."]
    else:
        try:
            temperature = Decimal(str(raw_temp)).quantize(Decimal("0.1"))
            if not (TEMPERATURE_MIN <= temperature <= TEMPERATURE_MAX):
                errors["temperature"] = [
                    f"La temperatura corporal debe estar entre {TEMPERATURE_MIN} y {TEMPERATURE_MAX} °C."
                ]
        except (InvalidOperation, ValueError):
            errors["temperature"] = ["La temperatura debe ser un número decimal válido."]

    sleep_state = payload["sleep_state"]
    if not isinstance(sleep_state, str) or sleep_state not in set(SleepState.values):
        errors["sleep_state"] = [
            "El estado de sueño debe ser 'asleep' o 'awake'."
        ]

    cannula_connected = False
    try:
        cannula_connected = _parse_strict_bool(
            payload["cannula_connected"], "cannula_connected", "conexión de cánula"
        )
    except DomainError as exc:
        errors.update(exc.details)

    iv_line_active = False
    try:
        iv_line_active = _parse_strict_bool(
            payload["iv_line_active"], "iv_line_active", "vía intravenosa activa"
        )
    except DomainError as exc:
        errors.update(exc.details)

    recorded_at = timezone.now()
    if payload.get("recorded_at") is not None:
        raw_ts = payload["recorded_at"]
        if isinstance(raw_ts, datetime):
            recorded_at = (
                timezone.make_aware(raw_ts) if timezone.is_naive(raw_ts) else raw_ts
            )
        elif isinstance(raw_ts, str):
            parsed = parse_datetime(raw_ts)
            if parsed is None:
                errors["recorded_at"] = ["El formato de fecha y hora (recorded_at) no es válido."]
            else:
                recorded_at = (
                    timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed
                )
        else:
            errors["recorded_at"] = ["El formato de fecha y hora (recorded_at) no es válido."]

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
