"""Seasonal gating logic — outdoor EMA + gate decision.  Pure, no HA deps.

Time is passed in (as a POSIX timestamp) so the class is trivially unit-tested
and so the value can be persisted and restored across restarts without resetting
the average.  The coordinator owns one instance for the whole installation.
"""
from __future__ import annotations

import math

# Time constant of the outdoor exponential moving average (48 hours).  Long
# enough that a single warm afternoon in winter does not gate the heating, but
# a genuine warm spell does.
EMA_TAU_S = 48 * 3600


class OutdoorEMA:
    """Time-weighted exponential moving average of an outdoor temperature."""

    def __init__(
        self,
        tau_s: float = EMA_TAU_S,
        value: float | None = None,
        updated_at: float | None = None,
    ) -> None:
        self._tau_s = float(tau_s)
        self._value = value
        self._updated_at = updated_at

    @property
    def value(self) -> float | None:
        return self._value

    @property
    def updated_at(self) -> float | None:
        return self._updated_at

    def update(self, now: float, reading: float) -> None:
        """Fold a new reading into the average using elapsed-time weighting."""
        reading = float(reading)
        if self._value is None or self._updated_at is None:
            self._value = reading
            self._updated_at = now
            return
        dt = max(0.0, now - self._updated_at)
        alpha = 1 - math.exp(-dt / self._tau_s)
        self._value += alpha * (reading - self._value)
        self._updated_at = now

    def as_dict(self) -> dict:
        return {"value": self._value, "updated_at": self._updated_at}

    @classmethod
    def from_dict(cls, data: dict, tau_s: float = EMA_TAU_S) -> "OutdoorEMA":
        return cls(
            tau_s=tau_s,
            value=data.get("value"),
            updated_at=data.get("updated_at"),
        )


def evaluate_gate(
    is_winter: bool,
    ema: float | None,
    heat_off_above: float,
    cool_off_below: float,
    currently_gated: bool,
    hysteresis: float = 0.5,
) -> bool:
    """Return whether zones should be paused for the current outdoor climate.

    Winter (heating): gate when the outdoor average is warm.  Summer (cooling):
    gate when it is cold.  A hysteresis band around each threshold prevents the
    gate from flapping.  When no average exists yet (source never available),
    fail open — never gate.
    """
    if ema is None:
        return False
    if is_winter:
        if currently_gated:
            return ema >= heat_off_above - hysteresis
        return ema > heat_off_above + hysteresis
    if currently_gated:
        return ema <= cool_off_below + hysteresis
    return ema < cool_off_below - hysteresis
