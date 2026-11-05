from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from poki_koa.exceptions import (
    AccountLockedError,
    AuthenticationDomainError,
    ConflictDomainError,
    DomainError,
)

from .models import User, UserRole
from .services import (
    MAX_FAILED_LOGIN_ATTEMPTS,
    authenticate_user,
    create_user_by_admin,
    disable_two_factor,
    enable_two_factor,
    logout_user,
    rotate_refresh_token,
    setup_two_factor,
    update_user_by_admin,
)
from .totp import generate_totp_code

PASSWORD = "Str0ng!Password2026"


class AuthenticationEdgeCaseTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="enfermera.edge",
            email="nurse_edge@pokikoa.cl",
            full_name="Enfermera Bordes",
            password=PASSWORD,
            role=UserRole.NURSE,
        )

    def test_login_requires_credentials_and_rejects_unknown_user(self) -> None:
        with self.assertRaises(DomainError):
            authenticate_user(username="", password="")
        with self.assertRaises(AuthenticationDomainError):
            authenticate_user(username="no.existe", password=PASSWORD)

    def test_login_by_email_identifier_is_case_insensitive(self) -> None:
        result = authenticate_user(email="NURSE_EDGE@pokikoa.cl", password=PASSWORD)
        self.assertEqual(result["user"].id, self.user.id)

    def test_inactive_account_cannot_login(self) -> None:
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        with self.assertRaises(AuthenticationDomainError) as ctx:
            authenticate_user(username="enfermera.edge", password=PASSWORD)
        self.assertEqual(ctx.exception.code, "account_inactive")

    def test_lockout_after_max_failures_blocks_even_correct_password(self) -> None:
        for _ in range(MAX_FAILED_LOGIN_ATTEMPTS - 1):
            with self.assertRaises(AuthenticationDomainError):
                authenticate_user(username="enfermera.edge", password="Incorrecta123")
        with self.assertRaises(AccountLockedError):
            authenticate_user(username="enfermera.edge", password="Incorrecta123")

        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.locked_until)
        with self.assertRaises(AccountLockedError):
            authenticate_user(username="enfermera.edge", password=PASSWORD)

    def test_successful_login_resets_failure_counter(self) -> None:
        with self.assertRaises(AuthenticationDomainError):
            authenticate_user(username="enfermera.edge", password="Incorrecta123")
        authenticate_user(username="enfermera.edge", password=PASSWORD)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 0)

    def test_two_factor_full_lifecycle(self) -> None:
        setup = setup_two_factor(user=self.user)
        self.assertIn("otpauth://", setup["provisioning_uri"])

        with self.assertRaises(DomainError):
            enable_two_factor(user=self.user, otp_code="000000x")
        enable_two_factor(user=self.user, otp_code=generate_totp_code(setup["secret"]))

        with self.assertRaises(ConflictDomainError):
            setup_two_factor(user=self.user)

        with self.assertRaises(AuthenticationDomainError) as missing:
            authenticate_user(username="enfermera.edge", password=PASSWORD)
        self.assertEqual(missing.exception.code, "two_factor_required")

        with self.assertRaises(AuthenticationDomainError) as invalid:
            authenticate_user(username="enfermera.edge", password=PASSWORD, otp_code="123")
        self.assertEqual(invalid.exception.code, "invalid_two_factor_code")

        ok = authenticate_user(
            username="enfermera.edge",
            password=PASSWORD,
            otp_code=generate_totp_code(setup["secret"]),
        )
        self.assertIn("access", ok)

        with self.assertRaises(DomainError):
            disable_two_factor(user=self.user, otp_code="999999x")
        disable_two_factor(user=self.user, otp_code=generate_totp_code(setup["secret"]))
        self.assertFalse(self.user.is_two_factor_enabled)
        with self.assertRaises(ConflictDomainError):
            disable_two_factor(user=self.user, otp_code="000000")

    def test_enable_two_factor_without_secret_fails(self) -> None:
        with self.assertRaises(DomainError):
            enable_two_factor(user=self.user, otp_code="123456")

    def test_refresh_rotation_and_logout_edge_cases(self) -> None:
        tokens = authenticate_user(username="enfermera.edge", password=PASSWORD)

        with self.assertRaises(DomainError):
            rotate_refresh_token(refresh_token_str="")
        with self.assertRaises(AuthenticationDomainError):
            rotate_refresh_token(refresh_token_str="token.invalido")

        rotated = rotate_refresh_token(refresh_token_str=tokens["refresh"])
        # El refresh original queda revocado tras la rotación
        with self.assertRaises(AuthenticationDomainError):
            rotate_refresh_token(refresh_token_str=tokens["refresh"])

        other = User.objects.create_user(
            username="otro.usuario",
            email="other_edge@pokikoa.cl",
            full_name="Otro Usuario",
            password=PASSWORD,
            role=UserRole.NURSE,
        )
        with self.assertRaises(DomainError):
            logout_user(refresh_token_str="", actor=self.user)
        with self.assertRaises(AuthenticationDomainError):
            logout_user(refresh_token_str="token.invalido", actor=self.user)
        with self.assertRaises(AuthenticationDomainError) as mismatch:
            logout_user(refresh_token_str=rotated["refresh"], actor=other)
        self.assertEqual(mismatch.exception.code, "token_owner_mismatch")

        logout_user(refresh_token_str=rotated["refresh"], actor=self.user)
        with self.assertRaises(AuthenticationDomainError):
            logout_user(refresh_token_str=rotated["refresh"], actor=self.user)

    def test_refresh_of_deactivated_account_is_rejected(self) -> None:
        tokens = authenticate_user(username="enfermera.edge", password=PASSWORD)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        with self.assertRaises(AuthenticationDomainError) as ctx:
            rotate_refresh_token(refresh_token_str=tokens["refresh"])
        self.assertEqual(ctx.exception.code, "account_inactive")


class UserAdministrationEdgeCaseTests(TestCase):
    def setUp(self) -> None:
        self.admin = User.objects.create_user(
            username="admin.edge",
            email="admin_edge@pokikoa.cl",
            full_name="Admin Bordes",
            password=PASSWORD,
            role=UserRole.ADMIN,
        )

    def test_create_user_validations(self) -> None:
        with self.assertRaises(DomainError):
            create_user_by_admin(actor=self.admin, full_name="Sin Usuario", password=PASSWORD)
        with self.assertRaises(DomainError):
            create_user_by_admin(
                actor=self.admin, username="x.y", full_name="  ", password=PASSWORD
            )
        with self.assertRaises(DomainError):
            create_user_by_admin(
                actor=self.admin,
                username="x.y",
                full_name="Rol Malo",
                password=PASSWORD,
                role="surgeon",
            )
        with self.assertRaises(DomainError):
            create_user_by_admin(
                actor=self.admin,
                username="x.y",
                full_name="Turno Malo",
                password=PASSWORD,
                shift="weekend",
            )
        with self.assertRaises(ValidationError):
            create_user_by_admin(
                actor=self.admin, username="x.y", full_name="Clave Débil", password="123"
            )

    def test_create_user_derives_username_from_email_and_detects_duplicates(self) -> None:
        user = create_user_by_admin(
            actor=self.admin,
            email="Matrona.Turno@PokiKoa.cl",
            full_name="Matrona Turno",
            password=PASSWORD,
            role=UserRole.NURSE,
            shift="night",
        )
        self.assertEqual(user.username, "matrona.turno")
        self.assertEqual(user.email, "matrona.turno@pokikoa.cl")

        with self.assertRaises(ConflictDomainError):
            create_user_by_admin(
                actor=self.admin,
                username="matrona.turno",
                full_name="Duplicado",
                password=PASSWORD,
            )
        with self.assertRaises(ConflictDomainError):
            create_user_by_admin(
                actor=self.admin,
                username="otro.nombre",
                email="matrona.turno@pokikoa.cl",
                full_name="Correo Duplicado",
                password=PASSWORD,
            )

    def test_admin_cannot_demote_or_deactivate_self(self) -> None:
        with self.assertRaises(ConflictDomainError):
            update_user_by_admin(
                actor=self.admin, target_user=self.admin, data={"is_active": False}
            )
        with self.assertRaises(ConflictDomainError):
            update_user_by_admin(
                actor=self.admin, target_user=self.admin, data={"role": UserRole.NURSE}
            )

    def test_update_user_all_fields_unlock_and_validations(self) -> None:
        target = create_user_by_admin(
            actor=self.admin,
            username="farmacia.edge",
            email="farmacia@pokikoa.cl",
            full_name="Farmacia Bordes",
            password=PASSWORD,
            role=UserRole.PHARMACIST,
        )
        create_user_by_admin(
            actor=self.admin,
            username="ocupado",
            email="ocupado@pokikoa.cl",
            full_name="Usuario Ocupado",
            password=PASSWORD,
        )

        for invalid in (
            {"username": "  "},
            {"full_name": ""},
            {"role": "surgeon"},
            {"shift": "weekend"},
        ):
            with self.subTest(data=invalid), self.assertRaises(DomainError):
                update_user_by_admin(actor=self.admin, target_user=target, data=invalid)

        with self.assertRaises(ConflictDomainError):
            update_user_by_admin(actor=self.admin, target_user=target, data={"username": "ocupado"})
        with self.assertRaises(ConflictDomainError):
            update_user_by_admin(
                actor=self.admin,
                target_user=target,
                data={"email": "ocupado@pokikoa.cl"},
            )

        User.objects.filter(pk=target.pk).update(
            failed_login_attempts=5,
            locked_until=timezone.now() + timedelta(minutes=10),
        )
        updated = update_user_by_admin(
            actor=self.admin,
            target_user=target,
            data={
                "username": "farmacia.jefa",
                "email": "jefa@pokikoa.cl",
                "full_name": "Farmacia Jefa",
                "role": UserRole.ADMIN,
                "shift": "morning",
                "is_active": False,
                "unlock_account": True,
                "password": "Nuev0!Password2026",
            },
        )
        self.assertEqual(updated.username, "farmacia.jefa")
        self.assertTrue(updated.is_staff)
        self.assertFalse(updated.is_active)
        self.assertEqual(updated.failed_login_attempts, 0)
        self.assertIsNone(updated.locked_until)
        self.assertTrue(updated.check_password("Nuev0!Password2026"))
