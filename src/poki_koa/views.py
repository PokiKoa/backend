"""Vistas de infraestructura: portada con estadísticas y chequeo de salud del servicio."""

import json
import time
from typing import Any, ClassVar

from channels.layers import get_channel_layer
from django.conf import settings
from django.db import connection
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .dashboard import get_clinical_dashboard_stats


def root_dashboard_view(request: HttpRequest) -> HttpResponse:
    """Renderiza la portada HTML con estadísticas agregadas de la unidad.

    Args:
        request: Petición HTTP.

    Returns:
        Página ``poki_koa/home.html`` con el contexto del panel.
    """
    context = get_clinical_dashboard_stats()
    return render(request, "poki_koa/home.html", context)


def _build_health_payload() -> dict[str, Any]:
    start = time.perf_counter()
    connection.ensure_connection()
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    db_latency_ms = round((time.perf_counter() - start) * 1000, 2)

    channel_layer = get_channel_layer()
    channel_backend = channel_layer.__class__.__name__ if channel_layer is not None else "disabled"
    stats = get_clinical_dashboard_stats()

    return {
        "status": "ok",
        "version": "2.0.0",
        "database": "ok",
        "timezone": settings.TIME_ZONE,
        "timestamp": timezone.localtime().strftime("%Y-%m-%d %H:%M:%S %Z"),
        "components": {
            "database": {
                "status": "ok",
                "engine": connection.vendor,
                "latency_ms": db_latency_ms,
            },
            "realtime": {
                "status": "ok" if channel_layer is not None else "degraded",
                "backend": channel_backend,
            },
            "alert_engine": {
                "status": "ok",
            },
        },
        "metrics": {
            "active_patients": stats["active_patients_count"],
            "total_cribs": stats["total_cribs_count"],
            "occupied_cribs": stats["occupied_cribs_count"],
            "available_cribs": stats["available_cribs_count"],
            "open_alerts": stats["open_alerts_count"],
            "critical_alerts": stats["critical_alerts_count"],
            "pending_prescriptions": stats["pending_prescriptions_count"],
        },
    }


class HealthCheckView(APIView):
    """Chequeo de salud: base de datos, canal de tiempo real y métricas; público y sin autenticación."""

    authentication_classes: ClassVar[list] = []
    permission_classes: ClassVar[list] = [AllowAny]

    @extend_schema(
        summary="Verifica el estado operativo del servicio, base de datos, tiempo real y métricas",
        responses={
            200: inline_serializer(
                name="HealthCheckResponse",
                fields={
                    "status": serializers.CharField(),
                    "version": serializers.CharField(),
                    "database": serializers.CharField(),
                    "timezone": serializers.CharField(),
                    "timestamp": serializers.CharField(),
                    "components": serializers.DictField(),
                    "metrics": serializers.DictField(),
                },
            )
        },
    )
    def get(self, request: Request) -> HttpResponse:
        """Responde 200 con el estado del servicio en JSON, o en HTML si el cliente lo solicita."""
        payload = _build_health_payload()
        accept = request.META.get("HTTP_ACCEPT", "")
        wants_html = (
            request.query_params.get("format") != "json"
            and "text/html" in accept
            and "application/json" not in accept
        )
        if wants_html:
            return render(
                request._request,
                "poki_koa/health.html",
                {
                    "health": payload,
                    "health_json": json.dumps(payload, indent=2, ensure_ascii=False),
                },
            )
        return Response(payload, status=status.HTTP_200_OK)
