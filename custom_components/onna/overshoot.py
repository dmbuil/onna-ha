"""Per-zone overshoot (slab-inertia) learner — pure logic, no Home Assistant deps.

The Onna KNX controller runs its own PI loop per zone; when a zone's demand flag
(1_X_7) falls the actuator head closes and the loop stops circulating water, but
the radiant slab keeps releasing (heating) or absorbing (cooling) stored energy,
so the room temperature coasts past the setpoint.  This class learns that coast
per zone and per season from the *external room sensor* and returns a damping
value the entity subtracts from (winter) or adds to (summer) the written
setpoint so the room stops closer to target.

The class is deliberately time-free: the climate entity owns the coast-window
timer (async_call_later) and simply calls close_sample() when it elapses or when
demand re-fires.  ``observe`` is fed the external temperature on each reading.
"""
from __future__ import annotations

# Overshoot samples are clamped to a sane band; a coast beyond 3 C is treated as
# a measurement artefact (door opened, sensor glitch) and capped.
SAMPLE_MAX = 3.0
# Exponential-moving-average weight for a fresh sample against the learned value.
EMA_ALPHA = 0.3
# Damping is only applied once the learned coast is meaningful (below this it is
# within sensor noise and not worth nudging the setpoint for).
APPLY_THRESHOLD = 0.2
# Absolute ceiling on the damping ever applied to a setpoint.
DAMPING_MAX = 2.0


class OvershootLearner:
    """Learns and applies per-season overshoot damping for one zone."""

    def __init__(self, learned_heat: float = 0.0, learned_cool: float = 0.0) -> None:
        self._learned_heat = float(learned_heat)
        self._learned_cool = float(learned_cool)
        self._sampling = False
        self._start = 0.0
        self._extreme = 0.0
        self._is_winter = True

    @property
    def learned_heat(self) -> float:
        return self._learned_heat

    @property
    def learned_cool(self) -> float:
        return self._learned_cool

    @property
    def sampling(self) -> bool:
        return self._sampling

    def start_sample(self, start_temp: float, is_winter: bool) -> None:
        """Begin a coast sample at demand-off; records the starting room temp."""
        self._sampling = True
        self._start = float(start_temp)
        self._extreme = float(start_temp)
        self._is_winter = bool(is_winter)

    def observe(self, ext_temp: float) -> None:
        """Track the peak (winter) or trough (summer) during the coast window."""
        if not self._sampling:
            return
        value = float(ext_temp)
        if self._is_winter:
            self._extreme = max(self._extreme, value)
        else:
            self._extreme = min(self._extreme, value)

    def close_sample(self) -> None:
        """Finalise the in-flight sample and blend it into the learned value."""
        if not self._sampling:
            return
        if self._is_winter:
            sample = self._extreme - self._start
        else:
            sample = self._start - self._extreme
        sample = max(0.0, min(SAMPLE_MAX, sample))
        blended = round(EMA_ALPHA * sample + (1 - EMA_ALPHA) * (
            self._learned_heat if self._is_winter else self._learned_cool
        ), 10)
        if self._is_winter:
            self._learned_heat = blended
        else:
            self._learned_cool = blended
        self._sampling = False

    def invalidate(self) -> None:
        """Discard the in-flight sample without learning from it."""
        self._sampling = False

    def damping(self, is_winter: bool) -> float:
        """Return the damping (C) to remove from the written active setpoint."""
        learned = self._learned_heat if is_winter else self._learned_cool
        if learned < APPLY_THRESHOLD:
            return 0.0
        return min(learned, DAMPING_MAX)

    def as_dict(self) -> dict[str, float]:
        return {"heat": self._learned_heat, "cool": self._learned_cool}

    @classmethod
    def from_dict(cls, data: dict) -> "OvershootLearner":
        return cls(
            learned_heat=float(data.get("heat", 0.0)),
            learned_cool=float(data.get("cool", 0.0)),
        )
