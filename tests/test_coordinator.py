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
# State persistence
#
# Onna only announces *changes*: there is no way to read an address's current
# value, and the READ_CONFIGURATION ack carries metadata only.  So an address
# that does not change — 0_0_7 flips twice a year — is invisible to HA after a
# restart, and entities silently fall back to their constructor defaults.  HA
# has to remember the last known value itself.
# ---------------------------------------------------------------------------

def _make_persisting_coordinator(stored=None):
    hass = MagicMock()
    client = MagicMock()
    client.connected = False
    client.on_connection_change = None
    coord = OnnaCoordinator(hass, client, entry_id="abc123")
    coord._store.saved = stored
    return coord


@pytest.mark.anyio
async def test_restores_persisted_addresses_before_entities_are_built():
    coord = _make_persisting_coordinator({"0_0_7": 0, "1_0_3": 21.5})
    await coord.async_restore_data()
    assert coord.data["0_0_7"] == 0
    assert coord.data["1_0_3"] == 21.5


@pytest.mark.anyio
async def test_restore_tolerates_empty_store():
    coord = _make_persisting_coordinator(None)
    await coord.async_restore_data()
    assert coord.data == {}


@pytest.mark.anyio
async def test_live_push_is_persisted():
    coord = _make_persisting_coordinator()
    coord.register_address("0_0_7")
    on_update = coord.client.register_address_callback.call_args.args[1]
    await on_update(1)
    assert coord._store.saved == {"0_0_7": 1}


@pytest.mark.anyio
async def test_async_stop_flushes_pending_snapshot():
    """An options change reloads the entry and discards the coordinator; without
    an explicit flush the next setup would read a snapshot up to 30 s stale."""
    coord = _make_persisting_coordinator()
    coord.client.async_shutdown = AsyncMock()
    coord.data["0_0_7"] = 0
    await coord.async_stop()
    assert coord._store.saved == {"0_0_7": 0}


@pytest.mark.anyio
async def test_only_knx_addresses_are_persisted():
    """Synthetic keys are owned by other restore paths (entity attributes) —
    persisting them here would create a second, competing source of truth."""
    coord = _make_persisting_coordinator()
    coord.data.update({
        "0_0_7": 0,
        "outdoor_ema": 33.3,
        "overshoot_1_0_1": 0.4,
        "cfg_internal_offset": -0.4,
    })
    assert coord._snapshot() == {"0_0_7": 0}


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
        send.assert_any_call(coord.hass, SIGNAL_SEASONAL_GATE, True)


def test_apply_reading_no_gate_dispatch_when_gate_unchanged():
    from custom_components.onna import coordinator as coord_mod
    from custom_components.onna.coordinator import SIGNAL_SEASONAL_GATE

    coord = OnnaCoordinator(MagicMock(), MagicMock())
    coord.data["0_0_7"] = True
    coord.configure_seasonal("weather.home", 20.0, 16.0)
    with patch.object(coord_mod, "async_dispatcher_send") as send:
        coord._apply_reading(now=0.0, reading=10.0)   # cold, no winter gate
        assert coord.seasonal_gate_active is False
        # The EMA signal still fires; only the gate signal must not.
        gate_calls = [
            c for c in send.call_args_list if c.args[1] == SIGNAL_SEASONAL_GATE
        ]
        assert gate_calls == []


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


def test_apply_reading_publishes_outdoor_ema_synthetic_address():
    from custom_components.onna import coordinator as coord_mod
    from custom_components.onna.coordinator import SIGNAL_ADDRESS_UPDATE

    coord = OnnaCoordinator(MagicMock(), MagicMock())
    coord.data["0_0_7"] = True
    coord.configure_seasonal("weather.home", 20.0, 16.0)
    with patch.object(coord_mod, "async_dispatcher_send") as send:
        coord._apply_reading(now=0.0, reading=18.0)
    assert coord.data["outdoor_ema"] == 18.0
    send.assert_any_call(
        coord.hass, SIGNAL_ADDRESS_UPDATE.format(address_id="outdoor_ema"), 18.0
    )


def test_seed_outdoor_ema_populates_synthetic_address():
    coord = OnnaCoordinator(MagicMock(), MagicMock())
    coord.seed_outdoor_ema(17.5, 100.0)
    assert coord.data["outdoor_ema"] == 17.5


# ---------------------------------------------------------------------------
# Smart-thermostat toggle
# ---------------------------------------------------------------------------

def test_smart_enabled_defaults_on():
    coord = OnnaCoordinator(MagicMock(), MagicMock())
    assert coord.smart_enabled is True


def test_set_smart_enabled_dispatches_only_on_change():
    from custom_components.onna import coordinator as coord_mod
    from custom_components.onna.coordinator import SIGNAL_SMART_ENABLED

    coord = OnnaCoordinator(MagicMock(), MagicMock())
    with patch.object(coord_mod, "async_dispatcher_send") as send:
        coord.set_smart_enabled(True)          # already on → no-op
        send.assert_not_called()
        coord.set_smart_enabled(False)
    assert coord.smart_enabled is False
    send.assert_any_call(coord.hass, SIGNAL_SMART_ENABLED, False)


def test_smart_disabled_keeps_gate_closed_but_tracks_ema():
    from custom_components.onna import coordinator as coord_mod

    coord = OnnaCoordinator(MagicMock(), MagicMock())
    coord.data["0_0_7"] = True
    coord.configure_seasonal("weather.home", 20.0, 16.0)
    coord.set_smart_enabled(False)
    with patch.object(coord_mod, "async_dispatcher_send"):
        coord._apply_reading(now=0.0, reading=25.0)   # would open the gate
    assert coord.seasonal_gate_active is False
    # The EMA and its monitoring sensor stay live for a prompt re-enable.
    assert coord.data["outdoor_ema"] == 25.0


def test_disabling_smart_closes_open_gate_and_reenabling_reopens_it():
    from custom_components.onna import coordinator as coord_mod
    from custom_components.onna.coordinator import SIGNAL_SEASONAL_GATE

    coord = OnnaCoordinator(MagicMock(), MagicMock())
    coord.data["0_0_7"] = True
    coord.configure_seasonal("weather.home", 20.0, 16.0)
    with patch.object(coord_mod, "async_dispatcher_send") as send:
        coord._apply_reading(now=0.0, reading=25.0)
        assert coord.seasonal_gate_active is True
        send.reset_mock()
        coord.set_smart_enabled(False)
        assert coord.seasonal_gate_active is False
        send.assert_any_call(coord.hass, SIGNAL_SEASONAL_GATE, False)
        send.reset_mock()
        coord.set_smart_enabled(True)
        assert coord.seasonal_gate_active is True
        send.assert_any_call(coord.hass, SIGNAL_SEASONAL_GATE, True)


@pytest.mark.anyio
async def test_start_seasonal_clears_restored_pauses_when_smart_disabled():
    """Zones may restore a seasonal pause from before the toggle was switched
    off; with no gate transition they would stay paused forever."""
    from custom_components.onna import coordinator as coord_mod
    from custom_components.onna.coordinator import SIGNAL_SEASONAL_GATE

    coord = OnnaCoordinator(MagicMock(), MagicMock())
    coord.configure_seasonal(None, 20.0, 16.0)
    coord.set_smart_enabled(False)
    with patch.object(coord_mod, "async_dispatcher_send") as send:
        await coord.async_start_seasonal()
    send.assert_called_once_with(coord.hass, SIGNAL_SEASONAL_GATE, False)
