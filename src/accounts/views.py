"""Vistas de cuentas: sesión JWT (con refresh en cookie httpOnly), 2FA, usuarios y turnos."""

from typing import ClassVar

import django_filters
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.services import get_client_ip
from vitals.serializers import CribOverviewSerializer
from vitals.services import build_unit_overview

from .cookies import clear_refresh_cookie, read_refresh_cookie, set_refresh_cookie
from .models import SHIFT_HOURS, ShiftAssignment, User, WorkShift
from .permissions import IsAdminRole
from .serializers import (
    ChangePasswordSerializer,
    LoginResponseSerializer,
    LoginSerializer,
    ShiftAssignmentCreateSerializer,
    ShiftAssignmentSerializer,
    ShiftSerializer,
    StaffMemberSerializer,
    TokenRefreshResponseSerializer,
    TwoFactorCodeSerializer,
    TwoFactorSetupResponseSerializer,
    UserCreateSerializer,
    UserSerializer,
    UserUpdateSerializer,
)
from .services import (
    assigned_crib_ids,
    authenticate_user,
    change_own_password,
    create_shift_assignment,
    create_user_by_admin,
    current_shift,
    delete_shift_assignment,
    disable_two_factor,
    enable_two_factor,
    logout_user,
    rotate_refresh_token,
    setup_two_factor,
    update_user_by_admin,
)
from .throttling import LoginRateThrottle


class LoginView(APIView):
    """Inicio de sesión: entrega el access token y deja el refresh en una cookie httpOnly."""

    authentication_classes: ClassVar[list] = []
    permission_classes: ClassVar[list] = [AllowAny]
    throttle_classes: ClassVar[list] = [LoginRateThrottle]

    @extend_schema(
        summary="Inicia sesión; entrega el access token y deja el refresh en una cookie httpOnly",
        request=LoginSerializer,
        responses={200: LoginResponseSerializer},
    )
    def post(self, request: Request) -> Response:
        """Autentica con usuario/correo y contraseña (y código 2FA si aplica); responde 200 con el access token."""
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
    """Renueva la sesión rotando el refresh token guardado en la cookie."""

    authentication_classes: ClassVar[list] = []
    permission_classes: ClassVar[list] = [AllowAny]

    @extend_schema(
        summary="Rota el refresh token de la cookie httpOnly y entrega un nuevo access token",
        request=None,
        responses={200: TokenRefreshResponseSerializer},
    )
    def post(self, request: Request) -> Response:
        """Rota el refresh de la cookie y responde 200 con un nuevo access token; 400 si falta y 401 si es inválido."""
        tokens = rotate_refresh_token(refresh_token_str=read_refresh_cookie(request))
        response = Response({"access": tokens["access"]}, status=status.HTTP_200_OK)
        set_refresh_cookie(response, tokens["refresh"])
        return response


class LogoutView(APIView):
    """Cierre de sesión: revoca el refresh token y elimina la cookie."""

    permission_classes: ClassVar[list] = [IsAuthenticated]

    @extend_schema(
        summary="Cierra sesión revocando el refresh token de la cookie y eliminándola",
        request=None,
        responses={204: None},
    )
    def post(self, request: Request) -> Response:
        """Revoca el refresh de la cookie y responde 204 aunque la cookie esté ausente."""
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
    """Perfil del usuario autenticado."""

    permission_classes: ClassVar[list] = [IsAuthenticated]

    @extend_schema(
        summary="Retorna el perfil del usuario autenticado",
        responses={200: UserSerializer},
    )
    def get(self, request: Request) -> Response:
        """Responde 200 con los datos del usuario de la petición."""
        return Response(UserSerializer(request.user).data, status=status.HTTP_200_OK)


class ChangePasswordView(APIView):
    """Cambio de la contraseña propia."""

    permission_classes: ClassVar[list] = [IsAuthenticated]

    @extend_schema(
        summary="Cambia la contraseña propia, cierra las demás sesiones y renueva los tokens",
        request=ChangePasswordSerializer,
        responses={200: TokenRefreshResponseSerializer},
    )
    def post(self, request: Request) -> Response:
        """Cambia la contraseña, cierra las demás sesiones y responde 200 con tokens renovados; 400 si la actual es incorrecta."""
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tokens = change_own_password(
            user=request.user,
            current_password=serializer.validated_data["current_password"],
            new_password=serializer.validated_data["new_password"],
            ip_address=get_client_ip(request),
        )
        response = Response({"access": tokens["access"]}, status=status.HTTP_200_OK)
        set_refresh_cookie(response, tokens["refresh"])
        return response


class TwoFactorSetupView(APIView):
    """Paso 1 de 2FA: genera el secreto TOTP."""

    permission_classes: ClassVar[list] = [IsAuthenticated]

    @extend_schema(
        summary="Genera un nuevo secreto TOTP para configurar 2FA",
        request=None,
        responses={200: TwoFactorSetupResponseSerializer},
    )
    def post(self, request: Request) -> Response:
        """Responde 200 con el secreto y la URI de aprovisionamiento; 409 si 2FA ya está activo."""
        payload = setup_two_factor(
            user=request.user,
            ip_address=get_client_ip(request),
        )
        return Response(payload, status=status.HTTP_200_OK)


class TwoFactorEnableView(APIView):
    """Paso 2 de 2FA: confirma el código y activa la verificación en dos pasos."""

    permission_classes: ClassVar[list] = [IsAuthenticated]

    @extend_schema(
        summary="Verifica un código TOTP y activa 2FA en la cuenta actual",
        request=TwoFactorCodeSerializer,
        responses={200: UserSerializer},
    )
    def post(self, request: Request) -> Response:
        """Verifica el código TOTP y responde 200 con el usuario; 400 si el código es inválido."""
        serializer = TwoFactorCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = enable_two_factor(
            user=request.user,
            otp_code=serializer.validated_data["otp_code"],
            ip_address=get_client_ip(request),
        )
        return Response(UserSerializer(user).data, status=status.HTTP_200_OK)


class TwoFactorDisableView(APIView):
    """Desactiva la verificación en dos pasos."""

    permission_classes: ClassVar[list] = [IsAuthenticated]

    @extend_schema(
        summary="Verifica un código TOTP y desactiva 2FA en la cuenta actual",
        request=TwoFactorCodeSerializer,
        responses={200: UserSerializer},
    )
    def post(self, request: Request) -> Response:
        """Verifica el código TOTP y responde 200 con el usuario; 409 si 2FA no estaba activo."""
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
    """Gestión de cuentas de usuario (listar, ver, crear y editar) para administradores."""

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
        """Elige el serializer de creación, de edición o de lectura según la acción."""
        if self.action == "create":
            return UserCreateSerializer
        if self.action in {"update", "partial_update"}:
            return UserUpdateSerializer
        return UserSerializer

    @extend_schema(request=UserCreateSerializer, responses={201: UserSerializer})
    def create(self, request: Request, *args, **kwargs) -> Response:
        """Crea una cuenta y responde 201 con el usuario."""
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

    @extend_schema(request=UserUpdateSerializer, responses={200: UserSerializer})
    def update(self, request: Request, *args, **kwargs) -> Response:
        """Reemplaza campos de la cuenta y responde 200."""
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

    @extend_schema(request=UserUpdateSerializer, responses={200: UserSerializer})
    def partial_update(self, request: Request, *args, **kwargs) -> Response:
        """Actualiza parcialmente la cuenta (mismo flujo que ``update``)."""
        return self.update(request, *args, **kwargs)


class StaffDirectoryViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Directorio de personal activo, de solo lectura, para asignar turnos y responsables."""

    # Directorio mínimo para selectores clínicos (médico tratante, asignaciones) sin datos de cuenta
    queryset = User.objects.filter(is_active=True).order_by("full_name", "id")
    serializer_class = StaffMemberSerializer
    permission_classes: ClassVar[list] = [IsAuthenticated]
    filterset_fields: ClassVar[list[str]] = ["role", "shift"]
    search_fields: ClassVar[list[str]] = ["full_name"]
    ordering_fields: ClassVar[list[str]] = ["full_name"]


class MyShiftSerializer(serializers.Serializer):
    """Respuesta de ``mine``: día, turno vigente y cunas asignadas al usuario."""

    date = serializers.DateField()
    shift = serializers.ChoiceField(choices=WorkShift.choices)
    cribs = CribOverviewSerializer(many=True)


class ShiftCatalogView(APIView):
    """Catálogo fijo de turnos con su horario."""

    permission_classes: ClassVar[list] = [IsAuthenticated]

    @extend_schema(
        summary="Catálogo fijo de turnos con su horario e indicación del turno vigente",
        responses={200: ShiftSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        """Responde 200 con los turnos y marca cuál está vigente."""
        _, active = current_shift()
        shifts = [
            {
                "value": value,
                "label": label,
                "starts_at": SHIFT_HOURS[value][0],
                "ends_at": SHIFT_HOURS[value][1],
                "is_current": value == active,
            }
            for value, label in WorkShift.choices
        ]
        return Response(ShiftSerializer(shifts, many=True).data, status=status.HTTP_200_OK)


class ShiftAssignmentFilter(django_filters.FilterSet):
    """Filtros del listado de asignaciones de turno."""

    date_after = django_filters.DateFilter(field_name="date", lookup_expr="gte")
    date_before = django_filters.DateFilter(field_name="date", lookup_expr="lte")

    class Meta:
        model = ShiftAssignment
        fields: ClassVar[list[str]] = ["date", "shift", "user", "crib"]


class ShiftAssignmentViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Asignaciones de profesionales a cunas por día y turno."""

    queryset = ShiftAssignment.objects.select_related("user", "crib").all()
    serializer_class = ShiftAssignmentSerializer
    permission_classes: ClassVar[list] = [IsAuthenticated]
    filterset_class = ShiftAssignmentFilter
    ordering_fields: ClassVar[list[str]] = ["date", "shift"]

    @extend_schema(
        request=ShiftAssignmentCreateSerializer, responses={201: ShiftAssignmentSerializer}
    )
    def create(self, request: Request, *args, **kwargs) -> Response:
        """Asigna un profesional a una cuna y turno; responde 201."""
        serializer = ShiftAssignmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        assignment = create_shift_assignment(
            actor=request.user,
            user_id=data["user_id"],
            crib_id=data["crib_id"],
            day=data["date"],
            shift=data["shift"],
            ip_address=get_client_ip(request),
        )
        return Response(
            ShiftAssignmentSerializer(self.get_queryset().get(pk=assignment.pk)).data,
            status=status.HTTP_201_CREATED,
        )

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        """Elimina una asignación y responde 204."""
        delete_shift_assignment(
            actor=request.user,
            assignment=self.get_object(),
            ip_address=get_client_ip(request),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary="Cunas asignadas al usuario en el turno vigente, con su estado de monitoreo",
        responses={200: MyShiftSerializer},
    )
    @action(detail=False, methods=["get"], url_path="mine")
    def mine(self, request: Request) -> Response:
        """Responde 200 con las cunas asignadas al usuario en el turno vigente y su estado de monitoreo."""
        day, shift, crib_ids = assigned_crib_ids(user=request.user)
        overview = build_unit_overview(crib_ids=crib_ids)
        payload = {"date": day, "shift": shift, "cribs": overview.cribs}
        return Response(MyShiftSerializer(payload).data, status=status.HTTP_200_OK)
