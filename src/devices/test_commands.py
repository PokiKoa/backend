import io
from datetime import timedelta
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError
from django.test import TestCase
from django.utils import timezone

from accounts.models import User, UserRole
from alerts.models import Alert, AlertType

from .models import Crib, CribStatus
from .services import create_crib


class CheckOfflineCribsCommandTests(TestCase):
    def setUp(self) -> None:
        admin = User.objects.create_user(
            email="admin_cmd@pokikoa.cl",
            full_name="Admin Comandos",
            password="Str0ng!Password2026",
            role=UserRole.ADMIN,
        )
        self.crib, _ = create_crib(actor=admin, code="C-CMD-1")
        Crib.objects.filter(pk=self.crib.pk).update(
            last_telemetry_at=timezone.now() - timedelta(minutes=10)
        )

    def _call(self, *args: str) -> tuple[str, str]:
        out, err = io.StringIO(), io.StringIO()
        call_command("check_offline_cribs", *args, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def test_single_run_marks_stale_crib_offline(self) -> None:
        out, _ = self._call()
        self.crib.refresh_from_db()
        self.assertEqual(self.crib.status, CribStatus.OFFLINE)
        self.assertIn("C-CMD-1", out)
        self.assertTrue(
            Alert.objects.filter(crib=self.crib, alert_type=AlertType.SENSOR_FAULT).exists()
        )

    def test_every_repeats_until_max_runs_and_sleeps_between_runs(self) -> None:
        with mock.patch("devices.management.commands.check_offline_cribs.time.sleep") as sleep:
            out, _ = self._call("--every", "30", "--max-runs", "3")
        self.assertEqual(sleep.call_count, 2)
        sleep.assert_called_with(30)
        self.assertEqual(out.count("offline"), 1)
        self.assertEqual(out.count("Sin cunas desconectadas"), 2)

    def test_every_survives_transient_database_errors(self) -> None:
        target = "devices.management.commands.check_offline_cribs.detect_offline_cribs"
        with (
            mock.patch("devices.management.commands.check_offline_cribs.time.sleep"),
            mock.patch(target, side_effect=[OperationalError("sin tablas"), []]) as detect,
        ):
            out, err = self._call("--every", "5", "--max-runs", "2")
        self.assertEqual(detect.call_count, 2)
        self.assertIn("Error de base de datos", err)
        self.assertIn("Sin cunas desconectadas", out)

    def test_rejects_negative_interval(self) -> None:
        with self.assertRaisesMessage(CommandError, "--every"):
            self._call("--every", "-1")
