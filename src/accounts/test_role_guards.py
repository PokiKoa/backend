"""Pruebas de caracterización de las guardas de rol en los servicios de dominio.

Fijan qué roles puede ejecutar cada operación y el mensaje exacto de rechazo, para
proteger el comportamiento observable al centralizar la regla (Guía Unidad 3).
"""

import importlib
import inspect
from unittest import mock

from django.test import TestCase

from accounts.models import User, UserRole
from poki_koa.exceptions import PermissionDomainError

GUARDED_OPERATIONS = [
    (
        "patients",
        "admit_patient",
        {UserRole.NEONATOLOGIST, UserRole.NURSE},
        "Solo Neonatólogos o Matronas/Enfermeras pueden registrar el ingreso de un paciente.",
    ),
    (
        "patients",
        "update_patient",
        {UserRole.NEONATOLOGIST, UserRole.NURSE},
        "Solo el personal clínico puede modificar datos de un paciente.",
    ),
    (
        "patients",
        "discharge_patient",
        {UserRole.NEONATOLOGIST},
        "Solo un Neonatólogo está autorizado para firmar el egreso clínico de un paciente.",
    ),
    (
        "patients",
        "assign_patient_to_crib",
        {UserRole.ADMIN, UserRole.NEONATOLOGIST, UserRole.NURSE},
        "Solo el personal clínico o administrativo puede asignar pacientes a una cuna.",
    ),
    (
        "patients",
        "release_patient_from_crib",
        {UserRole.ADMIN, UserRole.NEONATOLOGIST, UserRole.NURSE},
        "Solo el personal clínico o administrativo puede liberar una cuna.",
    ),
    (
        "patients",
        "swap_patients_between_cribs",
        {UserRole.ADMIN, UserRole.NEONATOLOGIST, UserRole.NURSE},
        "Solo el personal clínico o administrativo puede intercambiar pacientes de cuna.",
    ),
    (
        "patients",
        "delete_patient_permanently",
        {UserRole.ADMIN},
        "Solo un Administrador puede eliminar definitivamente a un paciente.",
    ),
    (
        "patients",
        "record_patient_weight",
        {UserRole.NEONATOLOGIST, UserRole.NURSE},
        "Solo el personal clínico puede registrar mediciones de peso.",
    ),
    (
        "patients",
        "create_care_plan",
        {UserRole.NEONATOLOGIST, UserRole.NURSE},
        "Solo el personal clínico puede crear planes de cuidado.",
    ),
    (
        "patients",
        "update_care_plan",
        {UserRole.NEONATOLOGIST, UserRole.NURSE},
        "Solo el personal clínico puede actualizar planes de cuidado.",
    ),
    (
        "patients",
        "create_clinical_observation",
        {UserRole.NEONATOLOGIST, UserRole.NURSE},
        "Solo el personal clínico puede registrar observaciones clínicas.",
    ),
    (
        "alerts",
        "upsert_threshold_config",
        {UserRole.ADMIN, UserRole.NEONATOLOGIST},
        "Solo un Neonatólogo o Administrador puede configurar los umbrales de alerta clínica.",
    ),
    (
        "alerts",
        "acknowledge_alert",
        {UserRole.ADMIN, UserRole.NEONATOLOGIST, UserRole.NURSE},
        "Solo el personal clínico o administrativo puede reconocer alertas.",
    ),
    (
        "alerts",
        "resolve_alert",
        {UserRole.ADMIN, UserRole.NEONATOLOGIST, UserRole.NURSE},
        "Solo el personal clínico o administrativo puede resolver alertas manualmente.",
    ),
    (
        "medications",
        "create_catalog_item",
        {UserRole.ADMIN, UserRole.PHARMACIST},
        "Solo un Químico Farmacéutico o Administrador puede registrar medicamentos en el catálogo.",
    ),
    (
        "medications",
        "update_catalog_item",
        {UserRole.ADMIN, UserRole.PHARMACIST},
        "Solo un Químico Farmacéutico o Administrador puede actualizar el catálogo o el stock.",
    ),
    (
        "medications",
        "create_prescription",
        {UserRole.NEONATOLOGIST},
        "Solo un Neonatólogo está autorizado para prescribir indicaciones médicas.",
    ),
    (
        "medications",
        "administer_prescription",
        {UserRole.NEONATOLOGIST, UserRole.NURSE},
        "Solo un Neonatólogo o Matrona/Enfermera puede administrar medicamentos a un paciente.",
    ),
    (
        "medications",
        "cancel_prescription",
        {UserRole.NEONATOLOGIST},
        "Solo un Neonatólogo puede cancelar una indicación médica.",
    ),
    (
        "devices",
        "create_crib",
        {UserRole.ADMIN},
        "Solo un administrador puede registrar nuevas cunas en el sistema.",
    ),
    (
        "devices",
        "update_crib",
        {UserRole.ADMIN},
        "Solo un administrador puede modificar la configuración de una cuna.",
    ),
    (
        "devices",
        "rotate_crib_api_key",
        {UserRole.ADMIN},
        "Solo un administrador puede rotar la API Key de una cuna.",
    ),
    (
        "accounts",
        "create_shift_assignment",
        {UserRole.ADMIN},
        "Solo un administrador puede asignar turnos.",
    ),
    (
        "accounts",
        "delete_shift_assignment",
        {UserRole.ADMIN},
        "Solo un administrador puede eliminar asignaciones de turno.",
    ),
]


def _call(app: str, name: str, actor: User) -> None:
    func = getattr(importlib.import_module(f"{app}.services"), name)
    kwargs = {
        param: mock.MagicMock()
        for param, spec in inspect.signature(func).parameters.items()
        if param != "actor" and spec.default is inspect.Parameter.empty
    }
    func(actor=actor, **kwargs)


class RoleGuardCharacterizationTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.users = {
            role: User.objects.create_user(
                email=f"guard_{role}@pokikoa.cl",
                full_name=f"Guardia {role}",
                password="Str0ng!Password2026",
                role=role,
            )
            for role in UserRole.values
        }

    def test_disallowed_roles_are_rejected_with_the_documented_message(self) -> None:
        for app, name, allowed, message in GUARDED_OPERATIONS:
            for role in set(UserRole.values) - set(allowed):
                with self.subTest(operation=name, role=role):
                    with self.assertRaises(PermissionDomainError) as ctx:
                        _call(app, name, self.users[role])
                    self.assertEqual(ctx.exception.message, message)

    def test_allowed_roles_pass_the_role_guard(self) -> None:
        for app, name, allowed, _message in GUARDED_OPERATIONS:
            for role in allowed:
                with self.subTest(operation=name, role=role):
                    try:
                        _call(app, name, self.users[role])
                    except PermissionDomainError as exc:
                        self.fail(f"{name} rechazó al rol permitido {role}: {exc}")
                    except Exception:  # noqa: BLE001 - los argumentos simulados fallan después de la guarda
                        pass
