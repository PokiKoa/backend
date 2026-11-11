"""Caracteriza el rechazo de operaciones sobre pacientes egresados o inexistentes."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.models import User, UserRole
from alerts.services import upsert_threshold_config
from devices.services import create_crib
from medications.services import create_catalog_item, create_prescription
from poki_koa.exceptions import ConflictDomainError, NotFoundDomainError

from .models import DischargeOutcome
from .services import (
    admit_patient,
    assign_patient_to_crib,
    create_care_plan,
    create_clinical_observation,
    discharge_patient,
    record_patient_weight,
    update_patient,
)

PASSWORD = "Str0ng!Password2026"
MISSING_ID = 999_999


class ActivePatientLockTests(TestCase):
    def setUp(self) -> None:
        def user(role: str) -> User:
            return User.objects.create_user(
                email=f"lock_{role}@pokikoa.cl",
                full_name=f"Bloqueo {role}",
                password=PASSWORD,
                role=role,
            )

        self.admin = user(UserRole.ADMIN)
        self.neo = user(UserRole.NEONATOLOGIST)
        pharmacist = user(UserRole.PHARMACIST)
        self.patient = admit_patient(
            actor=self.neo,
            medical_record_number="RN-LOCK-001",
            full_name="Paciente Bloqueo",
            sex="F",
            birth_date=timezone.localdate() - timedelta(days=2),
            gestational_age_weeks=Decimal("34.0"),
            birth_weight_g=1800,
        )
        discharge_patient(actor=self.neo, patient=self.patient, outcome=DischargeOutcome.SURVIVED)
        self.patient.refresh_from_db()
        self.crib, _ = create_crib(actor=self.admin, code="LOCK-01")
        self.medication = create_catalog_item(
            actor=pharmacist, name="Bloqueo", active_ingredient="X", concentration_mg=1, stock=5
        )

    def _prescribe(self, patient_id: int) -> None:
        create_prescription(
            actor=self.neo,
            patient_id=patient_id,
            medication_id=self.medication.id,
            dose="1 mg",
            starts_at=timezone.now() + timedelta(hours=1),
        )

    def test_discharged_patient_is_rejected_with_operation_specific_message(self) -> None:
        p = self.patient
        cases = {
            "No se pueden modificar los datos clínicos de un paciente ya egresado.": lambda: (
                update_patient(actor=self.neo, patient=p, data={"full_name": "Otro"})
            ),
            "El paciente ya fue egresado previamente.": lambda: discharge_patient(
                actor=self.neo, patient=p, outcome=DischargeOutcome.SURVIVED
            ),
            "No se puede asignar una cuna a un paciente que ya fue egresado.": lambda: (
                assign_patient_to_crib(actor=self.neo, crib=self.crib, patient_id=p.id)
            ),
            "No se pueden añadir registros de peso a un paciente egresado.": lambda: (
                record_patient_weight(actor=self.neo, patient=p, weight_g=2000)
            ),
            "No se pueden crear planes de cuidado para un paciente egresado.": lambda: (
                create_care_plan(
                    actor=self.neo,
                    patient_id=p.id,
                    care_area="Piel",
                    intervention="Cambio de posición",
                    frequency="Cada 3 horas",
                )
            ),
            "No se pueden agregar observaciones a un paciente ya egresado.": lambda: (
                create_clinical_observation(actor=self.neo, patient_id=p.id, content="Estable")
            ),
            "No se pueden modificar los umbrales de un paciente egresado.": lambda: (
                upsert_threshold_config(actor=self.neo, patient=p, data={})
            ),
            "No se pueden crear indicaciones médicas para un paciente ya egresado.": lambda: (
                self._prescribe(p.id)
            ),
        }
        for message, operation in cases.items():
            with self.subTest(message=message):
                with self.assertRaises(ConflictDomainError) as ctx:
                    operation()
                self.assertEqual(ctx.exception.message, message)

    def test_missing_patient_id_returns_not_found(self) -> None:
        cases = [
            lambda: assign_patient_to_crib(actor=self.neo, crib=self.crib, patient_id=MISSING_ID),
            lambda: create_care_plan(
                actor=self.neo,
                patient_id=MISSING_ID,
                care_area="Piel",
                intervention="Cambio de posición",
                frequency="Cada 3 horas",
            ),
            lambda: create_clinical_observation(
                actor=self.neo, patient_id=MISSING_ID, content="Estable"
            ),
            lambda: self._prescribe(MISSING_ID),
        ]
        for index, operation in enumerate(cases):
            with self.subTest(case=index):
                with self.assertRaises(NotFoundDomainError) as ctx:
                    operation()
                self.assertEqual(ctx.exception.message, "El paciente indicado no existe.")
