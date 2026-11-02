from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from devices.models import CribStatus
from devices.services import create_crib, update_crib
from patients.services import admit_patient
from poki_koa.exceptions import ConflictDomainError, DomainError, PermissionDomainError

from .models import VitalSignReading
from .rules import SleepState, validate_telemetry_payload
from .services import ingest_telemetry


class VitalsServiceAndRulesTests(TestCase):
    def setUp(self) -> None:
        self.admin = User.objects.create_user(
            email="admin_v@pokikoa.cl",
            full_name="Admin Vitals",
            password="Str0ng!Password2026",
            role=UserRole.ADMIN,
        )
        self.neo = User.objects.create_user(
            email="neo_v@pokikoa.cl",
            full_name="Neonatólogo Vitals",
            password="Str0ng!Password2026",
            role=UserRole.NEONATOLOGIST,
        )
        self.pharmacist = User.objects.create_user(
            email="pharm_v@pokikoa.cl",
            full_name="Farmacéutico Vitals",
            password="Str0ng!Password2026",
            role=UserRole.PHARMACIST,
        )
        self.crib, _ = create_crib(actor=self.admin, code="C-501")
        self.patient = admit_patient(
            actor=self.neo,
            medical_record_number="RN-VIT-01",
            full_name="RN Telemetría",
            sex="F",
            birth_date=timezone.localdate() - timedelta(days=1),
            gestational_age_weeks=Decimal("34.0"),
            birth_weight_g=2150,
            crib_id=self.crib.id,
        )

    def test_validate_telemetry_boundary_values_and_strict_types(self) -> None:
        # Límites inferiores válidos
        min_payload = validate_telemetry_payload(
            {
                "heart_rate": 1,
                "spo2": 0,
                "temperature": "25.0",
                "sleep_state": SleepState.ASLEEP,
                "cannula_connected": True,
                "iv_line_active": False,
            }
        )
        self.assertEqual(min_payload.heart_rate, 1)
        self.assertEqual(min_payload.spo2, 0)
        self.assertEqual(min_payload.temperature, Decimal("25.0"))

        # Límites superiores válidos
        max_payload = validate_telemetry_payload(
            {
                "heart_rate": 260,
                "spo2": 100,
                "temperature": "45.0",
                "sleep_state": SleepState.AWAKE,
                "cannula_connected": False,
                "iv_line_active": True,
            }
        )
        self.assertEqual(max_payload.heart_rate, 260)
        self.assertEqual(max_payload.spo2, 100)
        self.assertEqual(max_payload.temperature, Decimal("45.0"))

        # Equivalencias inválidas: fuera de rango o tipos booleanos en enteros
        invalid_payloads = [
            {
                "heart_rate": 0,
                "spo2": 98,
                "temperature": "36.8",
                "sleep_state": "asleep",
                "cannula_connected": True,
                "iv_line_active": True,
            },
            {
                "heart_rate": 261,
                "spo2": 98,
                "temperature": "36.8",
                "sleep_state": "asleep",
                "cannula_connected": True,
                "iv_line_active": True,
            },
            {
                "heart_rate": True,
                "spo2": 98,
                "temperature": "36.8",
                "sleep_state": "asleep",
                "cannula_connected": True,
                "iv_line_active": True,
            },
            {
                "heart_rate": 130,
                "spo2": 101,
                "temperature": "36.8",
                "sleep_state": "asleep",
                "cannula_connected": True,
                "iv_line_active": True,
            },
            {
                "heart_rate": 130,
                "spo2": 98,
                "temperature": "24.9",
                "sleep_state": "asleep",
                "cannula_connected": True,
                "iv_line_active": True,
            },
            {
                "heart_rate": 130,
                "spo2": 98,
                "temperature": "45.1",
                "sleep_state": "asleep",
                "cannula_connected": True,
                "iv_line_active": True,
            },
            {
                "heart_rate": 130,
                "spo2": 98,
                "temperature": "36.8",
                "sleep_state": "crying",
                "cannula_connected": True,
                "iv_line_active": True,
            },
            {
                "heart_rate": 130,
                "spo2": 98,
                "temperature": "36.8",
                "sleep_state": "asleep",
                "cannula_connected": "true",
                "iv_line_active": True,
            },
        ]
        for bad in invalid_payloads:
            with self.assertRaises(DomainError):
                validate_telemetry_payload(bad)

    def test_ingest_telemetry_atomic_rejection_and_permissions(self) -> None:
        valid_data = {
            "heart_rate": 135,
            "spo2": 97,
            "temperature": "36.8",
            "sleep_state": "asleep",
            "cannula_connected": True,
            "iv_line_active": True,
        }
        with self.assertRaises(PermissionDomainError):
            ingest_telemetry(
                crib=self.crib,
                payload=valid_data,
                actor_user=self.pharmacist,
                is_device_authenticated=False,
            )

        reading, eval_summary = ingest_telemetry(
            crib=self.crib,
            payload=valid_data,
            is_device_authenticated=True,
        )
        self.assertEqual(reading.patient_id, self.patient.id)
        self.assertEqual(len(eval_summary.created_alerts), 0)

        # Cuna deshabilitada rechaza telemetría atómicamente
        update_crib(
            actor=self.admin,
            crib=self.crib,
            data={"is_device_active": False},
        )
        with self.assertRaises(ConflictDomainError):
            ingest_telemetry(
                crib=self.crib,
                payload=valid_data,
                actor_user=self.neo,
            )
        self.assertEqual(VitalSignReading.objects.count(), 1)


class VitalsEndpointTests(APITestCase):
    def setUp(self) -> None:
        self.admin = User.objects.create_user(
            email="admin_vep@pokikoa.cl",
            full_name="Admin Vitals EP",
            password="Str0ng!Password2026",
            role=UserRole.ADMIN,
        )
        self.nurse = User.objects.create_user(
            email="nurse_vep@pokikoa.cl",
            full_name="Enfermera Vitals EP",
            password="Str0ng!Password2026",
            role=UserRole.NURSE,
        )
        self.pharmacist = User.objects.create_user(
            email="pharm_vep@pokikoa.cl",
            full_name="Farmacéutico Vitals EP",
            password="Str0ng!Password2026",
            role=UserRole.PHARMACIST,
        )
        self.crib1, self.crib1_key = create_crib(actor=self.admin, code="C-601")
        self.crib2, self.crib2_key = create_crib(actor=self.admin, code="C-602")
        self.patient = admit_patient(
            actor=self.nurse,
            medical_record_number="RN-VEP-01",
            full_name="RN Endpoint Telemetría",
            sex="M",
            birth_date=timezone.localdate(),
            gestational_age_weeks=Decimal("36.0"),
            birth_weight_g=2550,
            crib_id=self.crib1.id,
        )

    def test_device_api_key_ingestion_cross_crib_isolation_and_patient_history(self) -> None:
        payload = {
            "heart_rate": 140,
            "spo2": 98,
            "temperature": "36.9",
            "sleep_state": "asleep",
            "cannula_connected": True,
            "iv_line_active": False,
        }

        # Dispositivo 1 envía telemetría a su propia cuna (201)
        res_ok = self.client.post(
            f"/api/v1/cribs/{self.crib1.id}/telemetry/",
            payload,
            format="json",
            HTTP_X_DEVICE_API_KEY=self.crib1_key,
        )
        self.assertEqual(res_ok.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_ok.data["patient"], self.patient.id)
        self.assertEqual(res_ok.data["active_alerts"], [])

        # Dispositivo 2 intenta enviar telemetría a la cuna 1 -> 403 Forbidden
        res_cross = self.client.post(
            f"/api/v1/cribs/{self.crib1.id}/telemetry/",
            payload,
            format="json",
            HTTP_X_DEVICE_API_KEY=self.crib2_key,
        )
        self.assertEqual(res_cross.status_code, status.HTTP_403_FORBIDDEN)

        # Dispositivo intenta leer historial con GET -> 403 Forbidden
        res_dev_get = self.client.get(
            f"/api/v1/cribs/{self.crib1.id}/telemetry/",
            HTTP_X_DEVICE_API_KEY=self.crib1_key,
        )
        self.assertEqual(res_dev_get.status_code, status.HTTP_403_FORBIDDEN)

        # Farmacéutico autenticado con JWT no puede inyectar telemetría (403)
        self.client.force_authenticate(user=self.pharmacist)
        res_pharm = self.client.post(
            f"/api/v1/cribs/{self.crib1.id}/telemetry/",
            payload,
            format="json",
        )
        self.assertEqual(res_pharm.status_code, status.HTTP_403_FORBIDDEN)

        # Enfermera consulta historial por paciente y por cuna
        self.client.force_authenticate(user=self.nurse)
        patient_vitals = self.client.get(
            f"/api/v1/patients/{self.patient.id}/vitals/"
        )
        self.assertEqual(patient_vitals.status_code, status.HTTP_200_OK)
        self.assertEqual(patient_vitals.data["count"], 1)

        crib_vitals = self.client.get(
            f"/api/v1/cribs/{self.crib1.id}/telemetry/?sleep_state=asleep"
        )
        self.assertEqual(crib_vitals.status_code, status.HTTP_200_OK)
        self.assertEqual(crib_vitals.data["count"], 1)

        all_vitals = self.client.get(f"/api/v1/vitals/?patient={self.patient.id}")
        self.assertEqual(all_vitals.status_code, status.HTTP_200_OK)
        self.assertEqual(all_vitals.data["count"], 1)

        self.crib1.refresh_from_db()
        self.assertIsNotNone(self.crib1.last_telemetry_at)
        self.assertEqual(self.crib1.status, CribStatus.OCCUPIED)
