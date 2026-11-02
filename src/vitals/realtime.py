from typing import Any
from urllib.parse import parse_qs

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import User

UNIT_STREAM_GROUP = "unit_monitoring_stream"


def crib_stream_group(crib_id: int) -> str:
    return f"crib_stream_{crib_id}"


def patient_stream_group(patient_id: int) -> str:
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


def _extract_token_from_scope(scope: dict[str, Any]) -> str | None:
    headers = dict(scope.get("headers", []))
    auth_header = headers.get(b"authorization", b"").decode("latin1").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()

    raw_query = scope.get("query_string", b"").decode("utf-8", errors="ignore")
    if raw_query:
        params = parse_qs(raw_query)
        token_list = params.get("token")
        if token_list and token_list[0].strip():
            return token_list[0].strip()

    return None


class JwtWebSocketAuthMiddleware:
    """Middleware ASGI que autentica conexiones WebSocket mediante JWT Access Token."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> Any:
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
