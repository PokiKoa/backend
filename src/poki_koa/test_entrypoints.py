import importlib
import os
import sys
from io import StringIO
from unittest import mock

from django.contrib import admin
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from patients.models import CribMovement, Patient


class SeedDemoCommandTests(TestCase):
    def test_seed_demo_loads_data_and_is_idempotent(self) -> None:
        output = StringIO()
        call_command("seed_demo", stdout=output)
        call_command("seed_demo", stdout=output)

        self.assertIn("admin", output.getvalue())
        admin_user = User.objects.get(username="admin")
        self.assertTrue(admin_user.is_superuser)
        self.assertTrue(admin_user.check_password("admin2026"))
        self.assertEqual(
            Patient.objects.filter(medical_record_number__startswith="RN-2026").count(), 2
        )
        mateo = Patient.objects.get(medical_record_number="RN-2026-001")
        self.assertEqual(mateo.mother_rut, "16482937-5")
        self.assertEqual(mateo.father_phone, "+56955550102")
        self.assertTrue(CribMovement.objects.filter(patient=mateo).exists())


class EntrypointTests(TestCase):
    def test_main_defaults_to_runserver(self) -> None:
        from poki_koa import main as main_module

        with (
            mock.patch.object(sys, "argv", ["poki_koa"]),
            mock.patch("django.core.management.execute_from_command_line") as execute,
        ):
            main_module.main()
        execute.assert_called_once_with(["poki_koa", "runserver"])

    def test_main_runs_test_command_from_src(self) -> None:
        from poki_koa import main as main_module

        with (
            mock.patch.object(sys, "argv", ["poki_koa", "test"]),
            mock.patch("django.core.management.execute_from_command_line") as execute,
            mock.patch("poki_koa.main.Path.exists", return_value=True),
            mock.patch("poki_koa.main.os.chdir") as chdir,
        ):
            main_module.main()
        chdir.assert_called_once_with("src")
        execute.assert_called_once_with(["poki_koa", "test"])

    def test_manage_py_delegates_to_django(self) -> None:
        import manage

        with (
            mock.patch.object(sys, "argv", ["manage.py", "check"]),
            mock.patch("django.core.management.execute_from_command_line") as execute,
        ):
            manage.main()
        execute.assert_called_once_with(["manage.py", "check"])

    def test_wsgi_exposes_application(self) -> None:
        wsgi = importlib.import_module("poki_koa.wsgi")
        self.assertTrue(callable(wsgi.application))

    def test_prod_settings_require_and_harden_configuration(self) -> None:
        env = {
            "SECRET_KEY": "x" * 50,
            "ALLOWED_HOSTS": "pokikoa.example",
            "DATABASE_URL": "postgres://u:p@localhost:5432/db",
            "CORS_ALLOWED_ORIGINS": "https://pokikoa.example",
            "DEBUG": "False",
        }
        with mock.patch.dict(os.environ, env):
            sys.modules.pop("poki_koa.settings.prod", None)
            prod = importlib.import_module("poki_koa.settings.prod")
        self.assertFalse(prod.DEBUG)
        self.assertTrue(prod.SESSION_COOKIE_SECURE)
        self.assertTrue(prod.REFRESH_COOKIE["SECURE"])
        self.assertEqual(prod.CSRF_TRUSTED_ORIGINS, ["https://pokikoa.example"])
        sys.modules.pop("poki_koa.settings.prod", None)


class AdminPagesTests(TestCase):
    """Recorre el listado y el formulario de cada modelo registrado en el admin."""

    def setUp(self) -> None:
        call_command("seed_demo", stdout=StringIO())
        self.client.force_login(User.objects.get(username="admin"))

    def test_every_admin_changelist_and_change_view_renders(self) -> None:
        for model, model_admin in admin.site._registry.items():
            opts = model._meta
            changelist = reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist")
            response = self.client.get(changelist)
            self.assertEqual(response.status_code, 200, changelist)

            instance = model.objects.first()
            if instance is not None and model_admin.has_view_permission(
                mock.Mock(user=User.objects.get(username="admin")), instance
            ):
                change = reverse(
                    f"admin:{opts.app_label}_{opts.model_name}_change", args=[instance.pk]
                )
                self.assertEqual(self.client.get(change).status_code, 200, change)
