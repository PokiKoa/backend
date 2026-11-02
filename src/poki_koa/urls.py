from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from .views import HealthCheckView, root_dashboard_view

admin.site.site_header = "Poki Koa — Centro de Control Neonatal"
admin.site.site_title = "Poki Koa Admin"
admin.site.index_title = "Panel Clínico y Operativo de Neonatología"
admin.site.site_url = "/"

api_v1_patterns = [
    path("health/", HealthCheckView.as_view(), name="health-check"),
    path("schema/", SpectacularAPIView.as_view(), name="openapi-schema"),
    path(
        "docs/",
        SpectacularSwaggerView.as_view(url_name="openapi-schema"),
        name="swagger-ui",
    ),
    path("", include("accounts.urls")),
    path("", include("audit.urls")),
    path("", include("devices.urls")),
    path("", include("patients.urls")),
    path("", include("vitals.urls")),
    path("", include("alerts.urls")),
    path("", include("medications.urls")),
]

urlpatterns = [
    path("", root_dashboard_view, name="root-dashboard"),
    path("admin/", admin.site.urls),
    path("api/v1/", include(api_v1_patterns)),
]
