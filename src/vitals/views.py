"""Vistas de signos vitales: historial de lecturas y resumen operativo de la unidad."""

from typing import ClassVar

import django_filters
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import VitalSignReading
from .serializers import UnitOverviewSerializer, VitalSignReadingSerializer
from .services import build_unit_overview


class VitalSignReadingFilter(django_filters.FilterSet):
    """Filtros del historial de lecturas: cuna, paciente y rango de fechas."""

    recorded_after = django_filters.IsoDateTimeFilter(field_name="recorded_at", lookup_expr="gte")
    recorded_before = django_filters.IsoDateTimeFilter(field_name="recorded_at", lookup_expr="lte")

    class Meta:
        model = VitalSignReading
        fields: ClassVar[list[str]] = [
            "crib",
            "patient",
            "sleep_state",
            "cannula_connected",
            "iv_line_active",
            "recorded_after",
            "recorded_before",
        ]


class VitalSignReadingViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Historial de lecturas de signos vitales (solo lectura)."""

    queryset = (
        VitalSignReading.objects.select_related("crib", "patient")
        .all()
        .order_by("-recorded_at", "-id")
    )
    serializer_class = VitalSignReadingSerializer
    permission_classes: ClassVar[list] = [IsAuthenticated]
    filterset_class = VitalSignReadingFilter
    ordering_fields: ClassVar[list[str]] = [
        "recorded_at",
        "heart_rate",
        "spo2",
        "temperature",
    ]
    ordering: ClassVar[list[str]] = ["-recorded_at", "-id"]


class UnitOverviewView(APIView):
    """Panel de la unidad: cada cuna con su paciente, última lectura y alertas abiertas."""

    permission_classes: ClassVar[list] = [IsAuthenticated]

    @extend_schema(
        summary="Resumen de la unidad: cada cuna con su paciente, última lectura y alertas abiertas",
        responses={200: UnitOverviewSerializer},
    )
    def get(self, request: Request) -> Response:
        """Responde 200 con el resumen de todas las cunas de la unidad."""
        overview = build_unit_overview()
        return Response(UnitOverviewSerializer(overview).data, status=status.HTTP_200_OK)
