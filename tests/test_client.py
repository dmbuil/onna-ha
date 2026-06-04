import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
# anyio provides async test support without requiring pytest-asyncio
from custom_components.onna.client import OnnaClient


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_parse_sio_event_returns_event_name_and_payload():
    data = '42["SET_ADDRESS_VALUE_FROM_SERVER",{"id":"0_0_2","value":25.0}]'
    name, payload = OnnaClient.parse_sio_event(data)
    assert name == "SET_ADDRESS_VALUE_FROM_SERVER"
    assert payload == {"id": "0_0_2", "value": 25.0}


def test_parse_sio_event_returns_none_for_non_event_frames():
    assert OnnaClient.parse_sio_event("2") is None      # EIO ping
    assert OnnaClient.parse_sio_event("40") is None     # namespace connect
    assert OnnaClient.parse_sio_event("3") is None      # EIO pong


def test_parse_sio_event_returns_none_for_event_without_payload():
    assert OnnaClient.parse_sio_event('42["SOME_EVENT"]') is None


# ---------------------------------------------------------------------------
# Command building
# ---------------------------------------------------------------------------

def test_build_set_address_value_produces_correct_sio_frame():
    frame = OnnaClient.build_set_address_value("0_0_2", 22.5)
    assert frame.startswith("42")
    parsed = json.loads(frame[2:])
    assert parsed[0] == "SET_ADDRESS_VALUE_FROM_CLIENT"
    assert parsed[1] == {"id": "0_0_2", "value": 22.5}


def test_build_read_configuration_produces_ack_frame():
    frame = OnnaClient.build_read_configuration(ack_id=1)
    assert frame.startswith("421")
    parsed = json.loads(frame[3:])
    assert parsed[0] == "READ_CONFIGURATION"


# ---------------------------------------------------------------------------
# Callback dispatch
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_handle_address_update_calls_registered_callback():
    client = OnnaClient(host="192.168.10.3", onna_id="TEST")
    cb = AsyncMock()
    client.register_address_callback("0_0_2", cb)
    await client._dispatch_address_update("0_0_2", 25.0)
    cb.assert_called_once_with(25.0)


@pytest.mark.anyio
async def test_handle_address_update_ignores_unknown_address():
    client = OnnaClient(host="192.168.10.3", onna_id="TEST")
    cb = AsyncMock()
    client.register_address_callback("0_0_2", cb)
    await client._dispatch_address_update("9_9_9", 999.0)
    cb.assert_not_called()


@pytest.mark.anyio
async def test_multiple_callbacks_for_same_address_all_called():
    client = OnnaClient(host="192.168.10.3", onna_id="TEST")
    cb1, cb2 = AsyncMock(), AsyncMock()
    client.register_address_callback("1_0_4", cb1)
    client.register_address_callback("1_0_4", cb2)
    await client._dispatch_address_update("1_0_4", 21.5)
    cb1.assert_called_once_with(21.5)
    cb2.assert_called_once_with(21.5)


@pytest.mark.anyio
async def test_process_incoming_frame_dispatches_address_event():
    client = OnnaClient(host="192.168.10.3", onna_id="TEST")
    cb = AsyncMock()
    client.register_address_callback("0_0_2", cb)
    frame = '42["SET_ADDRESS_VALUE_FROM_SERVER",{"id":"0_0_2","value":25.0}]'
    await client._process_frame(frame)
    cb.assert_called_once_with(25.0)


@pytest.mark.anyio
async def test_process_incoming_frame_ignores_non_address_events():
    client = OnnaClient(host="192.168.10.3", onna_id="TEST")
    cb = AsyncMock()
    client.register_address_callback("0_0_2", cb)
    await client._process_frame("2")   # EIO ping
    cb.assert_not_called()


# ---------------------------------------------------------------------------
# READ_CONFIGURATION ack parsing
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_ack_stores_offset_in_config_settings():
    client = OnnaClient(host="192.168.10.3", onna_id="TEST")
    ack = '431[{"settings":{"internalSensorOffset":"-0.4"},"addresses":[]}]'
    await client._process_frame(ack)
    assert client.config_settings["internalSensorOffset"] == -0.4


@pytest.mark.anyio
async def test_ack_dispatches_offset_to_registered_callback():
    """Reconnect path: entity already registered, must receive the value."""
    client = OnnaClient(host="192.168.10.3", onna_id="TEST")
    cb = AsyncMock()
    client.register_address_callback("cfg_internal_offset", cb)
    ack = '431[{"settings":{"internalSensorOffset":"-0.4"},"addresses":[]}]'
    await client._process_frame(ack)
    cb.assert_called_once_with(-0.4)


@pytest.mark.anyio
async def test_ack_ignores_malformed_frame():
    client = OnnaClient(host="192.168.10.3", onna_id="TEST")
    await client._process_frame("431not-valid-json")
    assert client.config_settings == {}


@pytest.mark.anyio
async def test_ack_positive_offset():
    client = OnnaClient(host="192.168.10.3", onna_id="TEST")
    ack = '431[{"settings":{"internalSensorOffset":"1.5"},"addresses":[]}]'
    await client._process_frame(ack)
    assert client.config_settings["internalSensorOffset"] == 1.5


# ---------------------------------------------------------------------------
# Initial ready event
# ---------------------------------------------------------------------------

def test_initial_ready_is_not_set_on_construction():
    client = OnnaClient(host="192.168.10.3", onna_id="TEST")
    assert not client.initial_ready.is_set()


@pytest.mark.anyio
async def test_initial_ready_is_set_after_init_timeout():
    import asyncio
    client = OnnaClient(host="192.168.10.3", onna_id="TEST")
    assert not client.initial_ready.is_set()

    # Simulate _schedule_ready being called (as it would be inside _run)
    client._schedule_ready()
    await asyncio.sleep(client.INIT_COLLECT_S + 0.1)
    assert client.initial_ready.is_set()


# ---------------------------------------------------------------------------
# async_fetch_config
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_async_fetch_config_returns_payload():
    """async_fetch_config returns the dict from the 431 ack frame."""
    raw_payload = [{"addresses": [{"id": "0_0_8"}], "configuration": []}]
    frame_431 = "431" + json.dumps(raw_payload)

    mock_ws = AsyncMock()
    mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
    mock_ws.__aexit__ = AsyncMock(return_value=False)
    mock_ws.recv = AsyncMock(side_effect=["0{}", "40", frame_431])
    mock_ws.send = AsyncMock()

    with patch("custom_components.onna.client.websockets") as mock_wss:
        mock_wss.connect.return_value = mock_ws
        result = await OnnaClient.async_fetch_config("192.168.1.1", "abc123")

    assert result == raw_payload[0]


@pytest.mark.anyio
async def test_async_fetch_config_skips_non_431_frames():
    """async_fetch_config ignores ping frames while waiting for the 431 ack."""
    raw_payload = [{"addresses": [], "configuration": []}]
    frame_431 = "431" + json.dumps(raw_payload)

    mock_ws = AsyncMock()
    mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
    mock_ws.__aexit__ = AsyncMock(return_value=False)
    # EIO open, SIO namespace, EIO ping, then the 431 ack
    mock_ws.recv = AsyncMock(side_effect=["0{}", "40", "2", frame_431])
    mock_ws.send = AsyncMock()

    with patch("custom_components.onna.client.websockets") as mock_wss:
        mock_wss.connect.return_value = mock_ws
        result = await OnnaClient.async_fetch_config("192.168.1.1", "abc123")

    assert result == raw_payload[0]
    mock_ws.send.assert_any_call("3")


@pytest.mark.anyio
async def test_async_fetch_config_raises_cannot_connect_on_timeout():
    """async_fetch_config raises CannotConnect when the connection times out."""
    import asyncio as _asyncio
    from custom_components.onna.client import CannotConnect

    mock_ws = AsyncMock()
    mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
    mock_ws.__aexit__ = AsyncMock(return_value=False)
    mock_ws.recv = AsyncMock(side_effect=_asyncio.TimeoutError())
    mock_ws.send = AsyncMock()

    with patch("custom_components.onna.client.websockets") as mock_wss:
        mock_wss.connect.return_value = mock_ws
        with pytest.raises(CannotConnect):
            await OnnaClient.async_fetch_config("192.168.1.1", "abc123")
