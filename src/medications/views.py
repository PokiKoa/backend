from typing import ClassVar

import django_filters
from django.db import models
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from audit.services import get_client_ip

from .models import MedicationCatalogItem, Prescription
from .serializers import (
    MedicationCatalogCreateSerializer,
    MedicationCatalogItemSerializer,
    MedicationCatalogUpdateSerializer,
    PrescriptionAdministerSerializer,
    PrescriptionCancelSerializer,
    PrescriptionCreateSerializer,
    PrescriptionSerializer,
)
from .services import (
    administer_prescription,
    cancel_prescription,
    create_catalog_item,
    create_prescription,
    update_catalog_item,
)


class MedicationCatalogFilter(django_filters.FilterSet):
    low_stock = django_filters.BooleanFilter(method="filter_low_stock")

    class Meta:
        model = MedicationCatalogItem
        fields: ClassVar[list[str]] = ["is_active", "unit", "low_stock"]

    def filter_low_stock(self, queryset, name: str, value: bool):
        if value:
            return queryset.filter(stock__lte=models.F("min_stock_alert"))
        return queryset.filter(stock__gt=models.F("min_stock_alert"))


class MedicationCatalogViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = MedicationCatalogItem.objects.all().order_by("name")
    serializer_class = MedicationCatalogItemSerializer
    permission_classes: ClassVar[list] = [IsAuthenticated]
    filterset_class = MedicationCatalogFilter
    search_fields: ClassVar[list[str]] = ["name", "active_ingredient"]
    ordering_fields: ClassVar[list[str]] = [
        "name",
        "stock",
        "concentration_mg",
        "created_at",
    ]
    ordering: ClassVar[list[str]] = ["name"]

    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = MedicationCatalogCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = create_catalog_item(
            actor=request.user,
            name=serializer.validated_data["name"],
            active_ingredient=serializer.validated_data["active_ingredient"],
            concentration_mg=serializer.validated_data["concentration_mg"],
            unit=serializer.validated_data["unit"],
            stock=serializer.validated_data["stock"],
            min_stock_alert=serializer.validated_data["min_stock_alert"],
            is_active=serializer.validated_data["is_active"],
            ip_address=get_client_ip(request),
        )
        return Response(
            MedicationCatalogItemSerializer(item).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request: Request, *args, **kwargs) -> Response:
        item = self.get_object()
        serializer = MedicationCatalogUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = update_catalog_item(
            actor=request.user,
            item=item,
            data=serializer.validated_data,
            ip_address=get_client_ip(request),
        )
        return Response(
            MedicationCatalogItemSerializer(updated).data,
            status=status.HTTP_200_OK,
        )

    def partial_update(self, request: Request, *args, **kwargs) -> Response:
        return self.update(request, *args, **kwargs)


class PrescriptionViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = (
        Prescription.objects.select_related(
            "patient",
            "medication",
            "prescribed_by",
            "administered_by",
        )
        .all()
        .order_by("scheduled_time", "-id")
    )
    serializer_class = PrescriptionSerializer
    permission_classes: ClassVar[list] = [IsAuthenticated]
    filterset_fields: ClassVar[list[str]] = [
        "patient",
        "medication",
        "status",
        "route",
        "prescribed_by",
        "administered_by",
    ]
    search_fields: ClassVar[list[str]] = [
        "dose",
        "medication__name",
        "patient__full_name",
    ]
    ordering_fields: ClassVar[list[str]] = [
        "scheduled_time",
        "created_at",
        "administered_at",
        "status",
    ]
    ordering: ClassVar[list[str]] = ["scheduled_time", "-id"]

    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = PrescriptionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        prescription = create_prescription(
            actor=request.user,
            patient_id=serializer.validated_data["patient_id"],
            medication_id=serializer.validated_data["medication_id"],
            dose=serializer.validated_data["dose"],
            units_per_administration=serializer.validated_data[
                "units_per_administration"
            ],
            route=serializer.validated_data["route"],
            scheduled_time=serializer.validated_data["scheduled_time"],
            ip_address=get_client_ip(request),
        )
        return Response(
            PrescriptionSerializer(prescription).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="Administra atómicamente una indicación médica descontando stock del catálogo",
        request=PrescriptionAdministerSerializer,
        responses={200: PrescriptionSerializer},
    )
    @action(detail=True, methods=["post"], url_path="administer")
    def administer(self, request: Request, pk=None) -> Response:
        prescription = self.get_object()
        serializer = PrescriptionAdministerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = administer_prescription(
            actor=request.user,
            prescription=prescription,
            notes=serializer.validated_data.get("notes", ""),
            ip_address=get_client_ip(request),
        )
        return Response(
            PrescriptionSerializer(updated).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Cancela una indicación médica pendiente",
        request=PrescriptionCancelSerializer,
        responses={200: PrescriptionSerializer},
    )
    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request: Request, pk=None) -> Response:
        prescription = self.get_object()
        serializer = PrescriptionCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = cancel_prescription(
            actor=request.user,
            prescription=prescription,
            reason=serializer.validated_data.get("reason", ""),
            ip_address=get_client_ip(request),
        )
        return Response(
            PrescriptionSerializer(updated).data,
            status=status.HTTP_200_OK,
        )
