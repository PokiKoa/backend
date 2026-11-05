from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from audit.models import AuditAction, AuditLog

PASSWORD = "Str0ng!Password2026"
NEW_PASSWORD = "Nuev4Clave!Segura"


class ChangePasswordEndpointTests(APITestCase):
    url = "/api/v1/auth/change-password/"

    def setUp(self) -> None:
        cache.clear()
        self.user = User.objects.create_user(
            username="enf.clave",
            email="clave@pokikoa.cl",
            full_name="Enfermera Clave",
            password=PASSWORD,
            role=UserRole.NURSE,
        )

    def _login(self, password: str = PASSWORD):
        return self.client.post(
            "/api/v1/auth/login/", {"username": "enf.clave", "password": password}, format="json"
        )

    def test_requires_authentication(self) -> None:
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_change_password_revokes_other_sessions_and_renews_tokens(self) -> None:
        other_session = self._login().cookies["poki_refresh"].value
        login = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

        response = self.client.post(
            self.url,
            {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data), {"access"})
        new_cookie = response.cookies["poki_refresh"].value

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditAction.UPDATE, resource_type="user", changed_fields=["password"]
            ).exists()
        )

        self.client.credentials()
        self.client.cookies["poki_refresh"] = other_session
        self.assertEqual(
            self.client.post("/api/v1/auth/refresh/").status_code, status.HTTP_401_UNAUTHORIZED
        )
        self.client.cookies["poki_refresh"] = new_cookie
        self.assertEqual(self.client.post("/api/v1/auth/refresh/").status_code, status.HTTP_200_OK)

        self.assertEqual(self._login(PASSWORD).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self._login(NEW_PASSWORD).status_code, status.HTTP_200_OK)

    def test_rejections_keep_current_password(self) -> None:
        self.client.force_authenticate(user=self.user)
        cases = [
            ({"current_password": "incorrecta", "new_password": NEW_PASSWORD}, "current_password"),
            ({"current_password": PASSWORD, "new_password": PASSWORD}, "new_password"),
            ({"current_password": PASSWORD, "new_password": "corta"}, None),
        ]
        for payload, field in cases:
            with self.subTest(payload=payload):
                response = self.client.post(self.url, payload, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                if field:
                    self.assertIn(field, response.data["error"]["details"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))


class StaffDirectoryEndpointTests(APITestCase):
    def setUp(self) -> None:
        self.nurse = User.objects.create_user(
            email="dir_nurse@pokikoa.cl",
            full_name="Matrona Directorio",
            password=PASSWORD,
            role=UserRole.NURSE,
        )
        self.neo = User.objects.create_user(
            email="dir_neo@pokikoa.cl",
            full_name="Dra. Directorio",
            password=PASSWORD,
            role=UserRole.NEONATOLOGIST,
        )
        User.objects.create_user(
            email="dir_off@pokikoa.cl",
            full_name="Inactivo",
            password=PASSWORD,
            role=UserRole.NEONATOLOGIST,
            is_active=False,
        )

    def test_any_clinical_user_lists_active_staff_without_account_fields(self) -> None:
        self.client.force_authenticate(user=self.nurse)
        response = self.client.get("/api/v1/staff/", {"role": UserRole.NEONATOLOGIST})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        member = response.data["results"][0]
        self.assertEqual(member["id"], self.neo.id)
        self.assertEqual(set(member), {"id", "full_name", "role", "shift"})

    def test_requires_authentication(self) -> None:
        self.assertEqual(
            self.client.get("/api/v1/staff/").status_code, status.HTTP_401_UNAUTHORIZED
        )
