from typing import ClassVar

from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from audit.models import AuditAction
from audit.services import get_client_ip, record_audit_event

from .models import CarePlan, ClinicalObservation, Patient
from .serializers import (
    CarePlanCreateSerializer,
    CarePlanSerializer,
    CarePlanUpdateSerializer,
    ClinicalObservationCreateSerializer,
    ClinicalObservationSerializer,
    PatientCreateSerializer,
    PatientDischargeSerializer,
    PatientSerializer,
    PatientUpdateSerializer,
    WeightRecordCreateSerializer,
    WeightRecordSerializer,
)
from .services import (
    admit_patient,
    create_care_plan,
    create_clinical_observation,
    discharge_patient,
    record_patient_weight,
    update_care_plan,
    update_patient,
)


class PatientViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
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
    filterset_fields: ClassVar[list[str]] = [
        "status",
        "sex",
        "attending_physician",
        "crib",
    ]
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

    def create(self, request: Request, *args, **kwargs) -> Response:
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
            attending_physician_id=serializer.validated_data.get(
                "attending_physician_id"
            ),
            crib_id=serializer.validated_data.get("crib_id"),
            ip_address=get_client_ip(request),
        )
        return Response(
            PatientSerializer(patient).data, status=status.HTTP_201_CREATED
        )

    def update(self, request: Request, *args, **kwargs) -> Response:
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

    def partial_update(self, request: Request, *args, **kwargs) -> Response:
        return self.update(request, *args, **kwargs)

    @extend_schema(
        summary="Egresa lógicamente a un paciente conservando su historial y liberando su cuna",
        request=PatientDischargeSerializer,
        responses={200: PatientSerializer},
    )
    @action(detail=True, methods=["post"], url_path="discharge")
    def discharge(self, request: Request, pk=None) -> Response:
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


class CarePlanViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
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

    def create(self, request: Request, *args, **kwargs) -> Response:
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
        return Response(
            CarePlanSerializer(plan).data, status=status.HTTP_201_CREATED
        )

    def update(self, request: Request, *args, **kwargs) -> Response:
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

    def partial_update(self, request: Request, *args, **kwargs) -> Response:
        return self.update(request, *args, **kwargs)


class ClinicalObservationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
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

    def create(self, request: Request, *args, **kwargs) -> Response:
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
