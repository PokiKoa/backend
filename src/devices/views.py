from typing import ClassVar

from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.models import UserRole
from accounts.permissions import IsAdminRole
from audit.services import get_client_ip
from poki_koa.exceptions import PermissionDomainError

from .models import Crib
from .serializers import (
    CribAssignPatientSerializer,
    CribCreateSerializer,
    CribSerializer,
    CribUpdateSerializer,
)
from .services import create_crib, rotate_crib_api_key, update_crib


class CribViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Crib.objects.select_related("current_patient").all().order_by("code")
    serializer_class = CribSerializer
    permission_classes: ClassVar[list] = [IsAuthenticated]
    filterset_fields: ClassVar[list[str]] = ["status", "is_device_active"]
    search_fields: ClassVar[list[str]] = ["code", "name", "location"]
    ordering_fields: ClassVar[list[str]] = ["code", "status", "last_telemetry_at", "created_at"]
    ordering: ClassVar[list[str]] = ["code"]

    def get_permissions(self):
        if self.action in {"create", "update", "partial_update", "rotate_key"}:
            return [IsAdminRole()]
        return [IsAuthenticated()]

    def create(self, request: Request, *args, **kwargs) -> Response:
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

    def update(self, request: Request, *args, **kwargs) -> Response:
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

    def partial_update(self, request: Request, *args, **kwargs) -> Response:
        return self.update(request, *args, **kwargs)

    @extend_schema(
        summary="Rota la API Key del dispositivo asociado a la cuna",
        request=None,
    )
    @action(detail=True, methods=["post"], url_path="rotate-key")
    def rotate_key(self, request: Request, pk=None) -> Response:
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
