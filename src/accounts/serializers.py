"""Serializers de cuentas: usuarios, sesión, 2FA y turnos."""

from typing import ClassVar

from rest_framework import serializers

from .models import ShiftAssignment, User, UserRole, WorkShift


class UserSerializer(serializers.ModelSerializer):
    """Representación de lectura de un usuario (excluye credenciales).
    Expone los datos demográficos, el rol RBAC, turno asignado y estados
    de seguridad (bloqueo por intentos fallidos y 2FA).
    """

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
    """Representación mínima de lectura de un miembro del personal.
    Diseñado para listados públicos o directorios internos donde no
    se requiere información sensible de seguridad.
    """

    class Meta:
        model = User
        fields: ClassVar[list[str]] = ["id", "full_name", "role", "shift"]
        read_only_fields = fields


class UserCreateSerializer(serializers.Serializer):
    """Validación de entrada para la creación de una cuenta por parte de un administrador.
    Exige una contraseña robusta y permite asignar el rol y turno inicial.
    """

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
    """Validación de entrada para la edición parcial de una cuenta.
    Todos los campos son opcionales. Incluye un flag 'unlock_account'
    para remover bloqueos de seguridad manuales.
    """

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
    """Validación de credenciales para el inicio de sesión.
    Acepta 'username' o 'email', junto con la contraseña.
    El 'otp_code' es requerido si el usuario tiene el 2FA habilitado.
    """

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
    """Estructura de respuesta tras un inicio de sesión exitoso (Access Token JWT y perfil)."""

    access = serializers.CharField()
    user = UserSerializer()


class TokenRefreshResponseSerializer(serializers.Serializer):
    """Estructura de respuesta para la renovación de sesión (Nuevo Access Token)."""

    access = serializers.CharField()


class ChangePasswordSerializer(serializers.Serializer):
    """Validación para el cambio de contraseña (requiere la contraseña actual para verificar)."""

    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)


class TwoFactorSetupResponseSerializer(serializers.Serializer):
    """Respuesta con los datos necesarios para enlazar una app autenticadora (ej. Google Authenticator)."""

    secret = serializers.CharField()
    provisioning_uri = serializers.CharField()


class TwoFactorCodeSerializer(serializers.Serializer):
    """Validación del código TOTP de 6 dígitos ingresado por el usuario."""

    otp_code = serializers.CharField(min_length=6, max_length=6)


class ShiftSerializer(serializers.Serializer):
    """Estructura de lectura para un turno del catálogo, incluyendo su bloque horario y estado actual."""

    value = serializers.ChoiceField(choices=WorkShift.choices)
    label = serializers.CharField()
    starts_at = serializers.TimeField(format="%H:%M")
    ends_at = serializers.TimeField(format="%H:%M")
    is_current = serializers.BooleanField()


class ShiftAssignmentSerializer(serializers.ModelSerializer):
    """Representación de lectura de una asignación de turno.
    Incluye datos desnormalizados (nombre, rol, código de cuna) para
    evitar peticiones adicionales desde el frontend.
    """

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
    """Validación de entrada para asignar un profesional a una cuna.
    Garantiza la presencia de identificadores válidos y un turno reconocido.
    """

    user_id = serializers.IntegerField(min_value=1)
    crib_id = serializers.IntegerField(min_value=1)
    date = serializers.DateField()
    shift = serializers.ChoiceField(choices=WorkShift.choices)
