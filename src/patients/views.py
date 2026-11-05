"""Vistas de pacientes: ficha, egreso, peso, cunas, signos vitales, planes de cuidado y observaciones."""

from typing import ClassVar

import django_filters
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from audit.models import AuditAction
from audit.services import get_client_ip, record_audit_event

from .models import CarePlan, ClinicalObservation, Patient, PatientStatus
from .serializers import (
    CarePlanCreateSerializer,
    CarePlanSerializer,
    CarePlanUpdateSerializer,
    ClinicalObservationCreateSerializer,
    ClinicalObservationSerializer,
    CribMovementSerializer,
    PatientCreateSerializer,
    PatientDischargeSerializer,
    PatientPermanentDeleteSerializer,
    PatientSerializer,
    PatientUpdateSerializer,
    WeightRecordCreateSerializer,
    WeightRecordSerializer,
)
from .services import (
    GUARDIAN_FIELDS,
    admit_patient,
    create_care_plan,
    create_clinical_observation,
    delete_patient_permanently,
    discharge_patient,
    record_patient_weight,
    update_care_plan,
    update_patient,
)


class PatientFilter(django_filters.FilterSet):
    """Filtros del listado de pacientes: estado, sexo, médico, cuna, fecha de ingreso, peso y ``active``."""

    admitted_after = django_filters.IsoDateTimeFilter(field_name="admitted_at", lookup_expr="gte")
    admitted_before = django_filters.IsoDateTimeFilter(field_name="admitted_at", lookup_expr="lte")
    min_weight_g = django_filters.NumberFilter(field_name="current_weight_g", lookup_expr="gte")
    max_weight_g = django_filters.NumberFilter(field_name="current_weight_g", lookup_expr="lte")
    active = django_filters.BooleanFilter(
        method="filter_active",
        help_text="true: pacientes en la unidad; false: egresados, trasladados o fallecidos.",
    )

    def filter_active(self, queryset, name, value):
        """``active=true`` devuelve pacientes en la unidad; ``false``, los egresados, trasladados o fallecidos."""
        if value:
            return queryset.filter(status=PatientStatus.ACTIVE)
        return queryset.exclude(status=PatientStatus.ACTIVE)

    class Meta:
        model = Patient
        fields: ClassVar[list[str]] = [
            "status",
            "sex",
            "attending_physician",
            "crib",
            "admitted_after",
            "admitted_before",
            "min_weight_g",
            "max_weight_g",
            "active",
        ]


class PatientViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Ficha clínica de pacientes: listado, detalle, ingreso, edición y acciones asociadas (egreso, pesos, cunas, vitales, umbrales)."""

    queryset = (
        Patient.objects.select_related(
            "attending_physician",
            "crib",
            "discharged_by",
        )
        .all()
        .order_by("-admitted_at", "-id")
    )
    serializer_class = PatientSerializer
    permission_classes: ClassVar[list] = [IsAuthenticated]
    filterset_class = PatientFilter
    search_fields: ClassVar[list[str]] = ["full_name", "medical_record_number"]
    ordering_fields: ClassVar[list[str]] = [
        "admitted_at",
        "full_name",
        "birth_date",
        "current_weight_g",
        "gestational_age_weeks",
    ]
    ordering: ClassVar[list[str]] = ["-admitted_at", "-id"]

    def retrieve(self, request: Request, *args, **kwargs) -> Response:
        """Responde 200 con el paciente y registra el acceso de lectura en la auditoría."""
        patient = self.get_object()
        record_audit_event(
            action=AuditAction.READ,
            resource_type="patient",
            resource_id=patient.id,
            actor_user=request.user,
            patient_id=patient.id,
            changed_fields=[],
            ip_address=get_client_ip(request),
        )
        return Response(PatientSerializer(patient).data, status=status.HTTP_200_OK)

    @extend_schema(request=PatientCreateSerializer, responses={201: PatientSerializer})
    def create(self, request: Request, *args, **kwargs) -> Response:
        """Ingresa un paciente y responde 201."""
        serializer = PatientCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        patient = admit_patient(
            actor=request.user,
            medical_record_number=serializer.validated_data["medical_record_number"],
            full_name=serializer.validated_data["full_name"],
            sex=serializer.validated_data["sex"],
            birth_date=serializer.validated_data["birth_date"],
            gestational_age_weeks=serializer.validated_data["gestational_age_weeks"],
            birth_weight_g=serializer.validated_data["birth_weight_g"],
            current_weight_g=serializer.validated_data.get("current_weight_g"),
            diagnosis=serializer.validated_data.get("diagnosis", ""),
            attending_physician_id=serializer.validated_data.get("attending_physician_id"),
            crib_id=serializer.validated_data.get("crib_id"),
            guardians={
                field: serializer.validated_data[field]
                for field in GUARDIAN_FIELDS
                if field in serializer.validated_data
            },
            ip_address=get_client_ip(request),
        )
        return Response(PatientSerializer(patient).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=PatientUpdateSerializer, responses={200: PatientSerializer})
    def update(self, request: Request, *args, **kwargs) -> Response:
        """Actualiza datos del paciente y responde 200."""
        patient = self.get_object()
        serializer = PatientUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = update_patient(
            actor=request.user,
            patient=patient,
            data=serializer.validated_data,
            ip_address=get_client_ip(request),
        )
        return Response(PatientSerializer(updated).data, status=status.HTTP_200_OK)

    @extend_schema(request=PatientUpdateSerializer, responses={200: PatientSerializer})
    def partial_update(self, request: Request, *args, **kwargs) -> Response:
        """Actualiza parcialmente al paciente (mismo flujo que ``update``)."""
        return self.update(request, *args, **kwargs)

    @extend_schema(
        summary="Elimina definitivamente al paciente y todo su registro clínico (solo Administrador)",
        request=PatientPermanentDeleteSerializer,
        responses={204: None},
    )
    @action(detail=True, methods=["post"], url_path="delete-permanently")
    def delete_permanently(self, request: Request, pk=None) -> Response:
        """Elimina definitivamente al paciente y su registro clínico (solo Administrador); responde 204."""
        patient = self.get_object()
        serializer = PatientPermanentDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        delete_patient_permanently(
            actor=request.user,
            patient=patient,
            confirmation=serializer.validated_data["confirmation"],
            ip_address=get_client_ip(request),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary="Historial de cunas del paciente: asignaciones, traslados, intercambios y liberaciones",
        responses={200: CribMovementSerializer(many=True)},
    )
    @action(detail=True, methods=["get"], url_path="crib-movements", pagination_class=None)
    def crib_movements(self, request: Request, pk=None) -> Response:
        """Responde 200 con el historial de asignaciones, traslados, intercambios y liberaciones de cuna."""
        patient = self.get_object()
        movements = patient.crib_movements.select_related("moved_by").all()
        return Response(CribMovementSerializer(movements, many=True).data)

    @extend_schema(
        summary="Egresa lógicamente a un paciente conservando su historial y liberando su cuna",
        request=PatientDischargeSerializer,
        responses={200: PatientSerializer},
    )
    @action(detail=True, methods=["post"], url_path="discharge")
    def discharge(self, request: Request, pk=None) -> Response:
        """Egresa al paciente (alta, traslado o fallecimiento); responde 200 con el paciente."""
        patient = self.get_object()
        serializer = PatientDischargeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        discharged = discharge_patient(
            actor=request.user,
            patient=patient,
            outcome=serializer.validated_data["outcome"],
            cause=serializer.validated_data.get("cause"),
            notes=serializer.validated_data.get("notes", ""),
            ip_address=get_client_ip(request),
        )
        return Response(PatientSerializer(discharged).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Lista la curva ponderal o registra una nueva medición de peso del paciente",
        request=WeightRecordCreateSerializer,
        responses={200: WeightRecordSerializer(many=True), 201: WeightRecordSerializer},
    )
    @action(detail=True, methods=["get", "post"], url_path="weights")
    def weights(self, request: Request, pk=None) -> Response:
        """GET lista la curva ponderal; POST registra una medición de peso (201)."""
        patient = self.get_object()
        if request.method == "GET":
            qs = patient.weight_records.select_related("recorded_by").all()
            page = self.paginate_queryset(qs)
            if page is not None:
                serializer = WeightRecordSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            return Response(
                WeightRecordSerializer(qs, many=True).data,
                status=status.HTTP_200_OK,
            )

        serializer = WeightRecordCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        weight_record = record_patient_weight(
            actor=request.user,
            patient=patient,
            weight_g=serializer.validated_data["weight_g"],
            ip_address=get_client_ip(request),
        )
        return Response(
            WeightRecordSerializer(weight_record).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="Lista el historial de signos vitales registrados para el paciente",
    )
    @action(detail=True, methods=["get"], url_path="vitals")
    def vitals(self, request: Request, pk=None) -> Response:
        """Responde 200 con el historial paginado de signos vitales del paciente."""
        from vitals.serializers import VitalSignReadingSerializer
        from vitals.views import VitalSignReadingFilter

        patient = self.get_object()
        qs = patient.vital_readings.select_related("crib", "patient").all()
        filtered_qs = VitalSignReadingFilter(request.query_params, queryset=qs).qs
        page = self.paginate_queryset(filtered_qs)
        if page is not None:
            serializer = VitalSignReadingSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        return Response(
            VitalSignReadingSerializer(filtered_qs, many=True).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Consulta o personaliza los umbrales de alerta clínica para el paciente",
    )
    @action(detail=True, methods=["get", "put", "patch"], url_path="alert-thresholds")
    def alert_thresholds(self, request: Request, pk=None) -> Response:
        """GET consulta los umbrales efectivos; PUT/PATCH los personalizan para el paciente."""
        from alerts.serializers import (
            AlertThresholdConfigSerializer,
            AlertThresholdConfigUpdateSerializer,
        )
        from alerts.services import get_effective_thresholds, upsert_threshold_config

        patient = self.get_object()
        if request.method == "GET":
            config = get_effective_thresholds(patient=patient)
            return Response(
                AlertThresholdConfigSerializer(config).data,
                status=status.HTTP_200_OK,
            )

        serializer = AlertThresholdConfigUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        config = upsert_threshold_config(
            actor=request.user,
            patient=patient,
            data=serializer.validated_data,
            ip_address=get_client_ip(request),
        )
        return Response(
            AlertThresholdConfigSerializer(config).data,
            status=status.HTTP_200_OK,
        )


class CarePlanViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Planes de cuidado de pacientes (listar, ver, crear y editar)."""

    queryset = (
        CarePlan.objects.select_related("patient", "created_by")
        .all()
        .order_by("-created_at", "-id")
    )
    serializer_class = CarePlanSerializer
    permission_classes: ClassVar[list] = [IsAuthenticated]
    filterset_fields: ClassVar[list[str]] = ["patient", "status", "care_area"]
    search_fields: ClassVar[list[str]] = ["care_area", "intervention"]
    ordering_fields: ClassVar[list[str]] = ["created_at", "updated_at", "status"]
    ordering: ClassVar[list[str]] = ["-created_at", "-id"]

    @extend_schema(request=CarePlanCreateSerializer, responses={201: CarePlanSerializer})
    def create(self, request: Request, *args, **kwargs) -> Response:
        """Crea un plan de cuidado y responde 201."""
        serializer = CarePlanCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = create_care_plan(
            actor=request.user,
            patient_id=serializer.validated_data["patient_id"],
            care_area=serializer.validated_data["care_area"],
            intervention=serializer.validated_data["intervention"],
            frequency=serializer.validated_data["frequency"],
            status=serializer.validated_data["status"],
            ip_address=get_client_ip(request),
        )
        return Response(CarePlanSerializer(plan).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=CarePlanUpdateSerializer, responses={200: CarePlanSerializer})
    def update(self, request: Request, *args, **kwargs) -> Response:
        """Actualiza un plan de cuidado y responde 200."""
        plan = self.get_object()
        serializer = CarePlanUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = update_care_plan(
            actor=request.user,
            care_plan=plan,
            data=serializer.validated_data,
            ip_address=get_client_ip(request),
        )
        return Response(CarePlanSerializer(updated).data, status=status.HTTP_200_OK)

    @extend_schema(request=CarePlanUpdateSerializer, responses={200: CarePlanSerializer})
    def partial_update(self, request: Request, *args, **kwargs) -> Response:
        """Actualiza parcialmente un plan (mismo flujo que ``update``)."""
        return self.update(request, *args, **kwargs)


class ClinicalObservationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """Observaciones clínicas de pacientes (listar, ver y crear)."""

    queryset = (
        ClinicalObservation.objects.select_related("patient", "author")
        .all()
        .order_by("-created_at", "-id")
    )
    serializer_class = ClinicalObservationSerializer
    permission_classes: ClassVar[list] = [IsAuthenticated]
    filterset_fields: ClassVar[list[str]] = ["patient", "category", "author"]
    search_fields: ClassVar[list[str]] = ["content"]
    ordering_fields: ClassVar[list[str]] = ["created_at", "category"]
    ordering: ClassVar[list[str]] = ["-created_at", "-id"]

    @extend_schema(
        request=ClinicalObservationCreateSerializer, responses={201: ClinicalObservationSerializer}
    )
    def create(self, request: Request, *args, **kwargs) -> Response:
        """Registra una observación clínica y responde 201."""
        serializer = ClinicalObservationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        observation = create_clinical_observation(
            actor=request.user,
            patient_id=serializer.validated_data["patient_id"],
            category=serializer.validated_data["category"],
            content=serializer.validated_data["content"],
            ip_address=get_client_ip(request),
        )
        return Response(
            ClinicalObservationSerializer(observation).data,
            status=status.HTTP_201_CREATED,
        )
