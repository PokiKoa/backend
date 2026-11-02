from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User, UserRole, WorkShift
from accounts.services import (
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
from accounts.totp import generate_totp_code, generate_totp_secret, verify_totp_code
from audit.models import AuditAction, AuditLog
from poki_koa.exceptions import (
    AccountLockedError,
    AuthenticationDomainError,
    ConflictDomainError,
)


class TotpUtilityTests(TestCase):
    def test_totp_generation_and_verification_window(self) -> None:
        secret = generate_totp_secret()
        fixed_ts = 1_700_000_000
        code = generate_totp_code(secret, timestamp=fixed_ts)
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())
        self.assertTrue(verify_totp_code(secret, code, timestamp=fixed_ts))
        # Límite dentro de la ventana de ±1 paso (30s)
        self.assertTrue(verify_totp_code(secret, code, timestamp=fixed_ts + 30))
        # Fuera de la ventana (±60s)
        self.assertFalse(verify_totp_code(secret, code, timestamp=fixed_ts + 60))
        self.assertFalse(verify_totp_code(secret, "000000", timestamp=fixed_ts))
        self.assertFalse(verify_totp_code(secret, "abcdef", timestamp=fixed_ts))


class AccountsServiceTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.valid_password = "Neonatologia#2026"
        self.admin = User.objects.create_user(
            email="admin@pokikoa.cl",
            full_name="Administrador General",
            password=self.valid_password,
            role=UserRole.ADMIN,
        )
        self.doctor = User.objects.create_user(
            email="doctor@pokikoa.cl",
            full_name="Dr. Martín Soto",
            password=self.valid_password,
            role=UserRole.NEONATOLOGIST,
            shift=WorkShift.MORNING,
        )

    def test_authenticate_user_success_resets_attempts_and_logs(self) -> None:
        self.doctor.failed_login_attempts = MAX_FAILED_LOGIN_ATTEMPTS - 1
        self.doctor.save(update_fields=["failed_login_attempts"])

        result = authenticate_user(
            email="  DOCTOR@pokikoa.cl ",
            password=self.valid_password,
            ip_address="10.0.0.5",
        )
        self.doctor.refresh_from_db()
        self.assertEqual(self.doctor.failed_login_attempts, 0)
        self.assertIsNone(self.doctor.locked_until)
        self.assertIn("access", result)
        self.assertIn("refresh", result)
        self.assertTrue(
            AuditLog.objects.filter(
                actor_user=self.doctor,
                action=AuditAction.LOGIN_SUCCESS,
            ).exists()
        )

    def test_lockout_boundary_on_fifth_failed_attempt(self) -> None:
        for expected_attempts in range(1, MAX_FAILED_LOGIN_ATTEMPTS):
            with self.assertRaises(AuthenticationDomainError):
                authenticate_user(email=self.doctor.email, password="WrongPassword!1")
            self.doctor.refresh_from_db()
            self.assertEqual(self.doctor.failed_login_attempts, expected_attempts)
            self.assertFalse(self.doctor.is_temporarily_locked)

        # El 5.º intento fallido bloquea temporalmente la cuenta
        with self.assertRaises(AccountLockedError):
            authenticate_user(email=self.doctor.email, password="WrongPassword!1")

        self.doctor.refresh_from_db()
        self.assertEqual(self.doctor.failed_login_attempts, MAX_FAILED_LOGIN_ATTEMPTS)
        self.assertTrue(self.doctor.is_temporarily_locked)
        self.assertTrue(
            AuditLog.objects.filter(
                actor_user=self.doctor,
                action=AuditAction.ACCOUNT_LOCKED,
            ).exists()
        )

        # Incluso con la contraseña correcta se rechaza mientras esté bloqueada
        with self.assertRaises(AccountLockedError):
            authenticate_user(email=self.doctor.email, password=self.valid_password)

    def test_refresh_token_rotation_and_revocation(self) -> None:
        auth = authenticate_user(email=self.doctor.email, password=self.valid_password)
        first_refresh = auth["refresh"]

        rotated = rotate_refresh_token(refresh_token_str=first_refresh)
        self.assertNotEqual(rotated["refresh"], first_refresh)

        # Reutilizar el refresh token anterior debe fallar porque fue revocado
        with self.assertRaises(AuthenticationDomainError):
            rotate_refresh_token(refresh_token_str=first_refresh)

    def test_logout_revokes_refresh_token_and_prevents_cross_user_revocation(self) -> None:
        auth = authenticate_user(email=self.doctor.email, password=self.valid_password)
        refresh_token = auth["refresh"]

        # Otro usuario no puede cerrar sesión con el refresh token ajeno
        with self.assertRaises(AuthenticationDomainError):
            logout_user(refresh_token_str=refresh_token, actor=self.admin)

        logout_user(refresh_token_str=refresh_token, actor=self.doctor)

        with self.assertRaises(AuthenticationDomainError):
            rotate_refresh_token(refresh_token_str=refresh_token)

    def test_two_factor_setup_enable_authenticate_and_disable(self) -> None:
        setup_data = setup_two_factor(user=self.doctor)
        secret = setup_data["secret"]
        code = generate_totp_code(secret)

        enable_two_factor(user=self.doctor, otp_code=code)
        self.doctor.refresh_from_db()
        self.assertTrue(self.doctor.is_two_factor_enabled)

        # Sin código OTP falla con código específico two_factor_required
        with self.assertRaises(AuthenticationDomainError) as ctx:
            authenticate_user(email=self.doctor.email, password=self.valid_password)
        self.assertEqual(ctx.exception.code, "two_factor_required")

        # Con código OTP válido autentica correctamente
        auth = authenticate_user(
            email=self.doctor.email,
            password=self.valid_password,
            otp_code=code,
        )
        self.assertIn("access", auth)

        disable_two_factor(user=self.doctor, otp_code=code)
        self.doctor.refresh_from_db()
        self.assertFalse(self.doctor.is_two_factor_enabled)
        self.assertEqual(self.doctor.totp_secret, "")

    def test_password_policy_rejects_weak_passwords_atomically(self) -> None:
        weak_passwords = [
            "Corta!1",  # < 10 caracteres (límite inferior 9)
            "Abcdefgh!1"[1:],  # exactamente 9 caracteres
            " minusculas123!",  # sin mayúsculas
            "MAYUSCULAS123!",  # sin minúsculas
            "SinNumerosAbc!",  # sin dígitos
            "SinEspeciales123",  # sin carácter especial
        ]
        initial_count = User.objects.count()
        for weak in weak_passwords:
            with self.assertRaises(DjangoValidationError):
                create_user_by_admin(
                    actor=self.admin,
                    email="nuevo@pokikoa.cl",
                    full_name="Usuario Prueba",
                    password=weak,
                    role=UserRole.NURSE,
                )
        self.assertEqual(User.objects.count(), initial_count)

    def test_admin_cannot_deactivate_or_demote_self(self) -> None:
        with self.assertRaises(ConflictDomainError):
            update_user_by_admin(
                actor=self.admin,
                target_user=self.admin,
                data={"is_active": False},
            )
        with self.assertRaises(ConflictDomainError):
            update_user_by_admin(
                actor=self.admin,
                target_user=self.admin,
                data={"role": UserRole.NURSE},
            )


class AccountsAndHealthEndpointTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.client = APIClient()
        self.password = "ClinicaSegura#2026"
        self.admin = User.objects.create_user(
            email="admin@pokikoa.cl",
            full_name="Dra. Camila Rojas",
            password=self.password,
            role=UserRole.ADMIN,
        )
        self.neonatologist = User.objects.create_user(
            email="neo@pokikoa.cl",
            full_name="Dr. Jorge Pizarro",
            password=self.password,
            role=UserRole.NEONATOLOGIST,
            shift=WorkShift.MORNING,
        )
        self.nurse = User.objects.create_user(
            email="nurse@pokikoa.cl",
            full_name="Matrona Javiera Díaz",
            password=self.password,
            role=UserRole.NURSE,
            shift=WorkShift.NIGHT,
        )
        self.pharmacist = User.objects.create_user(
            email="pharma@pokikoa.cl",
            full_name="QF. Rodrigo Silva",
            password=self.password,
            role=UserRole.PHARMACIST,
        )

    def test_health_check_and_openapi_schema_endpoints(self) -> None:
        root_res = self.client.get("/")
        self.assertEqual(root_res.status_code, status.HTTP_200_OK)
        self.assertContains(root_res, "Poki Koa")

        health_res = self.client.get("/api/v1/health/")
        self.assertEqual(health_res.status_code, status.HTTP_200_OK)
        self.assertEqual(health_res.data["status"], "ok")

        # /api/v1/schema/ requiere autenticación como todo endpoint no público
        unauth_schema = self.client.get("/api/v1/schema/")
        self.assertEqual(unauth_schema.status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.force_authenticate(user=self.admin)
        schema_res = self.client.get("/api/v1/schema/")
        self.assertEqual(schema_res.status_code, status.HTTP_200_OK)

        self.admin.is_staff = True
        self.admin.is_superuser = True
        self.admin.save(update_fields=["is_staff", "is_superuser"])
        self.client.force_login(self.admin)
        admin_res = self.client.get("/admin/")
        self.assertEqual(admin_res.status_code, status.HTTP_200_OK)
        self.assertContains(admin_res, "Acciones rápidas")

    def test_login_refresh_me_and_logout_http_flow(self) -> None:
        login_res = self.client.post(
            "/api/v1/auth/login/",
            {"username": self.nurse.username, "password": self.password},
            format="json",
        )
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)
        access = login_res.data["access"]
        refresh = login_res.data["refresh"]
        self.assertEqual(login_res.data["user"]["role"], UserRole.NURSE)
        self.assertEqual(login_res.data["user"]["username"], self.nurse.username)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        me_res = self.client.get("/api/v1/auth/me/")
        self.assertEqual(me_res.status_code, status.HTTP_200_OK)
        self.assertEqual(me_res.data["username"], self.nurse.username)

        refresh_res = self.client.post(
            "/api/v1/auth/refresh/",
            {"refresh": refresh},
            format="json",
        )
        self.assertEqual(refresh_res.status_code, status.HTTP_200_OK)
        new_refresh = refresh_res.data["refresh"]

        logout_res = self.client.post(
            "/api/v1/auth/logout/",
            {"refresh": new_refresh},
            format="json",
        )
        self.assertEqual(logout_res.status_code, status.HTTP_204_NO_CONTENT)

        # Intentar refrescar tras logout falla con 401
        reuse_res = self.client.post(
            "/api/v1/auth/refresh/",
            {"refresh": new_refresh},
            format="json",
        )
        self.assertEqual(reuse_res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(reuse_res.data["error"]["code"], "token_invalid")

    @override_settings(
        REST_FRAMEWORK={
            "DEFAULT_AUTHENTICATION_CLASSES": (
                "rest_framework_simplejwt.authentication.JWTAuthentication",
            ),
            "DEFAULT_PERMISSION_CLASSES": (
                "rest_framework.permissions.IsAuthenticated",
            ),
            "EXCEPTION_HANDLER": "poki_koa.exceptions.custom_exception_handler",
            "DEFAULT_THROTTLE_RATES": {"login": "3/min"},
        }
    )
    def test_login_rate_limiting_returns_429_with_uniform_error(self) -> None:
        cache.clear()
        for _ in range(3):
            res = self.client.post(
                "/api/v1/auth/login/",
                {"email": self.nurse.email, "password": self.password},
                format="json",
            )
            self.assertEqual(res.status_code, status.HTTP_200_OK)

        throttled_res = self.client.post(
            "/api/v1/auth/login/",
            {"email": self.nurse.email, "password": self.password},
            format="json",
        )
        self.assertEqual(throttled_res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(throttled_res.data["error"]["code"], "rate_limit_exceeded")

    def test_users_endpoint_permissions_by_role(self) -> None:
        for non_admin in (self.neonatologist, self.nurse, self.pharmacist):
            self.client.force_authenticate(user=non_admin)
            res = self.client.get("/api/v1/users/")
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(res.data["error"]["code"], "permission_denied")

        self.client.force_authenticate(user=self.admin)
        list_res = self.client.get("/api/v1/users/?role=nurse")
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        self.assertEqual(list_res.data["count"], 1)
        self.assertEqual(list_res.data["results"][0]["email"], self.nurse.email)

        create_res = self.client.post(
            "/api/v1/users/",
            {
                "email": "nueva.matrona@pokikoa.cl",
                "full_name": "Matrona Valentina Ríos",
                "password": "Valentina#2026Segura",
                "role": UserRole.NURSE,
                "shift": WorkShift.AFTERNOON,
            },
            format="json",
        )
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)
        created_id = create_res.data["id"]

        patch_res = self.client.patch(
            f"/api/v1/users/{created_id}/",
            {"shift": WorkShift.NIGHT},
            format="json",
        )
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.data["shift"], WorkShift.NIGHT)
