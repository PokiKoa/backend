"""Autenticación de dispositivos de cuna mediante API Key por cabecera."""

from typing import Any

from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from .models import Crib, CribStatus, verify_device_api_key


class DevicePrincipal:
    """Identidad autenticada para una cuna/dispositivo IoT mediante API Key."""

    is_authenticated = True
    is_active = True
    is_device = True
    role = "device"

    def __init__(self, crib: Crib) -> None:
        self.crib = crib
        self.id = f"device:{crib.id}"


class DeviceApiKeyAuthentication(BaseAuthentication):
    """Autentica un dispositivo con la cabecera ``X-Device-Api-Key`` (formato ``pk_dev_<prefijo>_<secreto>``)."""

    header_name = "HTTP_X_DEVICE_API_KEY"

    def authenticate(self, request: Request) -> tuple[DevicePrincipal, Crib] | None:
        """Resuelve la cuna dueña de la API Key.

        Args:
            request: Petición entrante.

        Returns:
            ``(DevicePrincipal, cuna)``, o ``None`` si la cabecera no viene (otros autenticadores pueden actuar).

        Raises:
            AuthenticationFailed: Formato inválido, clave desconocida, o dispositivo deshabilitado o en mantenimiento.
        """
        raw_key = request.META.get(self.header_name)
        if not raw_key:
            return None

        raw_key = raw_key.strip()
        parts = raw_key.split("_")
        # Formato esperado: pk_dev_<8hex>_<48hex>
        if len(parts) != 4 or parts[0] != "pk" or parts[1] != "dev":
            raise AuthenticationFailed("Formato de API Key de dispositivo inválido.")

        prefix = f"pk_dev_{parts[2]}"
        crib = Crib.objects.filter(api_key_prefix=prefix).first()
        if crib is None or not verify_device_api_key(raw_key, crib.api_key_hash):
            raise AuthenticationFailed("API Key de dispositivo inválida.")

        if not crib.is_device_active or crib.status == CribStatus.MAINTENANCE:
            raise AuthenticationFailed(
                "El dispositivo se encuentra deshabilitado o en mantenimiento."
            )

        return (DevicePrincipal(crib), crib)


class IsAuthenticatedDeviceForCrib(BasePermission):
    """Permite el acceso solo a un dispositivo autenticado y, a nivel de objeto, solo a su propia cuna."""

    message = "Se requiere una API Key válida perteneciente a esta cuna."

    def has_permission(self, request: Request, view: Any) -> bool:
        """Devuelve ``True`` si la petición fue autenticada como dispositivo."""
        user = getattr(request, "user", None)
        return bool(user and getattr(user, "is_device", False))

    def has_object_permission(self, request: Request, view: Any, obj: Any) -> bool:
        """Devuelve ``True`` si el objeto es la cuna del dispositivo o pertenece a ella (``crib_id``)."""
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_device", False):
            return False
        crib_id = obj.id if isinstance(obj, Crib) else getattr(obj, "crib_id", None)
        return user.crib.id == crib_id


class DeviceApiKeyAuthenticationScheme(OpenApiAuthenticationExtension):
    """Declara el esquema ``apiKey`` en el contrato OpenAPI para la autenticación de dispositivos."""

    target_class = "devices.authentication.DeviceApiKeyAuthentication"
    name = "DeviceApiKeyAuth"

    def get_security_definition(self, auto_schema: Any) -> dict[str, Any]:
        """Devuelve la definición OpenAPI del esquema (cabecera ``X-Device-Api-Key``)."""
        return {
            "type": "apiKey",
            "in": "header",
            "name": "X-Device-Api-Key",
            "description": "API Key por dispositivo de cuna neonatal (pk_dev_<prefix>_<secret>).",
        }
