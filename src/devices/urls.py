"""Configuración de rutas URL para el módulo de cunas y dispositivos IoT."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CribViewSet

router = DefaultRouter()
router.register(r"cribs", CribViewSet, basename="crib")

urlpatterns = [
    path("", include(router.urls)),
]
