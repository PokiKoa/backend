"""Servicios de reportes: resumen operativo de la unidad y serie diaria de actividad."""

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


def _counts(queryset: Any, field: str, choices: list[str]) -> dict[str, int]:
    """Agrupa un queryset por un campo discreto garantizando todas las claves esperadas.

    Args:
        queryset: Consulta Django sobre la cual contar registros.
        field: Nombre del campo por el que se agrupa.
        choices: Lista completa de valores posibles que deben aparecer en el diccionario resultante.

    Returns:
        Diccionario ``{valor_campo: conteo}`` con ``0`` para las claves sin registros.
    """
    counts = dict.fromkeys(choices, 0)
    for row in queryset.values(field).annotate(n=Count("id")):
        counts[row[field]] = row["n"]
    return counts


def build_operations_summary(now: datetime | None = None) -> dict[str, Any]:
    """Construye el resumen operativo consolidado de la unidad neonatal.

    Precondiciones:
        - ``now`` debe ser ``None`` o una instancia válida de ``datetime`` con zona horaria.

    Postcondiciones:
        - Devuelve un diccionario con ``generated_at``, ``patients``, ``cribs``, ``prescriptions``,
          ``medications_low_stock``, ``alerts``, ``care_plans_active`` y ``staff``.
        - ``patients["total"] == patients["active"] + patients["discharged"]``.
        - ``0.0 <= cribs["occupancy_percent"] <= 100.0`` y la suma de ``cribs["by_status"]``
          coincide con ``cribs["total"]``.

    Invariante:
        - Operación de solo lectura: no modifica pacientes, cunas, alertas, indicaciones ni turnos.
    """
    assert now is None or isinstance(now, datetime), "now debe ser datetime o None."

    now = now or timezone.now()
    today = timezone.localdate(now)
    shift_day, _ = current_shift(now)

    patients = _counts(Patient.objects.all(), "status", PatientStatus.values)
    cribs = _counts(Crib.objects.all(), "status", CribStatus.values)
    cribs_total = sum(cribs.values())
    open_alerts = Alert.objects.filter(status__in=OPEN_ALERT_STATUSES)

    summary = {
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
            "assignments_current_shift_day": ShiftAssignment.objects.filter(date=shift_day).count(),
        },
    }

    assert (
        summary["patients"]["total"]
        == summary["patients"]["active"] + summary["patients"]["discharged"]
    ), "Inconsistencia en el desglose de pacientes activos y egresados."
    assert 0.0 <= summary["cribs"]["occupancy_percent"] <= 100.0, (
        "El porcentaje de ocupación de cunas debe estar entre 0.0 y 100.0."
    )
    assert sum(summary["cribs"]["by_status"].values()) == summary["cribs"]["total"], (
        "La suma de cunas por estado debe coincidir con el total."
    )
    return summary


def build_activity_series(*, days: int = 14, now: datetime | None = None) -> list[dict[str, Any]]:
    """Construye la serie diaria de ingresos de pacientes y alertas disparadas.

    Precondiciones:
        - ``1 <= days <= MAX_SERIES_DAYS`` (si está fuera de rango, lanza ``DomainError``).
        - ``now`` debe ser ``None`` o una instancia válida de ``datetime``.

    Postcondiciones:
        - Devuelve una lista de exactamente ``days`` elementos ordenados cronológicamente desde
          ``end - (days - 1)`` hasta ``end`` (fecha local de referencia).
        - Cada punto contiene ``date``, ``admissions >= 0`` y ``alerts >= 0``.

    Invariante:
        - Operación de solo lectura que agrupa eventos en la zona horaria local configurada sin
          alterar registros de pacientes ni alertas.
    """
    assert isinstance(days, int), "days debe ser un entero."
    assert now is None or isinstance(now, datetime), "now debe ser datetime o None."

    if not 1 <= days <= MAX_SERIES_DAYS:
        raise DomainError(f"El rango debe estar entre 1 y {MAX_SERIES_DAYS} días.")
    end = timezone.localdate(now or timezone.now())
    start = end - timedelta(days=days - 1)
    tz = timezone.get_current_timezone()

    def per_day(queryset: Any, field: str) -> dict[date, int]:
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
    series = [
        {
            "date": start + timedelta(days=offset),
            "admissions": admissions.get(start + timedelta(days=offset), 0),
            "alerts": alerts.get(start + timedelta(days=offset), 0),
        }
        for offset in range(days)
    ]

    assert len(series) == days, "La serie resultante debe contener exactamente 'days' puntos."
    assert series[0]["date"] == start and series[-1]["date"] == end, (
        "Los extremos de la serie no coinciden con el rango temporal calculado."
    )
    assert all(point["admissions"] >= 0 and point["alerts"] >= 0 for point in series), (
        "Los conteos diarios de ingresos y alertas no pueden ser negativos."
    )
    return series
