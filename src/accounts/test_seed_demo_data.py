import os
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings

from accounts.models import User
from patients.models import Patient

DEMO_USERNAMES = ("admin", "dr.soto", "matrona.diaz", "qf.silva")
GUARDIAN_RUT_FIELDS = ("mother_rut", "father_rut")
GUARDIAN_PHONE_FIELDS = ("mother_phone", "father_phone")


@override_settings(DEBUG=True)
@mock.patch.dict(os.environ, {"SEED_DEMO_PASSWORD": ""})
class SeedDemoFictitiousDataTests(TestCase):
    """Los repositorios son públicos: ningún dato de demostración puede apuntar a una persona real."""

    def setUp(self) -> None:
        call_command("seed_demo", stdout=StringIO())
        self.patients = list(Patient.objects.filter(medical_record_number__startswith="RN-2026"))

    def test_demo_patients_are_loaded(self) -> None:
        self.assertEqual(len(self.patients), 2)

    def test_guardians_have_no_rut(self) -> None:
        for patient in self.patients:
            for field in GUARDIAN_RUT_FIELDS:
                self.assertEqual(getattr(patient, field), "", f"{patient} {field}")

    def test_guardian_phones_are_placeholders(self) -> None:
        for patient in self.patients:
            for field in GUARDIAN_PHONE_FIELDS:
                phone = getattr(patient, field)
                if phone:
                    self.assertTrue(phone.startswith("+5690000"), f"{patient} {field}={phone}")

    def test_demo_users_use_reserved_email_domain(self) -> None:
        for user in User.objects.filter(username__in=DEMO_USERNAMES):
            self.assertTrue(user.email.endswith("@example.org"), user.email)

    def test_patients_are_marked_as_fictitious(self) -> None:
        for patient in self.patients:
            self.assertRegex(patient.full_name, r"\(Fictici[oa]\)$")
