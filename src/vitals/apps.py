"""Configuración de la aplicación Django para el módulo de signos vitales y telemetría."""

from django.apps import AppConfig


class VitalsConfig(AppConfig):
    """Define metadatos y configuración base de la app ``vitals``."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "vitals"
    verbose_name = "Signos Vitales y Telemetría"
