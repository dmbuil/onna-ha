"""Tests for the pure-logic seasonal EMA + gating decision (no HA deps)."""
import math

from custom_components.onna.seasonal import OutdoorEMA, evaluate_gate, EMA_TAU_S


def test_first_reading_seeds_value():
    ema = OutdoorEMA()
    ema.update(now=1000.0, reading=10.0)
    assert ema.value == 10.0
    assert ema.updated_at == 1000.0


def test_update_moves_toward_reading_by_time_weight():
    ema = OutdoorEMA(value=10.0, updated_at=0.0)
    dt = EMA_TAU_S  # one time-constant later
    ema.update(now=dt, reading=20.0)
    alpha = 1 - math.exp(-1.0)  # dt/tau = 1
    assert ema.value == 10.0 + alpha * (20.0 - 10.0)
    assert ema.updated_at == dt


def test_zero_dt_update_does_not_move():
    ema = OutdoorEMA(value=15.0, updated_at=500.0)
    ema.update(now=500.0, reading=25.0)
    assert ema.value == 15.0


def test_round_trip_serialization():
    ema = OutdoorEMA(value=12.5, updated_at=999.0)
    restored = OutdoorEMA.from_dict(ema.as_dict())
    assert restored.value == 12.5
    assert restored.updated_at == 999.0


def test_gate_fails_open_when_ema_none():
    assert evaluate_gate(True, None, 20.0, 16.0, currently_gated=False) is False
    assert evaluate_gate(False, None, 20.0, 16.0, currently_gated=False) is False


def test_winter_gates_when_warm_beyond_upper_hysteresis():
    # not gated → needs ema > heat_off_above + hysteresis (20.5)
    assert evaluate_gate(True, 20.6, 20.0, 16.0, currently_gated=False) is True
    assert evaluate_gate(True, 20.4, 20.0, 16.0, currently_gated=False) is False


def test_winter_clears_only_below_lower_hysteresis():
    # gated → stays gated until ema < heat_off_above - hysteresis (19.5)
    assert evaluate_gate(True, 19.6, 20.0, 16.0, currently_gated=True) is True
    assert evaluate_gate(True, 19.4, 20.0, 16.0, currently_gated=True) is False


def test_summer_gates_when_cold_below_lower_hysteresis():
    # not gated → needs ema < cool_off_below - hysteresis (15.5)
    assert evaluate_gate(False, 15.4, 20.0, 16.0, currently_gated=False) is True
    assert evaluate_gate(False, 15.6, 20.0, 16.0, currently_gated=False) is False


def test_summer_clears_only_above_upper_hysteresis():
    # gated → stays gated until ema > cool_off_below + hysteresis (16.5)
    assert evaluate_gate(False, 16.4, 20.0, 16.0, currently_gated=True) is True
    assert evaluate_gate(False, 16.6, 20.0, 16.0, currently_gated=True) is False
