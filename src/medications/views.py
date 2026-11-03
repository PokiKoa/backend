from typing import ClassVar

import django_filters
from django.db import models
from django.db.models import Count, Max
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from audit.services import get_client_ip

from .models import MedicationCatalogItem, Prescription
from .serializers import (
    MedicationAdministrationSerializer,
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

    @extend_schema(request=MedicationCatalogCreateSerializer, responses={201: MedicationCatalogItemSerializer})
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

    @extend_schema(request=MedicationCatalogUpdateSerializer, responses={200: MedicationCatalogItemSerializer})
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

    @extend_schema(request=MedicationCatalogUpdateSerializer, responses={200: MedicationCatalogItemSerializer})
    def partial_update(self, request: Request, *args, **kwargs) -> Response:
        return self.update(request, *args, **kwargs)


class PrescriptionFilter(django_filters.FilterSet):
    starts_after = django_filters.IsoDateTimeFilter(field_name="starts_at", lookup_expr="gte")
    starts_before = django_filters.IsoDateTimeFilter(field_name="starts_at", lookup_expr="lte")
    is_recurring = django_filters.BooleanFilter(
        field_name="frequency_hours", lookup_expr="isnull", exclude=True
    )

    class Meta:
        model = Prescription
        fields: ClassVar[list[str]] = [
            "patient",
            "medication",
            "status",
            "route",
            "prescribed_by",
        ]


class PrescriptionViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = (
        Prescription.objects.select_related("patient", "medication", "prescribed_by")
        .annotate(
            last_administered_slot=Max("administrations__scheduled_for"),
            administrations_count=Count("administrations"),
        )
        .order_by("starts_at", "-id")
    )
    serializer_class = PrescriptionSerializer
    permission_classes: ClassVar[list] = [IsAuthenticated]
    filterset_class = PrescriptionFilter
    search_fields: ClassVar[list[str]] = [
        "dose",
        "medication__name",
        "patient__full_name",
    ]
    ordering_fields: ClassVar[list[str]] = [
        "starts_at",
        "created_at",
        "status",
    ]
    ordering: ClassVar[list[str]] = ["starts_at", "-id"]

    @extend_schema(request=PrescriptionCreateSerializer, responses={201: PrescriptionSerializer})
    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = PrescriptionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        prescription = create_prescription(
            actor=request.user,
            patient_id=data["patient_id"],
            medication_id=data["medication_id"],
            dose=data["dose"],
            units_per_administration=data["units_per_administration"],
            route=data["route"],
            starts_at=data["starts_at"],
            frequency_hours=data["frequency_hours"],
            ends_at=data["ends_at"],
            ip_address=get_client_ip(request),
        )
        return Response(
            PrescriptionSerializer(prescription).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="Registra la administración de una dosis descontando stock del catálogo",
        description=(
            "Sin scheduled_for se administra la dosis más reciente ya habilitada "
            "(se admite hasta 60 minutos antes de su horario). Con scheduled_for se "
            "registra una dosis específica, por ejemplo una atrasada."
        ),
        request=PrescriptionAdministerSerializer,
        responses={200: PrescriptionSerializer},
    )
    @action(detail=True, methods=["post"], url_path="administer")
    def administer(self, request: Request, pk=None) -> Response:
        prescription = self.get_object()
        serializer = PrescriptionAdministerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        administer_prescription(
            actor=request.user,
            prescription=prescription,
            scheduled_for=serializer.validated_data["scheduled_for"],
            notes=serializer.validated_data.get("notes", ""),
            ip_address=get_client_ip(request),
        )
        return Response(
            PrescriptionSerializer(self.get_queryset().get(pk=prescription.pk)).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Historial de dosis administradas de la indicación",
        responses={200: MedicationAdministrationSerializer(many=True)},
    )
    @action(detail=True, methods=["get"], url_path="administrations")
    def administrations(self, request: Request, pk=None) -> Response:
        prescription = self.get_object()
        qs = prescription.administrations.select_related("administered_by").order_by(
            "-scheduled_for", "-id"
        )
        page = self.paginate_queryset(qs)
        serializer = MedicationAdministrationSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        summary="Cancela una indicación médica vigente",
        request=PrescriptionCancelSerializer,
        responses={200: PrescriptionSerializer},
    )
    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request: Request, pk=None) -> Response:
        prescription = self.get_object()
        serializer = PrescriptionCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cancel_prescription(
            actor=request.user,
            prescription=prescription,
            reason=serializer.validated_data.get("reason", ""),
            ip_address=get_client_ip(request),
        )
        return Response(
            PrescriptionSerializer(self.get_queryset().get(pk=prescription.pk)).data,
            status=status.HTTP_200_OK,
        )
