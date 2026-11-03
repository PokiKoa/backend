import json
from datetime import timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import unquote, urlparse

from asgiref.sync import async_to_sync, sync_to_async
from asgiref.testing import ApplicationCommunicator
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import User, UserRole
from alerts.services import acknowledge_alert, resolve_alert
from audit.models import AuditAction, AuditLog
from devices.models import CribStatus
from devices.services import create_crib, update_crib
from patients.services import admit_patient
from poki_koa.asgi import application
from poki_koa.exceptions import ConflictDomainError, DomainError, PermissionDomainError

from .consumers import (
    WS_CLOSE_FORBIDDEN,
    WS_CLOSE_NOT_FOUND,
    WS_CLOSE_UNAUTHORIZED,
)
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


class WebsocketCommunicator(ApplicationCommunicator):
    def __init__(
        self,
        app: Any,
        path: str,
        headers: list[tuple[bytes, bytes]] | None = None,
        subprotocols: list[str] | None = None,
    ) -> None:
        parsed = urlparse(path)
        scope = {
            "type": "websocket",
            "path": unquote(parsed.path),
            "query_string": parsed.query.encode("utf-8"),
            "headers": headers or [],
            "subprotocols": subprotocols or [],
        }
        super().__init__(app, scope)

    async def connect(self, timeout: float = 1.0) -> tuple[bool, int | None]:
        await self.send_input({"type": "websocket.connect"})
        response = await self.receive_output(timeout)
        if response["type"] == "websocket.close":
            return False, response.get("code", 1000)
        return True, response.get("subprotocol")

    async def send_json_to(self, data: dict[str, Any]) -> None:
        await self.send_input(
            {"type": "websocket.receive", "text": json.dumps(data)}
        )

    async def receive_json_from(self, timeout: float = 1.0) -> dict[str, Any]:
        response = await self.receive_output(timeout)
        return json.loads(response["text"])

    async def disconnect(self, code: int = 1000, timeout: float = 1.0) -> None:
        await self.send_input({"type": "websocket.disconnect", "code": code})
        await self.wait(timeout)


class RealtimeWebSocketTests(TransactionTestCase):
    def setUp(self) -> None:
        self.admin = User.objects.create_user(
            email="admin_ws@pokikoa.cl",
            full_name="Admin WS",
            password="Str0ng!Password2026",
            role=UserRole.ADMIN,
        )
        self.nurse = User.objects.create_user(
            email="nurse_ws@pokikoa.cl",
            full_name="Enfermera WS",
            password="Str0ng!Password2026",
            role=UserRole.NURSE,
        )
        self.pharmacist = User.objects.create_user(
            email="pharm_ws@pokikoa.cl",
            full_name="Farmacéutico WS",
            password="Str0ng!Password2026",
            role=UserRole.PHARMACIST,
        )
        self.crib, _ = create_crib(actor=self.admin, code="C-901")
        self.patient = admit_patient(
            actor=self.nurse,
            medical_record_number="RN-WS-01",
            full_name="RN Tiempo Real",
            sex="F",
            birth_date=timezone.localdate(),
            gestational_age_weeks=Decimal("34.0"),
            birth_weight_g=2100,
            crib_id=self.crib.id,
        )

    def test_websocket_auth_rbac_and_realtime_telemetry_alert_broadcast(self) -> None:
        nurse_token = str(AccessToken.for_user(self.nurse))
        pharm_token = str(AccessToken.for_user(self.pharmacist))

        async def _run_scenario() -> None:
            # 1. Conexión sin token es rechazada con 4401
            unauth_comm = WebsocketCommunicator(
                application, "/ws/v1/monitoring/stream/"
            )
            connected, close_code = await unauth_comm.connect()
            self.assertFalse(connected)
            self.assertEqual(close_code, WS_CLOSE_UNAUTHORIZED)

            # 2. Rol no autorizado (Farmacéutico) es rechazado con 4403
            forbidden_comm = WebsocketCommunicator(
                application,
                "/ws/v1/monitoring/stream/",
                subprotocols=["bearer", pharm_token],
            )
            connected_f, close_code_f = await forbidden_comm.connect()
            self.assertFalse(connected_f)
            self.assertEqual(close_code_f, WS_CLOSE_FORBIDDEN)

            # 3. Cuna inexistente devuelve 4404
            not_found_comm = WebsocketCommunicator(
                application,
                "/ws/v1/cribs/999999/stream/",
                subprotocols=["bearer", nurse_token],
            )
            connected_nf, close_code_nf = await not_found_comm.connect()
            self.assertFalse(connected_nf)
            self.assertEqual(close_code_nf, WS_CLOSE_NOT_FOUND)

            # 3b. El token en la URL ya no se acepta para no exponerlo en logs
            query_comm = WebsocketCommunicator(
                application, f"/ws/v1/monitoring/stream/?token={nurse_token}"
            )
            connected_q, close_code_q = await query_comm.connect()
            self.assertFalse(connected_q)
            self.assertEqual(close_code_q, WS_CLOSE_UNAUTHORIZED)

            # 4. Suscripción autenticada al stream de cuna (por subprotocolo) y de paciente (por cabecera Authorization)
            crib_comm = WebsocketCommunicator(
                application,
                f"/ws/v1/cribs/{self.crib.id}/stream/",
                subprotocols=["bearer", nurse_token],
            )
            patient_comm = WebsocketCommunicator(
                application,
                f"/ws/v1/patients/{self.patient.id}/stream/",
                headers=[(b"authorization", f"Bearer {nurse_token}".encode("latin1"))],
            )

            ok_crib, crib_subprotocol = await crib_comm.connect()
            ok_patient, patient_subprotocol = await patient_comm.connect()
            self.assertTrue(ok_crib)
            self.assertTrue(ok_patient)
            # El navegador cierra la conexión si el servidor no confirma el subprotocolo ofrecido
            self.assertEqual(crib_subprotocol, "bearer")
            self.assertIsNone(patient_subprotocol)

            welcome_crib = await crib_comm.receive_json_from()
            welcome_patient = await patient_comm.receive_json_from()
            self.assertEqual(welcome_crib["event"], "stream.connected")
            self.assertEqual(welcome_patient["event"], "stream.connected")

            # Ping / Pong
            await crib_comm.send_json_to({"action": "ping"})
            pong = await crib_comm.receive_json_from()
            self.assertEqual(pong["event"], "stream.pong")

            # Ingesta de telemetría con anomalía crítica (SpO2 84%) emite eventos en tiempo real
            _, eval_res = await sync_to_async(ingest_telemetry)(
                crib=self.crib,
                payload={
                    "heart_rate": 135,
                    "spo2": 84,
                    "temperature": "36.8",
                    "sleep_state": "asleep",
                    "cannula_connected": True,
                    "iv_line_active": True,
                },
                is_device_authenticated=True,
            )

            msg_crib = await crib_comm.receive_json_from()
            msg_patient = await patient_comm.receive_json_from()

            self.assertEqual(msg_crib["event"], "telemetry.reading")
            self.assertEqual(msg_crib["reading"]["spo2"], 84)
            self.assertEqual(len(msg_crib["active_alerts"]), 1)

            self.assertEqual(msg_patient["event"], "telemetry.reading")
            self.assertEqual(msg_patient["patient_id"], self.patient.id)

            # Reconocer y resolver la alerta también se emite en tiempo real
            alert_obj = eval_res.created_alerts[0]
            await sync_to_async(acknowledge_alert)(actor=self.nurse, alert=alert_obj)
            ack_event = await crib_comm.receive_json_from()
            _ = await patient_comm.receive_json_from()
            self.assertEqual(ack_event["event"], "alert.acknowledged")
            self.assertEqual(ack_event["alert"]["status"], "acknowledged")

            await sync_to_async(resolve_alert)(actor=self.nurse, alert=alert_obj)
            res_event = await crib_comm.receive_json_from()
            self.assertEqual(res_event["event"], "alert.resolved")
            self.assertEqual(res_event["alert"]["status"], "resolved")

            await crib_comm.disconnect()
            await patient_comm.disconnect()

        async_to_sync(_run_scenario)()

        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditAction.READ,
                resource_type="patient_stream",
                patient_id=self.patient.id,
            ).exists()
        )
