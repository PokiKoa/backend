"""Serializers de cuentas: usuarios, sesión, 2FA y turnos."""

from typing import ClassVar

from rest_framework import serializers

from .models import ShiftAssignment, User, UserRole, WorkShift


class UserSerializer(serializers.ModelSerializer):
    """Representación de un usuario (sin credenciales), con su estado de bloqueo y 2FA."""

    is_temporarily_locked = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields: ClassVar[list[str]] = [
            "id",
            "username",
            "email",
            "full_name",
            "role",
            "shift",
            "is_active",
            "is_two_factor_enabled",
            "is_temporarily_locked",
            "last_login",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class StaffMemberSerializer(serializers.ModelSerializer):
    """Datos públicos mínimos de un miembro del personal para el directorio."""

    class Meta:
        model = User
        fields: ClassVar[list[str]] = ["id", "full_name", "role", "shift"]
        read_only_fields = fields


class UserCreateSerializer(serializers.Serializer):
    """Entrada para que un administrador cree una cuenta."""

    username = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    full_name = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=10)
    role = serializers.ChoiceField(choices=UserRole.choices, default=UserRole.NURSE)
    shift = serializers.ChoiceField(
        choices=WorkShift.choices,
        required=False,
        allow_null=True,
        allow_blank=True,
    )
    is_active = serializers.BooleanField(default=True)


class UserUpdateSerializer(serializers.Serializer):
    """Entrada para que un administrador edite parcialmente una cuenta."""

    username = serializers.CharField(max_length=150, required=False)
    email = serializers.EmailField(required=False, allow_blank=True)
    full_name = serializers.CharField(max_length=150, required=False)
    password = serializers.CharField(write_only=True, min_length=10, required=False)
    role = serializers.ChoiceField(choices=UserRole.choices, required=False)
    shift = serializers.ChoiceField(
        choices=WorkShift.choices,
        required=False,
        allow_null=True,
        allow_blank=True,
    )
    is_active = serializers.BooleanField(required=False)
    unlock_account = serializers.BooleanField(required=False, default=False)


class LoginSerializer(serializers.Serializer):
    """Entrada de inicio de sesión: usuario o correo, contraseña y código 2FA opcional."""

    username = serializers.CharField(required=False, allow_blank=True)
    email = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    otp_code = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=6,
    )


class LoginResponseSerializer(serializers.Serializer):
    """Respuesta de inicio de sesión: access token y usuario."""

    access = serializers.CharField()
    user = UserSerializer()


class TokenRefreshResponseSerializer(serializers.Serializer):
    """Respuesta de renovación: nuevo access token."""

    access = serializers.CharField()


class ChangePasswordSerializer(serializers.Serializer):
    """Entrada para cambiar la contraseña propia."""

    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)


class TwoFactorSetupResponseSerializer(serializers.Serializer):
    """Respuesta de la configuración de 2FA: secreto y URI de aprovisionamiento."""

    secret = serializers.CharField()
    provisioning_uri = serializers.CharField()


class TwoFactorCodeSerializer(serializers.Serializer):
    """Entrada con el código TOTP de 6 dígitos."""

    otp_code = serializers.CharField(min_length=6, max_length=6)


class ShiftSerializer(serializers.Serializer):
    """Turno del catálogo con su horario e indicador de turno vigente."""

    value = serializers.ChoiceField(choices=WorkShift.choices)
    label = serializers.CharField()
    starts_at = serializers.TimeField(format="%H:%M")
    ends_at = serializers.TimeField(format="%H:%M")
    is_current = serializers.BooleanField()


class ShiftAssignmentSerializer(serializers.ModelSerializer):
    """Representación de una asignación de turno con el nombre y rol del profesional."""

    user_name = serializers.CharField(source="user.full_name", read_only=True)
    user_role = serializers.CharField(source="user.role", read_only=True)
    crib_code = serializers.CharField(source="crib.code", read_only=True)

    class Meta:
        model = ShiftAssignment
        fields: ClassVar[list[str]] = [
            "id",
            "user",
            "user_name",
            "user_role",
            "crib",
            "crib_code",
            "date",
            "shift",
            "created_by",
            "created_at",
        ]
        read_only_fields = fields


class ShiftAssignmentCreateSerializer(serializers.Serializer):
    """Entrada para asignar un profesional a una cuna en un turno."""

    user_id = serializers.IntegerField(min_value=1)
    crib_id = serializers.IntegerField(min_value=1)
    date = serializers.DateField()
    shift = serializers.ChoiceField(choices=WorkShift.choices)
