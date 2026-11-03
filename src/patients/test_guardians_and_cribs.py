from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from alerts.models import Alert
from audit.models import AuditAction, AuditLog
from devices.models import Crib, CribStatus
from devices.services import create_crib
from medications.models import MedicationAdministration, Prescription
from medications.services import (
    administer_prescription,
    create_catalog_item,
    create_prescription,
)
from poki_koa.exceptions import (
    ConflictDomainError,
    DomainError,
    NotFoundDomainError,
    PermissionDomainError,
)
from vitals.models import VitalSignReading
from vitals.services import ingest_telemetry

from .models import (
    CarePlan,
    ClinicalObservation,
    CribMovement,
    CribMovementKind,
    DischargeOutcome,
    Patient,
    WeightRecord,
)
from .services import (
    admit_patient,
    assign_patient_to_crib,
    create_care_plan,
    create_clinical_observation,
    delete_patient_permanently,
    discharge_patient,
    release_patient_from_crib,
    swap_patients_between_cribs,
    update_patient,
)
from .validators import normalize_phone, normalize_rut, rut_check_digit

PASSWORD = "Str0ng!Password2026"


def _user(email: str, role: str) -> User:
    return User.objects.create_user(
        email=email, full_name=email.split("@")[0], password=PASSWORD, role=role
    )


class ValidatorTests(TestCase):
    def test_rut_check_digit_covers_k_and_zero(self) -> None:
        self.assertEqual(rut_check_digit("12345678"), "5")
        self.assertEqual(rut_check_digit("10000013"), "K")
        self.assertEqual(rut_check_digit("1000013"), "0")

    def test_normalize_rut_accepts_common_formats(self) -> None:
        self.assertEqual(normalize_rut("12.345.678-5", label="x"), "12345678-5")
        self.assertEqual(normalize_rut(" 12345678-5 ", label="x"), "12345678-5")
        self.assertEqual(normalize_rut("10.000.013-k", label="x"), "10000013-K")
        self.assertEqual(normalize_rut("", label="x"), "")

    def test_normalize_rut_rejects_bad_format_and_check_digit(self) -> None:
        with self.assertRaisesMessage(DomainError, "formato"):
            normalize_rut("12A45678-5", label="de la madre")
        with self.assertRaisesMessage(DomainError, "dígito verificador"):
            normalize_rut("12.345.678-9", label="de la madre")

    def test_normalize_phone_formats(self) -> None:
        self.assertEqual(normalize_phone("+56 9 1234 5678", label="x"), "+56912345678")
        self.assertEqual(normalize_phone("56912345678", label="x"), "+56912345678")
        self.assertEqual(normalize_phone("9-1234-5678", label="x"), "+56912345678")
        self.assertEqual(normalize_phone("(2) 2123 4567", label="x"), "+56221234567")
        self.assertEqual(normalize_phone("  ", label="x"), "")

    def test_normalize_phone_rejects_invalid(self) -> None:
        with self.assertRaisesMessage(DomainError, "chileno"):
            normalize_phone("+54 9 1234 5678", label="del padre")
        with self.assertRaisesMessage(DomainError, "9 dígitos"):
            normalize_phone("12345", label="del padre")
        with self.assertRaisesMessage(DomainError, "9 dígitos"):
            normalize_phone("9123A5678", label="del padre")


class GuardianDataTests(TestCase):
    def setUp(self) -> None:
        self.neo = _user("neo_g@pokikoa.cl", UserRole.NEONATOLOGIST)
        self.nurse = _user("nurse_g@pokikoa.cl", UserRole.NURSE)

    def _admit(self, **guardians) -> Patient:
        return admit_patient(
            actor=self.neo,
            medical_record_number="RN-G-1",
            full_name="RN Guardianes (Ficticio)",
            sex="F",
            birth_date=timezone.localdate(),
            gestational_age_weeks=Decimal("37.0"),
            birth_weight_g=3000,
            guardians=guardians,
        )

    def test_admit_stores_normalized_guardian_data(self) -> None:
        patient = self._admit(
            mother_rut="12.345.678-5",
            mother_first_names="  Ana María ",
            mother_last_names="Tuki Pakarati",
            mother_phone="+56 9 8765 4321",
            father_rut="",
        )
        self.assertEqual(patient.mother_rut, "12345678-5")
        self.assertEqual(patient.mother_first_names, "Ana María")
        self.assertEqual(patient.mother_phone, "+56987654321")
        self.assertEqual(patient.father_rut, "")
        audit = AuditLog.objects.get(action=AuditAction.CREATE, resource_type="patient")
        self.assertIn("mother_rut", audit.changed_fields)
        # La auditoría guarda nombres de campos, nunca los valores
        self.assertNotIn("12345678-5", str(audit.changed_fields))

    def test_admit_rejects_invalid_rut_without_creating_patient(self) -> None:
        with self.assertRaisesMessage(DomainError, "de la madre"):
            self._admit(mother_rut="11.111.111-2")
        self.assertFalse(Patient.objects.exists())

    def test_update_changes_only_sent_guardian_fields(self) -> None:
        patient = self._admit(mother_rut="12345678-5", mother_phone="912345678")
        updated = update_patient(
            actor=self.nurse,
            patient=patient,
            data={"father_first_names": "Kai", "father_phone": "+56 2 2123 4567"},
        )
        self.assertEqual(updated.mother_rut, "12345678-5")
        self.assertEqual(updated.father_first_names, "Kai")
        self.assertEqual(updated.father_phone, "+56221234567")
        audit = AuditLog.objects.filter(action=AuditAction.UPDATE).first()
        self.assertEqual(sorted(audit.changed_fields), ["father_first_names", "father_phone"])

        # Reenviar el mismo valor no genera cambios ni auditoría
        update_patient(actor=self.nurse, patient=updated, data={"father_first_names": "Kai"})
        self.assertEqual(AuditLog.objects.filter(action=AuditAction.UPDATE).count(), 1)


class CribMovementTests(TestCase):
    def setUp(self) -> None:
        self.admin = _user("admin_m@pokikoa.cl", UserRole.ADMIN)
        self.neo = _user("neo_m@pokikoa.cl", UserRole.NEONATOLOGIST)
        self.pharmacist = _user("pharm_m@pokikoa.cl", UserRole.PHARMACIST)
        self.crib_a, _ = create_crib(actor=self.admin, code="M-01")
        self.crib_b, _ = create_crib(actor=self.admin, code="M-02")
        self.crib_c, _ = create_crib(actor=self.admin, code="M-03")
        self.p1 = self._admit("RN-M-1", self.crib_a)
        self.p2 = self._admit("RN-M-2", self.crib_b)

    def _admit(self, mrn: str, crib: Crib | None) -> Patient:
        return admit_patient(
            actor=self.neo,
            medical_record_number=mrn,
            full_name=f"RN {mrn} (Ficticio)",
            sex="M",
            birth_date=timezone.localdate(),
            gestational_age_weeks=Decimal("35.0"),
            birth_weight_g=2400,
            crib_id=crib.id if crib else None,
        )

    def _kinds(self, patient: Patient) -> list[str]:
        return list(
            CribMovement.objects.filter(patient=patient)
            .order_by("moved_at", "id")
            .values_list("kind", flat=True)
        )

    def test_admission_with_crib_records_assignment(self) -> None:
        movement = CribMovement.objects.get(patient=self.p1)
        self.assertEqual(movement.kind, CribMovementKind.ASSIGN)
        self.assertEqual(movement.to_crib_code, "M-01")
        self.assertEqual(movement.moved_by, self.neo)
        self.assertIn("M-01", str(movement))

    def test_release_then_reassign_keeps_patient_active(self) -> None:
        release_patient_from_crib(actor=self.neo, crib=self.crib_a)
        self.p1.refresh_from_db()
        self.assertEqual(self.p1.status, "active")
        self.assertIsNone(self.p1.crib_id)

        assign_patient_to_crib(actor=self.neo, crib=self.crib_c, patient_id=self.p1.id)
        self.p1.refresh_from_db()
        self.assertEqual(self.p1.crib_id, self.crib_c.id)
        self.assertEqual(
            self._kinds(self.p1),
            [CribMovementKind.ASSIGN, CribMovementKind.RELEASE, CribMovementKind.ASSIGN],
        )

    def test_assign_from_another_crib_is_a_move(self) -> None:
        assign_patient_to_crib(actor=self.neo, crib=self.crib_c, patient_id=self.p1.id)
        self.crib_a.refresh_from_db()
        self.assertEqual(self.crib_a.status, CribStatus.AVAILABLE)
        last = CribMovement.objects.filter(patient=self.p1).first()
        self.assertEqual(last.kind, CribMovementKind.MOVE)
        self.assertEqual((last.from_crib_code, last.to_crib_code), ("M-01", "M-03"))

    def test_assign_to_same_crib_is_rejected(self) -> None:
        with self.assertRaisesMessage(ConflictDomainError, "ya se encuentra en esa cuna"):
            assign_patient_to_crib(actor=self.neo, crib=self.crib_a, patient_id=self.p1.id)

    def test_update_patient_crib_records_move_and_release(self) -> None:
        update_patient(actor=self.neo, patient=self.p1, data={"crib_id": self.crib_c.id})
        self.p1.refresh_from_db()
        update_patient(actor=self.neo, patient=self.p1, data={"crib_id": None})
        p3 = self._admit("RN-M-3", None)
        update_patient(actor=self.neo, patient=p3, data={"crib_id": self.crib_a.id})
        self.assertEqual(
            self._kinds(self.p1),
            [CribMovementKind.ASSIGN, CribMovementKind.MOVE, CribMovementKind.RELEASE],
        )
        self.assertEqual(self._kinds(p3), [CribMovementKind.ASSIGN])

    def test_discharge_records_crib_release_by_discharge(self) -> None:
        discharge_patient(actor=self.neo, patient=self.p1, outcome=DischargeOutcome.SURVIVED)
        self.assertEqual(self._kinds(self.p1)[-1], CribMovementKind.DISCHARGE)

    def test_swap_exchanges_patients_and_records_both(self) -> None:
        swap_patients_between_cribs(actor=self.neo, crib=self.crib_a, other_crib_id=self.crib_b.id)
        self.p1.refresh_from_db()
        self.p2.refresh_from_db()
        self.assertEqual(self.p1.crib_id, self.crib_b.id)
        self.assertEqual(self.p2.crib_id, self.crib_a.id)
        self.assertEqual(self.p1.status, "active")
        for crib in (self.crib_a, self.crib_b):
            crib.refresh_from_db()
            self.assertEqual(crib.status, CribStatus.OCCUPIED)
        self.assertEqual(self._kinds(self.p1)[-1], CribMovementKind.SWAP)
        self.assertEqual(self._kinds(self.p2)[-1], CribMovementKind.SWAP)
        self.assertEqual(AuditLog.objects.filter(action=AuditAction.SWAP_CRIB).count(), 2)

    def test_swap_validations(self) -> None:
        with self.assertRaises(PermissionDomainError):
            swap_patients_between_cribs(
                actor=self.pharmacist, crib=self.crib_a, other_crib_id=self.crib_b.id
            )
        with self.assertRaisesMessage(DomainError, "distintas"):
            swap_patients_between_cribs(
                actor=self.neo, crib=self.crib_a, other_crib_id=self.crib_a.id
            )
        with self.assertRaises(NotFoundDomainError):
            swap_patients_between_cribs(actor=self.neo, crib=self.crib_a, other_crib_id=99999)
        with self.assertRaisesMessage(ConflictDomainError, "Ambas cunas"):
            swap_patients_between_cribs(
                actor=self.neo, crib=self.crib_a, other_crib_id=self.crib_c.id
            )
        Crib.objects.filter(pk=self.crib_b.pk).update(status=CribStatus.OFFLINE)
        with self.assertRaisesMessage(ConflictDomainError, "M-02"):
            swap_patients_between_cribs(
                actor=self.neo, crib=self.crib_a, other_crib_id=self.crib_b.id
            )
        # Ningún intento fallido dejó movimientos de intercambio
        self.assertFalse(CribMovement.objects.filter(kind=CribMovementKind.SWAP).exists())


class PermanentDeleteTests(TestCase):
    def setUp(self) -> None:
        self.admin = _user("admin_d@pokikoa.cl", UserRole.ADMIN)
        self.neo = _user("neo_d@pokikoa.cl", UserRole.NEONATOLOGIST)
        self.nurse = _user("nurse_d@pokikoa.cl", UserRole.NURSE)
        self.crib, _ = create_crib(actor=self.admin, code="D-01")
        self.patient = admit_patient(
            actor=self.neo,
            medical_record_number="RN-DEL-1",
            full_name="RN Borrado (Ficticio)",
            sex="F",
            birth_date=timezone.localdate(),
            gestational_age_weeks=Decimal("33.0"),
            birth_weight_g=1900,
            crib_id=self.crib.id,
        )

    def _populate_clinical_record(self) -> None:
        item = create_catalog_item(
            actor=self.admin, name="Cafeína", active_ingredient="Cafeína", concentration_mg="20", stock=5
        )
        prescription = create_prescription(
            actor=self.neo,
            patient_id=self.patient.id,
            medication_id=item.id,
            dose="10 mg",
            starts_at=timezone.now(),
        )
        administer_prescription(actor=self.nurse, prescription=prescription)
        ingest_telemetry(
            crib=self.crib,
            payload={
                "heart_rate": 140,
                "spo2": 80,
                "temperature": "36.8",
                "sleep_state": "asleep",
                "cannula_connected": True,
                "iv_line_active": True,
            },
            is_device_authenticated=True,
        )
        create_care_plan(
            actor=self.nurse,
            patient_id=self.patient.id,
            care_area="Respiratorio",
            intervention="Aspiración",
            frequency="c/6h",
        )
        create_clinical_observation(actor=self.nurse, patient_id=self.patient.id, content="Estable")

    def test_only_admin_with_matching_confirmation_can_delete(self) -> None:
        with self.assertRaises(PermissionDomainError):
            delete_patient_permanently(
                actor=self.neo, patient=self.patient, confirmation="RN-DEL-1"
            )
        with self.assertRaisesMessage(DomainError, "número de ficha"):
            delete_patient_permanently(
                actor=self.admin, patient=self.patient, confirmation="RN-OTRO"
            )
        self.assertTrue(Patient.objects.filter(pk=self.patient.pk).exists())

    def test_delete_removes_whole_record_and_frees_crib(self) -> None:
        self._populate_clinical_record()
        self.assertTrue(Alert.objects.filter(patient=self.patient).exists())
        patient_id = self.patient.id

        delete_patient_permanently(actor=self.admin, patient=self.patient, confirmation=" rn-del-1 ")

        self.assertFalse(Patient.objects.filter(pk=patient_id).exists())
        for model in (
            Prescription,
            Alert,
            VitalSignReading,
            WeightRecord,
            CarePlan,
            ClinicalObservation,
            CribMovement,
        ):
            self.assertFalse(model.objects.filter(patient_id=patient_id).exists(), model.__name__)
        self.assertFalse(MedicationAdministration.objects.exists())
        self.crib.refresh_from_db()
        self.assertEqual(self.crib.status, CribStatus.AVAILABLE)
        audit = AuditLog.objects.get(action=AuditAction.DELETE)
        self.assertEqual((audit.patient_id, audit.actor_user), (patient_id, self.admin))

    def test_delete_discharged_patient_without_crib(self) -> None:
        discharge_patient(actor=self.neo, patient=self.patient, outcome=DischargeOutcome.SURVIVED)
        delete_patient_permanently(actor=self.admin, patient=self.patient, confirmation="RN-DEL-1")
        self.assertFalse(Patient.objects.exists())


class PatientEndpointExtensionsTests(APITestCase):
    def setUp(self) -> None:
        self.admin = _user("admin_e@pokikoa.cl", UserRole.ADMIN)
        self.neo = _user("neo_e@pokikoa.cl", UserRole.NEONATOLOGIST)
        self.crib_a, _ = create_crib(actor=self.admin, code="E-01")
        self.crib_b, _ = create_crib(actor=self.admin, code="E-02")
        self.client.force_authenticate(user=self.neo)

    def _create(self, mrn: str, crib: Crib, **extra) -> dict:
        response = self.client.post(
            "/api/v1/patients/",
            {
                "medical_record_number": mrn,
                "full_name": f"RN {mrn} (Ficticio)",
                "sex": "F",
                "birth_date": str(timezone.localdate()),
                "gestational_age_weeks": "36.0",
                "birth_weight_g": 2700,
                "crib_id": crib.id,
                **extra,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data

    def test_create_with_guardians_and_validation_error(self) -> None:
        data = self._create(
            "RN-E-1",
            self.crib_a,
            mother_rut="12.345.678-5",
            mother_first_names="Ana",
            mother_last_names="Tuki",
            mother_phone="912345678",
        )
        self.assertEqual(data["mother_rut"], "12345678-5")
        self.assertEqual(data["mother_phone"], "+56912345678")
        self.assertEqual(data["father_rut"], "")

        bad = self.client.post(
            "/api/v1/patients/",
            {
                "medical_record_number": "RN-E-BAD",
                "full_name": "RN Malo",
                "sex": "F",
                "birth_date": str(timezone.localdate()),
                "gestational_age_weeks": "36.0",
                "birth_weight_g": 2700,
                "father_phone": "123",
            },
            format="json",
        )
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)

    def test_active_filter_splits_unit_and_inactive_patients(self) -> None:
        first = self._create("RN-E-1", self.crib_a)
        second = self._create("RN-E-2", self.crib_b)
        self.client.post(
            f"/api/v1/patients/{second['id']}/discharge/", {"outcome": "survived"}, format="json"
        )
        active = self.client.get("/api/v1/patients/?active=true").data["results"]
        inactive = self.client.get("/api/v1/patients/?active=false").data["results"]
        self.assertEqual([p["id"] for p in active], [first["id"]])
        self.assertEqual([p["id"] for p in inactive], [second["id"]])

    def test_swap_and_movement_history_endpoints(self) -> None:
        first = self._create("RN-E-1", self.crib_a)
        self._create("RN-E-2", self.crib_b)
        response = self.client.post(
            f"/api/v1/cribs/{self.crib_a.id}/swap/",
            {"other_crib_id": self.crib_b.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data), 2)

        history = self.client.get(f"/api/v1/patients/{first['id']}/crib-movements/")
        self.assertEqual(history.status_code, status.HTTP_200_OK)
        self.assertEqual([m["kind"] for m in history.data], ["swap", "assign"])
        self.assertEqual(history.data[0]["kind_label"], "Intercambio de cunas")
        self.assertEqual(
            (history.data[0]["from_crib_code"], history.data[0]["to_crib_code"]), ("E-01", "E-02")
        )

    def test_delete_permanently_endpoint(self) -> None:
        patient = self._create("RN-E-1", self.crib_a)
        url = f"/api/v1/patients/{patient['id']}/delete-permanently/"
        forbidden = self.client.post(url, {"confirmation": "RN-E-1"}, format="json")
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.admin)
        missing = self.client.post(url, {}, format="json")
        self.assertEqual(missing.status_code, status.HTTP_400_BAD_REQUEST)
        deleted = self.client.post(url, {"confirmation": "RN-E-1"}, format="json")
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.client.get(f"/api/v1/patients/{patient['id']}/").status_code, 404)
