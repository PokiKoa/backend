"""Vistas de cunas/dispositivos: configuración, asignación de pacientes, telemetría y detección de cunas sin señal."""

from typing import ClassVar

from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts.models import UserRole
from accounts.permissions import IsAdminRole
from audit.services import get_client_ip
from poki_koa.exceptions import PermissionDomainError

from .authentication import DeviceApiKeyAuthentication
from .models import Crib
from .serializers import (
    CribAssignPatientSerializer,
    CribCreateSerializer,
    CribSerializer,
    CribSwapSerializer,
    CribUpdateSerializer,
)
from .services import (
    create_crib,
    detect_offline_cribs,
    rotate_crib_api_key,
    update_crib,
)


class CribViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Cunas y su dispositivo de monitoreo: listado, detalle, configuración y acciones."""

    queryset = Crib.objects.select_related("current_patient").all().order_by("code")
    serializer_class = CribSerializer
    permission_classes: ClassVar[list] = [IsAuthenticated]
    # `code` exacto: lo usan los QR pegados en cada cuna para encontrarla
    filterset_fields: ClassVar[list[str]] = ["code", "status", "is_device_active"]
    search_fields: ClassVar[list[str]] = ["code", "name", "location"]
    ordering_fields: ClassVar[list[str]] = ["code", "status", "last_telemetry_at", "created_at"]
    ordering: ClassVar[list[str]] = ["code"]

    def get_permissions(self):
        """Exige rol administrador para crear, editar y rotar la clave; el resto solo autenticación."""
        if self.action in {"create", "update", "partial_update", "rotate_key"}:
            return [IsAdminRole()]
        return [IsAuthenticated()]

    @extend_schema(request=CribCreateSerializer, responses={201: CribSerializer})
    def create(self, request: Request, *args, **kwargs) -> Response:
        """Registra una cuna y responde 201 con la API Key en claro (solo esta vez)."""
        serializer = CribCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        crib, raw_api_key = create_crib(
            actor=request.user,
            code=serializer.validated_data["code"],
            name=serializer.validated_data.get("name", ""),
            location=serializer.validated_data.get("location", ""),
            status=serializer.validated_data["status"],
            is_device_active=serializer.validated_data["is_device_active"],
            ip_address=get_client_ip(request),
        )
        data = CribSerializer(crib).data
        data["api_key"] = raw_api_key
        return Response(data, status=status.HTTP_201_CREATED)

    @extend_schema(request=CribUpdateSerializer, responses={200: CribSerializer})
    def update(self, request: Request, *args, **kwargs) -> Response:
        """Actualiza la configuración de la cuna y responde 200."""
        crib = self.get_object()
        serializer = CribUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = update_crib(
            actor=request.user,
            crib=crib,
            data=serializer.validated_data,
            ip_address=get_client_ip(request),
        )
        updated.refresh_from_db()
        return Response(CribSerializer(updated).data, status=status.HTTP_200_OK)

    @extend_schema(request=CribUpdateSerializer, responses={200: CribSerializer})
    def partial_update(self, request: Request, *args, **kwargs) -> Response:
        """Actualiza parcialmente la cuna (mismo flujo que ``update``)."""
        return self.update(request, *args, **kwargs)

    @extend_schema(
        summary="Rota la API Key del dispositivo asociado a la cuna",
        request=None,
    )
    @action(detail=True, methods=["post"], url_path="rotate-key")
    def rotate_key(self, request: Request, pk=None) -> Response:
        """Rota la API Key del dispositivo y responde 200 con la nueva clave en claro."""
        crib = self.get_object()
        raw_api_key = rotate_crib_api_key(
            actor=request.user,
            crib=crib,
            ip_address=get_client_ip(request),
        )
        crib.refresh_from_db()
        return Response(
            {
                "crib_id": crib.id,
                "code": crib.code,
                "api_key_prefix": crib.api_key_prefix,
                "api_key": raw_api_key,
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Asigna un paciente activo a la cuna",
        request=CribAssignPatientSerializer,
        responses={200: CribSerializer},
    )
    @action(detail=True, methods=["post"], url_path="assign-patient")
    def assign_patient(self, request: Request, pk=None) -> Response:
        """Asigna un paciente activo a la cuna y responde 200 con la cuna."""
        if request.user.role not in {UserRole.ADMIN, UserRole.NEONATOLOGIST, UserRole.NURSE}:
            raise PermissionDomainError(
                "Solo el personal clínico o administrativo puede asignar pacientes a una cuna."
            )
        crib = self.get_object()
        serializer = CribAssignPatientSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from patients.services import assign_patient_to_crib

        updated_crib = assign_patient_to_crib(
            actor=request.user,
            crib=crib,
            patient_id=serializer.validated_data["patient_id"],
            ip_address=get_client_ip(request),
        )
        return Response(CribSerializer(updated_crib).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Libera la cuna desvinculando al paciente actual",
        request=None,
        responses={200: CribSerializer},
    )
    @action(detail=True, methods=["post"], url_path="release")
    def release(self, request: Request, pk=None) -> Response:
        """Libera la cuna desvinculando a su paciente y responde 200 con la cuna."""
        if request.user.role not in {UserRole.ADMIN, UserRole.NEONATOLOGIST, UserRole.NURSE}:
            raise PermissionDomainError(
                "Solo el personal clínico o administrativo puede liberar una cuna."
            )
        crib = self.get_object()

        from patients.services import release_patient_from_crib

        updated_crib = release_patient_from_crib(
            actor=request.user,
            crib=crib,
            ip_address=get_client_ip(request),
        )
        return Response(CribSerializer(updated_crib).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Intercambia a los pacientes de dos cunas ocupadas sin egresarlos",
        request=CribSwapSerializer,
        responses={200: CribSerializer(many=True)},
    )
    @action(detail=True, methods=["post"], url_path="swap")
    def swap(self, request: Request, pk=None) -> Response:
        """Intercambia los pacientes de dos cunas ocupadas sin egresarlos; responde 200."""
        crib = self.get_object()
        serializer = CribSwapSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from patients.services import swap_patients_between_cribs

        cribs = swap_patients_between_cribs(
            actor=request.user,
            crib=crib,
            other_crib_id=serializer.validated_data["other_crib_id"],
            ip_address=get_client_ip(request),
        )
        return Response(CribSerializer(list(cribs), many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Ingiere una lectura de telemetría o lista el historial de lecturas de la cuna",
    )
    @action(
        detail=True,
        methods=["get", "post"],
        url_path="telemetry",
        authentication_classes=[DeviceApiKeyAuthentication, JWTAuthentication],
        permission_classes=[IsAuthenticated],
    )
    def telemetry(self, request: Request, pk=None) -> Response:
        """GET lista el historial de lecturas de la cuna; POST ingiere una lectura (201) con API Key del dispositivo o sesión de personal."""
        from alerts.serializers import AlertSerializer
        from vitals.serializers import VitalSignReadingSerializer
        from vitals.services import ingest_telemetry
        from vitals.views import VitalSignReadingFilter

        crib = self.get_object()
        is_device = bool(getattr(request.user, "is_device", False))

        if request.method == "GET":
            if is_device:
                raise PermissionDomainError(
                    "Una credencial de dispositivo solo está autorizada para enviar telemetría."
                )
            qs = crib.vital_readings.select_related("crib", "patient").all()
            filtered_qs = VitalSignReadingFilter(request.query_params, queryset=qs).qs
            page = self.paginate_queryset(filtered_qs)
            if page is not None:
                serializer = VitalSignReadingSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            return Response(
                VitalSignReadingSerializer(filtered_qs, many=True).data,
                status=status.HTTP_200_OK,
            )

        if is_device and request.user.crib.id != crib.id:
            raise PermissionDomainError(
                "La API Key del dispositivo no corresponde a la cuna solicitada."
            )

        reading, evaluation = ingest_telemetry(
            crib=crib,
            payload=request.data if isinstance(request.data, dict) else {},
            actor_user=None if is_device else request.user,
            is_device_authenticated=is_device,
        )
        response_data = VitalSignReadingSerializer(reading).data
        response_data["active_alerts"] = AlertSerializer(
            evaluation.active_or_updated_alerts, many=True
        ).data
        response_data["auto_resolved_alerts"] = AlertSerializer(
            evaluation.auto_resolved_alerts, many=True
        ).data
        return Response(response_data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Evalúa y marca como offline las cunas activas que superaron el tiempo sin telemetría",
        request=None,
    )
    @action(detail=False, methods=["post"], url_path="check-offline")
    def check_offline(self, request: Request) -> Response:
        """Marca como offline las cunas activas sin telemetría reciente y responde 200 con las detectadas."""
        if request.user.role not in {
            UserRole.ADMIN,
            UserRole.NEONATOLOGIST,
            UserRole.NURSE,
        }:
            raise PermissionDomainError(
                "Solo el personal clínico o administrativo puede ejecutar la verificación de cunas desconectadas."
            )
        raw_timeout = (
            request.data.get("timeout_seconds", 120) if isinstance(request.data, dict) else 120
        )
        try:
            timeout_seconds = int(raw_timeout)
        except (TypeError, ValueError):
            timeout_seconds = 120

        offline_cribs = detect_offline_cribs(timeout_seconds=timeout_seconds)
        return Response(
            {
                "timeout_seconds": timeout_seconds,
                "transitioned_count": len(offline_cribs),
                "cribs": CribSerializer(offline_cribs, many=True).data,
            },
            status=status.HTTP_200_OK,
        )
