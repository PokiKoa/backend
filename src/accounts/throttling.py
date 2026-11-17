"""Limitación de tasa para endpoints sensibles de autenticación."""

from typing import Any

from django.conf import settings
from rest_framework.request import Request
from rest_framework.throttling import SimpleRateThrottle


class LoginRateThrottle(SimpleRateThrottle):
    """Limita la frecuencia de peticiones de inicio de sesión por dirección IP
    para mitigar ataques de fuerza bruta (por defecto 5 peticiones por minuto).
    """

    scope = "login"

    def get_rate(self) -> str:
        """Obtiene la tasa límite configurada en REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['login'].
        Si no está definida, utiliza un valor por defecto de '5/min'.

        Returns:
            str: La cadena con el límite de tasa (ej. '5/min').
        """
        rates = getattr(settings, "REST_FRAMEWORK", {}).get("DEFAULT_THROTTLE_RATES", {})
        return rates.get(self.scope, "5/min")

    def get_cache_key(self, request: Request, view: Any) -> str | None:
        """Genera la clave de caché única basada en la dirección IP del cliente
        para el seguimiento del consumo de tasa (throttle).

        Args:
            request: La petición HTTP entrante.
            view: La vista de DRF que se está ejecutando.

        Returns:
            str | None: La clave de caché formateada o None si se omite el throttling.
        """
        ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}
