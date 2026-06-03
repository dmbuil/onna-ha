"""Tests for OnnaFan."""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from custom_components.onna.fan import OnnaFan, async_setup_entry
from custom_components.onna.coordinator import SIGNAL_ADDRESS_UPDATE
from custom_components.onna.const import DOMAIN


def _make_coordinator(data=None):
    coord = MagicMock()
    coord.data = data or {}
    coord.client._onna_id = "TESTID"
    coord.client.async_set_address_value = AsyncMock()
    return coord


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

def test_fan_is_off_when_coordinator_has_no_data():
    coord = _make_coordinator()
    fan = OnnaFan(coord, "Fancoil Salón", "1_7_1", "1_7_3", "1_7_2")
    assert fan.is_on is False


def test_fan_is_on_when_valve_address_is_true():
    coord = _make_coordinator({"1_7_1": True})
    fan = OnnaFan(coord, "Fancoil Salón", "1_7_1", "1_7_3", "1_7_2")
    assert fan.is_on is True


def test_fan_is_off_when_valve_address_is_false():
    coord = _make_coordinator({"1_7_1": False})
    fan = OnnaFan(coord, "Fancoil Salón", "1_7_1", "1_7_3", "1_7_2")
    assert fan.is_on is False


def test_fan_percentage_is_none_when_no_data():
    coord = _make_coordinator()
    fan = OnnaFan(coord, "Fancoil Salón", "1_7_1", "1_7_3", "1_7_2")
    assert fan.percentage is None


def test_fan_percentage_from_speed_address():
    coord = _make_coordinator({"1_7_3": 75})
    fan = OnnaFan(coord, "Fancoil Salón", "1_7_1", "1_7_3", "1_7_2")
    assert fan.percentage == 75


def test_fan_override_inactive_on_init():
    coord = _make_coordinator()
    fan = OnnaFan(coord, "Fancoil Salón", "1_7_1", "1_7_3", "1_7_2")
    assert fan._override_active is False


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def test_fan_unique_id_includes_valve_address():
    coord = _make_coordinator()
    fan = OnnaFan(coord, "Fancoil Salón", "1_7_1", "1_7_3", "1_7_2")
    assert fan.unique_id == "onna_1_7_1"


def test_fan_device_info_uses_onna_id():
    coord = _make_coordinator()
    fan = OnnaFan(coord, "Fancoil Salón", "1_7_1", "1_7_3", "1_7_2")
    info = fan.device_info
    assert ("onna", "TESTID") in info["identifiers"]


# ---------------------------------------------------------------------------
# Push updates
# ---------------------------------------------------------------------------

def test_handle_valve_update_sets_is_on():
    coord = _make_coordinator()
    fan = OnnaFan(coord, "Fancoil Salón", "1_7_1", "1_7_3", "1_7_2")
    fan.async_write_ha_state = MagicMock()
    fan._handle_valve_update(True)
    assert fan.is_on is True
    fan.async_write_ha_state.assert_called_once()


def test_handle_valve_update_sets_is_off():
    coord = _make_coordinator({"1_7_1": True})
    fan = OnnaFan(coord, "Fancoil Salón", "1_7_1", "1_7_3", "1_7_2")
    fan.async_write_ha_state = MagicMock()
    fan._handle_valve_update(False)
    assert fan.is_on is False
    fan.async_write_ha_state.assert_called_once()


def test_handle_speed_update_sets_percentage():
    coord = _make_coordinator()
    fan = OnnaFan(coord, "Fancoil Salón", "1_7_1", "1_7_3", "1_7_2")
    fan.async_write_ha_state = MagicMock()
    fan._handle_speed_update(50)
    assert fan.percentage == 50
    fan.async_write_ha_state.assert_called_once()


# ---------------------------------------------------------------------------
# Dispatcher subscription
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_setup_entry_registers_both_addresses():
    hass = MagicMock()
    entry = MagicMock()
    coord = _make_coordinator()
    hass.data = {DOMAIN: {entry.entry_id: coord}}

    added = []
    await async_setup_entry(hass, entry, lambda entities: added.extend(entities))

    registered = [call.args[0] for call in coord.register_address.call_args_list]
    assert "1_7_1" in registered
    assert "1_7_3" in registered


@pytest.mark.anyio
async def test_async_added_to_hass_connects_both_dispatchers():
    coord = _make_coordinator()
    fan = OnnaFan(coord, "Fancoil Salón", "1_7_1", "1_7_3", "1_7_2")
    fan.hass = MagicMock()
    fan.async_on_remove = MagicMock()

    with patch(
        "custom_components.onna.fan.async_dispatcher_connect",
        return_value=lambda: None,
    ) as mock_connect:
        await fan.async_added_to_hass()

    signals = [call.args[1] for call in mock_connect.call_args_list]
    assert SIGNAL_ADDRESS_UPDATE.format(address_id="1_7_1") in signals
    assert SIGNAL_ADDRESS_UPDATE.format(address_id="1_7_3") in signals


# ---------------------------------------------------------------------------
# Manual override — write methods
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_turn_on_writes_last_known_speed():
    coord = _make_coordinator({"1_7_3": 60})
    fan = OnnaFan(coord, "Fancoil Salón", "1_7_1", "1_7_3", "1_7_2")
    fan.async_write_ha_state = MagicMock()
    await fan.async_turn_on()
    coord.client.async_set_address_value.assert_called_once_with("1_7_2", 60)
    assert fan._override_active is True
    assert fan.is_on is True
    assert fan.percentage == 60


@pytest.mark.anyio
async def test_turn_on_defaults_to_50_when_no_last_speed():
    coord = _make_coordinator()
    fan = OnnaFan(coord, "Fancoil Salón", "1_7_1", "1_7_3", "1_7_2")
    fan.async_write_ha_state = MagicMock()
    await fan.async_turn_on()
    coord.client.async_set_address_value.assert_called_once_with("1_7_2", 50)
    assert fan.percentage == 50


@pytest.mark.anyio
async def test_turn_on_defaults_to_50_when_last_speed_is_zero():
    coord = _make_coordinator({"1_7_3": 0})
    fan = OnnaFan(coord, "Fancoil Salón", "1_7_1", "1_7_3", "1_7_2")
    fan.async_write_ha_state = MagicMock()
    await fan.async_turn_on()
    coord.client.async_set_address_value.assert_called_once_with("1_7_2", 50)


@pytest.mark.anyio
async def test_turn_on_uses_explicit_percentage():
    coord = _make_coordinator({"1_7_3": 60})
    fan = OnnaFan(coord, "Fancoil Salón", "1_7_1", "1_7_3", "1_7_2")
    fan.async_write_ha_state = MagicMock()
    await fan.async_turn_on(percentage=80)
    coord.client.async_set_address_value.assert_called_once_with("1_7_2", 80)
    assert fan.percentage == 80


@pytest.mark.anyio
async def test_turn_off_writes_zero():
    coord = _make_coordinator({"1_7_1": True, "1_7_3": 75})
    fan = OnnaFan(coord, "Fancoil Salón", "1_7_1", "1_7_3", "1_7_2")
    fan.async_write_ha_state = MagicMock()
    await fan.async_turn_off()
    coord.client.async_set_address_value.assert_called_once_with("1_7_2", 0)
    assert fan._override_active is True
    assert fan.is_on is False
    assert fan.percentage == 0


@pytest.mark.anyio
async def test_set_percentage_writes_value():
    coord = _make_coordinator()
    fan = OnnaFan(coord, "Fancoil Salón", "1_7_1", "1_7_3", "1_7_2")
    fan.async_write_ha_state = MagicMock()
    await fan.async_set_percentage(35)
    coord.client.async_set_address_value.assert_called_once_with("1_7_2", 35)
    assert fan._override_active is True
    assert fan.percentage == 35
    assert fan.is_on is True


@pytest.mark.anyio
async def test_set_percentage_zero_turns_off():
    coord = _make_coordinator({"1_7_1": True, "1_7_3": 50})
    fan = OnnaFan(coord, "Fancoil Salón", "1_7_1", "1_7_3", "1_7_2")
    fan.async_write_ha_state = MagicMock()
    await fan.async_set_percentage(0)
    coord.client.async_set_address_value.assert_called_once_with("1_7_2", 0)
    assert fan.is_on is False


# RestoreEntity — last known state
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_fan_restore_on_with_percentage():
    coord = _make_coordinator()
    fan = OnnaFan(coord, "Fancoil Salón", "1_7_1", "1_7_3", "1_7_2")
    fan.hass = MagicMock()
    fan.async_on_remove = MagicMock()
    last = MagicMock()
    last.state = "on"
    last.attributes = {"percentage": 75}
    fan.async_get_last_state = AsyncMock(return_value=last)
    with patch("custom_components.onna.fan.async_dispatcher_connect", return_value=lambda: None):
        await fan.async_added_to_hass()
    assert fan._is_on is True
    assert fan._percentage == 75


@pytest.mark.anyio
async def test_fan_restore_off():
    coord = _make_coordinator()
    fan = OnnaFan(coord, "Fancoil Salón", "1_7_1", "1_7_3", "1_7_2")
    fan.hass = MagicMock()
    fan.async_on_remove = MagicMock()
    last = MagicMock()
    last.state = "off"
    last.attributes = {}
    fan.async_get_last_state = AsyncMock(return_value=last)
    with patch("custom_components.onna.fan.async_dispatcher_connect", return_value=lambda: None):
        await fan.async_added_to_hass()
    assert fan._is_on is False


@pytest.mark.anyio
async def test_fan_restore_skipped_when_unavailable():
    coord = _make_coordinator({"1_7_1": True, "1_7_3": 50})
    fan = OnnaFan(coord, "Fancoil Salón", "1_7_1", "1_7_3", "1_7_2")
    fan.hass = MagicMock()
    fan.async_on_remove = MagicMock()
    last = MagicMock()
    last.state = "unavailable"
    last.attributes = {}  # no attributes when unavailable
    fan.async_get_last_state = AsyncMock(return_value=last)
    with patch("custom_components.onna.fan.async_dispatcher_connect", return_value=lambda: None):
        await fan.async_added_to_hass()
    assert fan._is_on is True   # unchanged from coordinator seed
    assert fan._percentage == 50


@pytest.mark.anyio
async def test_fan_restore_skipped_when_no_last_state():
    coord = _make_coordinator()
    fan = OnnaFan(coord, "Fancoil Salón", "1_7_1", "1_7_3", "1_7_2")
    fan.hass = MagicMock()
    fan.async_on_remove = MagicMock()
    fan.async_get_last_state = AsyncMock(return_value=None)
    with patch("custom_components.onna.fan.async_dispatcher_connect", return_value=lambda: None):
        await fan.async_added_to_hass()
    assert fan._is_on is False  # default
