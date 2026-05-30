"""Tests for Onna __init__ entry setup/unload."""
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, call

from custom_components.onna.const import DOMAIN, CONF_HOST, CONF_ONNA_ID


def _make_hass():
    hass = MagicMock()
    hass.data = {}
    return hass


def _make_entry(host="192.168.10.3", onna_id="1HPNi16"):
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {CONF_HOST: host, CONF_ONNA_ID: onna_id}
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
