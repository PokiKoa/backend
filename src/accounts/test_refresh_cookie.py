from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User, UserRole

PASSWORD = "Str0ng!Password2026"
COOKIE = "poki_refresh"


@override_settings(CORS_ALLOWED_ORIGINS=["http://localhost:5173"])
class RefreshCookieFlowTests(APITestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = User.objects.create_user(
            username="enf.cookie",
            email="cookie@pokikoa.cl",
            full_name="Enfermera Cookie",
            password=PASSWORD,
            role=UserRole.NURSE,
        )

    def _login(self):
        response = self.client.post(
            "/api/v1/auth/login/", {"username": "enf.cookie", "password": PASSWORD}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response

    def test_login_sets_httponly_cookie_and_omits_refresh_from_body(self) -> None:
        response = self._login()
        self.assertIn("access", response.data)
        self.assertNotIn("refresh", response.data)
        cookie = response.cookies[COOKIE]
        self.assertTrue(cookie.value)
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["path"], "/api/v1/auth/")
        self.assertEqual(cookie["samesite"], "Lax")

    def test_refresh_rotates_cookie_and_revokes_previous_token(self) -> None:
        first = self._login().cookies[COOKIE].value
        refreshed = self.client.post("/api/v1/auth/refresh/", HTTP_ORIGIN="http://localhost:5173")
        self.assertEqual(refreshed.status_code, status.HTTP_200_OK)
        self.assertEqual(set(refreshed.data), {"access"})
        second = refreshed.cookies[COOKIE].value
        self.assertNotEqual(first, second)

        self.client.cookies[COOKIE] = first
        reused = self.client.post("/api/v1/auth/refresh/")
        self.assertEqual(reused.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_without_cookie_is_rejected(self) -> None:
        response = self.client.post("/api/v1/auth/refresh/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_refresh_from_unknown_origin_is_forbidden(self) -> None:
        self._login()
        response = self.client.post("/api/v1/auth/refresh/", HTTP_ORIGIN="https://evil.example")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_same_origin_requests_are_allowed(self) -> None:
        self._login()
        response = self.client.post("/api/v1/auth/refresh/", HTTP_ORIGIN="http://testserver")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_logout_revokes_token_and_clears_cookie(self) -> None:
        login = self._login()
        token = login.cookies[COOKIE].value
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

        logout = self.client.post("/api/v1/auth/logout/")
        self.assertEqual(logout.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(logout.cookies[COOKIE].value, "")
        self.assertEqual(logout.cookies[COOKIE]["max-age"], 0)

        self.client.cookies[COOKIE] = token
        self.client.credentials()
        self.assertEqual(
            self.client.post("/api/v1/auth/refresh/").status_code, status.HTTP_401_UNAUTHORIZED
        )

    def test_logout_without_cookie_is_idempotent(self) -> None:
        self.client.force_authenticate(user=self.user)
        response = self.client.post("/api/v1/auth/logout/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    @override_settings(
        REFRESH_COOKIE={
            "NAME": "poki_refresh",
            "PATH": "/api/v1/auth/",
            "DOMAIN": None,
            "SAMESITE": "None",
            "SECURE": True,
        }
    )
    def test_cross_site_configuration_marks_cookie_secure(self) -> None:
        cookie = self._login().cookies[COOKIE]
        self.assertTrue(cookie["secure"])
        self.assertEqual(cookie["samesite"], "None")
