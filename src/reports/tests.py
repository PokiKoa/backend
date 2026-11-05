from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from devices.services import create_crib, update_crib
from medications.services import (
    administer_prescription,
    create_catalog_item,
    create_prescription,
)
from patients.services import admit_patient, discharge_patient
from poki_koa.exceptions import DomainError
from vitals.services import ingest_telemetry

from .services import build_activity_series

PASSWORD = "Str0ng!Password2026"
CRITICAL_READING = {
    "heart_rate": 70,
    "spo2": 97,
    "temperature": "36.9",
    "sleep_state": "asleep",
    "cannula_connected": True,
    "iv_line_active": True,
}


class ReportsTests(APITestCase):
    def setUp(self) -> None:
        self.admin = User.objects.create_user(
            email="admin_rep@pokikoa.cl",
            full_name="Admin Rep",
            password=PASSWORD,
            role=UserRole.ADMIN,
        )
        self.neo = User.objects.create_user(
            email="neo_rep2@pokikoa.cl",
            full_name="Neo Rep",
            password=PASSWORD,
            role=UserRole.NEONATOLOGIST,
            shift="morning",
        )
        self.nurse = User.objects.create_user(
            email="nurse_rep2@pokikoa.cl",
            full_name="Enf Rep",
            password=PASSWORD,
            role=UserRole.NURSE,
        )
        pharmacist = User.objects.create_user(
            email="qf_rep2@pokikoa.cl",
            full_name="QF Rep",
            password=PASSWORD,
            role=UserRole.PHARMACIST,
        )
        self.crib, _ = create_crib(actor=self.admin, code="C-REP-1")
        create_crib(actor=self.admin, code="C-REP-2")
        broken, _ = create_crib(actor=self.admin, code="C-REP-3")
        update_crib(actor=self.admin, crib=broken, data={"status": "maintenance"})

        patient = self._admit("RN-REP-1", crib_id=self.crib.id)
        discharged = self._admit("RN-REP-2")
        discharge_patient(actor=self.neo, patient=discharged, outcome="survived")

        item = create_catalog_item(
            actor=pharmacist,
            name="Cafeína Rep",
            active_ingredient="Cafeína",
            concentration_mg="20",
            stock=3,
            min_stock_alert=5,
        )
        prescription = create_prescription(
            actor=self.neo,
            patient_id=patient.id,
            medication_id=item.id,
            dose="5 mg/kg",
            starts_at=timezone.now(),
        )
        administer_prescription(actor=self.nurse, prescription=prescription)
        ingest_telemetry(crib=self.crib, payload=CRITICAL_READING, is_device_authenticated=True)

    def _admit(self, mrn: str, crib_id: int | None = None):
        return admit_patient(
            actor=self.neo,
            medical_record_number=mrn,
            full_name=f"RN {mrn}",
            sex="M",
            birth_date=timezone.localdate() - timedelta(days=2),
            gestational_age_weeks=Decimal("33.0"),
            birth_weight_g=1900,
            crib_id=crib_id,
        )

    def test_summary_aggregates_every_domain(self) -> None:
        self.client.force_authenticate(user=self.nurse)
        response = self.client.get("/api/v1/reports/summary/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertEqual(data["patients"], {"total": 2, "active": 1, "discharged": 1})
        self.assertEqual(data["cribs"]["total"], 3)
        self.assertEqual(data["cribs"]["by_status"]["maintenance"], 1)
        self.assertEqual(data["cribs"]["occupancy_percent"], 33.3)
        self.assertEqual(data["prescriptions"]["by_status"]["completed"], 1)
        self.assertEqual(data["prescriptions"]["administrations_today"], 1)
        self.assertEqual(data["medications_low_stock"], 1)
        self.assertEqual(data["alerts"]["open"], 1)
        self.assertEqual(data["alerts"]["open_by_severity"]["critical"], 1)
        self.assertEqual(data["alerts"]["open_by_type"], {"heart_rate": 1})
        self.assertEqual(data["staff"]["active"], 4)
        self.assertEqual(data["staff"]["by_shift"], {"morning": 1})

    def test_series_counts_per_local_day(self) -> None:
        self.client.force_authenticate(user=self.nurse)
        response = self.client.get("/api/v1/reports/series/", {"days": 7})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 7)
        today = response.data[-1]
        self.assertEqual(today["date"], timezone.localdate().isoformat())
        self.assertEqual(today["admissions"], 2)
        self.assertEqual(today["alerts"], 1)
        self.assertEqual(sum(p["admissions"] for p in response.data[:-1]), 0)

    def test_series_validates_range(self) -> None:
        with self.assertRaises(DomainError):
            build_activity_series(days=0)
        self.client.force_authenticate(user=self.nurse)
        for days in ("91", "abc"):
            with self.subTest(days=days):
                response = self.client.get("/api/v1/reports/series/", {"days": days})
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_requires_authentication(self) -> None:
        self.assertEqual(
            self.client.get("/api/v1/reports/summary/").status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
