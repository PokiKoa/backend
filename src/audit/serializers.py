"""Serializer del registro de auditoría."""

from typing import ClassVar

from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    """Representación de solo lectura de un evento de auditoría."""

    actor_email = serializers.EmailField(source="actor_user.email", read_only=True, default=None)
    actor_name = serializers.CharField(source="actor_user.full_name", read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields: ClassVar[list[str]] = [
            "id",
            "actor_user",
            "actor_email",
            "actor_name",
            "actor_device_code",
            "patient_id",
            "action",
            "resource_type",
            "resource_id",
            "changed_fields",
            "ip_address",
            "timestamp",
        ]
        read_only_fields = fields
