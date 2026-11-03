from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from alerts.models import Alert, AlertSeverity, AlertStatus, AlertType
from devices.services import create_crib
from medications.models import MedicationCatalogItem
from patients.models import Patient
from patients.services import admit_patient


class ApiFilterTests(APITestCase):
    def setUp(self) -> None:
        self.admin = User.objects.create_user(
            email="admin_filters@pokikoa.cl",
            full_name="Admin Filtros",
            password="Str0ng!Password2026",
            role=UserRole.ADMIN,
        )
        self.neonatologist = User.objects.create_user(
            email="neo_filters@pokikoa.cl",
            full_name="Neonatólogo Filtros",
            password="Str0ng!Password2026",
            role=UserRole.NEONATOLOGIST,
        )
        self.crib, _ = create_crib(actor=self.admin, code="C-F01")

    def _admit(self, mrn: str, weight_g: int) -> Patient:
        return admit_patient(
            actor=self.neonatologist,
            medical_record_number=mrn,
            full_name=f"Paciente {mrn}",
            sex="F",
            birth_date=timezone.localdate() - timedelta(days=3),
            gestational_age_weeks=Decimal("34.0"),
            birth_weight_g=weight_g,
        )

    def _create_alert(self, alert_status: str) -> Alert:
        now = timezone.now()
        return Alert.objects.create(
            crib=self.crib,
            alert_type=AlertType.HEART_RATE,
            severity=AlertSeverity.WARNING,
            status=alert_status,
            message="Alerta de prueba de filtros.",
            triggered_at=now,
            last_evaluated_at=now,
        )

    def test_alert_is_open_and_triggered_range_filters(self) -> None:
        active = self._create_alert(AlertStatus.ACTIVE)
        acknowledged = self._create_alert(AlertStatus.ACKNOWLEDGED)
        resolved = self._create_alert(AlertStatus.RESOLVED)
        self.client.force_authenticate(user=self.neonatologist)

        open_res = self.client.get("/api/v1/alerts/", {"is_open": "true"})
        self.assertEqual(open_res.status_code, status.HTTP_200_OK)
        open_ids = {a["id"] for a in open_res.data["results"]}
        self.assertEqual(open_ids, {active.id, acknowledged.id})

        closed_res = self.client.get("/api/v1/alerts/", {"is_open": "false"})
        self.assertEqual({a["id"] for a in closed_res.data["results"]}, {resolved.id})

        future = (timezone.now() + timedelta(hours=1)).isoformat()
        after_res = self.client.get("/api/v1/alerts/", {"triggered_after": future})
        self.assertEqual(after_res.data["count"], 0)
        before_res = self.client.get("/api/v1/alerts/", {"triggered_before": future})
        self.assertEqual(before_res.data["count"], 3)

    def test_patient_weight_and_admission_range_filters(self) -> None:
        light = self._admit("RN-F-001", 1200)
        medium = self._admit("RN-F-002", 2000)
        heavy = self._admit("RN-F-003", 3100)
        self.client.force_authenticate(user=self.neonatologist)

        res = self.client.get(
            "/api/v1/patients/", {"min_weight_g": 1500, "max_weight_g": 2500}
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual({p["id"] for p in res.data["results"]}, {medium.id})

        res_min = self.client.get("/api/v1/patients/", {"min_weight_g": 2000})
        self.assertEqual(
            {p["id"] for p in res_min.data["results"]}, {medium.id, heavy.id}
        )

        past = (timezone.now() - timedelta(days=1)).isoformat()
        res_after = self.client.get("/api/v1/patients/", {"admitted_after": past})
        self.assertEqual(
            {p["id"] for p in res_after.data["results"]},
            {light.id, medium.id, heavy.id},
        )
        res_before = self.client.get("/api/v1/patients/", {"admitted_before": past})
        self.assertEqual(res_before.data["count"], 0)

    def test_medication_catalog_low_stock_filter(self) -> None:
        low = MedicationCatalogItem.objects.create(
            name="Cafeína Citrato",
            active_ingredient="Cafeína",
            concentration_mg=Decimal("20.00"),
            stock=3,
            min_stock_alert=5,
        )
        boundary = MedicationCatalogItem.objects.create(
            name="Ampicilina",
            active_ingredient="Ampicilina",
            concentration_mg=Decimal("500.00"),
            stock=5,
            min_stock_alert=5,
        )
        healthy = MedicationCatalogItem.objects.create(
            name="Gentamicina",
            active_ingredient="Gentamicina",
            concentration_mg=Decimal("10.00"),
            stock=40,
            min_stock_alert=5,
        )
        self.client.force_authenticate(user=self.neonatologist)

        low_res = self.client.get("/api/v1/medication-catalog/", {"low_stock": "true"})
        self.assertEqual(low_res.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {m["id"] for m in low_res.data["results"]}, {low.id, boundary.id}
        )

        ok_res = self.client.get("/api/v1/medication-catalog/", {"low_stock": "false"})
        self.assertEqual({m["id"] for m in ok_res.data["results"]}, {healthy.id})

    def test_audit_log_timestamp_range_filter(self) -> None:
        self._admit("RN-F-010", 1800)
        self.client.force_authenticate(user=self.admin)

        future = (timezone.now() + timedelta(hours=1)).isoformat()
        before_res = self.client.get("/api/v1/audit-logs/", {"timestamp_before": future})
        self.assertEqual(before_res.status_code, status.HTTP_200_OK)
        self.assertGreater(before_res.data["count"], 0)

        after_res = self.client.get("/api/v1/audit-logs/", {"timestamp_after": future})
        self.assertEqual(after_res.data["count"], 0)

        invalid_res = self.client.get(
            "/api/v1/audit-logs/", {"timestamp_after": "no-es-fecha"}
        )
        self.assertEqual(invalid_res.status_code, status.HTTP_400_BAD_REQUEST)
