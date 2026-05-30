"""Tests for OnnaSensor."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.onna.sensor import OnnaSensor
from custom_components.onna.coordinator import SIGNAL_ADDRESS_UPDATE


def _make_coordinator(data=None):
    coord = MagicMock()
    coord.data = data or {}
    coord.client._onna_id = "test_id"
    return coord


def _make_sensor(data=None, address="0_5_3"):
    coord = _make_coordinator(data)
    return OnnaSensor(coord, address, "Potencia", "W", "power", "measurement")


# Construction
# ---------------------------------------------------------------------------

def test_initial_value_from_coordinator():
    sensor = _make_sensor({"0_5_3": 1500.0})
    assert sensor._attr_native_value == 1500.0


def test_initial_value_none_when_no_data():
    sensor = _make_sensor()
    assert sensor._attr_native_value is None


def test_unique_id():
    sensor = _make_sensor(address="0_5_3")
    assert sensor._attr_unique_id == "onna_0_5_3"


# Update handler
# ---------------------------------------------------------------------------

def test_handle_update_sets_native_value():
    sensor = _make_sensor()
    sensor.async_write_ha_state = MagicMock()
    sensor._handle_update(2500.0)
    assert sensor._attr_native_value == 2500.0
    sensor.async_write_ha_state.assert_called_once()


# async_added_to_hass — dispatcher subscription
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_async_added_connects_dispatcher():
    sensor = _make_sensor(address="0_5_3")
    sensor.hass = MagicMock()
    sensor.async_on_remove = MagicMock()
    sensor.async_get_last_sensor_data = AsyncMock(return_value=None)

    with patch(
        "custom_components.onna.sensor.async_dispatcher_connect",
        return_value=lambda: None,
    ) as mock_connect:
        await sensor.async_added_to_hass()

    expected_signal = SIGNAL_ADDRESS_UPDATE.format(address_id="0_5_3")
    mock_connect.assert_called_once_with(sensor.hass, expected_signal, sensor._handle_update)


# RestoreSensor — last known value
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_restore_native_value_on_added():
    from tests.conftest import _SensorExtraStoredData
    sensor = _make_sensor()
    sensor.hass = MagicMock()
    sensor.async_on_remove = MagicMock()
    sensor.async_get_last_sensor_data = AsyncMock(
        return_value=_SensorExtraStoredData(native_value=1234.5)
    )

    with patch("custom_components.onna.sensor.async_dispatcher_connect", return_value=lambda: None):
        await sensor.async_added_to_hass()

    assert sensor._attr_native_value == 1234.5


@pytest.mark.anyio
async def test_restore_skipped_when_no_last_data():
    sensor = _make_sensor({"0_5_3": 100.0})
    sensor.hass = MagicMock()
    sensor.async_on_remove = MagicMock()
    sensor.async_get_last_sensor_data = AsyncMock(return_value=None)

    with patch("custom_components.onna.sensor.async_dispatcher_connect", return_value=lambda: None):
        await sensor.async_added_to_hass()

    assert sensor._attr_native_value == 100.0  # unchanged from coordinator seed


@pytest.mark.anyio
async def test_restore_overwrites_coordinator_seed():
    """Restored value takes priority over the (possibly stale) coordinator seed."""
    from tests.conftest import _SensorExtraStoredData
    sensor = _make_sensor({"0_5_3": 100.0})
    sensor.hass = MagicMock()
    sensor.async_on_remove = MagicMock()
    sensor.async_get_last_sensor_data = AsyncMock(
        return_value=_SensorExtraStoredData(native_value=999.0)
    )

    with patch("custom_components.onna.sensor.async_dispatcher_connect", return_value=lambda: None):
        await sensor.async_added_to_hass()

    assert sensor._attr_native_value == 999.0
