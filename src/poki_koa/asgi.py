"""Punto de entrada ASGI de Poki Koa: enruta peticiones HTTP y conexiones WebSocket autenticadas."""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

from poki_koa.env import load_env_file

load_env_file()
# Producción es el valor por defecto deliberado: si falta configuración, falla en vez de exponer DEBUG.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "poki_koa.settings.prod")

django_asgi_app = get_asgi_application()

from vitals.realtime import JwtWebSocketAuthMiddleware  # noqa: E402
from vitals.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JwtWebSocketAuthMiddleware(URLRouter(websocket_urlpatterns)),
    }
)
