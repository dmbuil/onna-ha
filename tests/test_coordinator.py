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
