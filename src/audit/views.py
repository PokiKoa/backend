"""Vistas de auditoría: consulta de solo lectura del registro de accesos y modificaciones."""

from typing import ClassVar

import django_filters
from django.db.models import Count
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.permissions import IsAdminRole

from .models import AuditAction, AuditLog
from .serializers import AuditLogSerializer


class AuditLogFilter(django_filters.FilterSet):
    """Filtros del registro de auditoría: acción, recurso, paciente, usuario y fechas."""

    timestamp_after = django_filters.IsoDateTimeFilter(field_name="timestamp", lookup_expr="gte")
    timestamp_before = django_filters.IsoDateTimeFilter(field_name="timestamp", lookup_expr="lte")

    class Meta:
        model = AuditLog
        fields: ClassVar[list[str]] = [
            "action",
            "resource_type",
            "resource_id",
            "patient_id",
            "actor_user",
            "timestamp_after",
            "timestamp_before",
        ]


class AuditActionCountSerializer(serializers.Serializer):
    """Conteo de eventos de auditoría por acción."""

    action = serializers.ChoiceField(choices=AuditAction.choices)
    total = serializers.IntegerField()


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Registro de auditoría de solo lectura (sin valores clínicos, solo nombres de campos)."""

    queryset = AuditLog.objects.select_related("actor_user").all()
    serializer_class = AuditLogSerializer
    permission_classes: ClassVar[list] = [IsAdminRole]
    filterset_class = AuditLogFilter
    search_fields: ClassVar[list[str]] = [
        "resource_type",
        "resource_id",
        "actor_user__email",
        "actor_user__full_name",
    ]
    ordering_fields: ClassVar[list[str]] = ["timestamp", "id"]
    ordering: ClassVar[list[str]] = ["-timestamp", "-id"]

    @extend_schema(
        summary="Conteo de eventos de auditoría por acción, con los mismos filtros del listado",
        responses={200: AuditActionCountSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="summary", pagination_class=None)
    def summary(self, request: Request) -> Response:
        """Responde 200 con el conteo de eventos por acción, con los mismos filtros del listado."""
        rows = (
            self.filter_queryset(self.get_queryset())
            .order_by()
            .values("action")
            .annotate(total=Count("id"))
            .order_by("-total", "action")
        )
        return Response(AuditActionCountSerializer(rows, many=True).data, status=status.HTTP_200_OK)
