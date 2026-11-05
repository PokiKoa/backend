"""Tiempo real: grupos de canal, autenticación JWT del WebSocket y difusión de lecturas y alertas."""

from typing import Any

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import User

UNIT_STREAM_GROUP = "unit_monitoring_stream"


def crib_stream_group(crib_id: int) -> str:
    """Nombre del grupo de canal de una cuna."""
    return f"crib_stream_{crib_id}"


def patient_stream_group(patient_id: int) -> str:
    """Nombre del grupo de canal de un paciente."""
    return f"patient_stream_{patient_id}"


@database_sync_to_async
def _get_user_from_access_token(raw_token: str) -> User | AnonymousUser:
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


WS_AUTH_SUBPROTOCOL = "bearer"


def _extract_token_from_scope(scope: dict[str, Any]) -> str | None:
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
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> Any:
        """Resuelve el usuario desde el JWT (cabecera o subprotocolo) y lo deja en ``scope['user']``; anónimo si falta o es inválido."""
        scope = dict(scope)
        raw_token = _extract_token_from_scope(scope)
        if raw_token:
            scope["user"] = await _get_user_from_access_token(raw_token)
        else:
            scope["user"] = AnonymousUser()
        return await self.app(scope, receive, send)


def _send_to_groups(groups: list[str], payload: dict[str, Any]) -> None:
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
