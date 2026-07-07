"""Tests for OnnaSensor."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.onna.sensor import OnnaSensor, _FLOW_STALENESS_TIMEOUT
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
async def test_restore_skipped_when_no_last_data_and_no_last_state():
    sensor = _make_sensor({"0_5_3": 100.0})
    sensor.hass = MagicMock()
    sensor.async_on_remove = MagicMock()
    sensor.async_get_last_sensor_data = AsyncMock(return_value=None)
    sensor.async_get_last_state = AsyncMock(return_value=None)

    with patch("custom_components.onna.sensor.async_dispatcher_connect", return_value=lambda: None):
        await sensor.async_added_to_hass()

    assert sensor._attr_native_value == 100.0  # unchanged from coordinator seed


@pytest.mark.anyio
async def test_restore_overwrites_coordinator_seed():
    """RestoreSensor extra data takes priority over the coordinator seed."""
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


@pytest.mark.anyio
async def test_restore_fallback_to_last_state_when_no_sensor_data():
    """On first boot after enabling restore, fall back to recorder state string."""
    sensor = _make_sensor()
    sensor.hass = MagicMock()
    sensor.async_on_remove = MagicMock()
    sensor.async_get_last_sensor_data = AsyncMock(return_value=None)
    last = MagicMock()
    last.state = "1500.0"
    sensor.async_get_last_state = AsyncMock(return_value=last)

    with patch("custom_components.onna.sensor.async_dispatcher_connect", return_value=lambda: None):
        await sensor.async_added_to_hass()

    assert sensor._attr_native_value == 1500.0


@pytest.mark.anyio
async def test_restore_fallback_skipped_when_state_unavailable():
    sensor = _make_sensor({"0_5_3": 100.0})
    sensor.hass = MagicMock()
    sensor.async_on_remove = MagicMock()
    sensor.async_get_last_sensor_data = AsyncMock(return_value=None)
    last = MagicMock()
    last.state = "unavailable"
    sensor.async_get_last_state = AsyncMock(return_value=last)

    with patch("custom_components.onna.sensor.async_dispatcher_connect", return_value=lambda: None):
        await sensor.async_added_to_hass()

    assert sensor._attr_native_value == 100.0  # unchanged


# ---------------------------------------------------------------------------
# Flow sensor staleness timeout
# ---------------------------------------------------------------------------

def _make_flow_sensor(data=None):
    coord = MagicMock()
    coord.data = data or {}
    coord.client._onna_id = "test_id"
    return OnnaSensor(coord, "0_5_6", "Caudal Agua Fría", "L/h", "volume_flow_rate", "measurement")


@pytest.mark.anyio
async def test_flow_sensor_arms_timer_on_added_when_nonzero():
    sensor = _make_flow_sensor({"0_5_6": 280.0})
    sensor.hass = MagicMock()
    sensor.async_on_remove = MagicMock()
    sensor.async_get_last_sensor_data = AsyncMock(return_value=None)
    sensor.async_get_last_state = AsyncMock(return_value=None)

    with patch("custom_components.onna.sensor.async_dispatcher_connect", return_value=lambda: None), \
         patch("custom_components.onna.sensor.async_call_later", return_value=MagicMock()) as mock_timer:
        await sensor.async_added_to_hass()

    mock_timer.assert_called_once_with(sensor.hass, _FLOW_STALENESS_TIMEOUT, sensor._handle_flow_stale)


@pytest.mark.anyio
async def test_flow_sensor_no_timer_when_value_is_zero():
    sensor = _make_flow_sensor({"0_5_6": 0.0})
    sensor.hass = MagicMock()
    sensor.async_on_remove = MagicMock()
    sensor.async_get_last_sensor_data = AsyncMock(return_value=None)
    sensor.async_get_last_state = AsyncMock(return_value=None)

    with patch("custom_components.onna.sensor.async_dispatcher_connect", return_value=lambda: None), \
         patch("custom_components.onna.sensor.async_call_later", return_value=MagicMock()) as mock_timer:
        await sensor.async_added_to_hass()

    mock_timer.assert_not_called()


def test_flow_stale_callback_resets_to_zero():
    sensor = _make_flow_sensor({"0_5_6": 280.0})
    sensor.async_write_ha_state = MagicMock()
    sensor._handle_flow_stale(None)
    assert sensor._attr_native_value == 0.0
    sensor.async_write_ha_state.assert_called_once()


def test_flow_update_rearms_timer():
    sensor = _make_flow_sensor()
    sensor.hass = MagicMock()
    sensor.async_write_ha_state = MagicMock()
    cancel = MagicMock()
    sensor._flow_stale_cancel = cancel

    with patch("custom_components.onna.sensor.async_call_later", return_value=MagicMock()) as mock_timer:
        sensor._handle_update(250.0)

    cancel.assert_called_once()  # old timer cancelled
    mock_timer.assert_called_once()  # new timer armed


def test_non_flow_sensor_no_timer():
    coord = MagicMock()
    coord.data = {"0_5_3": 200.0}
    coord.client._onna_id = "test_id"
    sensor = OnnaSensor(coord, "0_5_3", "Potencia", "W", "power", "measurement")
    assert sensor._is_flow_sensor is False
