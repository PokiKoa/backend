"""Rutas de la API de reportes operativos y series temporales de la unidad neonatal."""

from django.urls import path

from .views import ActivitySeriesView, OperationsSummaryView

urlpatterns = [
    path("reports/summary/", OperationsSummaryView.as_view(), name="reports-summary"),
    path("reports/series/", ActivitySeriesView.as_view(), name="reports-series"),
]
