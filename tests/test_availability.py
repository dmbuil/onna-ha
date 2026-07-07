"""Entity availability must mirror the WebSocket connection state.

When the connection to the Onna device drops, every entity switches to
unavailable instead of silently showing stale values; when it comes back,
entities recover.  All platforms share this behavior via the OnnaEntity mixin.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.onna.sensor import OnnaSensor
from custom_components.onna.binary_sensor import OnnaBinarySensor
from custom_components.onna.valve import OnnaValve, OnnaPositionValve
from custom_components.onna.fan import OnnaFan
from custom_components.onna.switch import OnnaSwitch
from custom_components.onna.climate import OnnaClimate, OnnaGeneralClimate
from custom_components.onna.coordinator import SIGNAL_CONNECTION


def _coord(connected=True):
    coord = MagicMock()
    coord.data = {}
    coord.connected = connected
    coord.client._onna_id = "TESTID"
    coord.client.async_set_address_value = AsyncMock()
    return coord


def _make_all_entities(coord):
    return [
        OnnaSensor(coord, "0_5_3", "Potencia", "W", "power", "measurement"),
        OnnaBinarySensor(coord, "0_4_2", "Alarma", "moisture", False),
        OnnaValve(coord, "0_0_5", "EV", "water"),
        OnnaPositionValve(coord, "1_0_8", "1_0_6", "Demanda", "water"),
        OnnaFan(coord, "Fancoil", "1_7_1", "1_7_3", "1_7_2", "1_0_1"),
        OnnaSwitch(coord, "1_7_10", "Fancoil Habilitado"),
        OnnaClimate(coord, "Salón", "1_0_4", "1_0_3", "1_0_2",
                    "1_0_1", "1_0_0", "1_0_7"),
        OnnaGeneralClimate(coord),
    ]


@pytest.mark.parametrize("connected", [True, False])
def test_available_mirrors_coordinator_connection(connected):
    coord = _coord(connected)
    for entity in _make_all_entities(coord):
        assert entity.available is connected, type(entity).__name__


def test_connection_change_writes_ha_state():
    coord = _coord()
    sensor = OnnaSensor(coord, "0_5_3", "Potencia", "W", "power", "measurement")
    sensor.async_write_ha_state = MagicMock()
    sensor._handle_connection_change(False)
    sensor.async_write_ha_state.assert_called_once()


# ---------------------------------------------------------------------------
# Every platform subscribes to the connection signal in async_added_to_hass
# ---------------------------------------------------------------------------

def _prepare(entity):
    entity.hass = MagicMock()
    entity.hass.states.get.return_value = None
    entity.async_on_remove = MagicMock()
    entity.async_get_last_state = AsyncMock(return_value=None)
    if hasattr(entity, "async_get_last_sensor_data"):
        entity.async_get_last_sensor_data = AsyncMock(return_value=None)
    return entity


async def _added_signals(entity):
    """Run async_added_to_hass and return the signals subscribed via the mixin."""
    with patch("custom_components.onna.entity.async_dispatcher_connect",
               return_value=lambda: None) as mock_connect, \
         patch("custom_components.onna.climate.async_dispatcher_connect",
               return_value=lambda: None, create=True):
        await entity.async_added_to_hass()
    return [c.args[1] for c in mock_connect.call_args_list]


@pytest.mark.anyio
@pytest.mark.parametrize("index", range(8))
async def test_entity_subscribes_to_connection_signal(index):
    entity = _prepare(_make_all_entities(_coord())[index])
    signals = await _added_signals(entity)
    assert SIGNAL_CONNECTION in signals, type(entity).__name__
