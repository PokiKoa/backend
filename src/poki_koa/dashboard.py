"""Estadísticas para la portada HTML del servicio."""

from typing import Any

from django.db.models import F

from alerts.models import Alert, AlertSeverity, AlertStatus
from devices.models import Crib, CribStatus
from medications.models import MedicationCatalogItem, Prescription, PrescriptionStatus
from patients.models import Patient, PatientStatus


def get_clinical_dashboard_stats() -> dict[str, Any]:
    """Devuelve contadores (pacientes, cunas, alertas, medicamentos con stock bajo e indicaciones vigentes),
    los 10 últimos pacientes activos y las 6 alertas abiertas más recientes.
    """
    active_patients = list(
        Patient.objects.filter(status=PatientStatus.ACTIVE)
        .select_related("crib", "attending_physician")
        .order_by("-admitted_at")[:10]
    )
    open_alerts_qs = Alert.objects.filter(
        status__in=[AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED]
    ).select_related("crib", "patient")

    return {
        "active_patients_count": Patient.objects.filter(status=PatientStatus.ACTIVE).count(),
        "discharged_patients_count": Patient.objects.exclude(status=PatientStatus.ACTIVE).count(),
        "total_cribs_count": Crib.objects.count(),
        "occupied_cribs_count": Crib.objects.filter(status=CribStatus.OCCUPIED).count(),
        "available_cribs_count": Crib.objects.filter(status=CribStatus.AVAILABLE).count(),
        "open_alerts_count": open_alerts_qs.count(),
        "critical_alerts_count": open_alerts_qs.filter(severity=AlertSeverity.CRITICAL).count(),
        "warning_alerts_count": open_alerts_qs.filter(severity=AlertSeverity.WARNING).count(),
        "low_stock_medications_count": MedicationCatalogItem.objects.filter(
            is_active=True,
            stock__lte=F("min_stock_alert"),
        ).count(),
        "pending_prescriptions_count": Prescription.objects.filter(
            status=PrescriptionStatus.ACTIVE
        ).count(),
        "active_patients": active_patients,
        "recent_alerts": list(open_alerts_qs.order_by("-triggered_at")[:6]),
    }
