"""Configuración del panel de administración para alertas clínicas y umbrales."""

from typing import ClassVar

from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    Alert,
    AlertSeverity,
    AlertStatus,
    AlertThresholdConfig,
    ResolutionReason,
)


@admin.register(AlertThresholdConfig)
class AlertThresholdConfigAdmin(admin.ModelAdmin):
    """Administración de los umbrales de alerta personalizados por paciente."""

    list_display: ClassVar[list[str]] = [
        "id",
        "patient",
        "heart_rate_critical_low",
        "heart_rate_warning_low",
        "heart_rate_warning_high",
        "heart_rate_critical_high",
        "spo2_critical_low",
        "spo2_warning_low",
        "temp_critical_low",
        "temp_critical_high",
        "updated_at",
    ]


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    """Administración y supervisión de registros de alertas clínicas activas e históricas."""

    list_display: ClassVar[list[str]] = [
        "id",
        "severity_badge",
        "status_badge",
        "alert_type",
        "crib",
        "patient",
        "message",
        "occurrence_count",
        "triggered_at",
    ]
    list_filter: ClassVar[list[str]] = [
        "status",
        "severity",
        "alert_type",
        "resolution_reason",
    ]
    search_fields: ClassVar[list[str]] = [
        "message",
        "crib__code",
        "patient__full_name",
    ]
    actions: ClassVar[list[str]] = ["mark_acknowledged", "mark_resolved"]

    @admin.display(description="Severidad")
    def severity_badge(self, obj: Alert) -> str:
        """
        Genera una etiqueta visual con código de colores según el nivel de severidad de la alerta.

        Args:
            obj: Instancia de la alerta clínica.

        Returns:
            str: Código HTML formateado con estilos inline para el badge de severidad.
        """
        colors = {
            AlertSeverity.CRITICAL: ("#fee2e2", "#991b1b"),
            AlertSeverity.WARNING: ("#fef3c7", "#92400e"),
            AlertSeverity.INFO: ("#e0f2fe", "#075985"),
        }
        bg, fg = colors.get(obj.severity, ("#f1f5f9", "#334155"))
        return format_html(
            '<span style="background:{};color:{};padding:3px 9px;border-radius:0.5rem;font-weight:700;font-size:0.75rem;">{}</span>',
            bg,
            fg,
            obj.get_severity_display().upper(),
        )

    @admin.display(description="Estado")
    def status_badge(self, obj: Alert) -> str:
        """
        Genera una etiqueta visual con código de colores según el estado actual de la alerta.

        Args:
            obj: Instancia de la alerta clínica.

        Returns:
            str: Código HTML formateado con estilos inline para el badge de estado.
        """
        colors = {
            AlertStatus.ACTIVE: ("#fee2e2", "#991b1b"),
            AlertStatus.ACKNOWLEDGED: ("#fef3c7", "#92400e"),
            AlertStatus.RESOLVED: ("#d1fae5", "#065f46"),
        }
        bg, fg = colors.get(obj.status, ("#f1f5f9", "#334155"))
        return format_html(
            '<span style="background:{};color:{};padding:3px 9px;border-radius:0.5rem;font-weight:700;font-size:0.75rem;">{}</span>',
            bg,
            fg,
            obj.get_status_display(),
        )

    @admin.action(description="Reconocer (acknowledge) alertas seleccionadas")
    def mark_acknowledged(self, request, queryset) -> None:
        """
        Acción administrativa masiva para marcar las alertas activas seleccionadas como reconocidas.

        Args:
            request: Petición HTTP del administrador.
            queryset: Conjunto de consultas con las alertas seleccionadas.
        """
        queryset.filter(status=AlertStatus.ACTIVE).update(
            status=AlertStatus.ACKNOWLEDGED,
            acknowledged_by=request.user,
            acknowledged_at=timezone.now(),
        )

    @admin.action(description="Resolver manualmente alertas seleccionadas")
    def mark_resolved(self, request, queryset) -> None:
        """
        Acción administrativa masiva para resolver manualmente las alertas seleccionadas.

        Args:
            request: Petición HTTP del administrador.
            queryset: Conjunto de consultas con las alertas seleccionadas.
        """
        queryset.exclude(status=AlertStatus.RESOLVED).update(
            status=AlertStatus.RESOLVED,
            resolved_by=request.user,
            resolved_at=timezone.now(),
            resolution_reason=ResolutionReason.MANUAL,
        )
