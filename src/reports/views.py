from typing import ClassVar

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from poki_koa.exceptions import DomainError

from .serializers import ActivityPointSerializer, OperationsSummarySerializer
from .services import build_activity_series, build_operations_summary


class OperationsSummaryView(APIView):
    permission_classes: ClassVar[list] = [IsAuthenticated]

    @extend_schema(
        summary="Resumen operativo de la unidad: pacientes, cunas, medicación, alertas y personal",
        responses={200: OperationsSummarySerializer},
    )
    def get(self, request: Request) -> Response:
        return Response(
            OperationsSummarySerializer(build_operations_summary()).data,
            status=status.HTTP_200_OK,
        )


class ActivitySeriesView(APIView):
    permission_classes: ClassVar[list] = [IsAuthenticated]

    @extend_schema(
        summary="Serie diaria de ingresos y alertas (días locales)",
        parameters=[
            OpenApiParameter(
                "days", int, description="Días hacia atrás, de 1 a 90 (por defecto 14)."
            )
        ],
        responses={200: ActivityPointSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        try:
            days = int(request.query_params.get("days", 14))
        except ValueError as exc:
            raise DomainError("El parámetro days debe ser un número entero.") from exc
        return Response(
            ActivityPointSerializer(build_activity_series(days=days), many=True).data,
            status=status.HTTP_200_OK,
        )
