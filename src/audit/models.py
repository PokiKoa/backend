from typing import ClassVar

from django.conf import settings
from django.db import models


class AuditAction(models.TextChoices):
    READ = "read", "Lectura"
    CREATE = "create", "Creación"
    UPDATE = "update", "Actualización"
    DISCHARGE = "discharge", "Egreso clínico"
    ASSIGN_CRIB = "assign_crib", "Asignación de cuna"
    RELEASE_CRIB = "release_crib", "Liberación de cuna"
    SWAP_CRIB = "swap_crib", "Intercambio de cunas"
    DELETE = "delete", "Eliminación definitiva"
    INGEST_TELEMETRY = "ingest_telemetry", "Ingesta de telemetría"
    ACKNOWLEDGE_ALERT = "acknowledge_alert", "Reconocimiento de alerta"
    RESOLVE_ALERT = "resolve_alert", "Resolución de alerta"
    PRESCRIBE_MEDICATION = "prescribe_medication", "Indicación médica"
    ADMINISTER_MEDICATION = "administer_medication", "Administración de medicamento"
    LOGIN_SUCCESS = "login_success", "Inicio de sesión exitoso"
    LOGIN_FAILED = "login_failed", "Intento de inicio de sesión fallido"
    LOGOUT = "logout", "Cierre de sesión"
    ACCOUNT_LOCKED = "account_locked", "Bloqueo temporal de cuenta"


class AuditLog(models.Model):
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    actor_device_code = models.CharField(max_length=32, blank=True, default="")
    patient_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    action = models.CharField(
        max_length=32,
        choices=AuditAction.choices,
        db_index=True,
    )
    resource_type = models.CharField(max_length=50, db_index=True)
    resource_id = models.CharField(max_length=64, blank=True, default="")
    # Solo almacena nombres de campos modificados (lista de strings), nunca valores clínicos
    changed_fields = models.JSONField(default=list, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-timestamp", "-id"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["patient_id", "-timestamp"], name="audit_patient_ts_idx"),
            models.Index(fields=["actor_user", "-timestamp"], name="audit_actor_ts_idx"),
            models.Index(
                fields=["resource_type", "resource_id", "-timestamp"],
                name="audit_resource_ts_idx",
            ),
        ]
        verbose_name = "Registro de Auditoría"
        verbose_name_plural = "Registros de Auditoría"

    def __str__(self) -> str:
        actor = self.actor_user_id or self.actor_device_code or "anonymous"
        return f"[{self.action}] {self.resource_type}:{self.resource_id} by {actor}"
