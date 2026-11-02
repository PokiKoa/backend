from typing import ClassVar

import django_filters
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from .models import VitalSignReading
from .serializers import VitalSignReadingSerializer


class VitalSignReadingFilter(django_filters.FilterSet):
    recorded_after = django_filters.IsoDateTimeFilter(
        field_name="recorded_at", lookup_expr="gte"
    )
    recorded_before = django_filters.IsoDateTimeFilter(
        field_name="recorded_at", lookup_expr="lte"
    )

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
