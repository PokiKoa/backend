import importlib
import os
import sys
from unittest import mock

from django.test import SimpleTestCase

PROD_ENV = {
    "SECRET_KEY": "x" * 50,
    "ALLOWED_HOSTS": "pokikoa.racsu.com",
    "DATABASE_URL": "postgres://u:p@localhost:5432/db",
    "CORS_ALLOWED_ORIGINS": "https://pokikoa.racsu.com",
}


def _load(module_name: str, env: dict[str, str]):
    # Importa una copia fresca del módulo y deja sys.modules como estaba
    original = sys.modules.pop(module_name, None)
    try:
        with mock.patch.dict(os.environ, env):
            return importlib.import_module(module_name)
    finally:
        sys.modules.pop(module_name, None)
        if original is not None:
            sys.modules[module_name] = original


class StaticSettingsParityTests(SimpleTestCase):
    """El Dockerfile ejecuta collectstatic con settings.dev: debe producir lo mismo que prod."""

    def setUp(self) -> None:
        self.dev = _load("poki_koa.settings.dev", {})
        self.prod = _load("poki_koa.settings.prod", PROD_ENV)

    def test_static_configuration_is_shared_by_dev_and_prod(self) -> None:
        for name in ("INSTALLED_APPS", "STATIC_URL", "STATIC_ROOT", "STORAGES"):
            self.assertEqual(getattr(self.dev, name), getattr(self.prod, name), name)

    def test_whitenoise_serves_static_right_after_security_middleware(self) -> None:
        middleware = self.prod.MIDDLEWARE
        security = middleware.index("django.middleware.security.SecurityMiddleware")
        self.assertEqual(middleware[security + 1], "whitenoise.middleware.WhiteNoiseMiddleware")
        self.assertIn("django.contrib.admin", self.prod.INSTALLED_APPS)
