"""Configuración del panel de administración para las cunas (dispositivos IoT y estado operativo)."""

from typing import ClassVar

from django.contrib import admin, messages
from django.utils.html import format_html

from .models import Crib, CribStatus, generate_device_api_key


@admin.register(Crib)
class CribAdmin(admin.ModelAdmin):
    """Panel de administración para la gestión de cunas, control de dispositivos IoT y generación de API Keys."""

    list_display: ClassVar[list[str]] = [
        "code",
        "name",
        "location",
        "status_badge",
        "occupant_display",
        "is_device_active",
        "last_telemetry_at",
    ]
    list_filter: ClassVar[list[str]] = ["status", "is_device_active"]
    search_fields: ClassVar[list[str]] = ["code", "name", "location"]
    readonly_fields: ClassVar[list[str]] = [
        "api_key_prefix",
        "api_key_hash",
        "last_telemetry_at",
        "created_at",
        "updated_at",
    ]

    @admin.display(description="Estado Operativo")
    def status_badge(self, obj: Crib) -> str:
        """
        Genera un distintivo visual (badge) HTML coloreado según el estado operativo de la cuna.

        Args:
            obj: Instancia de la cuna.

        Returns:
            str: HTML renderizado con el badge de estado.
        """
        colors = {
            CribStatus.AVAILABLE: ("#d1fae5", "#065f46"),
            CribStatus.OCCUPIED: ("#e0f2fe", "#075985"),
            CribStatus.MAINTENANCE: ("#fef3c7", "#92400e"),
            CribStatus.OFFLINE: ("#fee2e2", "#991b1b"),
        }
        bg, fg = colors.get(obj.status, ("#f1f5f9", "#334155"))
        return format_html(
            '<span style="background:{};color:{};padding:3px 9px;border-radius:0.5rem;font-weight:700;font-size:0.76rem;">{}</span>',
            bg,
            fg,
            obj.get_status_display(),
        )

    @admin.display(description="Paciente Asignado")
    def occupant_display(self, obj: Crib) -> str:
        """
        Muestra el nombre y número de ficha médica del paciente asignado actualmente a la cuna.

        Args:
            obj: Instancia de la cuna.

        Returns:
            str: Nombre del paciente y ficha médica, o un guion si está desocupada.
        """
        patient = getattr(obj, "current_patient", None)
        if patient is None:
            return "—"
        return f"{patient.full_name} ({patient.medical_record_number})"

    def save_model(self, request, obj: Crib, form, change: bool) -> None:
        """
        Guarda el modelo de cuna asegurando el formato del código y generando una nueva API Key
        si el registro es nuevo y carece de hash de seguridad.

        Args:
            request: Petición HTTP de administración.
            obj: Instancia del modelo Crib.
            form: Formulario de administración.
            change: Booleano indicando si es una actualización (True) o creación (False).
        """
        obj.code = obj.code.strip().upper()
        if not obj.api_key_hash:
            raw_key, prefix, key_hash = generate_device_api_key()
            obj.api_key_prefix = prefix
            obj.api_key_hash = key_hash
            messages.info(
                request,
                f"API Key generada para la cuna {obj.code} (guárdela ahora): {raw_key}",
            )
        super().save_model(request, obj, form, change)
