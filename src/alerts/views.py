from typing import ClassVar

from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.services import get_client_ip

from .models import Alert
from .serializers import (
    AlertSerializer,
    AlertThresholdConfigSerializer,
    AlertThresholdConfigUpdateSerializer,
)
from .services import (
    acknowledge_alert,
    get_effective_thresholds,
    resolve_alert,
    upsert_threshold_config,
)


class AlertViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = (
        Alert.objects.select_related(
            "crib",
            "patient",
            "acknowledged_by",
            "resolved_by",
        )
        .all()
        .order_by("-triggered_at", "-id")
    )
    serializer_class = AlertSerializer
    permission_classes: ClassVar[list] = [IsAuthenticated]
    filterset_fields: ClassVar[list[str]] = [
        "status",
        "severity",
        "alert_type",
        "crib",
        "patient",
    ]
    search_fields: ClassVar[list[str]] = ["message", "crib__code", "patient__full_name"]
    ordering_fields: ClassVar[list[str]] = [
        "triggered_at",
        "last_evaluated_at",
        "severity",
        "occurrence_count",
    ]
    ordering: ClassVar[list[str]] = ["-triggered_at", "-id"]

    @extend_schema(
        summary="Reconoce (acknowledge) una alerta clínica activa",
        request=None,
        responses={200: AlertSerializer},
    )
    @action(detail=True, methods=["post"], url_path="acknowledge")
    def acknowledge(self, request: Request, pk=None) -> Response:
        alert = self.get_object()
        updated = acknowledge_alert(
            actor=request.user,
            alert=alert,
            ip_address=get_client_ip(request),
        )
        return Response(AlertSerializer(updated).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Resuelve manualmente una alerta clínica",
        request=None,
        responses={200: AlertSerializer},
    )
    @action(detail=True, methods=["post"], url_path="resolve")
    def resolve(self, request: Request, pk=None) -> Response:
        alert = self.get_object()
        updated = resolve_alert(
            actor=request.user,
            alert=alert,
            ip_address=get_client_ip(request),
        )
        return Response(AlertSerializer(updated).data, status=status.HTTP_200_OK)


class DefaultAlertThresholdView(APIView):
    permission_classes: ClassVar[list] = [IsAuthenticated]

    @extend_schema(
        summary="Consulta los umbrales globales neonatales por defecto",
        responses={200: AlertThresholdConfigSerializer},
    )
    def get(self, request: Request) -> Response:
        config = get_effective_thresholds(patient=None)
        return Response(
            AlertThresholdConfigSerializer(config).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Actualiza los umbrales globales neonatales por defecto",
        request=AlertThresholdConfigUpdateSerializer,
        responses={200: AlertThresholdConfigSerializer},
    )
    def put(self, request: Request) -> Response:
        serializer = AlertThresholdConfigUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        config = upsert_threshold_config(
            actor=request.user,
            patient=None,
            data=serializer.validated_data,
            ip_address=get_client_ip(request),
        )
        return Response(
            AlertThresholdConfigSerializer(config).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Actualiza parcialmente los umbrales globales neonatales por defecto",
        request=AlertThresholdConfigUpdateSerializer,
        responses={200: AlertThresholdConfigSerializer},
    )
    def patch(self, request: Request) -> Response:
        return self.put(request)
