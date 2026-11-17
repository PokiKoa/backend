"""Configuración de la aplicación de auditoría clínica."""

from django.apps import AppConfig


class AuditConfig(AppConfig):
    """Configuración del módulo de auditoría y trazabilidad forense."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "audit"
    verbose_name = "Auditoría Clínica"
