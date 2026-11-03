import re
from collections.abc import Iterable
from typing import Any

from .models import AuditLog

_FIELD_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def get_client_ip(request: Any) -> str | None:
    if request is None or not hasattr(request, "META"):
        return None
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def sanitize_changed_fields(changed_fields: Iterable[str] | None) -> list[str]:
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
