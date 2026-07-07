"""Tests for OnnaSwitch."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from custom_components.onna.switch import OnnaSwitch



def _make_coordinator():
    coord = MagicMock()
    coord.data = {}
    coord.client._onna_id = "TESTID"
    coord.client.async_set_address_value = AsyncMock()
    return coord


def _make_switch():
    sw = OnnaSwitch(_make_coordinator(), "1_7_10", "Fancoil Salón Habilitado")
    # async_added_to_hass now subscribes to the connection signal.
    sw.hass = MagicMock()
    sw.async_on_remove = MagicMock()
    return sw


def test_initial_state_is_unknown():
    sw = _make_switch()
    assert sw.is_on is None


def test_unique_id():
    sw = _make_switch()
    assert sw.unique_id == "onna_switch_1_7_10"


@pytest.mark.anyio
async def test_turn_on_writes_one_and_updates_state():
    sw = _make_switch()
    sw.async_write_ha_state = MagicMock()
    await sw.async_turn_on()
    sw._coordinator.client.async_set_address_value.assert_called_once_with("1_7_10", 1)
    assert sw.is_on is True
    sw.async_write_ha_state.assert_called_once()


@pytest.mark.anyio
async def test_turn_off_writes_zero_and_updates_state():
    sw = _make_switch()
    sw.async_write_ha_state = MagicMock()
    await sw.async_turn_off()
    sw._coordinator.client.async_set_address_value.assert_called_once_with("1_7_10", 0)
    assert sw.is_on is False
    sw.async_write_ha_state.assert_called_once()


@pytest.mark.anyio
async def test_toggle_on_then_off():
    sw = _make_switch()
    sw.async_write_ha_state = MagicMock()
    await sw.async_turn_on()
    assert sw.is_on is True
    await sw.async_turn_off()
    assert sw.is_on is False


# ---------------------------------------------------------------------------
# RestoreEntity — last known state
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_restore_on_state():
    sw = _make_switch()
    last = MagicMock()
    last.state = "on"
    sw.async_get_last_state = AsyncMock(return_value=last)
    await sw.async_added_to_hass()
    assert sw.is_on is True


@pytest.mark.anyio
async def test_restore_off_state():
    sw = _make_switch()
    last = MagicMock()
    last.state = "off"
    sw.async_get_last_state = AsyncMock(return_value=last)
    await sw.async_added_to_hass()
    assert sw.is_on is False


@pytest.mark.anyio
async def test_restore_skipped_when_unavailable():
    sw = _make_switch()
    last = MagicMock()
    last.state = "unavailable"
    sw.async_get_last_state = AsyncMock(return_value=last)
    await sw.async_added_to_hass()
    assert sw.is_on is None


@pytest.mark.anyio
async def test_restore_skipped_when_no_last_state():
    sw = _make_switch()
    sw.async_get_last_state = AsyncMock(return_value=None)
    await sw.async_added_to_hass()
    assert sw.is_on is None


def test_switch_reports_assumed_state():
    """Write-only address with no read-back — HA must render assumed-state UI."""
    sw = _make_switch()
    assert sw._attr_assumed_state is True
