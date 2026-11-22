"""Tiempo real: grupos de canal, autenticación JWT del WebSocket y difusión de lecturas y alertas."""

from typing import Any

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.security.websocket import OriginValidator
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import User

UNIT_STREAM_GROUP = "unit_monitoring_stream"
WS_AUTH_SUBPROTOCOL = "bearer"


def crib_stream_group(crib_id: int) -> str:
    """Construye el nombre del grupo de canal asociado a una cuna específica.

    Args:
        crib_id: Identificador numérico de la cuna.

    Returns:
        Nombre del grupo de Channels (``crib_stream_<crib_id>``).
    """
    return f"crib_stream_{crib_id}"


def patient_stream_group(patient_id: int) -> str:
    """Construye el nombre del grupo de canal asociado a un paciente específico.

    Args:
        patient_id: Identificador numérico del paciente.

    Returns:
        Nombre del grupo de Channels (``patient_stream_<patient_id>``).
    """
    return f"patient_stream_{patient_id}"


@database_sync_to_async
def _get_user_from_access_token(raw_token: str) -> User | AnonymousUser:
    """Valida un token JWT de acceso y recupera al usuario activo no bloqueado.

    Args:
        raw_token: Cadena JWT sin el prefijo ``Bearer``.

    Returns:
        Instancia activa de ``User`` si el token es válido y la cuenta está habilitada;
        ``AnonymousUser`` en cualquier caso de error, expiración o bloqueo.
    """
    try:
        validated = AccessToken(raw_token)
        user_id = validated.get("user_id")
        if user_id is None:
            return AnonymousUser()
        user = User.objects.filter(pk=user_id, is_active=True).first()
        if user is None or user.is_temporarily_locked:
            return AnonymousUser()
        return user
    except (TokenError, ValueError, TypeError):
        return AnonymousUser()


def _extract_token_from_scope(scope: dict[str, Any]) -> str | None:
    """Extrae el token JWT desde la cabecera ``Authorization`` o los subprotocolos WebSocket.

    Args:
        scope: Diccionario de alcance ASGI de la conexión entrante.

    Returns:
        Token JWT sin espacios si se encuentra; ``None`` si la conexión no incluye credenciales.
    """
    headers = dict(scope.get("headers", []))
    auth_header = headers.get(b"authorization", b"").decode("latin1").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()

    # Los navegadores no permiten cabeceras en WebSocket: el token viaja como subprotocolo
    # (["bearer", "<access>"]) en vez de la URL, para que no quede en logs de proxies
    subprotocols = list(scope.get("subprotocols") or [])
    if WS_AUTH_SUBPROTOCOL in subprotocols:
        index = subprotocols.index(WS_AUTH_SUBPROTOCOL)
        if index + 1 < len(subprotocols) and subprotocols[index + 1].strip():
            return subprotocols[index + 1].strip()

    return None


class JwtWebSocketAuthMiddleware:
    """Middleware ASGI que autentica conexiones WebSocket mediante JWT Access Token."""

    def __init__(self, app: Any) -> None:
        """Inicializa el middleware envolviendo la aplicación ASGI interna.

        Args:
            app: Aplicación o router ASGI siguiente en la cadena de procesamiento.
        """
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> Any:
        """Resuelve el usuario desde el JWT (cabecera o subprotocolo) y lo deja en ``scope['user']``.

        Args:
            scope: Diccionario de contexto de la conexión ASGI.
            receive: Canal asíncrono de recepción de eventos ASGI.
            send: Canal asíncrono de envío de eventos ASGI.

        Returns:
            Resultado de delegar la ejecución a ``self.app`` con ``scope['user']`` poblado
            (``User`` autenticado o ``AnonymousUser``).
        """
        scope = dict(scope)
        raw_token = _extract_token_from_scope(scope)
        if raw_token:
            scope["user"] = await _get_user_from_access_token(raw_token)
        else:
            scope["user"] = AnonymousUser()
        return await self.app(scope, receive, send)


class SettingsOriginValidator(OriginValidator):
    """Rechaza el handshake WebSocket si ``Origin`` no es de ``ALLOWED_HOSTS`` ni de ``CORS_ALLOWED_ORIGINS``.

    Evita que una página de otro sitio abra el canal en nombre del usuario (CSWSH). Se aceptan
    el mismo origen que la API (``ALLOWED_HOSTS``) y los frontends autorizados por CORS; una
    conexión sin ``Origin`` se rechaza salvo que ``ALLOWED_HOSTS`` contenga ``*``.
    """

    def __init__(self, application: Any) -> None:
        self.application = application

    @property
    def allowed_origins(self) -> list[str]:
        """Orígenes permitidos, leídos de settings en cada conexión."""
        hosts = list(settings.ALLOWED_HOSTS)
        if settings.DEBUG and not hosts:
            hosts = ["localhost", "127.0.0.1", "[::1]"]
        return [*hosts, *getattr(settings, "CORS_ALLOWED_ORIGINS", [])]


def _send_to_groups(groups: list[str], payload: dict[str, Any]) -> None:
    """Envía una carga útil JSON a una lista deduplicada de grupos de Channels.

    Args:
        groups: Nombres de grupos destino en la capa de canales.
        payload: Diccionario serializable que será reenviado por los consumers.

    Returns:
        None: Omite el envío de forma segura si ``channel_layer`` no está configurado.
    """
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    message = {
        "type": "stream.event",
        "payload": payload,
    }
    for group_name in dict.fromkeys(groups):
        async_to_sync(channel_layer.group_send)(group_name, message)


def broadcast_telemetry_reading(
    *,
    reading_data: dict[str, Any],
    active_alerts_data: list[dict[str, Any]],
    auto_resolved_alerts_data: list[dict[str, Any]],
    crib_id: int,
    patient_id: int | None,
) -> None:
    """Difunde una lectura y sus alertas a la unidad, la cuna y el paciente.

    Args:
        reading_data: Lectura serializada.
        active_alerts_data: Alertas abiertas tras la evaluación.
        auto_resolved_alerts_data: Alertas resueltas automáticamente.
        crib_id: Cuna de origen.
        patient_id: Paciente asignado, si hay.

    Returns:
        None
    """
    groups = [UNIT_STREAM_GROUP, crib_stream_group(crib_id)]
    if patient_id is not None:
        groups.append(patient_stream_group(patient_id))

    _send_to_groups(
        groups,
        {
            "event": "telemetry.reading",
            "crib_id": crib_id,
            "patient_id": patient_id,
            "reading": reading_data,
            "active_alerts": active_alerts_data,
            "auto_resolved_alerts": auto_resolved_alerts_data,
        },
    )


def broadcast_alert_event(
    *,
    event_name: str,
    alert_data: dict[str, Any],
    crib_id: int,
    patient_id: int | None,
) -> None:
    """Difunde un evento de alerta a la unidad, la cuna y el paciente.

    Args:
        event_name: Nombre del evento (p. ej. creación o resolución).
        alert_data: Alerta serializada.
        crib_id: Cuna asociada.
        patient_id: Paciente asignado, si hay.

    Returns:
        None
    """
    groups = [UNIT_STREAM_GROUP, crib_stream_group(crib_id)]
    if patient_id is not None:
        groups.append(patient_stream_group(patient_id))

    _send_to_groups(
        groups,
        {
            "event": event_name,
            "crib_id": crib_id,
            "patient_id": patient_id,
            "alert": alert_data,
        },
    )
