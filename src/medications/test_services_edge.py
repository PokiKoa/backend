from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.models import User, UserRole
from patients.services import admit_patient, discharge_patient
from poki_koa.exceptions import (
    ConflictDomainError,
    DomainError,
    NotFoundDomainError,
    PermissionDomainError,
)

from .models import PrescriptionStatus
from .services import (
    administer_prescription,
    cancel_prescription,
    create_catalog_item,
    create_prescription,
    update_catalog_item,
)

PASSWORD = "Str0ng!Password2026"


class MedicationEdgeCaseTests(TestCase):
    def setUp(self) -> None:
        self.pharmacist = User.objects.create_user(
            email="pharm_edge@pokikoa.cl",
            full_name="Farmacia Bordes",
            password=PASSWORD,
            role=UserRole.PHARMACIST,
        )
        self.neonatologist = User.objects.create_user(
            email="neo_edge@pokikoa.cl",
            full_name="Neonatólogo Bordes",
            password=PASSWORD,
            role=UserRole.NEONATOLOGIST,
        )
        self.nurse = User.objects.create_user(
            email="nurse_med_edge@pokikoa.cl",
            full_name="Enfermera Bordes",
            password=PASSWORD,
            role=UserRole.NURSE,
        )
        self.patient = admit_patient(
            actor=self.neonatologist,
            medical_record_number="RN-MED-001",
            full_name="Paciente Medicación",
            sex="M",
            birth_date=timezone.localdate() - timedelta(days=4),
            gestational_age_weeks=Decimal("32.0"),
            birth_weight_g=1600,
        )
        self.item = create_catalog_item(
            actor=self.pharmacist,
            name="Surfactante",
            active_ingredient="Poractant alfa",
            concentration_mg="80.00",
            stock=2,
            min_stock_alert=1,
        )

    def _prescribe(self, units: int = 1):
        return create_prescription(
            actor=self.neonatologist,
            patient_id=self.patient.id,
            medication_id=self.item.id,
            dose="2.5 ml/kg",
            starts_at=timezone.now(),
            units_per_administration=units,
        )

    def test_catalog_creation_validations(self) -> None:
        with self.assertRaises(PermissionDomainError):
            create_catalog_item(
                actor=self.nurse, name="X", active_ingredient="X", concentration_mg=1
            )
        invalid_cases = [
            {"name": " ", "active_ingredient": "X", "concentration_mg": 1},
            {"name": "X", "active_ingredient": " ", "concentration_mg": 1},
            {"name": "X", "active_ingredient": "X", "concentration_mg": 1, "unit": " "},
            {"name": "X", "active_ingredient": "X", "concentration_mg": 0},
            {"name": "X", "active_ingredient": "X", "concentration_mg": 1, "stock": -1},
            {
                "name": "X",
                "active_ingredient": "X",
                "concentration_mg": 1,
                "min_stock_alert": -1,
            },
        ]
        for case in invalid_cases:
            with self.subTest(case=case), self.assertRaises(DomainError):
                create_catalog_item(actor=self.pharmacist, **case)

        with self.assertRaises(ConflictDomainError):
            create_catalog_item(
                actor=self.pharmacist,
                name="surfactante",
                active_ingredient="Duplicado",
                concentration_mg=1,
            )

    def test_catalog_update_validations_and_changes(self) -> None:
        create_catalog_item(
            actor=self.pharmacist,
            name="Cafeina",
            active_ingredient="Cafeína citrato",
            concentration_mg=20,
        )
        with self.assertRaises(PermissionDomainError):
            update_catalog_item(actor=self.nurse, item=self.item, data={"stock": 10})

        for invalid in (
            {"name": ""},
            {"unit": " "},
            {"concentration_mg": "0"},
            {"stock": -5},
            {"min_stock_alert": -1},
        ):
            with self.subTest(data=invalid), self.assertRaises(DomainError):
                update_catalog_item(actor=self.pharmacist, item=self.item, data=invalid)

        # Nombre ASCII: SQLite solo compara sin mayúsculas en ASCII (PostgreSQL sí en Unicode)
        with self.assertRaises(ConflictDomainError):
            update_catalog_item(actor=self.pharmacist, item=self.item, data={"name": "CAFEINA"})

        updated = update_catalog_item(
            actor=self.pharmacist,
            item=self.item,
            data={
                "name": "Surfactante Pulmonar",
                "active_ingredient": "Poractant",
                "unit": "vial",
                "concentration_mg": "120",
                "stock": 10,
                "min_stock_alert": 3,
                "is_active": False,
            },
        )
        self.assertEqual(updated.unit, "vial")
        self.assertEqual(updated.concentration_mg, Decimal("120.00"))
        self.assertFalse(updated.is_active)

    def test_prescription_validations(self) -> None:
        with self.assertRaises(PermissionDomainError):
            create_prescription(
                actor=self.nurse,
                patient_id=self.patient.id,
                medication_id=self.item.id,
                dose="1 ml",
                starts_at=timezone.now(),
            )
        base = {
            "actor": self.neonatologist,
            "patient_id": self.patient.id,
            "medication_id": self.item.id,
            "dose": "1 ml",
            "starts_at": timezone.now(),
        }
        for override in ({"dose": " "}, {"route": "NASAL"}, {"units_per_administration": 0}):
            with self.subTest(override=override), self.assertRaises(DomainError):
                create_prescription(**{**base, **override})

        with self.assertRaises(NotFoundDomainError):
            create_prescription(**{**base, "patient_id": 999999})
        with self.assertRaises(NotFoundDomainError):
            create_prescription(**{**base, "medication_id": 999999})

        update_catalog_item(actor=self.pharmacist, item=self.item, data={"is_active": False})
        with self.assertRaises(ConflictDomainError):
            create_prescription(**base)

    def test_stock_reaches_exactly_zero_then_blocks_next_administration(self) -> None:
        first = self._prescribe(units=2)
        second = self._prescribe(units=1)

        administered = administer_prescription(actor=self.nurse, prescription=first)
        self.assertEqual(administered.prescription.status, PrescriptionStatus.COMPLETED)
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock, 0)

        with self.assertRaises(ConflictDomainError):
            administer_prescription(actor=self.nurse, prescription=second)
        second.refresh_from_db()
        self.assertEqual(second.status, PrescriptionStatus.ACTIVE)

    def test_double_administration_and_cancelled_prescriptions_are_blocked(self) -> None:
        prescription = self._prescribe()
        administer_prescription(actor=self.nurse, prescription=prescription)
        with self.assertRaises(ConflictDomainError):
            administer_prescription(actor=self.nurse, prescription=prescription)
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock, 1)

        with self.assertRaises(PermissionDomainError):
            administer_prescription(actor=self.pharmacist, prescription=prescription)

        pending = self._prescribe()
        with self.assertRaises(PermissionDomainError):
            cancel_prescription(actor=self.nurse, prescription=pending)
        cancelled = cancel_prescription(
            actor=self.neonatologist, prescription=pending, reason="Suspensión médica"
        )
        self.assertEqual(cancelled.status, PrescriptionStatus.CANCELLED)
        with self.assertRaises(ConflictDomainError):
            cancel_prescription(actor=self.neonatologist, prescription=pending)
        with self.assertRaises(ConflictDomainError):
            administer_prescription(actor=self.nurse, prescription=pending)

    def test_inactive_medication_cannot_be_administered(self) -> None:
        prescription = self._prescribe()
        update_catalog_item(actor=self.pharmacist, item=self.item, data={"is_active": False})
        with self.assertRaises(ConflictDomainError):
            administer_prescription(actor=self.nurse, prescription=prescription)

    def test_discharge_cancels_pending_and_blocks_new_prescriptions(self) -> None:
        pending = self._prescribe()
        discharge_patient(actor=self.neonatologist, patient=self.patient, outcome="survived")
        pending.refresh_from_db()
        self.assertEqual(pending.status, PrescriptionStatus.CANCELLED)

        with self.assertRaises(ConflictDomainError):
            self._prescribe()
