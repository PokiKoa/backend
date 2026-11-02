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
    return Crib.objects.filter(pk=crib_id).exists()


@database_sync_to_async
def _verify_and_audit_patient_stream(user: User, patient_id: int) -> bool:
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
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.subscribed_groups: set[str] = set()

    async def connect(self) -> None:
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

        await self.accept()
        await self.send_json(
            {
                "event": "stream.connected",
                "groups": sorted(self.subscribed_groups),
                "role": user.role,
            }
        )

    async def disconnect(self, close_code: int) -> None:
        if self.channel_layer is not None:
            for group_name in list(self.subscribed_groups):
                await self.channel_layer.group_discard(group_name, self.channel_name)
        self.subscribed_groups.clear()

    async def receive_json(self, content: Any, **kwargs: Any) -> None:
        if isinstance(content, dict) and content.get("action") == "ping":
            await self.send_json({"event": "stream.pong"})

    async def stream_event(self, event: dict[str, Any]) -> None:
        await self.send_json(event["payload"])
