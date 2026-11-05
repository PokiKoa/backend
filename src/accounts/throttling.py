"""Limitación de tasa para endpoints sensibles de autenticación."""

from typing import Any

from django.conf import settings
from rest_framework.request import Request
from rest_framework.throttling import SimpleRateThrottle


class LoginRateThrottle(SimpleRateThrottle):
    """Limita los intentos de inicio de sesión por IP (por defecto 5 por minuto)."""

    scope = "login"

    def get_rate(self) -> str:
        """Lee la tasa de ``DEFAULT_THROTTLE_RATES['login']``; usa ``5/min`` si no está configurada."""
        rates = getattr(settings, "REST_FRAMEWORK", {}).get("DEFAULT_THROTTLE_RATES", {})
        return rates.get(self.scope, "5/min")

    def get_cache_key(self, request: Request, view: Any) -> str:
        """Clave de caché por IP del cliente, para contar los intentos."""
        ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}
