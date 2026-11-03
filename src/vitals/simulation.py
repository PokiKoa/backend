import random
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from . import rules
from .rules import SleepState

# Objetivos derivados de los umbrales por defecto para no duplicar rangos clínicos
NORMAL_TARGETS = {
    "heart_rate": (rules.DEFAULT_HR_WARNING_LOW + rules.DEFAULT_HR_WARNING_HIGH) / 2,
    "spo2": (rules.DEFAULT_SPO2_WARNING_LOW + rules.SPO2_MAX) / 2,
    "temperature": float(
        (rules.DEFAULT_TEMP_WARNING_LOW + rules.DEFAULT_TEMP_WARNING_HIGH) / 2
    ),
}

EPISODE_TARGETS: dict[str, tuple[str, float]] = {
    "bradycardia": ("heart_rate", rules.DEFAULT_HR_CRITICAL_LOW - 10),
    "tachycardia": ("heart_rate", rules.DEFAULT_HR_CRITICAL_HIGH + 10),
    "desaturation": ("spo2", rules.DEFAULT_SPO2_CRITICAL_LOW - 5),
    "hypothermia": ("temperature", float(rules.DEFAULT_TEMP_CRITICAL_LOW) - 0.4),
    "hyperthermia": ("temperature", float(rules.DEFAULT_TEMP_CRITICAL_HIGH) + 0.3),
    "cannula_disconnected": ("", 0.0),
}

NOISE = {"heart_rate": 3.0, "spo2": 0.6, "temperature": 0.05}
LIMITS = {
    "heart_rate": (rules.HEART_RATE_MIN, rules.HEART_RATE_MAX),
    "spo2": (rules.SPO2_MIN, rules.SPO2_MAX),
    "temperature": (float(rules.TEMPERATURE_MIN), float(rules.TEMPERATURE_MAX)),
}


@dataclass
class SimulatedCribState:
    heart_rate: float = NORMAL_TARGETS["heart_rate"]
    spo2: float = NORMAL_TARGETS["spo2"]
    temperature: float = NORMAL_TARGETS["temperature"]
    sleep_state: str = SleepState.ASLEEP
    episode: str | None = None
    episode_ticks_left: int = 0


def _step(current: float, target: float, noise: float, rng: random.Random) -> float:
    # Paseo aleatorio con reversión a la media: evita saltos irreales entre lecturas
    return current + (target - current) * 0.4 + rng.gauss(0, noise)


def next_payload(
    state: SimulatedCribState,
    rng: random.Random,
    *,
    anomaly_rate: float = 0.05,
    episode_ticks: tuple[int, int] = (3, 8),
) -> dict[str, Any]:
    if state.episode is None and rng.random() < anomaly_rate:
        state.episode = rng.choice(list(EPISODE_TARGETS))
        state.episode_ticks_left = rng.randint(*episode_ticks)

    targets = dict(NORMAL_TARGETS)
    if state.episode is not None:
        field_name, target = EPISODE_TARGETS[state.episode]
        if field_name:
            targets[field_name] = target

    for field_name, target in targets.items():
        low, high = LIMITS[field_name]
        value = _step(getattr(state, field_name), target, NOISE[field_name], rng)
        setattr(state, field_name, min(max(value, low), high))

    if rng.random() < 0.05:
        state.sleep_state = (
            SleepState.AWAKE if state.sleep_state == SleepState.ASLEEP else SleepState.ASLEEP
        )

    cannula_connected = state.episode != "cannula_disconnected"

    if state.episode is not None:
        state.episode_ticks_left -= 1
        if state.episode_ticks_left <= 0:
            state.episode = None

    return {
        "heart_rate": round(state.heart_rate),
        "spo2": round(state.spo2),
        "temperature": str(Decimal(str(state.temperature)).quantize(Decimal("0.1"))),
        "sleep_state": str(state.sleep_state),
        "cannula_connected": cannula_connected,
        "iv_line_active": True,
    }
