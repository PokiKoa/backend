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
    """Registra una nueva cuna aplicando Design by Contract (precondiciones, postcondiciones e invariantes).

    Preconditions:
        - El actor debe estar autenticado y tener rol de administrador.
        - El código de la cuna no puede estar vacío.
        - El estado inicial debe ser válido y no puede ser 'occupied'.

    Postconditions:
        - Se crea y persiste una instancia de Crib con sus credenciales de API Key.
        - Se registra el evento forense de auditoría correspondiente.
    """
    # --- Precondiciones ---
    assert actor is not None and getattr(actor, "is_authenticated", False), (
        "Precondición fallida: Actor no autenticado."
    )
    require_role(
        actor, ADMIN_ONLY, "Solo un administrador puede registrar nuevas cunas en el sistema."
    )
    normalized_code = (code or "").strip().upper()
    if len(normalized_code) == 0:
        raise DomainError("Precondición fallida: El código de cuna es obligatorio.")
    assert status in set(CribStatus.values), (
        "Precondición fallida: El estado operativo no es válido."
    )
    if status == CribStatus.OCCUPIED:
        raise DomainError("Precondición fallida: Una cuna nueva no puede crearse ocupada.")

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

    # --- Postcondiciones ---
    assert crib.pk is not None, "Postcondición fallida: La cuna no se persistió correctamente."
    assert crib.api_key_hash != "", (
        "Postcondición fallida: La cuna debe poseer un hash de API Key válido."
    )

    return crib, raw_key


def _normalize_crib_code(crib: Crib, value: Any) -> str:
    """Valida y normaliza el código de una cuna existente."""
    code = str(value).strip().upper()
    assert len(code) > 0, "Precondición fallida: El código normalizado no puede estar vacío."
    if code != crib.code and Crib.objects.filter(code=code).exclude(pk=crib.pk).exists():
        raise ConflictDomainError("Ya existe otra cuna con ese código.")
    return code


def _normalize_crib_status(crib: Crib, value: Any) -> str:
    """Valida las transiciones de estado de la cuna según su ocupación."""
    assert value in set(CribStatus.values), "Precondición fallida: Estado operativo inválido."
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
    """Actualiza parcialmente la configuración de una cuna aplicando Design by Contract.

    Preconditions:
        - El actor debe ser administrador autenticado.
        - La cuna y los datos a actualizar deben ser válidos.

    Postconditions:
        - Los cambios se persisten transaccionalmente y se auditan si hubo modificaciones.
    """
    # --- Precondiciones ---
    assert actor is not None and getattr(actor, "is_authenticated", False), (
        "Precondición fallida: Actor no autenticado."
    )
    require_role(
        actor, ADMIN_ONLY, "Solo un administrador puede modificar la configuración de una cuna."
    )
    assert crib is not None and crib.pk is not None, "Precondición fallida: La cuna debe existir."

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

    # --- Postcondiciones ---
    assert locked_crib is not None, (
        "Postcondición fallida: Objeto cuna corrupto tras la actualización."
    )
    return locked_crib


def rotate_crib_api_key(
    *,
    actor: User,
    crib: Crib,
    ip_address: str | None = None,
) -> str:
    """Rota la API Key de una cuna aplicando Design by Contract.

    Preconditions:
        - El actor debe ser administrador.
        - La cuna debe existir en la base de datos.

    Postconditions:
        - Se actualiza el hash de la API key de la cuna y se registra la auditoría.
    """
    # --- Precondiciones ---
    assert actor is not None and getattr(actor, "is_authenticated", False), (
        "Precondición fallida: Actor no autenticado."
    )
    require_role(actor, ADMIN_ONLY, "Solo un administrador puede rotar la API Key de una cuna.")
    assert crib is not None and crib.pk is not None, "Precondición fallida: La cuna debe existir."

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

    # --- Postcondiciones ---
    assert locked_crib.api_key_hash == key_hash, (
        "Postcondición fallida: El hash de la API key no se actualizó."
    )
    return raw_key


def detect_offline_cribs(*, timeout_seconds: int = 120) -> list[Crib]:
    """Detecta cunas desconectadas aplicando Design by Contract.

    Preconditions:
        - El umbral ``timeout_seconds`` debe ser al menos de 10 segundos.

    Postconditions:
        - Las cunas que superan el umbral pasan a estado OFFLINE y generan alertas de pérdida de señal.
    """
    # --- Precondiciones ---
    if timeout_seconds < 10:
        raise DomainError("Precondición fallida: El timeout debe ser de al menos 10 segundos.")

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

    # --- Postcondiciones ---
    for c in offline_cribs:
        assert c.status == CribStatus.OFFLINE, (
            "Postcondición fallida: La cuna detectada debe quedar en estado OFFLINE."
        )

    return offline_cribs