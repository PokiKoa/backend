"""Configuración de la aplicación de alertas clínicas."""

from django.apps import AppConfig


class AlertsConfig(AppConfig):
    """Configuración del módulo de alertas para el registro y gestión del motor clínico."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "alerts"
    verbose_name = "Motor de Alertas Clínicas"
