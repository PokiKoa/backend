"""Consumer WebSocket que transmite telemetría y alertas en tiempo real."""

from typing import Any

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from accounts.models import User, UserRole
from audit.models import AuditAction
from audit.services import record_audit_event
from devices.models import Crib
from patients.models import Patient

from .realtime import (
    UNIT_STREAM_GROUP,
    WS_AUTH_SUBPROTOCOL,
    crib_stream_group,
    patient_stream_group,
)

WS_CLOSE_UNAUTHORIZED = 4401
WS_CLOSE_FORBIDDEN = 4403
WS_CLOSE_NOT_FOUND = 4404

ALLOWED_WS_ROLES = {
    UserRole.ADMIN,
    UserRole.NEONATOLOGIST,
    UserRole.NURSE,
}


@database_sync_to_async
def _crib_exists(crib_id: int) -> bool:
    """Verifica de forma asíncrona si existe una cuna con el identificador dado.

    Args:
        crib_id: Clave primaria de la cuna a consultar.

    Returns:
        ``True`` si la cuna existe en base de datos; ``False`` en caso contrario.
    """
    return Crib.objects.filter(pk=crib_id).exists()


@database_sync_to_async
def _verify_and_audit_patient_stream(user: User, patient_id: int) -> bool:
    """Verifica la existencia del paciente y registra el acceso de lectura al flujo en auditoría.

    Args:
        user: Usuario autenticado que solicita suscribirse al stream del paciente.
        patient_id: Clave primaria del paciente solicitado.

    Returns:
        ``True`` si el paciente existe y el acceso fue auditado; ``False`` si no existe.
    """
    if not Patient.objects.filter(pk=patient_id).exists():
        return False
    record_audit_event(
        action=AuditAction.READ,
        resource_type="patient_stream",
        resource_id=patient_id,
        actor_user=user,
        patient_id=patient_id,
        changed_fields=[],
    )
    return True


class TelemetryAlertConsumer(AsyncJsonWebsocketConsumer):
    """Suscribe al cliente al flujo de la unidad, de una cuna o de un paciente según la ruta."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Inicializa el consumer y el conjunto de grupos de canal suscritos.

        Args:
            *args: Argumentos posicionales delegados a ``AsyncJsonWebsocketConsumer``.
            **kwargs: Argumentos nominales delegados a ``AsyncJsonWebsocketConsumer``.
        """
        super().__init__(*args, **kwargs)
        self.subscribed_groups: set[str] = set()

    async def connect(self) -> None:
        """Acepta la conexión de usuarios autorizados y los suscribe al grupo correspondiente.

        Cierra el socket con código ``4401`` (sin sesión), ``4403`` (rol no permitido) o
        ``4404`` (cuna o paciente inexistente).

        Returns:
            None: Acepta el handshake WebSocket y envía el evento ``stream.connected``.
        """
        user = self.scope.get("user")
        if user is None or not getattr(user, "is_authenticated", False):
            await self.close(code=WS_CLOSE_UNAUTHORIZED)
            return

        if getattr(user, "role", None) not in ALLOWED_WS_ROLES:
            await self.close(code=WS_CLOSE_FORBIDDEN)
            return

        kwargs = self.scope.get("url_route", {}).get("kwargs", {})
        crib_id = kwargs.get("crib_id")
        patient_id = kwargs.get("patient_id")

        if crib_id is not None:
            exists = await _crib_exists(int(crib_id))
            if not exists:
                await self.close(code=WS_CLOSE_NOT_FOUND)
                return
            group_name = crib_stream_group(int(crib_id))
        elif patient_id is not None:
            exists = await _verify_and_audit_patient_stream(user, int(patient_id))
            if not exists:
                await self.close(code=WS_CLOSE_NOT_FOUND)
                return
            group_name = patient_stream_group(int(patient_id))
        else:
            group_name = UNIT_STREAM_GROUP

        if self.channel_layer is not None:
            await self.channel_layer.group_add(group_name, self.channel_name)
            self.subscribed_groups.add(group_name)

        # Si el cliente ofreció el subprotocolo de autenticación, el navegador exige que se confirme
        offered = self.scope.get("subprotocols") or []
        await self.accept(
            subprotocol=WS_AUTH_SUBPROTOCOL if WS_AUTH_SUBPROTOCOL in offered else None
        )
        await self.send_json(
            {
                "event": "stream.connected",
                "groups": sorted(self.subscribed_groups),
                "role": user.role,
            }
        )

    async def disconnect(self, close_code: int) -> None:
        """Cancela las suscripciones activas en los grupos de canal al cerrar el socket.

        Args:
            close_code: Código numérico de cierre WebSocket reportado por ASGI.

        Returns:
            None
        """
        if self.channel_layer is not None:
            for group_name in list(self.subscribed_groups):
                await self.channel_layer.group_discard(group_name, self.channel_name)
        self.subscribed_groups.clear()

    async def receive_json(self, content: Any, **kwargs: Any) -> None:
        """Procesa mensajes JSON entrantes del cliente y responde ``stream.pong`` ante ``ping``.

        Args:
            content: Carga útil JSON decodificada enviada por el cliente.
            **kwargs: Parámetros adicionales delegados por ``AsyncJsonWebsocketConsumer``.

        Returns:
            None
        """
        if isinstance(content, dict) and content.get("action") == "ping":
            await self.send_json({"event": "stream.pong"})

    async def stream_event(self, event: dict[str, Any]) -> None:
        """Reenvía al cliente WebSocket el payload recibido desde el grupo de Channels.

        Args:
            event: Diccionario de mensaje interno emitido por ``channel_layer.group_send``.

        Returns:
            None
        """
        await self.send_json(event["payload"])
