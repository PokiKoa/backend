from datetime import datetime
from decimal import Decimal

from django.test import SimpleTestCase
from django.utils import timezone

from poki_koa.exceptions import DomainError

from .rules import (
    HEART_RATE_MAX,
    HEART_RATE_MIN,
    SPO2_MAX,
    SPO2_MIN,
    TEMPERATURE_MAX,
    TEMPERATURE_MIN,
    validate_telemetry_payload,
)


def _payload(**overrides) -> dict:
    base = {
        "heart_rate": 140,
        "spo2": 97,
        "temperature": "36.8",
        "sleep_state": "asleep",
        "cannula_connected": True,
        "iv_line_active": False,
    }
    base.update(overrides)
    return base


class TelemetryRulesBoundaryTests(SimpleTestCase):
    def assert_rejected(self, payload, field: str) -> None:
        with self.assertRaises(DomainError) as ctx:
            validate_telemetry_payload(payload)
        self.assertIn(field, ctx.exception.details)

    def test_accepts_exact_physical_limits(self) -> None:
        low = validate_telemetry_payload(
            _payload(
                heart_rate=HEART_RATE_MIN,
                spo2=SPO2_MIN,
                temperature=str(TEMPERATURE_MIN),
            )
        )
        self.assertEqual(low.heart_rate, HEART_RATE_MIN)
        self.assertEqual(low.spo2, SPO2_MIN)
        self.assertEqual(low.temperature, TEMPERATURE_MIN)

        high = validate_telemetry_payload(
            _payload(
                heart_rate=HEART_RATE_MAX,
                spo2=SPO2_MAX,
                temperature=float(TEMPERATURE_MAX),
            )
        )
        self.assertEqual(high.heart_rate, HEART_RATE_MAX)
        self.assertEqual(high.spo2, SPO2_MAX)
        self.assertEqual(high.temperature, TEMPERATURE_MAX)

    def test_rejects_values_just_outside_limits(self) -> None:
        self.assert_rejected(_payload(heart_rate=HEART_RATE_MIN - 1), "heart_rate")
        self.assert_rejected(_payload(heart_rate=HEART_RATE_MAX + 1), "heart_rate")
        self.assert_rejected(_payload(spo2=SPO2_MIN - 1), "spo2")
        self.assert_rejected(_payload(spo2=SPO2_MAX + 1), "spo2")
        self.assert_rejected(_payload(temperature="24.9"), "temperature")
        self.assert_rejected(_payload(temperature="45.1"), "temperature")

    def test_numeric_strings_are_parsed_but_garbage_is_rejected(self) -> None:
        parsed = validate_telemetry_payload(_payload(heart_rate=" 150 ", spo2="96"))
        self.assertEqual(parsed.heart_rate, 150)
        self.assertEqual(parsed.spo2, 96)

        self.assert_rejected(_payload(heart_rate="abc"), "heart_rate")
        self.assert_rejected(_payload(heart_rate=140.5), "heart_rate")
        self.assert_rejected(_payload(spo2=None), "spo2")
        self.assert_rejected(_payload(temperature="no-numero"), "temperature")
        self.assert_rejected(_payload(temperature=None), "temperature")

    def test_booleans_must_be_strict(self) -> None:
        # Un booleano no es un entero válido para signos vitales
        self.assert_rejected(_payload(heart_rate=True), "heart_rate")
        self.assert_rejected(_payload(temperature=False), "temperature")
        # Valores "truthy" no se aceptan como booleanos
        self.assert_rejected(_payload(cannula_connected="true"), "cannula_connected")
        self.assert_rejected(_payload(iv_line_active=1), "iv_line_active")

    def test_sleep_state_must_be_known_value(self) -> None:
        self.assert_rejected(_payload(sleep_state="drowsy"), "sleep_state")
        self.assert_rejected(_payload(sleep_state=1), "sleep_state")

    def test_missing_fields_and_non_dict_payload(self) -> None:
        with self.assertRaises(DomainError):
            validate_telemetry_payload(["no", "es", "objeto"])

        payload = _payload()
        del payload["spo2"]
        del payload["sleep_state"]
        with self.assertRaises(DomainError) as ctx:
            validate_telemetry_payload(payload)
        self.assertEqual(set(ctx.exception.details), {"spo2", "sleep_state"})

    def test_multiple_errors_are_reported_together(self) -> None:
        with self.assertRaises(DomainError) as ctx:
            validate_telemetry_payload(_payload(heart_rate=0, spo2=150, temperature="50.0"))
        self.assertEqual(set(ctx.exception.details), {"heart_rate", "spo2", "temperature"})

    def test_recorded_at_parsing(self) -> None:
        aware = validate_telemetry_payload(_payload(recorded_at="2026-11-03T08:00:00-03:00"))
        self.assertTrue(timezone.is_aware(aware.recorded_at))

        naive_str = validate_telemetry_payload(_payload(recorded_at="2026-11-03T08:00:00"))
        self.assertTrue(timezone.is_aware(naive_str.recorded_at))

        # Fecha sin zona horaria a propósito: valida que se convierta a aware
        naive_dt = validate_telemetry_payload(
            _payload(recorded_at=datetime(2026, 11, 3, 8, 0, 0))  # noqa: DTZ001
        )
        self.assertTrue(timezone.is_aware(naive_dt.recorded_at))

        self.assert_rejected(_payload(recorded_at="ayer"), "recorded_at")
        self.assert_rejected(_payload(recorded_at=12345), "recorded_at")

    def test_temperature_is_quantized_to_one_decimal(self) -> None:
        parsed = validate_telemetry_payload(_payload(temperature=36.84))
        self.assertEqual(parsed.temperature, Decimal("36.8"))
