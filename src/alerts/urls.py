from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AlertViewSet, DefaultAlertThresholdView

router = DefaultRouter()
router.register(r"alerts", AlertViewSet, basename="alerts")

urlpatterns = [
    path(
        "alert-thresholds/default/",
        DefaultAlertThresholdView.as_view(),
        name="default-alert-thresholds",
    ),
    path("", include(router.urls)),
]
