"""Tests for OnnaBinarySensor."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from custom_components.onna.binary_sensor import OnnaBinarySensor
from custom_components.onna.coordinator import SIGNAL_ADDRESS_UPDATE


def _make_coordinator(data=None):
    coord = MagicMock()
    coord.data = data or {}
    coord.client._onna_id = "TESTID"
    return coord


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

def test_binary_sensor_is_off_when_coordinator_has_no_data():
    coord = _make_coordinator()
    sensor = OnnaBinarySensor(coord, "0_4_2", "Alarma Inundación", "moisture", False)
    assert sensor.is_on is False


def test_binary_sensor_is_on_when_coordinator_data_is_true():
    coord = _make_coordinator({"0_4_2": True})
    sensor = OnnaBinarySensor(coord, "0_4_2", "Alarma Inundación", "moisture", False)
    assert sensor.is_on is True


def test_binary_sensor_is_off_when_coordinator_data_is_false():
    coord = _make_coordinator({"0_4_2": False})
    sensor = OnnaBinarySensor(coord, "0_4_2", "Alarma Inundación", "moisture", False)
    assert sensor.is_on is False


def test_binary_sensor_inverted_flips_is_on():
    coord = _make_coordinator({"0_0_7": False})
    sensor = OnnaBinarySensor(coord, "0_0_7", "Modo Invierno", None, True)
    assert sensor.is_on is True


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def test_binary_sensor_unique_id_includes_address():
    coord = _make_coordinator()
    sensor = OnnaBinarySensor(coord, "0_4_2", "Alarma Inundación", "moisture", False)
    assert sensor.unique_id == "onna_0_4_2"


def test_binary_sensor_device_class_set_from_string():
    coord = _make_coordinator()
    sensor = OnnaBinarySensor(coord, "0_4_2", "Alarma Inundación", "moisture", False)
    assert sensor.device_class == BinarySensorDeviceClass.MOISTURE


def test_binary_sensor_no_device_class_when_none():
    coord = _make_coordinator()
    sensor = OnnaBinarySensor(coord, "0_0_7", "Modo Invierno", None, False)
    assert sensor.device_class is None


def test_binary_sensor_device_info_uses_onna_id():
    coord = _make_coordinator()
    sensor = OnnaBinarySensor(coord, "0_4_2", "Alarma Inundación", "moisture", False)
    info = sensor.device_info
    assert ("onna", "TESTID") in info["identifiers"]


# ---------------------------------------------------------------------------
# Push update
# ---------------------------------------------------------------------------

def test_handle_update_sets_is_on_and_writes_state():
    coord = _make_coordinator()
    sensor = OnnaBinarySensor(coord, "0_4_2", "Alarma Inundación", "moisture", False)
    sensor.async_write_ha_state = MagicMock()
    sensor._handle_update(True)
    assert sensor.is_on is True
    sensor.async_write_ha_state.assert_called_once()


def test_handle_update_inverted_flips_value():
    coord = _make_coordinator()
    sensor = OnnaBinarySensor(coord, "0_0_7", "Modo Invierno", None, True)
    sensor.async_write_ha_state = MagicMock()
    sensor._handle_update(False)
    assert sensor.is_on is True


@pytest.mark.anyio
async def test_async_added_to_hass_connects_dispatcher():
    coord = _make_coordinator()
    sensor = OnnaBinarySensor(coord, "0_4_2", "Alarma Inundación", "moisture", False)
    sensor.hass = MagicMock()
    sensor.async_on_remove = MagicMock()

    with patch(
        "custom_components.onna.binary_sensor.async_dispatcher_connect",
        return_value=lambda: None,
    ) as mock_connect:
        await sensor.async_added_to_hass()

    expected_signal = SIGNAL_ADDRESS_UPDATE.format(address_id="0_4_2")
    mock_connect.assert_called_once_with(
        sensor.hass, expected_signal, sensor._handle_update
    )


# RestoreEntity — last known state
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_restore_state_on():
    coord = _make_coordinator()
    sensor = OnnaBinarySensor(coord, "0_4_2", "Alarma Inundación", "moisture", False)
    sensor.hass = MagicMock()
    sensor.async_on_remove = MagicMock()
    last = MagicMock()
    last.state = "on"
    sensor.async_get_last_state = AsyncMock(return_value=last)
    with patch("custom_components.onna.binary_sensor.async_dispatcher_connect", return_value=lambda: None):
        await sensor.async_added_to_hass()
    assert sensor.is_on is True


@pytest.mark.anyio
async def test_restore_state_off():
    coord = _make_coordinator()
    sensor = OnnaBinarySensor(coord, "0_4_2", "Alarma Inundación", "moisture", False)
    sensor.hass = MagicMock()
    sensor.async_on_remove = MagicMock()
    last = MagicMock()
    last.state = "off"
    sensor.async_get_last_state = AsyncMock(return_value=last)
    with patch("custom_components.onna.binary_sensor.async_dispatcher_connect", return_value=lambda: None):
        await sensor.async_added_to_hass()
    assert sensor.is_on is False


@pytest.mark.anyio
async def test_restore_skipped_when_unavailable():
    coord = _make_coordinator({"0_4_2": False})
    sensor = OnnaBinarySensor(coord, "0_4_2", "Alarma Inundación", "moisture", False)
    sensor.hass = MagicMock()
    sensor.async_on_remove = MagicMock()
    last = MagicMock()
    last.state = "unavailable"
    sensor.async_get_last_state = AsyncMock(return_value=last)
    with patch("custom_components.onna.binary_sensor.async_dispatcher_connect", return_value=lambda: None):
        await sensor.async_added_to_hass()
    assert sensor.is_on is False  # unchanged from coordinator seed


@pytest.mark.anyio
async def test_restore_skipped_when_no_last_state():
    coord = _make_coordinator({"0_4_2": True})
    sensor = OnnaBinarySensor(coord, "0_4_2", "Alarma Inundación", "moisture", False)
    sensor.hass = MagicMock()
    sensor.async_on_remove = MagicMock()
    sensor.async_get_last_state = AsyncMock(return_value=None)
    with patch("custom_components.onna.binary_sensor.async_dispatcher_connect", return_value=lambda: None):
        await sensor.async_added_to_hass()
    assert sensor.is_on is True  # unchanged from coordinator seed
