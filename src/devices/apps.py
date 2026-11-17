"""Configuración de la aplicación de dispositivos y cunas (IoT)."""

from django.apps import AppConfig


class DevicesConfig(AppConfig):
    """Configuración del módulo de gestión de cunas y dispositivos de telemetría."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "devices"
    verbose_name = "Cunas y Dispositivos"
