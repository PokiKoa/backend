from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from .views import HealthCheckView

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
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include(api_v1_patterns)),
]
