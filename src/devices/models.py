import hashlib
import hmac
import secrets
from typing import ClassVar

from django.db import models


class CribStatus(models.TextChoices):
    AVAILABLE = "available", "Disponible"
    OCCUPIED = "occupied", "Ocupada"
    MAINTENANCE = "maintenance", "En mantenimiento"
    OFFLINE = "offline", "Fuera de línea"


def generate_device_api_key() -> tuple[str, str, str]:
    prefix_token = secrets.token_hex(4)
    secret_token = secrets.token_hex(24)
    prefix = f"pk_dev_{prefix_token}"
    raw_key = f"{prefix}_{secret_token}"
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return raw_key, prefix, key_hash


def verify_device_api_key(raw_key: str, expected_hash: str) -> bool:
    if not raw_key or not expected_hash:
        return False
    candidate_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return hmac.compare_digest(candidate_hash, expected_hash)


class Crib(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100, blank=True, default="")
    location = models.CharField(max_length=100, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=CribStatus.choices,
        default=CribStatus.AVAILABLE,
        db_index=True,
    )
    api_key_prefix = models.CharField(max_length=20, db_index=True, blank=True, default="")
    api_key_hash = models.CharField(max_length=128, blank=True, default="")
    is_device_active = models.BooleanField(default=True, db_index=True)
    last_telemetry_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["code"]
        verbose_name = "Cuna"
        verbose_name_plural = "Cunas"

    def __str__(self) -> str:
        return f"{self.code} ({self.get_status_display()})"
