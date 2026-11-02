from typing import Any

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
    header_name = "HTTP_X_DEVICE_API_KEY"

    def authenticate(self, request: Request) -> tuple[DevicePrincipal, Crib] | None:
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
    message = "Se requiere una API Key válida perteneciente a esta cuna."

    def has_permission(self, request: Request, view: Any) -> bool:
        user = getattr(request, "user", None)
        return bool(user and getattr(user, "is_device", False))

    def has_object_permission(self, request: Request, view: Any, obj: Any) -> bool:
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_device", False):
            return False
        crib_id = obj.id if isinstance(obj, Crib) else getattr(obj, "crib_id", None)
        return user.crib.id == crib_id
