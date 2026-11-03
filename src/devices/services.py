from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from accounts.models import User, UserRole
from alerts.services import trigger_or_deduplicate_offline_alert
from audit.models import AuditAction
from audit.services import record_audit_event
from poki_koa.exceptions import ConflictDomainError, DomainError, PermissionDomainError

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
    if actor.role != UserRole.ADMIN:
        raise PermissionDomainError(
            "Solo un administrador puede registrar nuevas cunas en el sistema."
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


def update_crib(
    *,
    actor: User,
    crib: Crib,
    data: dict[str, Any],
    ip_address: str | None = None,
) -> Crib:
    if actor.role != UserRole.ADMIN:
        raise PermissionDomainError(
            "Solo un administrador puede modificar la configuración de una cuna."
        )
    with transaction.atomic():
        locked_crib = Crib.objects.select_for_update().get(pk=crib.pk)
        changed_fields: list[str] = []

        has_patient = hasattr(locked_crib, "current_patient") and locked_crib.current_patient is not None

        if "code" in data:
            new_code = str(data["code"]).strip().upper()
            if not new_code:
                raise DomainError("El código de la cuna no puede estar vacío.")
            if new_code != locked_crib.code:
                if Crib.objects.filter(code=new_code).exclude(pk=locked_crib.pk).exists():
                    raise ConflictDomainError("Ya existe otra cuna con ese código.")
                locked_crib.code = new_code
                changed_fields.append("code")

        if "name" in data:
            new_name = str(data["name"]).strip()
            if new_name != locked_crib.name:
                locked_crib.name = new_name
                changed_fields.append("name")

        if "location" in data:
            new_location = str(data["location"]).strip()
            if new_location != locked_crib.location:
                locked_crib.location = new_location
                changed_fields.append("location")

        if "status" in data:
            new_status = data["status"]
            if new_status not in set(CribStatus.values):
                raise DomainError("El estado operativo de la cuna no es válido.")
            if has_patient and new_status != CribStatus.OCCUPIED:
                raise ConflictDomainError(
                    "No se puede cambiar el estado de una cuna con paciente asignado; libere o egrese primero al paciente."
                )
            if not has_patient and new_status == CribStatus.OCCUPIED:
                raise ConflictDomainError(
                    "No se puede marcar una cuna como ocupada sin asignarle un paciente."
                )
            if new_status != locked_crib.status:
                locked_crib.status = new_status
                changed_fields.append("status")

        if "is_device_active" in data:
            new_active = bool(data["is_device_active"])
            if new_active != locked_crib.is_device_active:
                locked_crib.is_device_active = new_active
                changed_fields.append("is_device_active")

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
    if actor.role != UserRole.ADMIN:
        raise PermissionDomainError(
            "Solo un administrador puede rotar la API Key de una cuna."
        )
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
