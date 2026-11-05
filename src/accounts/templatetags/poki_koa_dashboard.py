"""Template tag que expone las estadísticas clínicas al panel de administración."""

from typing import Any

from django import template

from poki_koa.dashboard import get_clinical_dashboard_stats

register = template.Library()


@register.simple_tag
def clinical_dashboard_stats() -> dict[str, Any]:
    """Devuelve las estadísticas del panel clínico para usarlas en plantillas."""
    return get_clinical_dashboard_stats()
