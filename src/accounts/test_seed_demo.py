import os
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from accounts.management.commands.seed_demo import DEMO_ADMIN_PASSWORD, DEMO_STAFF_PASSWORD
from accounts.models import User

DEMO_USERNAMES = ("admin", "dr.soto", "matrona.diaz", "qf.silva")
STRONG_PASSWORD = "Demo#Despliegue-2026"


def _seed(password: str) -> str:
    output = StringIO()
    with mock.patch.dict(os.environ, {"SEED_DEMO_PASSWORD": password}):
        call_command("seed_demo", stdout=output)
    return output.getvalue()


@override_settings(DEBUG=False)
class SeedDemoProductionTests(TestCase):
    def test_refuses_public_passwords_without_env_var(self) -> None:
        with self.assertRaisesMessage(CommandError, "SEED_DEMO_PASSWORD"):
            _seed("")
        self.assertFalse(User.objects.filter(username__in=DEMO_USERNAMES).exists())

    def test_rejects_public_demo_passwords_given_by_env_var(self) -> None:
        for public in (DEMO_ADMIN_PASSWORD, DEMO_STAFF_PASSWORD):
            with self.assertRaisesMessage(CommandError, "contraseñas públicas"):
                _seed(public)
        self.assertFalse(User.objects.filter(username="admin").exists())

    def test_rejects_weak_password(self) -> None:
        with self.assertRaisesMessage(CommandError, "política de contraseñas"):
            _seed("corta")
        self.assertFalse(User.objects.filter(username="admin").exists())

    def test_uses_env_password_for_every_demo_user_without_printing_it(self) -> None:
        output = _seed(STRONG_PASSWORD)
        for username in DEMO_USERNAMES:
            user = User.objects.get(username=username)
            self.assertTrue(user.check_password(STRONG_PASSWORD), username)
            self.assertFalse(user.check_password(DEMO_ADMIN_PASSWORD), username)
            self.assertFalse(user.check_password(DEMO_STAFF_PASSWORD), username)
        self.assertNotIn(STRONG_PASSWORD, output)
        self.assertIn("SEED_DEMO_PASSWORD", output)

    def test_rerun_rotates_existing_admin_password(self) -> None:
        with override_settings(DEBUG=True):
            _seed("")
        self.assertTrue(User.objects.get(username="admin").check_password(DEMO_ADMIN_PASSWORD))
        _seed(STRONG_PASSWORD)
        admin = User.objects.get(username="admin")
        self.assertFalse(admin.check_password(DEMO_ADMIN_PASSWORD))
        self.assertTrue(admin.check_password(STRONG_PASSWORD))


@override_settings(DEBUG=True)
class SeedDemoDevelopmentTests(TestCase):
    def test_uses_public_passwords_in_debug(self) -> None:
        output = _seed("")
        self.assertTrue(User.objects.get(username="admin").check_password(DEMO_ADMIN_PASSWORD))
        self.assertTrue(User.objects.get(username="dr.soto").check_password(DEMO_STAFF_PASSWORD))
        self.assertIn(DEMO_ADMIN_PASSWORD, output)

    def test_env_password_also_applies_in_debug(self) -> None:
        _seed(STRONG_PASSWORD)
        self.assertTrue(User.objects.get(username="qf.silva").check_password(STRONG_PASSWORD))


@override_settings(DEBUG=True)
class SeedDemoKeepsExistingPasswordsTests(TestCase):
    def test_rerun_without_env_var_keeps_existing_passwords(self) -> None:
        _seed("")
        for username in DEMO_USERNAMES:
            user = User.objects.get(username=username)
            user.set_password(STRONG_PASSWORD)
            user.save()

        output = _seed("")

        for username in DEMO_USERNAMES:
            user = User.objects.get(username=username)
            self.assertTrue(user.check_password(STRONG_PASSWORD), username)
            self.assertFalse(user.check_password(DEMO_ADMIN_PASSWORD), username)
            self.assertFalse(user.check_password(DEMO_STAFF_PASSWORD), username)
        self.assertIn("sin cambios", output)
        self.assertNotIn(DEMO_ADMIN_PASSWORD, output)
