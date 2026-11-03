from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory, APITestCase

from accounts.models import User, UserRole
from audit.models import AuditAction, AuditLog
from patients.services import admit_patient
from poki_koa.exceptions import (
    ConflictDomainError,
    DomainError,
    PermissionDomainError,
)

from .authentication import DeviceApiKeyAuthentication, DevicePrincipal
from .models import Crib, CribStatus
from .services import (
    create_crib,
    detect_offline_cribs,
    rotate_crib_api_key,
    update_crib,
)


class DevicesServiceAndAuthTests(TestCase):
    def setUp(self) -> None:
        self.admin = User.objects.create_user(
            email="admin_dev@pokikoa.cl",
            full_name="Admin Dispositivos",
            password="Str0ng!Password2026",
            role=UserRole.ADMIN,
        )
        self.nurse = User.objects.create_user(
            email="nurse_dev@pokikoa.cl",
            full_name="Enfermera Dispositivos",
            password="Str0ng!Password2026",
            role=UserRole.NURSE,
        )

    def test_create_crib_and_authenticate_device_api_key(self) -> None:
        crib, raw_key = create_crib(
            actor=self.admin,
            code="c-101",
            name="Incubadora UCI 1",
            location="Sector A",
        )
        self.assertEqual(crib.code, "C-101")
        self.assertTrue(raw_key.startswith(f"{crib.api_key_prefix}_"))
        self.assertNotEqual(crib.api_key_hash, raw_key)

        factory = APIRequestFactory()
        request = factory.post(
            "/api/v1/telemetry/",
            HTTP_X_DEVICE_API_KEY=raw_key,
        )
        auth = DeviceApiKeyAuthentication()
        principal, auth_crib = auth.authenticate(request)
        self.assertIsInstance(principal, DevicePrincipal)
        self.assertEqual(auth_crib.id, crib.id)

        # Rotar API key invalida la credencial anterior
        new_key = rotate_crib_api_key(actor=self.admin, crib=crib)
        self.assertNotEqual(new_key, raw_key)

        old_req = factory.post(
            "/api/v1/telemetry/",
            HTTP_X_DEVICE_API_KEY=raw_key,
        )
        with self.assertRaises(AuthenticationFailed):
            auth.authenticate(old_req)

        new_req = factory.post(
            "/api/v1/telemetry/",
            HTTP_X_DEVICE_API_KEY=new_key,
        )
        _, rotated_crib = auth.authenticate(new_req)
        self.assertEqual(rotated_crib.id, crib.id)

    def test_create_crib_invalid_equivalence_classes_and_permissions(self) -> None:
        with self.assertRaises(PermissionDomainError):
            create_crib(actor=self.nurse, code="C-102")

        with self.assertRaises(DomainError):
            create_crib(actor=self.admin, code="   ")

        with self.assertRaises(DomainError):
            create_crib(actor=self.admin, code="C-102", status=CribStatus.OCCUPIED)

        create_crib(actor=self.admin, code="C-102")
        with self.assertRaises(ConflictDomainError):
            create_crib(actor=self.admin, code="c-102")

    def test_device_auth_rejects_inactive_or_maintenance_crib(self) -> None:
        crib, raw_key = create_crib(
            actor=self.admin,
            code="C-103",
            status=CribStatus.MAINTENANCE,
        )
        factory = APIRequestFactory()
        auth = DeviceApiKeyAuthentication()
        req = factory.post("/api/v1/telemetry/", HTTP_X_DEVICE_API_KEY=raw_key)
        with self.assertRaises(AuthenticationFailed):
            auth.authenticate(req)

        update_crib(
            actor=self.admin,
            crib=crib,
            data={"status": CribStatus.AVAILABLE, "is_device_active": False},
        )
        with self.assertRaises(AuthenticationFailed):
            auth.authenticate(req)


class DevicesEndpointTests(APITestCase):
    def setUp(self) -> None:
        self.admin = User.objects.create_user(
            email="admin_api@pokikoa.cl",
            full_name="Admin API",
            password="Str0ng!Password2026",
            role=UserRole.ADMIN,
        )
        self.neonatologist = User.objects.create_user(
            email="neo_api@pokikoa.cl",
            full_name="Neonatólogo API",
            password="Str0ng!Password2026",
            role=UserRole.NEONATOLOGIST,
        )
        self.nurse = User.objects.create_user(
            email="nurse_api@pokikoa.cl",
            full_name="Enfermera API",
            password="Str0ng!Password2026",
            role=UserRole.NURSE,
        )
        self.pharmacist = User.objects.create_user(
            email="pharm_api@pokikoa.cl",
            full_name="Farmacéutico API",
            password="Str0ng!Password2026",
            role=UserRole.PHARMACIST,
        )

    def test_crib_crud_rbac_and_patient_assignment_lifecycle(self) -> None:
        # Enfermera no puede dar de alta cunas
        self.client.force_authenticate(user=self.nurse)
        forbidden = self.client.post("/api/v1/cribs/", {"code": "C-201"}, format="json")
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

        # Admin crea dos cunas
        self.client.force_authenticate(user=self.admin)
        c1_res = self.client.post(
            "/api/v1/cribs/",
            {"code": "C-201", "name": "Cuna 1", "location": "UCI-A"},
            format="json",
        )
        self.assertEqual(c1_res.status_code, status.HTTP_201_CREATED)
        self.assertIn("api_key", c1_res.data)
        crib1_id = c1_res.data["id"]

        c2_res = self.client.post(
            "/api/v1/cribs/",
            {"code": "C-202", "name": "Cuna 2", "location": "UCI-B"},
            format="json",
        )
        crib2_id = c2_res.data["id"]

        # Admin actualiza metadatos y rota API key por endpoint
        patch_crib = self.client.patch(
            f"/api/v1/cribs/{crib2_id}/",
            {"code": "C-202B", "name": "Cuna 2 Bis", "location": "UCI-C"},
            format="json",
        )
        self.assertEqual(patch_crib.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_crib.data["code"], "C-202B")

        rot_res = self.client.post(f"/api/v1/cribs/{crib2_id}/rotate-key/")
        self.assertEqual(rot_res.status_code, status.HTTP_200_OK)
        self.assertIn("api_key", rot_res.data)

        # Admitir un paciente sin cuna inicial
        patient = admit_patient(
            actor=self.neonatologist,
            medical_record_number="RN-2026-001",
            full_name="Bebé Prueba Cuna",
            sex="F",
            birth_date=timezone.localdate() - timedelta(days=2),
            gestational_age_weeks="34.5",
            birth_weight_g=2100,
        )

        # Farmacéutico no puede asignar paciente a cuna
        self.client.force_authenticate(user=self.pharmacist)
        pharm_assign = self.client.post(
            f"/api/v1/cribs/{crib1_id}/assign-patient/",
            {"patient_id": patient.id},
            format="json",
        )
        self.assertEqual(pharm_assign.status_code, status.HTTP_403_FORBIDDEN)

        # Enfermera asigna paciente a cuna 1
        self.client.force_authenticate(user=self.nurse)
        assign_res = self.client.post(
            f"/api/v1/cribs/{crib1_id}/assign-patient/",
            {"patient_id": patient.id},
            format="json",
        )
        self.assertEqual(assign_res.status_code, status.HTTP_200_OK)
        self.assertEqual(assign_res.data["status"], CribStatus.OCCUPIED)
        self.assertEqual(assign_res.data["current_patient_id"], patient.id)

        # Reasignar al mismo paciente a cuna 2 libera automáticamente cuna 1
        reassign_res = self.client.post(
            f"/api/v1/cribs/{crib2_id}/assign-patient/",
            {"patient_id": patient.id},
            format="json",
        )
        self.assertEqual(reassign_res.status_code, status.HTTP_200_OK)
        self.assertEqual(reassign_res.data["status"], CribStatus.OCCUPIED)
        self.assertEqual(
            Crib.objects.get(pk=crib1_id).status,
            CribStatus.AVAILABLE,
        )

        # Liberar cuna 2
        release_res = self.client.post(
            f"/api/v1/cribs/{crib2_id}/release/",
            format="json",
        )
        self.assertEqual(release_res.status_code, status.HTTP_200_OK)
        self.assertEqual(release_res.data["status"], CribStatus.AVAILABLE)
        self.assertIsNone(release_res.data["current_patient_id"])

        # Liberar una cuna ya libre devuelve 409 Conflict
        double_release = self.client.post(
            f"/api/v1/cribs/{crib2_id}/release/",
            format="json",
        )
        self.assertEqual(double_release.status_code, status.HTTP_409_CONFLICT)

        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditAction.ASSIGN_CRIB,
                patient_id=patient.id,
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditAction.RELEASE_CRIB,
                patient_id=patient.id,
            ).exists()
        )

    def test_detect_offline_cribs_and_auto_resolve_on_telemetry_recovery(self) -> None:
        from alerts.models import Alert, AlertSeverity, AlertStatus, AlertType

        crib, raw_key = create_crib(
            actor=self.admin,
            code="C-205",
            name="Cuna Monitoreo",
            location="UCI-A",
        )
        patient = admit_patient(
            actor=self.neonatologist,
            medical_record_number="RN-2026-099",
            full_name="Bebé Offline Test",
            sex="M",
            birth_date=timezone.localdate() - timedelta(days=1),
            gestational_age_weeks="33.0",
            birth_weight_g=1850,
            crib_id=crib.id,
        )

        # Simular última telemetría hace 5 minutos
        Crib.objects.filter(pk=crib.pk).update(
            last_telemetry_at=timezone.now() - timedelta(minutes=5)
        )

        with self.assertRaises(DomainError):
            detect_offline_cribs(timeout_seconds=5)

        # Ejecutar verificación por endpoint REST
        self.client.force_authenticate(user=self.nurse)
        res = self.client.post(
            "/api/v1/cribs/check-offline/",
            {"timeout_seconds": 120},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["transitioned_count"], 1)

        crib.refresh_from_db()
        self.assertEqual(crib.status, CribStatus.OFFLINE)

        offline_alert = Alert.objects.get(
            crib=crib,
            alert_type=AlertType.SENSOR_FAULT,
            status=AlertStatus.ACTIVE,
        )
        self.assertEqual(offline_alert.severity, AlertSeverity.CRITICAL)
        self.assertEqual(offline_alert.patient_id, patient.id)

        # Cuando el dispositivo vuelve a reportar telemetría, la cuna vuelve a OCCUPIED
        # y la alerta de fallo de señal se autorresuelve automáticamente
        self.client.force_authenticate(user=None)
        telemetry_res = self.client.post(
            f"/api/v1/cribs/{crib.id}/telemetry/",
            {
                "heart_rate": 140,
                "spo2": 97,
                "temperature": "36.8",
                "sleep_state": "asleep",
                "cannula_connected": True,
                "iv_line_active": True,
            },
            format="json",
            HTTP_X_DEVICE_API_KEY=raw_key,
        )
        self.assertEqual(telemetry_res.status_code, status.HTTP_201_CREATED)

        crib.refresh_from_db()
        self.assertEqual(crib.status, CribStatus.OCCUPIED)

        offline_alert.refresh_from_db()
        self.assertEqual(offline_alert.status, AlertStatus.RESOLVED)
        self.assertEqual(offline_alert.resolution_reason, "auto_normalized")
