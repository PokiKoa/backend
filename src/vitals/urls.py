from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import VitalSignReadingViewSet

router = DefaultRouter()
router.register(r"vitals", VitalSignReadingViewSet, basename="vitals")

urlpatterns = [
    path("", include(router.urls)),
]
