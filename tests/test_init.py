"""Tests for Onna __init__ entry setup/unload."""
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, call

from custom_components.onna.const import DOMAIN, CONF_HOST, CONF_ONNA_ID


def _make_hass():
    hass = MagicMock()
    hass.data = {}
    return hass


_MINIMAL_DEVICE_CONFIG = {
    "sensor_addresses": {},
    "binary_sensor_addresses": {},
    "valve_addresses": {},
    "valve_position_addresses": {},
    "climate_addresses": {},
    "switch_addresses": {},
    "fan_addresses": {},
}


def _make_entry(host="192.168.10.3", onna_id="ONNA_ID"):
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {CONF_HOST: host, CONF_ONNA_ID: onna_id, "device_config": _MINIMAL_DEVICE_CONFIG}
    entry.options = {}
    return entry


# ---------------------------------------------------------------------------
# async_setup_entry
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_setup_entry_stores_coordinator_in_hass_data():
    from custom_components.onna import async_setup_entry

    hass = _make_hass()
    entry = _make_entry()

    mock_coord = MagicMock()
    mock_coord.async_start = AsyncMock()

    with patch("custom_components.onna.OnnaClient"), \
         patch("custom_components.onna.OnnaCoordinator", return_value=mock_coord), \
         patch.object(hass, "config_entries", create=True):

        hass.config_entries = MagicMock()
        hass.config_entries.async_forward_entry_setups = AsyncMock()

        result = await async_setup_entry(hass, entry)

    assert result is True
    assert DOMAIN in hass.data
    assert entry.entry_id in hass.data[DOMAIN]
    mock_coord.async_start.assert_called_once()


@pytest.mark.anyio
async def test_setup_entry_forwards_to_sensor_and_binary_sensor_platforms():
    from custom_components.onna import async_setup_entry

    hass = _make_hass()
    entry = _make_entry()

    mock_coord = MagicMock()
    mock_coord.async_start = AsyncMock()

    with patch("custom_components.onna.OnnaClient"), \
         patch("custom_components.onna.OnnaCoordinator", return_value=mock_coord):

        hass.config_entries = MagicMock()
        hass.config_entries.async_forward_entry_setups = AsyncMock()

        await async_setup_entry(hass, entry)

    call_args = hass.config_entries.async_forward_entry_setups.call_args
    platforms = call_args[0][1]
    assert "sensor" in platforms
    assert "binary_sensor" in platforms
    assert "valve" in platforms
    assert "fan" in platforms


# ---------------------------------------------------------------------------
# async_unload_entry
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_unload_entry_stops_coordinator_and_removes_data():
    from custom_components.onna import async_setup_entry, async_unload_entry

    hass = _make_hass()
    entry = _make_entry()

    mock_coord = MagicMock()
    mock_coord.async_start = AsyncMock()
    mock_coord.async_stop = AsyncMock()

    with patch("custom_components.onna.OnnaClient"), \
         patch("custom_components.onna.OnnaCoordinator", return_value=mock_coord):

        hass.config_entries = MagicMock()
        hass.config_entries.async_forward_entry_setups = AsyncMock()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

        await async_setup_entry(hass, entry)
        result = await async_unload_entry(hass, entry)

    assert result is True
    mock_coord.async_stop.assert_called_once()
    assert entry.entry_id not in hass.data.get(DOMAIN, {})


@pytest.mark.anyio
async def test_coordinator_async_start_waits_for_client_initial_ready():
    """async_start must not return until client.initial_ready is set."""
    from custom_components.onna.coordinator import OnnaCoordinator

    ready_event = asyncio.Event()

    mock_client = MagicMock()
    mock_client.initial_ready = ready_event
    mock_client.connect = AsyncMock()
    mock_client.INIT_COLLECT_S = 0.1  # short timeout for tests

    mock_hass = MagicMock()
    # Must be sync — HA's async_create_background_task schedules and returns a Task
    mock_hass.async_create_background_task = lambda coro, *, name=None: asyncio.ensure_future(coro)

    coord = OnnaCoordinator(mock_hass, mock_client)

    # Fire ready_event after a short delay
    async def set_ready():
        await asyncio.sleep(0.05)
        ready_event.set()

    asyncio.ensure_future(set_ready())

    started_at = asyncio.get_event_loop().time()
    await coord.async_start()
    elapsed = asyncio.get_event_loop().time() - started_at

    # async_start should have waited at least until the event was set
    assert ready_event.is_set()
    assert elapsed >= 0.05


# ---------------------------------------------------------------------------
# async_migrate_entry
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_migrate_entry_v1_to_v3_adds_device_config_and_options():
    """async_migrate_entry upgrades a VERSION 1 entry to v3, adding device_config and options."""
    from custom_components.onna import async_migrate_entry

    mock_hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.version = 1
    mock_entry.data = {CONF_HOST: "192.168.1.1", CONF_ONNA_ID: "abc"}
    mock_entry.options = {}

    captured = {}
    def _update(entry, *, data=None, options=None, version=None):
        if data is not None:
            captured["data"] = data
        if options is not None:
            captured["options"] = options
        if version is not None:
            captured["version"] = version
    mock_hass.config_entries.async_update_entry.side_effect = _update

    result = await async_migrate_entry(mock_hass, mock_entry)
    assert result is True
    assert "device_config" in captured["data"]
    assert "sensor_addresses" in captured["data"]["device_config"]
    assert "climate_addresses" in captured["data"]["device_config"]
    assert "climate_temp_override" in captured["options"]
    assert "climate_window_sensor" in captured["options"]
    assert captured["options"]["climate_temp_override"]["zone_0"] == "sensor.sonoff_ths_2_temperature"
    assert captured["version"] == 3


@pytest.mark.anyio
async def test_migrate_entry_v2_to_v3_backfills_options():
    """async_migrate_entry upgrades a VERSION 2 entry by backfilling climate overrides into options."""
    from custom_components.onna import async_migrate_entry

    mock_hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.version = 2
    mock_entry.data = {CONF_HOST: "192.168.1.1", CONF_ONNA_ID: "abc", "device_config": {}}
    mock_entry.options = {}

    captured = {}
    def _update(entry, *, data=None, options=None, version=None):
        if data is not None:
            captured["data"] = data
        if options is not None:
            captured["options"] = options
        if version is not None:
            captured["version"] = version
    mock_hass.config_entries.async_update_entry.side_effect = _update

    result = await async_migrate_entry(mock_hass, mock_entry)
    assert result is True
    assert "climate_temp_override" in captured["options"]
    assert "climate_window_sensor" in captured["options"]
    assert captured["options"]["climate_temp_override"]["zone_1"] == "sensor.sonoff_ths_1_temperature"
    assert captured["version"] == 3


@pytest.mark.anyio
async def test_migrate_entry_v2_to_v3_preserves_existing_options():
    """v2→v3 migration does not overwrite options the user already configured."""
    from custom_components.onna import async_migrate_entry

    mock_hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.version = 2
    mock_entry.data = {CONF_HOST: "192.168.1.1", CONF_ONNA_ID: "abc", "device_config": {}}
    mock_entry.options = {"climate_temp_override": {"zone_0": "sensor.my_custom_sensor"}}

    captured = {}
    def _update(entry, *, data=None, options=None, version=None):
        if options is not None:
            captured["options"] = options
    mock_hass.config_entries.async_update_entry.side_effect = _update

    await async_migrate_entry(mock_hass, mock_entry)
    # User's custom value must be preserved; migration must not overwrite it
    assert captured["options"]["climate_temp_override"]["zone_0"] == "sensor.my_custom_sensor"


# ---------------------------------------------------------------------------
# Options-flow update listener → entry reload
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_setup_entry_registers_update_listener():
    from custom_components.onna import async_setup_entry

    hass = _make_hass()
    entry = _make_entry()
    mock_coord = MagicMock()
    mock_coord.async_start = AsyncMock()

    with patch("custom_components.onna.OnnaClient"), \
         patch("custom_components.onna.OnnaCoordinator", return_value=mock_coord):
        hass.config_entries = MagicMock()
        hass.config_entries.async_forward_entry_setups = AsyncMock()
        await async_setup_entry(hass, entry)

    entry.add_update_listener.assert_called_once()
    entry.async_on_unload.assert_called_once_with(entry.add_update_listener.return_value)


@pytest.mark.anyio
async def test_update_listener_reloads_entry():
    from custom_components.onna import _async_update_listener

    hass = _make_hass()
    entry = _make_entry()
    hass.config_entries = MagicMock()
    hass.config_entries.async_reload = AsyncMock()

    await _async_update_listener(hass, entry)

    hass.config_entries.async_reload.assert_called_once_with(entry.entry_id)
