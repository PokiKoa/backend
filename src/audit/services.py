"""Servicios de auditoría: registro inmutable de accesos y modificaciones sin datos clínicos."""

import ipaddress
import re
from collections.abc import Iterable
from typing import Any

from django.conf import settings

from .models import AuditLog

_FIELD_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _valid_ip(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def get_client_ip(request: Any) -> str | None:
    """Obtiene la IP del cliente confiando solo en los proxies propios (``TRUSTED_PROXY_COUNT``).

    Cada proxy agrega a la derecha de ``X-Forwarded-For`` la IP de quien le habló, así que solo
    las últimas ``TRUSTED_PROXY_COUNT`` entradas son confiables: lo que esté más a la izquierda
    lo escribió el cliente y puede ser falso. Con ``0`` se ignora la cabecera y se usa
    ``REMOTE_ADDR``.

    Args:
        request: Petición HTTP (o ``None``).

    Returns:
        IP del cliente o ``None`` si no se puede determinar.
    """
    if request is None or not hasattr(request, "META"):
        return None
    remote_addr = _valid_ip(request.META.get("REMOTE_ADDR"))
    trusted_proxies = settings.TRUSTED_PROXY_COUNT
    if trusted_proxies <= 0:
        return remote_addr
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    hops = [hop.strip() for hop in forwarded_for.split(",") if hop.strip()]
    # Menos saltos que proxies propios: la petición no pasó por todos, la cabecera no es confiable
    if len(hops) < trusted_proxies:
        return remote_addr
    return _valid_ip(hops[-trusted_proxies]) or remote_addr


def sanitize_changed_fields(changed_fields: Iterable[str] | None) -> list[str]:
    """Valida y deduplica nombres de campos modificados para la auditoría.

    Args:
        changed_fields: Colección de identificadores de campo.

    Returns:
        Lista sin duplicados que conserva el orden.

    Raises:
        TypeError: Si se entrega texto libre o un diccionario.
        ValueError: Si algún nombre no es un identificador válido (evita filtrar valores clínicos).
    """
    if changed_fields is None:
        return []
    if isinstance(changed_fields, (str, bytes, dict)):
        raise TypeError(
            "changed_fields debe ser una colección de nombres de campos, no un diccionario ni texto libre."
        )
    sanitized: list[str] = []
    for field_name in changed_fields:
        if not isinstance(field_name, str) or not _FIELD_NAME_RE.match(field_name):
            raise ValueError(
                f"Nombre de campo de auditoría inválido: {field_name!r}. Solo se permiten identificadores de campo."
            )
        if field_name not in sanitized:
            sanitized.append(field_name)
    return sanitized


def record_audit_event(
    *,
    action: str,
    resource_type: str,
    resource_id: str | int = "",
    actor_user: Any = None,
    actor_device_code: str = "",
    patient_id: int | None = None,
    changed_fields: Iterable[str] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """Registra un evento de auditoría guardando solo nombres de campos, nunca valores.

    Args:
        action: Acción (``AuditAction``).
        resource_type: Tipo de recurso afectado.
        resource_id: Identificador del recurso.
        actor_user: Usuario autor, si existe.
        actor_device_code: Código de la cuna cuando el autor es un dispositivo.
        patient_id: Paciente asociado, si aplica.
        changed_fields: Nombres de campos modificados.
        ip_address: IP de origen.

    Returns:
        El registro de auditoría creado.

    Raises:
        TypeError: Si ``changed_fields`` no es una colección de nombres.
        ValueError: Si algún nombre de campo es inválido.
    """
    validated_fields = sanitize_changed_fields(changed_fields)
    user_instance = (
        actor_user
        if actor_user is not None and getattr(actor_user, "is_authenticated", False)
        else None
    )
    return AuditLog.objects.create(
        actor_user=user_instance,
        actor_device_code=actor_device_code,
        patient_id=patient_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id != "" else "",
        changed_fields=validated_fields,
        ip_address=ip_address,
    )
