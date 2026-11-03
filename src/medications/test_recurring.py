from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from patients.services import admit_patient
from poki_koa.exceptions import ConflictDomainError, DomainError

from . import schedule
from .models import MedicationAdministration, Prescription, PrescriptionStatus
from .services import administer_prescription, create_catalog_item, create_prescription

PASSWORD = "Str0ng!Password2026"
T0 = datetime(2026, 11, 3, 8, 0, tzinfo=UTC)


def _unsaved(frequency_hours=None, ends_at=None, starts_at=T0) -> Prescription:
    return Prescription(starts_at=starts_at, frequency_hours=frequency_hours, ends_at=ends_at)


class ScheduleFunctionTests(SimpleTestCase):
    def test_single_dose_has_one_slot(self) -> None:
        p = _unsaved()
        self.assertEqual(schedule.last_slot(p), T0)
        self.assertTrue(schedule.is_valid_slot(p, T0))
        self.assertFalse(schedule.is_valid_slot(p, T0 + timedelta(hours=8)))
        self.assertIsNone(schedule.next_slot_after(p, T0))

    def test_recurring_slots_are_aligned_and_bounded_by_end(self) -> None:
        p = _unsaved(frequency_hours=8, ends_at=T0 + timedelta(hours=20))
        self.assertEqual(schedule.last_slot(p), T0 + timedelta(hours=16))
        self.assertTrue(schedule.is_valid_slot(p, T0 + timedelta(hours=8)))
        self.assertFalse(schedule.is_valid_slot(p, T0 + timedelta(hours=3)))
        self.assertFalse(schedule.is_valid_slot(p, T0 + timedelta(hours=24)))
        self.assertFalse(schedule.is_valid_slot(p, T0 - timedelta(hours=8)))
        self.assertEqual(schedule.next_slot_after(p, None), T0)
        self.assertEqual(schedule.next_slot_after(p, T0), T0 + timedelta(hours=8))
        self.assertIsNone(schedule.next_slot_after(p, T0 + timedelta(hours=16)))

    def test_open_ended_recurring_has_no_last_slot(self) -> None:
        p = _unsaved(frequency_hours=12)
        self.assertIsNone(schedule.last_slot(p))
        self.assertTrue(schedule.is_valid_slot(p, T0 + timedelta(days=30)))

    def test_latest_due_slot_respects_early_window(self) -> None:
        p = _unsaved(frequency_hours=8)
        self.assertIsNone(schedule.latest_due_slot(p, T0 - timedelta(minutes=61)))
        self.assertEqual(schedule.latest_due_slot(p, T0 - timedelta(minutes=60)), T0)
        # A las 15:00 la dosis de las 16:00 ya está habilitada (60 min de anticipación)
        self.assertEqual(
            schedule.latest_due_slot(p, T0 + timedelta(hours=7)), T0 + timedelta(hours=8)
        )
        self.assertEqual(
            schedule.latest_due_slot(p, T0 + timedelta(hours=6)), T0
        )
        bounded = _unsaved(frequency_hours=8, ends_at=T0 + timedelta(hours=9))
        self.assertEqual(
            schedule.latest_due_slot(bounded, T0 + timedelta(days=2)), T0 + timedelta(hours=8)
        )


class RecurringPrescriptionServiceTests(TestCase):
    def setUp(self) -> None:
        self.neo = User.objects.create_user(
            email="neo_rec@pokikoa.cl", full_name="Neo Rec", password=PASSWORD,
            role=UserRole.NEONATOLOGIST,
        )
        self.nurse = User.objects.create_user(
            email="nurse_rec@pokikoa.cl", full_name="Enf Rec", password=PASSWORD,
            role=UserRole.NURSE,
        )
        pharmacist = User.objects.create_user(
            email="qf_rec@pokikoa.cl", full_name="QF Rec", password=PASSWORD,
            role=UserRole.PHARMACIST,
        )
        self.patient = admit_patient(
            actor=self.neo,
            medical_record_number="RN-REC-01",
            full_name="RN Recurrente",
            sex="F",
            birth_date=timezone.localdate() - timedelta(days=2),
            gestational_age_weeks=Decimal("30.0"),
            birth_weight_g=1300,
        )
        self.item = create_catalog_item(
            actor=pharmacist, name="Ampicilina", active_ingredient="Ampicilina",
            concentration_mg="500", stock=10,
        )
        self.now = timezone.now().replace(second=0, microsecond=0)

    def _prescribe(self, **overrides) -> Prescription:
        params = {
            "actor": self.neo,
            "patient_id": self.patient.id,
            "medication_id": self.item.id,
            "dose": "50 mg/kg IV",
            "starts_at": self.now - timedelta(hours=17),
            "frequency_hours": 8,
        }
        return create_prescription(**{**params, **overrides})

    def test_creation_validations(self) -> None:
        invalid = [
            {"frequency_hours": 0},
            {"frequency_hours": 169},
            {"frequency_hours": None, "ends_at": self.now + timedelta(days=1)},
            {"ends_at": self.now - timedelta(days=1)},
            {"starts_at": timezone.make_naive(self.now)},
        ]
        for override in invalid:
            with self.subTest(override=override), self.assertRaises(DomainError):
                self._prescribe(**override)

    def test_starts_at_is_truncated_to_the_minute(self) -> None:
        p = self._prescribe(starts_at=self.now + timedelta(seconds=42, microseconds=7))
        self.assertEqual(p.starts_at, self.now)

    def test_default_administration_targets_latest_due_dose_and_blocks_repeat(self) -> None:
        p = self._prescribe()
        first = administer_prescription(actor=self.nurse, prescription=p)
        self.assertEqual(first.scheduled_for, p.starts_at + timedelta(hours=16))
        self.assertEqual(first.prescription.status, PrescriptionStatus.ACTIVE)

        with self.assertRaisesMessage(ConflictDomainError, "ya fue administrada"):
            administer_prescription(actor=self.nurse, prescription=p)

        overdue = administer_prescription(
            actor=self.nurse, prescription=p, scheduled_for=p.starts_at + timedelta(hours=8)
        )
        self.assertEqual(overdue.units_deducted, 1)
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock, 8)

    def test_explicit_slot_must_be_valid_and_not_too_early(self) -> None:
        p = self._prescribe()
        with self.assertRaises(DomainError):
            administer_prescription(
                actor=self.nurse, prescription=p, scheduled_for=p.starts_at + timedelta(hours=3)
            )
        with self.assertRaisesMessage(ConflictDomainError, "anticipación"):
            administer_prescription(
                actor=self.nurse, prescription=p, scheduled_for=p.starts_at + timedelta(hours=24)
            )

    def test_future_first_dose_cannot_be_given_yet(self) -> None:
        p = self._prescribe(starts_at=self.now + timedelta(hours=2))
        with self.assertRaisesMessage(ConflictDomainError, "Aún no corresponde"):
            administer_prescription(actor=self.nurse, prescription=p)

        early_ok = self._prescribe(starts_at=self.now + timedelta(minutes=45), frequency_hours=None)
        given = administer_prescription(actor=self.nurse, prescription=early_ok)
        self.assertEqual(given.prescription.status, PrescriptionStatus.COMPLETED)

    def test_administering_last_dose_completes_prescription(self) -> None:
        p = self._prescribe(ends_at=self.now - timedelta(minutes=30))
        administration = administer_prescription(actor=self.nurse, prescription=p)
        self.assertEqual(administration.scheduled_for, p.starts_at + timedelta(hours=16))
        self.assertEqual(administration.prescription.status, PrescriptionStatus.COMPLETED)
        with self.assertRaisesMessage(ConflictDomainError, "completada o cancelada"):
            administer_prescription(
                actor=self.nurse, prescription=p, scheduled_for=p.starts_at
            )

    def test_schedule_state_reports_next_dose_and_overdue(self) -> None:
        p = self._prescribe()
        state = schedule.schedule_state(p, self.now)
        self.assertEqual(state.next_dose_at, p.starts_at)
        self.assertTrue(state.is_overdue)
        self.assertEqual(state.administrations_count, 0)

        administer_prescription(actor=self.nurse, prescription=p)
        state = schedule.schedule_state(p, self.now)
        self.assertEqual(state.next_dose_at, p.starts_at + timedelta(hours=24))
        self.assertFalse(state.is_overdue)
        self.assertEqual(state.administrations_count, 1)

    def test_database_rejects_duplicate_dose_slot(self) -> None:
        p = self._prescribe()
        administration = administer_prescription(actor=self.nurse, prescription=p)
        with self.assertRaises(IntegrityError), transaction.atomic():
            MedicationAdministration.objects.create(
                prescription=p,
                scheduled_for=administration.scheduled_for,
                administered_at=timezone.now(),
                administered_by=self.nurse,
                units_deducted=1,
            )


class RecurringPrescriptionEndpointTests(APITestCase):
    def setUp(self) -> None:
        self.neo = User.objects.create_user(
            email="neo_rep@pokikoa.cl", full_name="Neo Rep", password=PASSWORD,
            role=UserRole.NEONATOLOGIST,
        )
        self.nurse = User.objects.create_user(
            email="nurse_rep@pokikoa.cl", full_name="Enf Rep", password=PASSWORD,
            role=UserRole.NURSE,
        )
        pharmacist = User.objects.create_user(
            email="qf_rep@pokikoa.cl", full_name="QF Rep", password=PASSWORD,
            role=UserRole.PHARMACIST,
        )
        self.patient = admit_patient(
            actor=self.neo,
            medical_record_number="RN-REP-01",
            full_name="RN Endpoint Recurrente",
            sex="M",
            birth_date=timezone.localdate() - timedelta(days=1),
            gestational_age_weeks=Decimal("34.0"),
            birth_weight_g=2100,
        )
        self.item = create_catalog_item(
            actor=pharmacist, name="Gentamicina", active_ingredient="Gentamicina",
            concentration_mg="10", stock=5,
        )

    def test_recurring_flow_with_schedule_fields_and_history(self) -> None:
        starts_at = (timezone.now() - timedelta(hours=1)).replace(second=0, microsecond=0)
        self.client.force_authenticate(user=self.neo)
        created = self.client.post(
            "/api/v1/prescriptions/",
            {
                "patient_id": self.patient.id,
                "medication_id": self.item.id,
                "dose": "4 mg/kg IV",
                "starts_at": starts_at.isoformat(),
                "frequency_hours": 36,
            },
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(created.data["status"], PrescriptionStatus.ACTIVE)
        self.assertTrue(created.data["is_overdue"])
        self.assertEqual(created.data["administrations_count"], 0)
        presc_id = created.data["id"]

        self.client.force_authenticate(user=self.nurse)
        given = self.client.post(
            f"/api/v1/prescriptions/{presc_id}/administer/", {"notes": "Sin incidentes"}, format="json"
        )
        self.assertEqual(given.status_code, status.HTTP_200_OK)
        self.assertEqual(given.data["administrations_count"], 1)
        self.assertFalse(given.data["is_overdue"])
        self.assertIsNotNone(given.data["next_dose_at"])

        bad_slot = self.client.post(
            f"/api/v1/prescriptions/{presc_id}/administer/",
            {"scheduled_for": (starts_at + timedelta(minutes=5)).isoformat()},
            format="json",
        )
        self.assertEqual(bad_slot.status_code, status.HTTP_400_BAD_REQUEST)

        history = self.client.get(f"/api/v1/prescriptions/{presc_id}/administrations/")
        self.assertEqual(history.status_code, status.HTTP_200_OK)
        self.assertEqual(history.data["count"], 1)
        self.assertEqual(history.data["results"][0]["administered_by"], self.nurse.id)
        self.assertEqual(history.data["results"][0]["notes"], "Sin incidentes")

        listing = self.client.get("/api/v1/prescriptions/", {"is_recurring": "true"})
        self.assertEqual(listing.data["count"], 1)
        self.assertEqual(listing.data["results"][0]["administrations_count"], 1)
        single = self.client.get("/api/v1/prescriptions/", {"is_recurring": "false"})
        self.assertEqual(single.data["count"], 0)
