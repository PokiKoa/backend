from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import UnitOverviewView, VitalSignReadingViewSet

router = DefaultRouter()
router.register(r"vitals", VitalSignReadingViewSet, basename="vitals")

urlpatterns = [
    path("monitoring/overview/", UnitOverviewView.as_view(), name="monitoring-overview"),
    path("", include(router.urls)),
]
