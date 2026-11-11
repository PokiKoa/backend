"""Contrato de ``accounts.roles``: conjuntos de roles y guarda ``require_role``."""

from types import SimpleNamespace

from django.test import SimpleTestCase

from accounts.models import UserRole
from accounts.roles import (
    ADMIN_ONLY,
    CATALOG_MANAGERS,
    CLINICAL_OR_ADMIN,
    CLINICAL_STAFF,
    THRESHOLD_MANAGERS,
    has_role,
    require_role,
)
from poki_koa.exceptions import PermissionDomainError


class RoleSetsTests(SimpleTestCase):
    def test_role_sets_have_the_expected_members(self) -> None:
        self.assertEqual(CLINICAL_STAFF, {UserRole.NEONATOLOGIST, UserRole.NURSE})
        self.assertEqual(CLINICAL_OR_ADMIN, CLINICAL_STAFF | {UserRole.ADMIN})
        self.assertEqual(THRESHOLD_MANAGERS, {UserRole.ADMIN, UserRole.NEONATOLOGIST})
        self.assertEqual(CATALOG_MANAGERS, {UserRole.ADMIN, UserRole.PHARMACIST})

    def test_role_sets_are_immutable(self) -> None:
        self.assertIsInstance(CLINICAL_STAFF, frozenset)


class RequireRoleTests(SimpleTestCase):
    def test_allowed_role_returns_none(self) -> None:
        actor = SimpleNamespace(role=UserRole.NURSE)
        self.assertIsNone(require_role(actor, CLINICAL_STAFF, "rechazado"))

    def test_disallowed_role_raises_permission_error_with_message(self) -> None:
        actor = SimpleNamespace(role=UserRole.PHARMACIST)
        with self.assertRaises(PermissionDomainError) as ctx:
            require_role(actor, CLINICAL_STAFF, "Solo el personal clínico.")
        self.assertEqual(ctx.exception.message, "Solo el personal clínico.")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_empty_allowed_set_rejects_every_role(self) -> None:
        for role in UserRole.values:
            with self.subTest(role=role), self.assertRaises(PermissionDomainError):
                require_role(SimpleNamespace(role=role), frozenset(), "nadie")

    def test_has_role_rejects_missing_user_or_role(self) -> None:
        self.assertFalse(has_role(None, ADMIN_ONLY))
        self.assertFalse(has_role(SimpleNamespace(), ADMIN_ONLY))
        self.assertTrue(has_role(SimpleNamespace(role=UserRole.ADMIN), ADMIN_ONLY))
