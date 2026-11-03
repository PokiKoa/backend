from datetime import timedelta
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from alerts.models import Alert, AlertSeverity, AlertStatus
from alerts.services import acknowledge_alert
from devices.services import create_crib, update_crib
from patients.services import admit_patient

from .services import ingest_telemetry

NORMAL = {
    "heart_rate": 135,
    "spo2": 97,
    "temperature": "36.9",
    "sleep_state": "asleep",
    "cannula_connected": True,
    "iv_line_active": True,
}


class UnitOverviewEndpointTests(APITestCase):
    def setUp(self) -> None:
        self.admin = User.objects.create_user(
            email="admin_ov@pokikoa.cl",
            full_name="Admin Overview",
            password="Str0ng!Password2026",
            role=UserRole.ADMIN,
        )
        self.neo = User.objects.create_user(
            email="neo_ov@pokikoa.cl",
            full_name="Neo Overview",
            password="Str0ng!Password2026",
            role=UserRole.NEONATOLOGIST,
        )
        self.pharmacist = User.objects.create_user(
            email="qf_ov@pokikoa.cl",
            full_name="QF Overview",
            password="Str0ng!Password2026",
            role=UserRole.PHARMACIST,
        )
        self.occupied, _ = create_crib(actor=self.admin, code="C-OV-1")
        self.empty, _ = create_crib(actor=self.admin, code="C-OV-2")
        self.maintenance, _ = create_crib(actor=self.admin, code="C-OV-3")
        update_crib(actor=self.admin, crib=self.maintenance, data={"status": "maintenance"})
        self.patient = self._admit("RN-OV-01", self.occupied)
        self.url = reverse("monitoring-overview")

    def _admit(self, mrn: str, crib):
        return admit_patient(
            actor=self.neo,
            medical_record_number=mrn,
            full_name=f"RN {mrn}",
            sex="M",
            birth_date=timezone.localdate() - timedelta(days=3),
            gestational_age_weeks=Decimal("32.0"),
            birth_weight_g=1600,
            current_weight_g=1650,
            diagnosis="Ficticio",
            attending_physician_id=self.neo.id,
            crib_id=crib.id,
        )

    def _crib_row(self, data: dict, code: str) -> dict:
        return next(row for row in data["cribs"] if row["code"] == code)

    def test_requires_authentication(self) -> None:
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_overview_combines_patient_latest_reading_and_open_alerts(self) -> None:
        ingest_telemetry(crib=self.occupied, payload=NORMAL, is_device_authenticated=True)
        ingest_telemetry(
            crib=self.occupied,
            payload={**NORMAL, "heart_rate": 70, "spo2": 93},
            is_device_authenticated=True,
        )

        self.client.force_authenticate(user=self.pharmacist)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertEqual([row["code"] for row in data["cribs"]], ["C-OV-1", "C-OV-2", "C-OV-3"])
        row = self._crib_row(data, "C-OV-1")
        self.assertEqual(row["patient"]["id"], self.patient.id)
        self.assertEqual(row["patient"]["age_days"], 3)
        self.assertEqual(row["latest_reading"]["heart_rate"], 70)
        self.assertEqual(row["open_alerts"]["critical"], 1)
        self.assertEqual(row["open_alerts"]["warning"], 1)
        self.assertEqual(row["open_alerts"]["total"], 2)
        self.assertEqual(row["highest_open_severity"], AlertSeverity.CRITICAL)

        empty = self._crib_row(data, "C-OV-2")
        self.assertIsNone(empty["patient"])
        self.assertIsNone(empty["latest_reading"])
        self.assertEqual(empty["open_alerts"]["total"], 0)
        self.assertIsNone(empty["highest_open_severity"])

        summary = data["summary"]
        self.assertEqual(summary["cribs_total"], 3)
        self.assertEqual(
            summary["cribs_by_status"],
            {"available": 1, "occupied": 1, "maintenance": 1, "offline": 0},
        )
        self.assertEqual(summary["patients_monitored"], 1)
        self.assertEqual(summary["open_alerts"]["total"], 2)

    def test_acknowledged_alerts_stay_open_and_resolved_ones_are_excluded(self) -> None:
        ingest_telemetry(
            crib=self.occupied, payload={**NORMAL, "heart_rate": 70}, is_device_authenticated=True
        )
        alert = Alert.objects.get(crib=self.occupied, status=AlertStatus.ACTIVE)
        acknowledge_alert(actor=self.neo, alert=alert)

        self.client.force_authenticate(user=self.neo)
        row = self._crib_row(self.client.get(self.url).json(), "C-OV-1")
        self.assertEqual(row["open_alerts"]["total"], 1)

        ingest_telemetry(crib=self.occupied, payload=NORMAL, is_device_authenticated=True)
        row = self._crib_row(self.client.get(self.url).json(), "C-OV-1")
        self.assertEqual(row["open_alerts"]["total"], 0)

    def test_query_count_does_not_grow_with_number_of_cribs(self) -> None:
        ingest_telemetry(crib=self.occupied, payload=NORMAL, is_device_authenticated=True)
        self.client.force_authenticate(user=self.neo)
        with CaptureQueriesContext(connection) as baseline:
            self.client.get(self.url)

        for index in range(4):
            crib, _ = create_crib(actor=self.admin, code=f"C-OV-X{index}")
            self._admit(f"RN-OV-X{index}", crib)
            ingest_telemetry(
                crib=crib, payload={**NORMAL, "spo2": 85}, is_device_authenticated=True
            )
        with CaptureQueriesContext(connection) as scaled:
            response = self.client.get(self.url)

        self.assertEqual(len(response.json()["cribs"]), 7)
        self.assertEqual(len(scaled), len(baseline))
