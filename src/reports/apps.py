"""Configuración de la aplicación Django para el módulo de reportes clínicos."""

from django.apps import AppConfig


class ReportsConfig(AppConfig):
    """Define metadatos y configuración base de la app ``reports``."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "reports"
    verbose_name = "Reportes"
