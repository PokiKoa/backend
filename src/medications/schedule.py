from dataclasses import dataclass
from datetime import datetime, timedelta

from .models import Prescription, PrescriptionStatus

# Fuente única de verdad para las ventanas de administración
EARLY_ADMINISTRATION_WINDOW = timedelta(minutes=60)
OVERDUE_GRACE = timedelta(minutes=30)

_UNSET = object()


def _interval(prescription: Prescription) -> timedelta | None:
    if prescription.frequency_hours is None:
        return None
    return timedelta(hours=prescription.frequency_hours)


def last_slot(prescription: Prescription) -> datetime | None:
    """Última dosis programada; None si la indicación recurrente no tiene término."""
    interval = _interval(prescription)
    if interval is None:
        return prescription.starts_at
    if prescription.ends_at is None:
        return None
    steps = (prescription.ends_at - prescription.starts_at) // interval
    return prescription.starts_at + steps * interval


def is_valid_slot(prescription: Prescription, when: datetime) -> bool:
    if when < prescription.starts_at:
        return False
    interval = _interval(prescription)
    if interval is None:
        return when == prescription.starts_at
    end = last_slot(prescription)
    if end is not None and when > end:
        return False
    return (when - prescription.starts_at) % interval == timedelta(0)


def latest_due_slot(prescription: Prescription, now: datetime) -> datetime | None:
    """Dosis más reciente que ya puede administrarse (incluye la ventana de anticipación)."""
    horizon = now + EARLY_ADMINISTRATION_WINDOW
    if prescription.starts_at > horizon:
        return None
    interval = _interval(prescription)
    if interval is None:
        return prescription.starts_at
    slot = prescription.starts_at + ((horizon - prescription.starts_at) // interval) * interval
    end = last_slot(prescription)
    return min(slot, end) if end is not None else slot


def next_slot_after(prescription: Prescription, after: datetime | None) -> datetime | None:
    if after is None or after < prescription.starts_at:
        return prescription.starts_at
    interval = _interval(prescription)
    if interval is None:
        return None
    slot = prescription.starts_at + ((after - prescription.starts_at) // interval + 1) * interval
    end = last_slot(prescription)
    if end is not None and slot > end:
        return None
    return slot


@dataclass(frozen=True)
class ScheduleState:
    next_dose_at: datetime | None
    is_overdue: bool
    last_administered_slot: datetime | None
    administrations_count: int


def schedule_state(prescription: Prescription, now: datetime) -> ScheduleState:
    # Las anotaciones del queryset evitan una consulta por indicación en los listados
    last_given = getattr(prescription, "last_administered_slot", _UNSET)
    count = getattr(prescription, "administrations_count", _UNSET)
    if last_given is _UNSET or count is _UNSET:
        slots = list(
            prescription.administrations.order_by("-scheduled_for").values_list(
                "scheduled_for", flat=True
            )
        )
        last_given = slots[0] if slots else None
        count = len(slots)

    next_dose = None
    if prescription.status == PrescriptionStatus.ACTIVE:
        next_dose = next_slot_after(prescription, last_given)

    return ScheduleState(
        next_dose_at=next_dose,
        is_overdue=next_dose is not None and next_dose + OVERDUE_GRACE < now,
        last_administered_slot=last_given,
        administrations_count=count,
    )
