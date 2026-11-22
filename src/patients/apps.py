"""Configuración de la aplicación Django para el módulo de pacientes neonatales."""

from django.apps import AppConfig


class PatientsConfig(AppConfig):
    """Definición de metadatos y configuración base de la aplicación ``patients``."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "patients"
    verbose_name = "Pacientes Neonatales"
