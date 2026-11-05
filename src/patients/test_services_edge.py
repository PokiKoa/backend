from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.models import User, UserRole
from devices.models import CribStatus
from devices.services import create_crib, update_crib
from poki_koa.exceptions import (
    ConflictDomainError,
    DomainError,
    NotFoundDomainError,
    PermissionDomainError,
)

from .models import CarePlanStatus, PatientStatus
from .services import (
    admit_patient,
    create_care_plan,
    create_clinical_observation,
    discharge_patient,
    record_patient_weight,
    update_care_plan,
    update_patient,
)

PASSWORD = "Str0ng!Password2026"


class PatientEdgeCaseTests(TestCase):
    def setUp(self) -> None:
        self.admin = User.objects.create_user(
            email="admin_pat_edge@pokikoa.cl",
            full_name="Admin Pacientes",
            password=PASSWORD,
            role=UserRole.ADMIN,
        )
        self.neonatologist = User.objects.create_user(
            email="neo_pat_edge@pokikoa.cl",
            full_name="Neonatólogo Pacientes",
            password=PASSWORD,
            role=UserRole.NEONATOLOGIST,
        )
        self.nurse = User.objects.create_user(
            email="nurse_pat_edge@pokikoa.cl",
            full_name="Enfermera Pacientes",
            password=PASSWORD,
            role=UserRole.NURSE,
        )
        self.base = {
            "actor": self.neonatologist,
            "medical_record_number": "RN-EDGE-001",
            "full_name": "Paciente Bordes",
            "sex": "F",
            "birth_date": timezone.localdate() - timedelta(days=2),
            "gestational_age_weeks": Decimal("33.0"),
            "birth_weight_g": 1700,
        }

    def test_admission_validations_and_boundaries(self) -> None:
        with self.assertRaises(PermissionDomainError):
            admit_patient(**{**self.base, "actor": self.admin})

        invalid_overrides = [
            {"medical_record_number": " "},
            {"full_name": ""},
            {"sex": "X"},
            {"birth_date": timezone.localdate() + timedelta(days=1)},
            {"gestational_age_weeks": Decimal("19.9")},
            {"gestational_age_weeks": Decimal("45.1")},
            {"birth_weight_g": 199},
            {"birth_weight_g": 8001},
            {"current_weight_g": 10001},
        ]
        for override in invalid_overrides:
            with self.subTest(override=override), self.assertRaises(DomainError):
                admit_patient(**{**self.base, **override})

        # Límites exactos válidos
        patient = admit_patient(
            **{
                **self.base,
                "gestational_age_weeks": Decimal("20.0"),
                "birth_weight_g": 200,
            }
        )
        self.assertEqual(patient.current_weight_g, 200)

        with self.assertRaises(ConflictDomainError):
            admit_patient(**{**self.base, "medical_record_number": "rn-edge-001"})

    def test_admission_rejects_invalid_physician_and_unavailable_crib(self) -> None:
        with self.assertRaises(NotFoundDomainError):
            admit_patient(**self.base, attending_physician_id=999999)
        with self.assertRaises(DomainError):
            admit_patient(**self.base, attending_physician_id=self.nurse.id)
        with self.assertRaises(NotFoundDomainError):
            admit_patient(**self.base, crib_id=999999)

        crib, _ = create_crib(actor=self.admin, code="C-EDGE")
        update_crib(actor=self.admin, crib=crib, data={"status": CribStatus.MAINTENANCE})
        with self.assertRaises(ConflictDomainError):
            admit_patient(**self.base, crib_id=crib.id)

        update_crib(actor=self.admin, crib=crib, data={"status": CribStatus.AVAILABLE})
        admit_patient(**self.base, crib_id=crib.id)
        with self.assertRaises(ConflictDomainError):
            admit_patient(
                **{**self.base, "medical_record_number": "RN-EDGE-002"},
                crib_id=crib.id,
            )

    def test_update_patient_validations_and_field_rbac(self) -> None:
        patient = admit_patient(**self.base)

        with self.assertRaises(PermissionDomainError):
            update_patient(actor=self.admin, patient=patient, data={"full_name": "X"})
        with self.assertRaises(PermissionDomainError):
            update_patient(actor=self.nurse, patient=patient, data={"diagnosis": "Sepsis"})

        for invalid in (
            {"full_name": " "},
            {"sex": "X"},
            {"birth_date": timezone.localdate() + timedelta(days=1)},
            {"gestational_age_weeks": "46"},
            {"current_weight_g": 150},
        ):
            with self.subTest(data=invalid), self.assertRaises(DomainError):
                update_patient(actor=self.neonatologist, patient=patient, data=invalid)

        updated = update_patient(
            actor=self.neonatologist,
            patient=patient,
            data={
                "full_name": "Paciente Actualizado",
                "sex": "M",
                "birth_date": timezone.localdate() - timedelta(days=3),
                "gestational_age_weeks": "34.5",
                "current_weight_g": 1750,
                "diagnosis": "Prematurez moderada",
                "attending_physician_id": self.neonatologist.id,
            },
        )
        self.assertEqual(updated.attending_physician_id, self.neonatologist.id)
        self.assertEqual(updated.weight_records.count(), 2)

    def test_discharge_validations_and_post_discharge_restrictions(self) -> None:
        patient = admit_patient(**self.base)

        with self.assertRaises(PermissionDomainError):
            discharge_patient(actor=self.nurse, patient=patient, outcome="survived")
        with self.assertRaises(DomainError):
            discharge_patient(actor=self.neonatologist, patient=patient, outcome="x")
        with self.assertRaises(DomainError):
            discharge_patient(
                actor=self.neonatologist, patient=patient, outcome="survived", cause="x"
            )
        # Fallecimiento exige causa clínica
        with self.assertRaises(DomainError):
            discharge_patient(actor=self.neonatologist, patient=patient, outcome="deceased")

        discharged = discharge_patient(
            actor=self.neonatologist,
            patient=patient,
            outcome="transferred",
            notes="Traslado a centro de mayor complejidad",
        )
        self.assertEqual(discharged.status, PatientStatus.TRANSFERRED)

        with self.assertRaises(ConflictDomainError):
            discharge_patient(actor=self.neonatologist, patient=patient, outcome="survived")
        with self.assertRaises(ConflictDomainError):
            update_patient(actor=self.neonatologist, patient=patient, data={"sex": "M"})
        with self.assertRaises(ConflictDomainError):
            record_patient_weight(actor=self.nurse, patient=patient, weight_g=1800)
        with self.assertRaises(ConflictDomainError):
            create_care_plan(
                actor=self.nurse,
                patient_id=patient.id,
                care_area="Termorregulación",
                intervention="Control térmico",
                frequency="Cada 4 h",
            )
        with self.assertRaises(ConflictDomainError):
            create_clinical_observation(
                actor=self.nurse, patient_id=patient.id, content="Observación"
            )

    def test_weight_care_plan_and_observation_validations(self) -> None:
        patient = admit_patient(**self.base)

        with self.assertRaises(PermissionDomainError):
            record_patient_weight(actor=self.admin, patient=patient, weight_g=1800)
        with self.assertRaises(DomainError):
            record_patient_weight(actor=self.nurse, patient=patient, weight_g=199)

        plan_args = {
            "actor": self.nurse,
            "patient_id": patient.id,
            "care_area": "Alimentación",
            "intervention": "Sonda orogástrica",
            "frequency": "Cada 3 h",
        }
        with self.assertRaises(PermissionDomainError):
            create_care_plan(**{**plan_args, "actor": self.admin})
        with self.assertRaises(DomainError):
            create_care_plan(**{**plan_args, "status": "unknown"})
        with self.assertRaises(DomainError):
            create_care_plan(**{**plan_args, "frequency": " "})
        with self.assertRaises(NotFoundDomainError):
            create_care_plan(**{**plan_args, "patient_id": 999999})

        plan = create_care_plan(**plan_args)
        with self.assertRaises(PermissionDomainError):
            update_care_plan(actor=self.admin, care_plan=plan, data={"status": "completed"})
        with self.assertRaises(DomainError):
            update_care_plan(actor=self.nurse, care_plan=plan, data={"intervention": ""})
        with self.assertRaises(DomainError):
            update_care_plan(actor=self.nurse, care_plan=plan, data={"status": "x"})
        updated = update_care_plan(
            actor=self.nurse,
            care_plan=plan,
            data={"frequency": "Cada 2 h", "status": CarePlanStatus.SUSPENDED},
        )
        self.assertEqual(updated.status, CarePlanStatus.SUSPENDED)

        with self.assertRaises(PermissionDomainError):
            create_clinical_observation(actor=self.admin, patient_id=patient.id, content="Texto")
        with self.assertRaises(DomainError):
            create_clinical_observation(
                actor=self.nurse, patient_id=patient.id, content="x", category="otra"
            )
        with self.assertRaises(DomainError):
            create_clinical_observation(actor=self.nurse, patient_id=patient.id, content="   ")
        with self.assertRaises(NotFoundDomainError):
            create_clinical_observation(actor=self.nurse, patient_id=999999, content="Texto")
