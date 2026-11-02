"""Configuración de URLs principal del proyecto Poki Koa.

Define dos grupos de rutas:
- /admin/    → Panel de administración de Django
- /api/      → Todas las rutas de la API REST (delegadas a cunas/urls.py)
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Panel de administración de Django (interfaz web para gestionar la base de datos)
    path("admin/", admin.site.urls),
    # Rutas de la API REST: delega a cunas/urls.py todo lo que empiece con /api/
    path("api/", include("cunas.urls")),
]
