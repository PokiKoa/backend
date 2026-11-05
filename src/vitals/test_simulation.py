import io
import json
import random
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User, UserRole
from alerts.models import Alert
from devices.models import Crib, verify_device_api_key
from devices.services import create_crib
from patients.services import admit_patient

from . import rules
from .models import VitalSignReading
from .rules import validate_telemetry_payload
from .simulation import SimulatedCribState, next_payload


class TelemetrySimulationGeneratorTests(TestCase):
    def test_normal_readings_stay_within_warning_thresholds(self) -> None:
        rng = random.Random(7)
        state = SimulatedCribState()
        for _ in range(200):
            payload = next_payload(state, rng, anomaly_rate=0)
            validated = validate_telemetry_payload(payload)
            self.assertTrue(
                rules.DEFAULT_HR_CRITICAL_LOW
                < validated.heart_rate
                < rules.DEFAULT_HR_CRITICAL_HIGH
            )
            self.assertGreaterEqual(validated.spo2, rules.DEFAULT_SPO2_CRITICAL_LOW)
            self.assertTrue(
                rules.DEFAULT_TEMP_CRITICAL_LOW
                < validated.temperature
                < rules.DEFAULT_TEMP_CRITICAL_HIGH
            )
            self.assertTrue(validated.cannula_connected)

    def test_episode_drives_value_out_of_range_and_then_recovers(self) -> None:
        rng = random.Random(1)
        state = SimulatedCribState(episode="bradycardia", episode_ticks_left=6)
        payloads = [next_payload(state, rng, anomaly_rate=0) for _ in range(6)]
        self.assertLess(payloads[-1]["heart_rate"], rules.DEFAULT_HR_CRITICAL_LOW)
        self.assertIsNone(state.episode)

        for _ in range(10):
            payload = next_payload(state, rng, anomaly_rate=0)
        self.assertGreater(payload["heart_rate"], rules.DEFAULT_HR_WARNING_LOW)

    def test_cannula_episode_reports_disconnection(self) -> None:
        state = SimulatedCribState(episode="cannula_disconnected", episode_ticks_left=1)
        payload = next_payload(state, random.Random(0), anomaly_rate=0)
        self.assertFalse(payload["cannula_connected"])

    def test_values_are_clamped_to_physical_limits(self) -> None:
        state = SimulatedCribState(temperature=60.0, spo2=150.0)
        payload = next_payload(state, random.Random(0), anomaly_rate=0)
        validated = validate_telemetry_payload(payload)
        self.assertLessEqual(validated.temperature, rules.TEMPERATURE_MAX)
        self.assertLessEqual(validated.spo2, rules.SPO2_MAX)
        self.assertIsInstance(Decimal(payload["temperature"]), Decimal)


class SimulateTelemetryCommandTests(TestCase):
    def setUp(self) -> None:
        self.admin = User.objects.create_user(
            email="admin_sim@pokikoa.cl",
            full_name="Admin Simulación",
            password="Str0ng!Password2026",
            role=UserRole.ADMIN,
        )
        neo = User.objects.create_user(
            email="neo_sim@pokikoa.cl",
            full_name="Neo Simulación",
            password="Str0ng!Password2026",
            role=UserRole.NEONATOLOGIST,
        )
        self.crib, self.original_key = create_crib(actor=self.admin, code="C-SIM-1")
        self.empty_crib, _ = create_crib(actor=self.admin, code="C-SIM-2")
        admit_patient(
            actor=neo,
            medical_record_number="RN-SIM-01",
            full_name="RN Simulado",
            sex="F",
            birth_date=timezone.localdate() - timedelta(days=1),
            gestational_age_weeks=Decimal("33.0"),
            birth_weight_g=1800,
            current_weight_g=1800,
            diagnosis="Ficticio",
            attending_physician_id=neo.id,
            crib_id=self.crib.id,
        )

    def _call(self, *args: str) -> str:
        out = io.StringIO()
        call_command("simulate_telemetry", *args, stdout=out, stderr=io.StringIO())
        return out.getvalue()

    def test_refuses_to_run_without_debug(self) -> None:
        with self.assertRaisesMessage(CommandError, "DEBUG=True"):
            self._call("--mode", "direct", "--iterations", "1")

    @override_settings(DEBUG=True)
    def test_direct_mode_ingests_only_occupied_cribs(self) -> None:
        output = self._call(
            "--mode", "direct", "--iterations", "2", "--interval", "0", "--seed", "3"
        )
        self.assertEqual(VitalSignReading.objects.filter(crib=self.crib).count(), 2)
        self.assertFalse(VitalSignReading.objects.filter(crib=self.empty_crib).exists())
        self.assertIn("C-SIM-1", output)
        self.assertNotIn("C-SIM-2", output)

    @override_settings(DEBUG=True)
    def test_direct_mode_with_anomalies_generates_alerts(self) -> None:
        self._call(
            "--mode",
            "direct",
            "--iterations",
            "8",
            "--interval",
            "0",
            "--anomaly-rate",
            "1",
            "--seed",
            "5",
        )
        self.assertTrue(Alert.objects.filter(crib=self.crib).exists())

    @override_settings(DEBUG=True)
    def test_http_mode_rotates_key_and_posts_with_device_header(self) -> None:
        response = mock.MagicMock()
        response.read.return_value = json.dumps({"active_alerts": []}).encode()
        response.__enter__.return_value = response
        with mock.patch("urllib.request.urlopen", return_value=response) as urlopen:
            self._call("--cribs", "c-sim-1", "--iterations", "1", "--base-url", "http://api.test/")

        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url, f"http://api.test/api/v1/cribs/{self.crib.id}/telemetry/"
        )
        sent_key = request.get_header("X-device-api-key")
        self.crib.refresh_from_db()
        self.assertTrue(verify_device_api_key(sent_key, self.crib.api_key_hash))
        self.assertFalse(verify_device_api_key(self.original_key, self.crib.api_key_hash))
        self.assertIn("heart_rate", json.loads(request.data))

    @override_settings(DEBUG=True)
    def test_fails_when_no_cribs_match(self) -> None:
        Crib.objects.update(is_device_active=False)
        with self.assertRaisesMessage(CommandError, "No hay cunas"):
            self._call("--mode", "direct", "--iterations", "1")

    @override_settings(DEBUG=True)
    def test_rejects_invalid_anomaly_rate(self) -> None:
        with self.assertRaisesMessage(CommandError, "--anomaly-rate"):
            self._call("--anomaly-rate", "2")
