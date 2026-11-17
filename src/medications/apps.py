"""Configuración de la aplicación Django para el módulo de medicamentos e indicaciones médicas."""

from django.apps import AppConfig


class MedicationsConfig(AppConfig):
    """Definición de metadatos y configuración base de la aplicación ``medications``."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "medications"
    verbose_name = "Catálogo de Medicamentos y Prescripciones"
