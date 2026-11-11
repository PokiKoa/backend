"""Servicios de cunas/dispositivos: alta, configuración, rotación de API Key y detección de cunas sin señal."""

from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from accounts.models import User
from accounts.roles import ADMIN_ONLY, require_role
from alerts.services import trigger_or_deduplicate_offline_alert
from audit.models import AuditAction
from audit.services import record_audit_event
from poki_koa.exceptions import ConflictDomainError, DomainError

from .models import Crib, CribStatus, generate_device_api_key


def create_crib(
    *,
    actor: User,
    code: str,
    name: str = "",
    location: str = "",
    status: str = CribStatus.AVAILABLE,
    is_device_active: bool = True,
    ip_address: str | None = None,
) -> tuple[Crib, str]:
    """Registra una cuna y genera su API Key de dispositivo.

    Args:
        actor: Administrador.
        code: Código identificador único (se normaliza a mayúsculas).
        name: Nombre descriptivo.
        location: Ubicación física.
        status: Estado operativo inicial (no puede ser ``occupied``).
        is_device_active: Si el dispositivo puede enviar telemetría.
        ip_address: IP de origen para la auditoría.

    Returns:
        Tupla ``(cuna, api_key_en_claro)``; la clave solo se muestra en este momento.

    Raises:
        PermissionDomainError: Si el actor no es administrador.
        ConflictDomainError: Si el código ya existe.
        DomainError: Si el código está vacío o el estado es inválido.
    """
    require_role(
        actor, ADMIN_ONLY, "Solo un administrador puede registrar nuevas cunas en el sistema."
    )
    normalized_code = (code or "").strip().upper()
    if not normalized_code:
        raise DomainError("El código identificador de la cuna es obligatorio.")
    if status not in set(CribStatus.values):
        raise DomainError("El estado operativo de la cuna no es válido.")
    if status == CribStatus.OCCUPIED:
        raise DomainError(
            "Una cuna nueva no puede crearse directamente en estado ocupada sin paciente."
        )

    raw_key, prefix, key_hash = generate_device_api_key()

    with transaction.atomic():
        if Crib.objects.filter(code=normalized_code).exists():
            raise ConflictDomainError("Ya existe una cuna registrada con ese código.")

        crib = Crib.objects.create(
            code=normalized_code,
            name=(name or "").strip(),
            location=(location or "").strip(),
            status=status,
            api_key_prefix=prefix,
            api_key_hash=key_hash,
            is_device_active=is_device_active,
        )
        record_audit_event(
            action=AuditAction.CREATE,
            resource_type="crib",
            resource_id=crib.id,
            actor_user=actor,
            changed_fields=["code", "name", "location", "status", "is_device_active"],
            ip_address=ip_address,
        )
    return crib, raw_key


def _normalize_crib_code(crib: Crib, value: Any) -> str:
    code = str(value).strip().upper()
    if not code:
        raise DomainError("El código de la cuna no puede estar vacío.")
    if code != crib.code and Crib.objects.filter(code=code).exclude(pk=crib.pk).exists():
        raise ConflictDomainError("Ya existe otra cuna con ese código.")
    return code


def _normalize_crib_status(crib: Crib, value: Any) -> str:
    if value not in set(CribStatus.values):
        raise DomainError("El estado operativo de la cuna no es válido.")
    has_patient = hasattr(crib, "current_patient") and crib.current_patient is not None
    if has_patient and value != CribStatus.OCCUPIED:
        raise ConflictDomainError(
            "No se puede cambiar el estado de una cuna con paciente asignado; "
            "libere o egrese primero al paciente."
        )
    if not has_patient and value == CribStatus.OCCUPIED:
        raise ConflictDomainError(
            "No se puede marcar una cuna como ocupada sin asignarle un paciente."
        )
    return value


# Campos editables de una cuna. El orden define ``changed_fields`` en la auditoría.
_CRIB_EDITABLE_FIELDS = {
    "code": _normalize_crib_code,
    "name": lambda crib, value: str(value).strip(),
    "location": lambda crib, value: str(value).strip(),
    "status": _normalize_crib_status,
    "is_device_active": lambda crib, value: bool(value),
}


def update_crib(
    *,
    actor: User,
    crib: Crib,
    data: dict[str, Any],
    ip_address: str | None = None,
) -> Crib:
    """Actualiza parcialmente la configuración de una cuna y audita los campos modificados.

    Args:
        actor: Administrador que realiza el cambio.
        crib: Cuna a modificar; se relee con bloqueo de fila.
        data: Solo los campos a cambiar (``code``, ``name``, ``location``, ``status``,
            ``is_device_active``).
        ip_address: IP de origen para la auditoría.

    Returns:
        La cuna actualizada.

    Raises:
        PermissionDomainError: Si el actor no es administrador.
        ConflictDomainError: Código duplicado o estado incompatible con la ocupación.
        DomainError: Código vacío o estado operativo inválido.
    """
    require_role(
        actor, ADMIN_ONLY, "Solo un administrador puede modificar la configuración de una cuna."
    )
    with transaction.atomic():
        locked_crib = Crib.objects.select_for_update().get(pk=crib.pk)
        changed_fields: list[str] = []

        for field, normalize in _CRIB_EDITABLE_FIELDS.items():
            if field not in data:
                continue
            new_value = normalize(locked_crib, data[field])
            if new_value != getattr(locked_crib, field):
                setattr(locked_crib, field, new_value)
                changed_fields.append(field)

        if changed_fields:
            locked_crib.save()
            record_audit_event(
                action=AuditAction.UPDATE,
                resource_type="crib",
                resource_id=locked_crib.id,
                actor_user=actor,
                changed_fields=changed_fields,
                ip_address=ip_address,
            )
    return locked_crib


def rotate_crib_api_key(
    *,
    actor: User,
    crib: Crib,
    ip_address: str | None = None,
) -> str:
    """Rota la API Key de una cuna, invalidando la anterior.

    Args:
        actor: Administrador.
        crib: Cuna cuyo dispositivo recibirá una nueva clave.
        ip_address: IP de origen para la auditoría.

    Returns:
        La nueva API Key en claro (no se vuelve a poder consultar).

    Raises:
        PermissionDomainError: Si el actor no es administrador.
    """
    require_role(actor, ADMIN_ONLY, "Solo un administrador puede rotar la API Key de una cuna.")
    raw_key, prefix, key_hash = generate_device_api_key()
    with transaction.atomic():
        locked_crib = Crib.objects.select_for_update().get(pk=crib.pk)
        locked_crib.api_key_prefix = prefix
        locked_crib.api_key_hash = key_hash
        locked_crib.save(update_fields=["api_key_prefix", "api_key_hash", "updated_at"])
        record_audit_event(
            action=AuditAction.UPDATE,
            resource_type="crib",
            resource_id=locked_crib.id,
            actor_user=actor,
            changed_fields=["api_key_prefix", "api_key_hash"],
            ip_address=ip_address,
        )
    return raw_key


def detect_offline_cribs(*, timeout_seconds: int = 120) -> list[Crib]:
    """Detecta cunas activas sin telemetría reciente y dispara su alerta de pérdida de señal.

    Args:
        timeout_seconds: Segundos sin lecturas tras los cuales la cuna se considera desconectada (mínimo 10).

    Returns:
        Cunas detectadas como desconectadas.

    Raises:
        DomainError: Si ``timeout_seconds`` es menor que 10.
    """
    if timeout_seconds < 10:
        raise DomainError(
            "El umbral de inactividad para detectar cunas desconectadas debe ser de al menos 10 segundos."
        )

    cutoff = timezone.now() - timedelta(seconds=timeout_seconds)
    candidates = list(
        Crib.objects.filter(
            is_device_active=True,
            status__in=[CribStatus.OCCUPIED, CribStatus.AVAILABLE],
            last_telemetry_at__isnull=False,
            last_telemetry_at__lt=cutoff,
        ).order_by("id")
    )

    offline_cribs: list[Crib] = []
    for candidate in candidates:
        with transaction.atomic():
            locked_crib = Crib.objects.select_for_update().get(pk=candidate.pk)
            if (
                not locked_crib.is_device_active
                or locked_crib.status not in {CribStatus.OCCUPIED, CribStatus.AVAILABLE}
                or locked_crib.last_telemetry_at is None
                or locked_crib.last_telemetry_at >= cutoff
            ):
                continue

            current_patient = getattr(locked_crib, "current_patient", None)
            locked_crib.status = CribStatus.OFFLINE
            locked_crib.save(update_fields=["status", "updated_at"])

            trigger_or_deduplicate_offline_alert(
                crib=locked_crib,
                patient=current_patient,
                timeout_seconds=timeout_seconds,
            )
            offline_cribs.append(locked_crib)

    return offline_cribs
