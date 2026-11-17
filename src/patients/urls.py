"""Rutas URL del módulo de pacientes: fichas clínicas, planes de cuidado y observaciones."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CarePlanViewSet, ClinicalObservationViewSet, PatientViewSet

router = DefaultRouter()
router.register(r"patients", PatientViewSet, basename="patients")
router.register(r"care-plans", CarePlanViewSet, basename="care-plans")
router.register(r"observations", ClinicalObservationViewSet, basename="observations")

urlpatterns = [
    path("", include(router.urls)),
]
