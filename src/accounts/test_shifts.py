from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import AuditLog
from devices.services import create_crib
from patients.services import admit_patient
from poki_koa.exceptions import ConflictDomainError, DomainError, PermissionDomainError

from .models import ShiftAssignment, User, UserRole, WorkShift
from .services import create_shift_assignment, current_shift, shift_window

PASSWORD = "Str0ng!Password2026"


def _local(day: date, hour: int, minute: int = 0) -> datetime:
    return timezone.make_aware(datetime.combine(day, time(hour, minute)))


class ShiftClockTests(TestCase):
    def test_every_hour_maps_to_exactly_one_shift(self) -> None:
        day = date(2026, 11, 3)
        cases = {
            (7, 0): (day, WorkShift.MORNING),
            (14, 59): (day, WorkShift.MORNING),
            (15, 0): (day, WorkShift.AFTERNOON),
            (23, 0): (day, WorkShift.NIGHT),
            (6, 59): (day - timedelta(days=1), WorkShift.NIGHT),
        }
        for (hour, minute), expected in cases.items():
            with self.subTest(hour=hour, minute=minute):
                self.assertEqual(current_shift(_local(day, hour, minute)), expected)

    def test_night_window_crosses_midnight(self) -> None:
        start, end = shift_window(WorkShift.NIGHT, date(2026, 11, 3))
        self.assertEqual(timezone.localtime(start), _local(date(2026, 11, 3), 23))
        self.assertEqual(timezone.localtime(end), _local(date(2026, 11, 4), 7))


class ShiftAssignmentTests(APITestCase):
    def setUp(self) -> None:
        # Reloj fijo a media mañana: evita fallos si la prueba cruza un cambio de turno
        frozen = _local(timezone.localdate(), 10)
        patcher = mock.patch("django.utils.timezone.now", return_value=frozen)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.admin = User.objects.create_user(
            email="admin_sh@pokikoa.cl",
            full_name="Admin Turnos",
            password=PASSWORD,
            role=UserRole.ADMIN,
        )
        self.nurse = User.objects.create_user(
            email="nurse_sh@pokikoa.cl",
            full_name="Matrona Turnos",
            password=PASSWORD,
            role=UserRole.NURSE,
        )
        self.pharmacist = User.objects.create_user(
            email="qf_sh@pokikoa.cl",
            full_name="QF Turnos",
            password=PASSWORD,
            role=UserRole.PHARMACIST,
        )
        neo = User.objects.create_user(
            email="neo_sh@pokikoa.cl",
            full_name="Neo Turnos",
            password=PASSWORD,
            role=UserRole.NEONATOLOGIST,
        )
        self.crib, _ = create_crib(actor=self.admin, code="C-SH-1")
        self.other_crib, _ = create_crib(actor=self.admin, code="C-SH-2")
        admit_patient(
            actor=neo,
            medical_record_number="RN-SH-01",
            full_name="RN Turno",
            sex="F",
            birth_date=timezone.localdate() - timedelta(days=1),
            gestational_age_weeks=Decimal("35.0"),
            birth_weight_g=2300,
            crib_id=self.crib.id,
        )

    def _assign(self, **overrides):
        day, shift = current_shift()
        params = {
            "actor": self.admin,
            "user_id": self.nurse.id,
            "crib_id": self.crib.id,
            "day": day,
            "shift": shift,
        }
        return create_shift_assignment(**{**params, **overrides})

    def test_service_rules(self) -> None:
        assignment = self._assign()
        self.assertTrue(
            AuditLog.objects.filter(
                resource_type="shift_assignment", resource_id=str(assignment.id)
            ).exists()
        )
        with self.assertRaises(ConflictDomainError):
            self._assign()
        with self.assertRaises(PermissionDomainError):
            self._assign(actor=self.nurse, crib_id=self.other_crib.id)
        with self.assertRaises(DomainError):
            self._assign(user_id=self.pharmacist.id)
        with self.assertRaises(DomainError):
            self._assign(shift="weekend")

    def test_shift_catalog_marks_current_shift(self) -> None:
        self.client.force_authenticate(user=self.nurse)
        response = self.client.get("/api/v1/shifts/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([s["value"] for s in response.data], list(WorkShift.values))
        self.assertEqual(sum(s["is_current"] for s in response.data), 1)
        self.assertEqual(response.data[0]["starts_at"], "07:00")

    def test_admin_manages_assignments_and_nurse_sees_own_cribs(self) -> None:
        day, shift = current_shift()
        self.client.force_authenticate(user=self.admin)
        created = self.client.post(
            "/api/v1/shift-assignments/",
            {"user_id": self.nurse.id, "crib_id": self.crib.id, "date": day, "shift": shift},
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(created.data["crib_code"], "C-SH-1")
        self._assign(day=day - timedelta(days=1), crib_id=self.other_crib.id)

        listing = self.client.get("/api/v1/shift-assignments/", {"date": day.isoformat()})
        self.assertEqual(listing.data["count"], 1)

        self.client.force_authenticate(user=self.nurse)
        mine = self.client.get("/api/v1/shift-assignments/mine/")
        self.assertEqual(mine.status_code, status.HTTP_200_OK)
        self.assertEqual(mine.data["shift"], shift)
        self.assertEqual([c["code"] for c in mine.data["cribs"]], ["C-SH-1"])
        self.assertEqual(mine.data["cribs"][0]["patient"]["medical_record_number"], "RN-SH-01")

        forbidden = self.client.delete(f"/api/v1/shift-assignments/{created.data['id']}/")
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.admin)
        deleted = self.client.delete(f"/api/v1/shift-assignments/{created.data['id']}/")
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ShiftAssignment.objects.filter(pk=created.data["id"]).exists())

    def test_mine_is_empty_outside_assigned_shift(self) -> None:
        _, shift = current_shift()
        other = next(s for s in WorkShift.values if s != shift)
        self._assign(shift=other)
        self.client.force_authenticate(user=self.nurse)
        mine = self.client.get("/api/v1/shift-assignments/mine/")
        self.assertEqual(mine.data["cribs"], [])
