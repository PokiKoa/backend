import importlib
import os
import sys
from unittest import mock

from django.db import OperationalError
from django.test import TestCase, override_settings

READY_URL = "/api/v1/health/ready/"
PROD_ENV = {
    "SECRET_KEY": "x" * 50,
    "ALLOWED_HOSTS": "pokikoa.racsu.com",
    "DATABASE_URL": "postgres://u:p@localhost:5432/db",
    "CORS_ALLOWED_ORIGINS": "https://pokikoa.racsu.com",
}


def _load_prod_settings():
    with mock.patch.dict(os.environ, PROD_ENV):
        sys.modules.pop("poki_koa.settings.prod", None)
        try:
            return importlib.import_module("poki_koa.settings.prod")
        finally:
            sys.modules.pop("poki_koa.settings.prod", None)


class ReadinessViewTests(TestCase):
    def test_returns_ok_without_authentication_or_sensitive_data(self) -> None:
        response = self.client.get(READY_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_head_is_allowed_and_writes_are_rejected(self) -> None:
        self.assertEqual(self.client.head(READY_URL).status_code, 200)
        self.assertEqual(self.client.post(READY_URL).status_code, 405)

    def test_returns_503_when_database_is_down(self) -> None:
        with (
            mock.patch(
                "poki_koa.views.connection.cursor", side_effect=OperationalError("sin conexión")
            ),
            self.assertLogs("poki_koa.views", level="WARNING"),
        ):
            response = self.client.get(READY_URL)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})


class ReadinessBehindSslRedirectTests(TestCase):
    """Con la configuración real de prod.py, el healthcheck interno por HTTP no se redirige."""

    def setUp(self) -> None:
        prod = _load_prod_settings()
        self.assertTrue(prod.SECURE_SSL_REDIRECT)
        self.prod_overrides = override_settings(
            ALLOWED_HOSTS=prod.ALLOWED_HOSTS,
            SECURE_SSL_REDIRECT=prod.SECURE_SSL_REDIRECT,
            SECURE_REDIRECT_EXEMPT=prod.SECURE_REDIRECT_EXEMPT,
            SECURE_PROXY_SSL_HEADER=prod.SECURE_PROXY_SSL_HEADER,
        )
        self.prod_overrides.enable()
        self.addCleanup(self.prod_overrides.disable)

    def test_plain_http_readiness_is_exempt_from_redirect(self) -> None:
        response = self.client.get(READY_URL, HTTP_HOST="pokikoa.racsu.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_other_plain_http_paths_still_redirect_to_https(self) -> None:
        response = self.client.get("/api/v1/health/", HTTP_HOST="pokikoa.racsu.com")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "https://pokikoa.racsu.com/api/v1/health/")

    def test_exemption_only_matches_the_exact_path(self) -> None:
        response = self.client.get(f"{READY_URL}extra/", HTTP_HOST="pokikoa.racsu.com")
        self.assertEqual(response.status_code, 301)
