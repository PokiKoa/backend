from typing import Any

from django import template

from poki_koa.dashboard import get_clinical_dashboard_stats

register = template.Library()


@register.simple_tag
def clinical_dashboard_stats() -> dict[str, Any]:
    return get_clinical_dashboard_stats()
