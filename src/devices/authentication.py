"""Autenticación de dispositivos de cuna mediante API Key por cabecera."""

from typing import Any

from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from .models import Crib, CribStatus, verify_device_api_key


class DevicePrincipal:
    """Identidad autenticada para una cuna o dispositivo IoT mediante API Key."""

    is_authenticated = True
    is_active = True
    is_device = True
    role = "device"

    def __init__(self, crib: Crib) -> None:
        """Inicializa la identidad del dispositivo asociado a una cuna.

        Args:
            crib: Instancia de la cuna autenticada.
        """
        self.crib = crib
        self.id = f"device:{crib.id}"


class DeviceApiKeyAuthentication(BaseAuthentication):
    """Autentica un dispositivo IoT mediante la cabecera ``X-Device-Api-Key`` (formato ``pk_dev_<prefijo>_<secreto>``)."""

    header_name = "HTTP_X_DEVICE_API_KEY"

    def authenticate(self, request: Request) -> tuple[DevicePrincipal, Crib] | None:
        """Valida la API Key provista en la cabecera y resuelve la cuna asociada.

        Args:
            request: Petición HTTP entrante.

        Returns:
            tuple[DevicePrincipal, Crib] | None: Tupla con la identidad y la cuna si la autenticación es exitosa,
            o ``None`` si la cabecera no está presente.

        Raises:
            AuthenticationFailed: Si el formato de la clave es inválido, no existe, la clave es incorrecta,
            o el dispositivo se encuentra deshabilitado o en mantenimiento.
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
    """Permite el acceso exclusivo a dispositivos autenticados y, a nivel de objeto, únicamente a su propia cuna."""

    message = "Se requiere una API Key válida perteneciente a esta cuna."

    def has_permission(self, request: Request, view: Any) -> bool:
        """Valida que la petición esté autenticada como un dispositivo IoT válido.

        Args:
            request: Petición HTTP entrante.
            view: Vista de DRF evaluada.

        Returns:
            bool: ``True`` si el usuario de la petición es un dispositivo autenticado.
        """
        user = getattr(request, "user", None)
        return bool(user and getattr(user, "is_device", False))

    def has_object_permission(self, request: Request, view: Any, obj: Any) -> bool:
        """Valida que el dispositivo solo acceda a recursos correspondientes a su propia cuna.

        Args:
            request: Petición HTTP entrante.
            view: Vista de DRF evaluada.
            obj: Instancia del objeto solicitado.

        Returns:
            bool: ``True`` si la cuna del dispositivo coincide con el recurso solicitado.
        """
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_device", False):
            return False
        crib_id = obj.id if isinstance(obj, Crib) else getattr(obj, "crib_id", None)
        return user.crib.id == crib_id


class DeviceApiKeyAuthenticationScheme(OpenApiAuthenticationExtension):
    """Declara el esquema de seguridad ``apiKey`` en el contrato OpenAPI para la autenticación de dispositivos."""

    target_class = "devices.authentication.DeviceApiKeyAuthentication"
    name = "DeviceApiKeyAuth"

    def get_security_definition(self, auto_schema: Any) -> dict[str, Any]:
        """Retorna la definición OpenAPI del esquema de autenticación por cabecera ``X-Device-Api-Key``.

        Args:
            auto_schema: Instancia del generador de esquemas.

        Returns:
            dict[str, Any]: Diccionario con la especificación de seguridad OpenAPI.
        """
        return {
            "type": "apiKey",
            "in": "header",
            "name": "X-Device-Api-Key",
            "description": "API Key por dispositivo de cuna neonatal (pk_dev_<prefix>_<secret>).",
        }
