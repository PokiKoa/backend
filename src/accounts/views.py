from typing import ClassVar

from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.services import get_client_ip

from .cookies import clear_refresh_cookie, read_refresh_cookie, set_refresh_cookie
from .models import User
from .permissions import IsAdminRole
from .serializers import (
    LoginResponseSerializer,
    LoginSerializer,
    TokenRefreshResponseSerializer,
    TwoFactorCodeSerializer,
    TwoFactorSetupResponseSerializer,
    UserCreateSerializer,
    UserSerializer,
    UserUpdateSerializer,
)
from .services import (
    authenticate_user,
    create_user_by_admin,
    disable_two_factor,
    enable_two_factor,
    logout_user,
    rotate_refresh_token,
    setup_two_factor,
    update_user_by_admin,
)
from .throttling import LoginRateThrottle


class LoginView(APIView):
    authentication_classes: ClassVar[list] = []
    permission_classes: ClassVar[list] = [AllowAny]
    throttle_classes: ClassVar[list] = [LoginRateThrottle]

    @extend_schema(
        summary="Inicia sesión; entrega el access token y deja el refresh en una cookie httpOnly",
        request=LoginSerializer,
        responses={200: LoginResponseSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = authenticate_user(
            username=serializer.validated_data.get("username"),
            email=serializer.validated_data.get("email"),
            password=serializer.validated_data["password"],
            otp_code=serializer.validated_data.get("otp_code"),
            ip_address=get_client_ip(request),
        )
        response = Response(
            {
                "access": result["access"],
                "user": UserSerializer(result["user"]).data,
            },
            status=status.HTTP_200_OK,
        )
        set_refresh_cookie(response, result["refresh"])
        return response


class RefreshTokenView(APIView):
    authentication_classes: ClassVar[list] = []
    permission_classes: ClassVar[list] = [AllowAny]

    @extend_schema(
        summary="Rota el refresh token de la cookie httpOnly y entrega un nuevo access token",
        request=None,
        responses={200: TokenRefreshResponseSerializer},
    )
    def post(self, request: Request) -> Response:
        tokens = rotate_refresh_token(refresh_token_str=read_refresh_cookie(request))
        response = Response({"access": tokens["access"]}, status=status.HTTP_200_OK)
        set_refresh_cookie(response, tokens["refresh"])
        return response


class LogoutView(APIView):
    permission_classes: ClassVar[list] = [IsAuthenticated]

    @extend_schema(
        summary="Cierra sesión revocando el refresh token de la cookie y eliminándola",
        request=None,
        responses={204: None},
    )
    def post(self, request: Request) -> Response:
        refresh_token = read_refresh_cookie(request)
        # Sin cookie no hay sesión que revocar: cerrar sesión es idempotente
        if refresh_token:
            logout_user(
                refresh_token_str=refresh_token,
                actor=request.user,
                ip_address=get_client_ip(request),
            )
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_refresh_cookie(response)
        return response


class CurrentUserView(APIView):
    permission_classes: ClassVar[list] = [IsAuthenticated]

    @extend_schema(
        summary="Retorna el perfil del usuario autenticado",
        responses={200: UserSerializer},
    )
    def get(self, request: Request) -> Response:
        return Response(UserSerializer(request.user).data, status=status.HTTP_200_OK)


class TwoFactorSetupView(APIView):
    permission_classes: ClassVar[list] = [IsAuthenticated]

    @extend_schema(
        summary="Genera un nuevo secreto TOTP para configurar 2FA",
        request=None,
        responses={200: TwoFactorSetupResponseSerializer},
    )
    def post(self, request: Request) -> Response:
        payload = setup_two_factor(
            user=request.user,
            ip_address=get_client_ip(request),
        )
        return Response(payload, status=status.HTTP_200_OK)


class TwoFactorEnableView(APIView):
    permission_classes: ClassVar[list] = [IsAuthenticated]

    @extend_schema(
        summary="Verifica un código TOTP y activa 2FA en la cuenta actual",
        request=TwoFactorCodeSerializer,
        responses={200: UserSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = TwoFactorCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = enable_two_factor(
            user=request.user,
            otp_code=serializer.validated_data["otp_code"],
            ip_address=get_client_ip(request),
        )
        return Response(UserSerializer(user).data, status=status.HTTP_200_OK)


class TwoFactorDisableView(APIView):
    permission_classes: ClassVar[list] = [IsAuthenticated]

    @extend_schema(
        summary="Verifica un código TOTP y desactiva 2FA en la cuenta actual",
        request=TwoFactorCodeSerializer,
        responses={200: UserSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = TwoFactorCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = disable_two_factor(
            user=request.user,
            otp_code=serializer.validated_data["otp_code"],
            ip_address=get_client_ip(request),
        )
        return Response(UserSerializer(user).data, status=status.HTTP_200_OK)


class UserViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = User.objects.all().order_by("id")
    serializer_class = UserSerializer
    permission_classes: ClassVar[list] = [IsAdminRole]
    filterset_fields: ClassVar[list[str]] = ["role", "shift", "is_active"]
    search_fields: ClassVar[list[str]] = ["username", "full_name", "email"]
    ordering_fields: ClassVar[list[str]] = [
        "id",
        "username",
        "full_name",
        "email",
        "created_at",
    ]
    ordering: ClassVar[list[str]] = ["id"]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        if self.action in {"update", "partial_update"}:
            return UserUpdateSerializer
        return UserSerializer

    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = UserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = create_user_by_admin(
            actor=request.user,
            username=serializer.validated_data.get("username"),
            email=serializer.validated_data.get("email", ""),
            full_name=serializer.validated_data["full_name"],
            password=serializer.validated_data["password"],
            role=serializer.validated_data["role"],
            shift=serializer.validated_data.get("shift") or None,
            is_active=serializer.validated_data["is_active"],
            ip_address=get_client_ip(request),
        )
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)

    def update(self, request: Request, *args, **kwargs) -> Response:
        target_user = self.get_object()
        serializer = UserUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = update_user_by_admin(
            actor=request.user,
            target_user=target_user,
            data=serializer.validated_data,
            ip_address=get_client_ip(request),
        )
        return Response(UserSerializer(updated).data, status=status.HTTP_200_OK)

    def partial_update(self, request: Request, *args, **kwargs) -> Response:
        return self.update(request, *args, **kwargs)
