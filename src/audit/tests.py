from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User, UserRole
from audit.models import AuditAction, AuditLog
from audit.services import record_audit_event, sanitize_changed_fields


class AuditServiceTests(TestCase):
    def setUp(self) -> None:
        self.admin = User.objects.create_user(
            email="admin@pokikoa.cl",
            full_name="Dra. Elena Vargas",
            password="PasswordSegura!2026",
            role=UserRole.ADMIN,
        )

    def test_record_audit_event_stores_only_field_names(self) -> None:
        log = record_audit_event(
            action=AuditAction.UPDATE,
            resource_type="patient",
            resource_id=42,
            actor_user=self.admin,
            patient_id=42,
            changed_fields=["diagnosis", "current_weight_g", "diagnosis"],
            ip_address="192.168.1.10",
        )
        self.assertEqual(log.action, AuditAction.UPDATE)
        self.assertEqual(log.resource_type, "patient")
        self.assertEqual(log.resource_id, "42")
        self.assertEqual(log.patient_id, 42)
        self.assertEqual(log.changed_fields, ["diagnosis", "current_weight_g"])
        self.assertEqual(log.ip_address, "192.168.1.10")

    def test_sanitize_changed_fields_rejects_dict_or_clinical_values(self) -> None:
        with self.assertRaises(TypeError):
            sanitize_changed_fields({"diagnosis": "Sepsis neonatal"})  # type: ignore[arg-type]

        with self.assertRaises(TypeError):
            sanitize_changed_fields("diagnosis")  # type: ignore[arg-type]

        with self.assertRaises(ValueError):
            sanitize_changed_fields(["diagnosis: Sepsis"])


class AuditEndpointTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.admin = User.objects.create_user(
            email="admin@pokikoa.cl",
            full_name="Admin UCIN",
            password="PasswordSegura!2026",
            role=UserRole.ADMIN,
        )
        self.nurse = User.objects.create_user(
            email="matrona@pokikoa.cl",
            full_name="Matrona Sofía",
            password="PasswordSegura!2026",
            role=UserRole.NURSE,
        )
        record_audit_event(
            action=AuditAction.READ,
            resource_type="patient",
            resource_id="101",
            actor_user=self.nurse,
            patient_id=101,
        )
        record_audit_event(
            action=AuditAction.UPDATE,
            resource_type="patient",
            resource_id="102",
            actor_user=self.admin,
            patient_id=102,
            changed_fields=["diagnosis"],
        )

    def test_unauthenticated_request_is_rejected(self) -> None:
        response = self.client.get("/api/v1/audit-logs/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["error"]["code"], "not_authenticated")

    def test_non_admin_roles_cannot_read_audit_logs(self) -> None:
        self.client.force_authenticate(user=self.nurse)
        response = self.client.get("/api/v1/audit-logs/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["error"]["code"], "permission_denied")

    def test_admin_can_list_and_filter_audit_logs(self) -> None:
        self.client.force_authenticate(user=self.admin)
        response = self.client.get("/api/v1/audit-logs/?patient_id=102")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        entry = response.data["results"][0]
        self.assertEqual(entry["patient_id"], 102)
        self.assertEqual(entry["changed_fields"], ["diagnosis"])
        self.assertEqual(AuditLog.objects.count(), 2)

    def test_summary_counts_by_action_honoring_filters(self) -> None:
        self.client.force_authenticate(user=self.nurse)
        self.assertEqual(
            self.client.get("/api/v1/audit-logs/summary/").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.client.force_authenticate(user=self.admin)
        response = self.client.get("/api/v1/audit-logs/summary/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            sorted((row["action"], row["total"]) for row in response.data),
            [(AuditAction.READ, 1), (AuditAction.UPDATE, 1)],
        )
        filtered = self.client.get("/api/v1/audit-logs/summary/", {"patient_id": 102})
        self.assertEqual(list(filtered.data), [{"action": AuditAction.UPDATE, "total": 1}])
