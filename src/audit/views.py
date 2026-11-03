from typing import ClassVar

import django_filters
from rest_framework import viewsets

from accounts.permissions import IsAdminRole

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogFilter(django_filters.FilterSet):
    timestamp_after = django_filters.IsoDateTimeFilter(
        field_name="timestamp", lookup_expr="gte"
    )
    timestamp_before = django_filters.IsoDateTimeFilter(
        field_name="timestamp", lookup_expr="lte"
    )

    class Meta:
        model = AuditLog
        fields: ClassVar[list[str]] = [
            "action",
            "resource_type",
            "resource_id",
            "patient_id",
            "actor_user",
            "timestamp_after",
            "timestamp_before",
        ]


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.select_related("actor_user").all()
    serializer_class = AuditLogSerializer
    permission_classes: ClassVar[list] = [IsAdminRole]
    filterset_class = AuditLogFilter
    search_fields: ClassVar[list[str]] = [
        "resource_type",
        "resource_id",
        "actor_user__email",
        "actor_user__full_name",
    ]
    ordering_fields: ClassVar[list[str]] = ["timestamp", "id"]
    ordering: ClassVar[list[str]] = ["-timestamp", "-id"]
