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
    """Endpoint para el inicio de sesión y emisión de credenciales JWT."""

    authentication_classes: ClassVar[list] = []
    permission_classes: ClassVar[list] = [AllowAny]
    throttle_classes: ClassVar[list] = [LoginRateThrottle]

    @extend_schema(
        summary="Inicia sesión; entrega el access token y deja el refresh en una cookie httpOnly",
        request=LoginSerializer,
        responses={200: LoginResponseSerializer},
    )
    def post(self, request: Request) -> Response:
        """Autentica al usuario mediante usuario/correo, contraseña y código 2FA opcional.

        Args:
            request: Petición HTTP con las credenciales de acceso.

        Returns:
            Response: Respuesta HTTP 200 con el access token y perfil de usuario,
            configurando la cookie segura de refresco.
        """
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
    """Endpoint para la renovación de tokens de acceso mediante rotación de refresh token."""

    authentication_classes: ClassVar[list] = []
    permission_classes: ClassVar[list] = [AllowAny]

    @extend_schema(
        summary="Rota el refresh token de la cookie httpOnly y entrega un nuevo access token",
        request=None,
        responses={200: TokenRefreshResponseSerializer},
    )
    def post(self, request: Request) -> Response:
        """Lee la cookie de refresco, la rota y emite un nuevo par de tokens.

        Args:
            request: Petición HTTP entrante con la cookie httpOnly.

        Returns:
            Response: Respuesta HTTP 200 con el nuevo access token y cookie de refresco actualizada.
        """
        tokens = rotate_refresh_token(refresh_token_str=read_refresh_cookie(request))
        response = Response({"access": tokens["access"]}, status=status.HTTP_200_OK)
        set_refresh_cookie(response, tokens["refresh"])
        return response


class LogoutView(APIView):
    """Endpoint para el cierre de sesión y revocación de tokens."""

    permission_classes: ClassVar[list] = [IsAuthenticated]

    @extend_schema(
        summary="Cierra sesión revocando el refresh token de la cookie y eliminándola",
        request=None,
        responses={204: None},
    )
    def post(self, request: Request) -> Response:
        """Invalida el refresh token actual y limpia la cookie de sesión del cliente.

        Args:
            request: Petición HTTP autenticada.

        Returns:
            Response: Respuesta HTTP 204 sin contenido y con la cookie eliminada.
        """
        refresh_token = read_refresh_cookie(request)
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
    """Endpoint para consultar el perfil del usuario autenticado actual."""

    permission_classes: ClassVar[list] = [IsAuthenticated]

    @extend_schema(
        summary="Retorna el perfil del usuario autenticado",
        responses={200: UserSerializer},
    )
    def get(self, request: Request) -> Response:
        """Obtiene los datos demográficos y de rol del usuario asociado a la sesión activa.

        Args:
            request: Petición HTTP autenticada.

        Returns:
            Response: Respuesta HTTP 200 con la serialización del usuario.
        """
        return Response(UserSerializer(request.user).data, status=status.HTTP_200_OK)


class ChangePasswordView(APIView):
    """Endpoint para la modificación de la contraseña propia."""

    permission_classes: ClassVar[list] = [IsAuthenticated]

    @extend_schema(
        summary="Cambia la contraseña propia, cierra las demás sesiones y renueva los tokens",
        request=ChangePasswordSerializer,
        responses={200: TokenRefreshResponseSerializer},
    )
    def post(self, request: Request) -> Response:
        """Valida la contraseña actual, actualiza a la nueva clave y reemite los tokens de sesión.

        Args:
            request: Petición HTTP con 'current_password' y 'new_password'.

        Returns:
            Response: Respuesta HTTP 200 con el nuevo access token y refresh cookie.
        """
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
    """Endpoint para iniciar la configuración de la autenticación en dos pasos (2FA)."""

    permission_classes: ClassVar[list] = [IsAuthenticated]

    @extend_schema(
        summary="Genera un nuevo secreto TOTP para configurar 2FA",
        request=None,
        responses={200: TwoFactorSetupResponseSerializer},
    )
    def post(self, request: Request) -> Response:
        """Genera el secreto temporal y la URI de aprovisionamiento para código QR.

        Args:
            request: Petición HTTP autenticada.

        Returns:
            Response: Respuesta HTTP 200 con el secreto y la URI de configuración.
        """
        payload = setup_two_factor(
            user=request.user,
            ip_address=get_client_ip(request),
        )
        return Response(payload, status=status.HTTP_200_OK)


class TwoFactorEnableView(APIView):
    """Endpoint para confirmar y activar definitivamente el 2FA."""

    permission_classes: ClassVar[list] = [IsAuthenticated]

    @extend_schema(
        summary="Verifica un código TOTP y activa 2FA en la cuenta actual",
        request=TwoFactorCodeSerializer,
        responses={200: UserSerializer},
    )
    def post(self, request: Request) -> Response:
        """Valida el código TOTP ingresado y activa el flag de doble factor en la cuenta.

        Args:
            request: Petición HTTP con el código 'otp_code' de 6 dígitos.

        Returns:
            Response: Respuesta HTTP 200 con los datos actualizados del usuario.
        """
        serializer = TwoFactorCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = enable_two_factor(
            user=request.user,
            otp_code=serializer.validated_data["otp_code"],
            ip_address=get_client_ip(request),
        )
        return Response(UserSerializer(user).data, status=status.HTTP_200_OK)


class TwoFactorDisableView(APIView):
    """Endpoint para desactivar el doble factor de autenticación."""

    permission_classes: ClassVar[list] = [IsAuthenticated]

    @extend_schema(
        summary="Verifica un código TOTP y desactiva 2FA en la cuenta actual",
        request=TwoFactorCodeSerializer,
        responses={200: UserSerializer},
    )
    def post(self, request: Request) -> Response:
        """Verifica el código TOTP vigente y deshabilita el 2FA de la cuenta.

        Args:
            request: Petición HTTP con el código 'otp_code'.

        Returns:
            Response: Respuesta HTTP 200 con los datos actualizados del usuario.
        """
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
    """ViewSet para la gestión administrativa de cuentas de usuario."""

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
        """Selecciona el serializer adecuado según la acción solicitada (creación, edición o lectura).

        Returns:
            Serializer class: La clase de serialización correspondiente.
        """
        if self.action == "create":
            return UserCreateSerializer
        if self.action in {"update", "partial_update"}:
            return UserUpdateSerializer
        return UserSerializer

    @extend_schema(request=UserCreateSerializer, responses={201: UserSerializer})
    def create(self, request: Request, *args, **kwargs) -> Response:
        """Crea una nueva cuenta de usuario con privilegios administrativos.

        Args:
            request: Petición HTTP con los datos del nuevo usuario.

        Returns:
            Response: Respuesta HTTP 201 con el recurso creado.
        """
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
        """Actualiza completamente una cuenta de usuario existente.

        Args:
            request: Petición HTTP con los datos de reemplazo.

        Returns:
            Response: Respuesta HTTP 200 con el usuario actualizado.
        """
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
        """Actualiza parcialmente una cuenta de usuario (delega en ``update``)."""
        return self.update(request, *args, **kwargs)


class StaffDirectoryViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """ViewSet de solo lectura para consultar el directorio público del personal activo."""

    queryset = User.objects.filter(is_active=True).order_by("full_name", "id")
    serializer_class = StaffMemberSerializer
    permission_classes: ClassVar[list] = [IsAuthenticated]
    filterset_fields: ClassVar[list[str]] = ["role", "shift"]
    search_fields: ClassVar[list[str]] = ["full_name"]
    ordering_fields: ClassVar[list[str]] = ["full_name"]


class MyShiftSerializer(serializers.Serializer):
    """Serializador para estructurar las cunas y turnos asignados al usuario autenticado."""

    date = serializers.DateField()
    shift = serializers.ChoiceField(choices=WorkShift.choices)
    cribs = CribOverviewSerializer(many=True)


class ShiftCatalogView(APIView):
    """Endpoint para consultar el catálogo fijo de turnos de la clínica."""

    permission_classes: ClassVar[list] = [IsAuthenticated]

    @extend_schema(
        summary="Catálogo fijo de turnos con su horario e indicación del turno vigente",
        responses={200: ShiftSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        """Retorna la lista de turnos disponibles y marca cuál se encuentra activo actualmente.

        Args:
            request: Petición HTTP autenticada.

        Returns:
            Response: Respuesta HTTP 200 con el catálogo de turnos.
        """
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
    """Filtros de búsqueda avanzada para las asignaciones de turnos."""

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
    """ViewSet para la administración y consulta de asignaciones de turnos a profesionales."""

    queryset = ShiftAssignment.objects.select_related("user", "crib").all()
    serializer_class = ShiftAssignmentSerializer
    permission_classes: ClassVar[list] = [IsAuthenticated]
    filterset_class = ShiftAssignmentFilter
    ordering_fields: ClassVar[list[str]] = ["date", "shift"]

    @extend_schema(
        request=ShiftAssignmentCreateSerializer, responses={201: ShiftAssignmentSerializer}
    )
    def create(self, request: Request, *args, **kwargs) -> Response:
        """Asigna un profesional de salud a una cuna para un día y turno específico.

        Args:
            request: Petición HTTP con los datos de asignación.

        Returns:
            Response: Respuesta HTTP 201 con la asignación creada.
        """
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
        """Elimina una asignación de turno existente.

        Args:
            request: Petición HTTP de borrado.

        Returns:
            Response: Respuesta HTTP 204 sin contenido.
        """
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
        """Consulta las cunas supervisadas por el usuario actual durante su turno activo.

        Args:
            request: Petición HTTP del profesional autenticado.

        Returns:
            Response: Respuesta HTTP 200 con el resumen de cunas del turno actual.
        """
        day, shift, crib_ids = assigned_crib_ids(user=request.user)
        overview = build_unit_overview(crib_ids=crib_ids)
        payload = {"date": day, "shift": shift, "cribs": overview.cribs}
        return Response(MyShiftSerializer(payload).data, status=status.HTTP_200_OK)
