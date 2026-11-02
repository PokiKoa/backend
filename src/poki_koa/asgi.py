import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "poki_koa.settings.prod")

django_asgi_app = get_asgi_application()

from vitals.realtime import JwtWebSocketAuthMiddleware
from vitals.routing import websocket_urlpatterns

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JwtWebSocketAuthMiddleware(URLRouter(websocket_urlpatterns)),
    }
)
