from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from audit.models import AuditAction, AuditLog
from devices.services import create_crib
from patients.models import DischargeOutcome
from patients.services import admit_patient, discharge_patient
from poki_koa.exceptions import ConflictDomainError, DomainError, PermissionDomainError
from vitals.services import ingest_telemetry

from .models import Alert, AlertSeverity, AlertStatus, AlertType, ResolutionReason
from .services import acknowledge_alert, resolve_alert, upsert_threshold_config


class AlertsEngineServiceTests(TestCase):
    def setUp(self) -> None:
        self.admin = User.objects.create_user(
            email="admin_al@pokikoa.cl",
            full_name="Admin Alertas",
            password="Str0ng!Password2026",
            role=UserRole.ADMIN,
        )
        self.neo = User.objects.create_user(
            email="neo_al@pokikoa.cl",
            full_name="Neonatóloga Alertas",
            password="Str0ng!Password2026",
            role=UserRole.NEONATOLOGIST,
        )
        self.nurse = User.objects.create_user(
            email="nurse_al@pokikoa.cl",
            full_name="Enfermera Alertas",
            password="Str0ng!Password2026",
            role=UserRole.NURSE,
        )
        self.pharmacist = User.objects.create_user(
            email="pharm_al@pokikoa.cl",
            full_name="Farmacéutico Alertas",
            password="Str0ng!Password2026",
            role=UserRole.PHARMACIST,
        )
        self.crib, _ = create_crib(actor=self.admin, code="C-701")
        self.patient = admit_patient(
            actor=self.neo,
            medical_record_number="RN-AL-01",
            full_name="RN Motor Alertas",
            sex="F",
            birth_date=timezone.localdate(),
            gestational_age_weeks=Decimal("32.0"),
            birth_weight_g=1680,
            crib_id=self.crib.id,
        )

    def test_deduplication_severity_escalation_and_auto_resolution(self) -> None:
        # 1. Lectura con taquicardia en nivel WARNING (FC 165 >= 160)
        _, eval1 = ingest_telemetry(
            crib=self.crib,
            payload={
                "heart_rate": 165,
                "spo2": 97,
                "temperature": "36.8",
                "sleep_state": "awake",
                "cannula_connected": True,
                "iv_line_active": True,
            },
            is_device_authenticated=True,
        )
        self.assertEqual(len(eval1.created_alerts), 1)
        alert_warn = eval1.created_alerts[0]
        self.assertEqual(alert_warn.alert_type, AlertType.HEART_RATE)
        self.assertEqual(alert_warn.severity, AlertSeverity.WARNING)
        self.assertEqual(alert_warn.occurrence_count, 1)

        # 2. Segunda lectura en el mismo nivel WARNING (FC 172) -> deduplica e incrementa contador
        _, eval2 = ingest_telemetry(
            crib=self.crib,
            payload={
                "heart_rate": 172,
                "spo2": 97,
                "temperature": "36.8",
                "sleep_state": "awake",
                "cannula_connected": True,
                "iv_line_active": True,
            },
            is_device_authenticated=True,
        )
        self.assertEqual(len(eval2.created_alerts), 0)
        self.assertEqual(len(eval2.deduplicated_alerts), 1)
        alert_warn.refresh_from_db()
        self.assertEqual(alert_warn.occurrence_count, 2)
        self.assertEqual(alert_warn.measured_value, Decimal("172.0"))

        # 3. Tercera lectura escala a CRITICAL (FC 190 >= 180) -> cierra la previa y abre crítica
        _, eval3 = ingest_telemetry(
            crib=self.crib,
            payload={
                "heart_rate": 190,
                "spo2": 97,
                "temperature": "36.8",
                "sleep_state": "awake",
                "cannula_connected": True,
                "iv_line_active": True,
            },
            is_device_authenticated=True,
        )
        alert_warn.refresh_from_db()
        self.assertEqual(alert_warn.status, AlertStatus.RESOLVED)
        self.assertEqual(alert_warn.resolution_reason, ResolutionReason.SEVERITY_ESCALATED)
        self.assertEqual(len(eval3.created_alerts), 1)
        alert_crit = eval3.created_alerts[0]
        self.assertEqual(alert_crit.severity, AlertSeverity.CRITICAL)
        self.assertEqual(alert_crit.status, AlertStatus.ACTIVE)

        # 4. Cuarta lectura vuelve a rango normal (FC 135) -> autorresolución
        _, eval4 = ingest_telemetry(
            crib=self.crib,
            payload={
                "heart_rate": 135,
                "spo2": 97,
                "temperature": "36.8",
                "sleep_state": "asleep",
                "cannula_connected": True,
                "iv_line_active": True,
            },
            is_device_authenticated=True,
        )
        self.assertEqual(len(eval4.auto_resolved_alerts), 1)
        alert_crit.refresh_from_db()
        self.assertEqual(alert_crit.status, AlertStatus.RESOLVED)
        self.assertEqual(alert_crit.resolution_reason, ResolutionReason.AUTO_NORMALIZED)

    def test_custom_threshold_ordering_validation_and_discharge_resolution(self) -> None:
        # Enfermera no puede modificar umbrales
        with self.assertRaises(PermissionDomainError):
            upsert_threshold_config(
                actor=self.nurse,
                patient=self.patient,
                data={"heart_rate_warning_high": 170},
            )

        # Orden inválido (critical_low >= warning_low) rechazado con DomainError
        with self.assertRaises(DomainError):
            upsert_threshold_config(
                actor=self.neo,
                patient=self.patient,
                data={
                    "heart_rate_critical_low": 110,
                    "heart_rate_warning_low": 100,
                },
            )

        # Personalizar umbral para este paciente (warning_high = 175)
        upsert_threshold_config(
            actor=self.neo,
            patient=self.patient,
            data={
                "heart_rate_warning_high": 175,
                "heart_rate_critical_high": 195,
            },
        )

        # FC 168 ahora es normal para este paciente pero desconexión de cánula dispara crítica
        _, eval_res = ingest_telemetry(
            crib=self.crib,
            payload={
                "heart_rate": 168,
                "spo2": 97,
                "temperature": "36.8",
                "sleep_state": "asleep",
                "cannula_connected": False,
                "iv_line_active": True,
            },
            is_device_authenticated=True,
        )
        self.assertEqual(len(eval_res.created_alerts), 1)
        cannula_alert = eval_res.created_alerts[0]
        self.assertEqual(cannula_alert.alert_type, AlertType.CANNULA)

        # Reconocimiento por servicio y rechazo de doble reconocimiento (ConflictDomainError)
        acknowledged = acknowledge_alert(actor=self.nurse, alert=cannula_alert)
        self.assertEqual(acknowledged.status, AlertStatus.ACKNOWLEDGED)
        with self.assertRaises(ConflictDomainError):
            acknowledge_alert(actor=self.nurse, alert=cannula_alert)

        # Al egresar al paciente, las alertas abiertas se resuelven con 'patient_discharged'
        discharge_patient(
            actor=self.neo,
            patient=self.patient,
            outcome=DischargeOutcome.SURVIVED,
        )
        cannula_alert.refresh_from_db()
        self.assertEqual(cannula_alert.status, AlertStatus.RESOLVED)
        self.assertEqual(
            cannula_alert.resolution_reason,
            ResolutionReason.PATIENT_DISCHARGED,
        )
        with self.assertRaises(ConflictDomainError):
            resolve_alert(actor=self.neo, alert=cannula_alert)


class AlertsEndpointTests(APITestCase):
    def setUp(self) -> None:
        self.admin = User.objects.create_user(
            email="admin_aep@pokikoa.cl",
            full_name="Admin Alertas EP",
            password="Str0ng!Password2026",
            role=UserRole.ADMIN,
        )
        self.neo = User.objects.create_user(
            email="neo_aep@pokikoa.cl",
            full_name="Neonatólogo Alertas EP",
            password="Str0ng!Password2026",
            role=UserRole.NEONATOLOGIST,
        )
        self.nurse = User.objects.create_user(
            email="nurse_aep@pokikoa.cl",
            full_name="Enfermera Alertas EP",
            password="Str0ng!Password2026",
            role=UserRole.NURSE,
        )
        self.pharmacist = User.objects.create_user(
            email="pharm_aep@pokikoa.cl",
            full_name="Farmacéutico Alertas EP",
            password="Str0ng!Password2026",
            role=UserRole.PHARMACIST,
        )
        self.crib, self.crib_key = create_crib(actor=self.admin, code="C-801")
        self.patient = admit_patient(
            actor=self.neo,
            medical_record_number="RN-AEP-01",
            full_name="RN Endpoint Alertas",
            sex="M",
            birth_date=timezone.localdate(),
            gestational_age_weeks=Decimal("30.0"),
            birth_weight_g=1400,
            crib_id=self.crib.id,
        )

    def test_alert_lifecycle_endpoints_acknowledge_resolve_and_thresholds(self) -> None:
        # Ingerir lectura con hipoxemia crítica (SpO2 85% < 90%) y bradicardia crítica (FC 75 <= 80)
        ingest_res = self.client.post(
            f"/api/v1/cribs/{self.crib.id}/telemetry/",
            {
                "heart_rate": 75,
                "spo2": 85,
                "temperature": "35.8",
                "sleep_state": "asleep",
                "cannula_connected": True,
                "iv_line_active": True,
            },
            format="json",
            HTTP_X_DEVICE_API_KEY=self.crib_key,
        )
        self.assertEqual(ingest_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(ingest_res.data["active_alerts"]), 3)

        alert_id = ingest_res.data["active_alerts"][0]["id"]

        # Farmacéutico no puede reconocer ni resolver alertas (403)
        self.client.force_authenticate(user=self.pharmacist)
        pharm_ack = self.client.post(f"/api/v1/alerts/{alert_id}/acknowledge/")
        self.assertEqual(pharm_ack.status_code, status.HTTP_403_FORBIDDEN)

        # Enfermera reconoce la alerta (200)
        self.client.force_authenticate(user=self.nurse)
        ack_res = self.client.post(f"/api/v1/alerts/{alert_id}/acknowledge/")
        self.assertEqual(ack_res.status_code, status.HTTP_200_OK)
        self.assertEqual(ack_res.data["status"], AlertStatus.ACKNOWLEDGED)
        self.assertEqual(ack_res.data["acknowledged_by"], self.nurse.id)

        # Segundo reconocimiento sobre la misma alerta devuelve 409 Conflict
        dup_ack = self.client.post(f"/api/v1/alerts/{alert_id}/acknowledge/")
        self.assertEqual(dup_ack.status_code, status.HTTP_409_CONFLICT)

        # Enfermera resuelve manualmente la alerta (200)
        res_manual = self.client.post(f"/api/v1/alerts/{alert_id}/resolve/")
        self.assertEqual(res_manual.status_code, status.HTTP_200_OK)
        self.assertEqual(res_manual.data["status"], AlertStatus.RESOLVED)
        self.assertEqual(res_manual.data["resolution_reason"], ResolutionReason.MANUAL)

        # Intentar resolver nuevamente devuelve 409 Conflict
        dup_res = self.client.post(f"/api/v1/alerts/{alert_id}/resolve/")
        self.assertEqual(dup_res.status_code, status.HTTP_409_CONFLICT)

        # Consultar y actualizar umbrales globales y por paciente
        self.client.force_authenticate(user=self.neo)
        def_get = self.client.get("/api/v1/alert-thresholds/default/")
        self.assertEqual(def_get.status_code, status.HTTP_200_OK)
        self.assertEqual(def_get.data["spo2_critical_low"], 90)

        def_put = self.client.put(
            "/api/v1/alert-thresholds/default/",
            {"spo2_critical_low": 88, "spo2_warning_low": 94},
            format="json",
        )
        self.assertEqual(def_put.status_code, status.HTTP_200_OK)
        self.assertEqual(def_put.data["spo2_critical_low"], 88)

        pat_thr_put = self.client.put(
            f"/api/v1/patients/{self.patient.id}/alert-thresholds/",
            {"spo2_critical_low": 89, "spo2_warning_low": 95},
            format="json",
        )
        self.assertEqual(pat_thr_put.status_code, status.HTTP_200_OK)
        self.assertEqual(pat_thr_put.data["spo2_critical_low"], 89)

        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditAction.ACKNOWLEDGE_ALERT,
                resource_id=str(alert_id),
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditAction.RESOLVE_ALERT,
                resource_id=str(alert_id),
            ).exists()
        )
        self.assertEqual(
            Alert.objects.filter(patient=self.patient, status=AlertStatus.ACTIVE).count(),
            2,
        )
