"""Template tag que expone las estadísticas clínicas al panel de administración."""

from typing import Any

from django import template

from poki_koa.dashboard import get_clinical_dashboard_stats

register = template.Library()


@register.simple_tag
def clinical_dashboard_stats() -> dict[str, Any]:
    """Obtiene las métricas actuales del panel clínico para renderizarlas
    directamente en las plantillas HTML del administrador.

    Returns:
        dict[str, Any]: Un diccionario con los indicadores y estadísticas
        del dashboard (ej. cunas ocupadas, pacientes activos).
    """
    return get_clinical_dashboard_stats()
