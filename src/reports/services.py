from datetime import date, datetime, timedelta
from typing import Any

from django.db.models import Count, F
from django.db.models.functions import TruncDate
from django.utils import timezone

from accounts.models import ShiftAssignment, User
from accounts.services import current_shift
from alerts.models import Alert, AlertSeverity, AlertStatus
from devices.models import Crib, CribStatus
from medications.models import (
    MedicationAdministration,
    MedicationCatalogItem,
    Prescription,
    PrescriptionStatus,
)
from patients.models import CarePlan, CarePlanStatus, Patient, PatientStatus
from poki_koa.exceptions import DomainError

MAX_SERIES_DAYS = 90
OPEN_ALERT_STATUSES = (AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED)


def _counts(queryset, field: str, choices: list[str]) -> dict[str, int]:
    counts = dict.fromkeys(choices, 0)
    for row in queryset.values(field).annotate(n=Count("id")):
        counts[row[field]] = row["n"]
    return counts


def build_operations_summary(now: datetime | None = None) -> dict[str, Any]:
    now = now or timezone.now()
    today = timezone.localdate(now)
    shift_day, _ = current_shift(now)

    patients = _counts(Patient.objects.all(), "status", PatientStatus.values)
    cribs = _counts(Crib.objects.all(), "status", CribStatus.values)
    cribs_total = sum(cribs.values())
    open_alerts = Alert.objects.filter(status__in=OPEN_ALERT_STATUSES)

    return {
        "generated_at": now,
        "patients": {
            "total": sum(patients.values()),
            "active": patients[PatientStatus.ACTIVE],
            "discharged": sum(n for s, n in patients.items() if s != PatientStatus.ACTIVE),
        },
        "cribs": {
            "total": cribs_total,
            "by_status": cribs,
            "occupancy_percent": round(100 * cribs[CribStatus.OCCUPIED] / cribs_total, 1)
            if cribs_total
            else 0.0,
        },
        "prescriptions": {
            "by_status": _counts(Prescription.objects.all(), "status", PrescriptionStatus.values),
            "administrations_today": MedicationAdministration.objects.filter(
                administered_at__date=today
            ).count(),
        },
        "medications_low_stock": MedicationCatalogItem.objects.filter(
            is_active=True, stock__lte=F("min_stock_alert")
        ).count(),
        "alerts": {
            "open": open_alerts.count(),
            "open_by_severity": _counts(open_alerts, "severity", AlertSeverity.values),
            "open_by_type": dict(
                open_alerts.values_list("alert_type").annotate(n=Count("id")).order_by()
            ),
        },
        "care_plans_active": CarePlan.objects.filter(status=CarePlanStatus.ACTIVE).count(),
        "staff": {
            "active": User.objects.filter(is_active=True).count(),
            "by_shift": dict(
                User.objects.filter(is_active=True, shift__isnull=False)
                .values_list("shift")
                .annotate(n=Count("id"))
                .order_by()
            ),
            "assignments_current_shift_day": ShiftAssignment.objects.filter(
                date=shift_day
            ).count(),
        },
    }


def build_activity_series(*, days: int = 14, now: datetime | None = None) -> list[dict[str, Any]]:
    if not 1 <= days <= MAX_SERIES_DAYS:
        raise DomainError(f"El rango debe estar entre 1 y {MAX_SERIES_DAYS} días.")
    end = timezone.localdate(now or timezone.now())
    start = end - timedelta(days=days - 1)
    tz = timezone.get_current_timezone()

    def per_day(queryset, field: str) -> dict[date, int]:
        # Agrupa por día local para que la serie coincida con lo que ve la unidad
        return dict(
            queryset.filter(**{f"{field}__date__gte": start})
            .annotate(day=TruncDate(field, tzinfo=tz))
            .values_list("day")
            .annotate(n=Count("id"))
            .order_by()
        )

    admissions = per_day(Patient.objects.all(), "admitted_at")
    alerts = per_day(Alert.objects.all(), "triggered_at")
    return [
        {
            "date": start + timedelta(days=offset),
            "admissions": admissions.get(start + timedelta(days=offset), 0),
            "alerts": alerts.get(start + timedelta(days=offset), 0),
        }
        for offset in range(days)
    ]
