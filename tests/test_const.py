"""Tests for Onna legacy const address registry — fancoil entities."""
from custom_components.onna.const import (
    _LEGACY_SENSOR_ADDRESSES as SENSOR_ADDRESSES,
    _LEGACY_VALVE_ADDRESSES as VALVE_ADDRESSES,
    _LEGACY_FAN_ADDRESSES as FAN_ADDRESSES,
)


def test_fancoil_salon_is_registered_as_fan():
    assert "fancoil_salon" in FAN_ADDRESSES
    name, valve_addr, speed_addr, speed_write = FAN_ADDRESSES["fancoil_salon"]
    assert name == "Fancoil Salón"
    assert valve_addr == "1_7_1"
    assert speed_addr == "1_7_3"
    assert speed_write == "1_7_2"


def test_fancoil_salon_valve_not_in_valve_addresses():
    assert "1_7_1" not in VALVE_ADDRESSES


def test_fancoil_salon_speed_not_in_sensor_addresses():
    assert "1_7_3" not in SENSOR_ADDRESSES
