from django.urls import path

from .consumers import TelemetryAlertConsumer

websocket_urlpatterns = [
    path(
        "ws/v1/cribs/<int:crib_id>/stream/",
        TelemetryAlertConsumer.as_asgi(),
        name="ws-crib-stream",
    ),
    path(
        "ws/v1/patients/<int:patient_id>/stream/",
        TelemetryAlertConsumer.as_asgi(),
        name="ws-patient-stream",
    ),
    path(
        "ws/v1/monitoring/stream/",
        TelemetryAlertConsumer.as_asgi(),
        name="ws-unit-stream",
    ),
]
