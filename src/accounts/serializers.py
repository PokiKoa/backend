from typing import ClassVar

from rest_framework import serializers

from .models import User, UserRole, WorkShift


class UserSerializer(serializers.ModelSerializer):
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


class UserCreateSerializer(serializers.Serializer):
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
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = UserSerializer()


class TokenRefreshRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class TokenRefreshResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class TwoFactorSetupResponseSerializer(serializers.Serializer):
    secret = serializers.CharField()
    provisioning_uri = serializers.CharField()


class TwoFactorCodeSerializer(serializers.Serializer):
    otp_code = serializers.CharField(min_length=6, max_length=6)
