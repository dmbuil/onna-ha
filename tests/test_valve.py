"""Tests for OnnaValve."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.onna.valve import OnnaPositionValve, OnnaValve
from custom_components.onna.coordinator import SIGNAL_ADDRESS_UPDATE


def _make_coordinator(data=None):
    coord = MagicMock()
    coord.data = data or {}
    coord.client._onna_id = "TESTID"
    return coord


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

def test_valve_is_closed_when_coordinator_has_no_data():
    coord = _make_coordinator()
    valve = OnnaValve(coord, "0_0_6", "Válvulas Colector", "water")
    assert valve.is_closed is True


def test_valve_is_open_when_coordinator_data_is_true():
    coord = _make_coordinator({"0_0_6": True})
    valve = OnnaValve(coord, "0_0_6", "Válvulas Colector", "water")
    assert valve.is_closed is False


def test_valve_is_closed_when_coordinator_data_is_false():
    coord = _make_coordinator({"0_0_6": False})
    valve = OnnaValve(coord, "0_0_6", "Válvulas Colector", "water")
    assert valve.is_closed is True


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def test_valve_unique_id_includes_address():
    coord = _make_coordinator()
    valve = OnnaValve(coord, "0_0_6", "Válvulas Colector", "water")
    assert valve.unique_id == "onna_0_0_6"


def test_valve_device_class_is_water():
    from homeassistant.components.valve import ValveDeviceClass
    coord = _make_coordinator()
    valve = OnnaValve(coord, "0_0_6", "Válvulas Colector", "water")
    assert valve.device_class == ValveDeviceClass.WATER


def test_valve_reports_no_position():
    coord = _make_coordinator()
    valve = OnnaValve(coord, "0_0_6", "Válvulas Colector", "water")
    assert valve.reports_position is False


def test_valve_device_info_uses_onna_id():
    coord = _make_coordinator()
    valve = OnnaValve(coord, "0_0_6", "Válvulas Colector", "water")
    info = valve.device_info
    assert ("onna", "TESTID") in info["identifiers"]


# ---------------------------------------------------------------------------
# Push update
# ---------------------------------------------------------------------------

def test_handle_update_open_writes_state():
    coord = _make_coordinator()
    valve = OnnaValve(coord, "0_0_6", "Válvulas Colector", "water")
    valve.async_write_ha_state = MagicMock()
    valve._handle_update(True)
    assert valve.is_closed is False
    valve.async_write_ha_state.assert_called_once()


def test_handle_update_close_writes_state():
    coord = _make_coordinator({"0_0_6": True})
    valve = OnnaValve(coord, "0_0_6", "Válvulas Colector", "water")
    valve.async_write_ha_state = MagicMock()
    valve._handle_update(False)
    assert valve.is_closed is True
    valve.async_write_ha_state.assert_called_once()


@pytest.mark.anyio
async def test_async_added_to_hass_connects_dispatcher():
    coord = _make_coordinator()
    valve = OnnaValve(coord, "0_0_6", "Válvulas Colector", "water")
    valve.hass = MagicMock()
    valve.async_on_remove = MagicMock()

    with patch(
        "custom_components.onna.valve.async_dispatcher_connect",
        return_value=lambda: None,
    ) as mock_connect:
        await valve.async_added_to_hass()

    expected_signal = SIGNAL_ADDRESS_UPDATE.format(address_id="0_0_6")
    mock_connect.assert_called_once_with(
        valve.hass, expected_signal, valve._handle_update
    )


# RestoreEntity — OnnaValve
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_valve_restore_open():
    coord = _make_coordinator()
    valve = OnnaValve(coord, "0_0_6", "Válvulas Colector", "water")
    valve.hass = MagicMock()
    valve.async_on_remove = MagicMock()
    last = MagicMock()
    last.state = "open"
    valve.async_get_last_state = AsyncMock(return_value=last)
    with patch("custom_components.onna.valve.async_dispatcher_connect", return_value=lambda: None):
        await valve.async_added_to_hass()
    assert valve.is_closed is False


@pytest.mark.anyio
async def test_valve_restore_closed():
    coord = _make_coordinator()
    valve = OnnaValve(coord, "0_0_6", "Válvulas Colector", "water")
    valve.hass = MagicMock()
    valve.async_on_remove = MagicMock()
    last = MagicMock()
    last.state = "closed"
    valve.async_get_last_state = AsyncMock(return_value=last)
    with patch("custom_components.onna.valve.async_dispatcher_connect", return_value=lambda: None):
        await valve.async_added_to_hass()
    assert valve.is_closed is True


@pytest.mark.anyio
async def test_valve_restore_skipped_when_unavailable():
    coord = _make_coordinator({"0_0_6": True})  # open
    valve = OnnaValve(coord, "0_0_6", "Válvulas Colector", "water")
    valve.hass = MagicMock()
    valve.async_on_remove = MagicMock()
    last = MagicMock()
    last.state = "unavailable"
    valve.async_get_last_state = AsyncMock(return_value=last)
    with patch("custom_components.onna.valve.async_dispatcher_connect", return_value=lambda: None):
        await valve.async_added_to_hass()
    assert valve.is_closed is False  # unchanged from coordinator seed


# RestoreEntity — OnnaPositionValve
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_position_valve_restore_state_and_position():
    coord = _make_coordinator()
    valve = OnnaPositionValve(coord, "1_0_8", "1_0_6", "Salón Demanda Suelo", "water")
    valve.hass = MagicMock()
    valve.async_on_remove = MagicMock()
    last = MagicMock()
    last.state = "open"
    last.attributes = {"current_position": 65}
    valve.async_get_last_state = AsyncMock(return_value=last)
    with patch("custom_components.onna.valve.async_dispatcher_connect", return_value=lambda: None):
        await valve.async_added_to_hass()
    assert valve.is_closed is False
    assert valve.current_valve_position == 65


@pytest.mark.anyio
async def test_position_valve_restore_skipped_when_no_last_state():
    coord = _make_coordinator({"1_0_8": 30, "1_0_6": False})
    valve = OnnaPositionValve(coord, "1_0_8", "1_0_6", "Salón Demanda Suelo", "water")
    valve.hass = MagicMock()
    valve.async_on_remove = MagicMock()
    valve.async_get_last_state = AsyncMock(return_value=None)
    with patch("custom_components.onna.valve.async_dispatcher_connect", return_value=lambda: None):
        await valve.async_added_to_hass()
    assert valve.current_valve_position == 30
    assert valve.is_closed is True  # unchanged from coordinator seed
