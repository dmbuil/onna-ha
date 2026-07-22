"""Tests for OnnaCoordinator connection-state handling."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.onna.coordinator import OnnaCoordinator, SIGNAL_CONNECTION


def _make_coordinator():
    hass = MagicMock()
    client = MagicMock()
    client.connected = False
    client.on_connection_change = None
    return OnnaCoordinator(hass, client), hass, client


# Connection-state wiring
# ---------------------------------------------------------------------------

def test_coordinator_registers_connection_callback_on_client():
    coord, _hass, client = _make_coordinator()
    assert client.on_connection_change == coord._handle_connection_change


def test_connected_property_mirrors_client():
    coord, _hass, client = _make_coordinator()
    client.connected = False
    assert coord.connected is False
    client.connected = True
    assert coord.connected is True


def test_connection_change_dispatches_signal():
    coord, hass, _client = _make_coordinator()
    with patch(
        "custom_components.onna.coordinator.async_dispatcher_send"
    ) as mock_send:
        coord._handle_connection_change(False)
    mock_send.assert_called_once_with(hass, SIGNAL_CONNECTION, False)


# Shutdown
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_async_stop_shuts_down_client():
    coord, _hass, client = _make_coordinator()
    client.async_shutdown = AsyncMock()
    await coord.async_stop()
    client.async_shutdown.assert_called_once()


# ---------------------------------------------------------------------------
# Seasonal gating
# ---------------------------------------------------------------------------

def test_seasonal_gate_defaults_off_and_no_source():
    coord = OnnaCoordinator(MagicMock(), MagicMock())
    assert coord.seasonal_gate_active is False
    assert coord.outdoor_ema_snapshot() == (None, None)


def test_apply_reading_winter_gate_dispatches_on_crossing():
    from custom_components.onna import coordinator as coord_mod
    from custom_components.onna.coordinator import SIGNAL_SEASONAL_GATE

    coord = OnnaCoordinator(MagicMock(), MagicMock())
    coord.data["0_0_7"] = True  # winter
    coord.configure_seasonal("weather.home", heat_off_above=20.0, cool_off_below=16.0)

    with patch.object(coord_mod, "async_dispatcher_send") as send:
        # first reading seeds EMA at 25 (> 20.5) → gate turns on, dispatch True
        coord._apply_reading(now=0.0, reading=25.0)
        assert coord.seasonal_gate_active is True
        send.assert_called_once_with(coord.hass, SIGNAL_SEASONAL_GATE, True)


def test_apply_reading_no_dispatch_when_gate_unchanged():
    from custom_components.onna import coordinator as coord_mod

    coord = OnnaCoordinator(MagicMock(), MagicMock())
    coord.data["0_0_7"] = True
    coord.configure_seasonal("weather.home", 20.0, 16.0)
    with patch.object(coord_mod, "async_dispatcher_send") as send:
        coord._apply_reading(now=0.0, reading=10.0)   # cold, no winter gate
        assert coord.seasonal_gate_active is False
        send.assert_not_called()


def test_seed_outdoor_ema_restores_snapshot():
    coord = OnnaCoordinator(MagicMock(), MagicMock())
    coord.seed_outdoor_ema(18.0, 123.0)
    assert coord.outdoor_ema_snapshot() == (18.0, 123.0)


def test_read_outdoor_from_weather_attribute():
    coord = OnnaCoordinator(MagicMock(), MagicMock())
    coord._outdoor_entity = "weather.home"
    state = MagicMock()
    state.domain = "weather"
    state.state = "sunny"
    state.attributes = {"temperature": 22.5}
    assert coord._read_outdoor(state) == 22.5


def test_read_outdoor_from_sensor_state():
    coord = OnnaCoordinator(MagicMock(), MagicMock())
    coord._outdoor_entity = "sensor.outdoor"
    state = MagicMock()
    state.domain = "sensor"
    state.state = "12.0"
    state.attributes = {}
    assert coord._read_outdoor(state) == 12.0


def test_read_outdoor_returns_none_on_unavailable():
    coord = OnnaCoordinator(MagicMock(), MagicMock())
    coord._outdoor_entity = "sensor.outdoor"
    state = MagicMock()
    state.domain = "sensor"
    state.state = "unavailable"
    state.attributes = {}
    assert coord._read_outdoor(state) is None


@pytest.mark.anyio
async def test_start_seasonal_noop_without_source():
    coord = OnnaCoordinator(MagicMock(), MagicMock())
    coord.configure_seasonal(None, 20.0, 16.0)
    await coord.async_start_seasonal()  # must not raise, no trackers
    assert coord._seasonal_unsubs == []
