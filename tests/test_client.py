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


# ---------------------------------------------------------------------------
# Receive-loop resilience & connection state
# ---------------------------------------------------------------------------

class _FakeWS:
    """Minimal fake WebSocket: recv() serves handshake frames, then the
    object async-iterates the event frames (mirroring how _run consumes it)."""

    def __init__(self, handshake=("0{}", "40"), frames=(), handshake_exc=None):
        self._handshake = list(handshake)
        self._frames = list(frames)
        self._handshake_exc = handshake_exc
        self.sent = []

    async def recv(self):
        if self._handshake_exc is not None:
            raise self._handshake_exc
        return self._handshake.pop(0)

    async def send(self, frame):
        self.sent.append(frame)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._frames:
            return self._frames.pop(0)
        raise StopAsyncIteration


class _AsyncIter:
    """Stand-in for the reconnect iterator returned by websockets.connect()."""

    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._items:
            return self._items.pop(0)
        raise StopAsyncIteration


@pytest.mark.anyio
async def test_connect_survives_handshake_failure_and_moves_to_next_connection():
    """A handshake timeout on one connection must not kill the connect loop."""
    import asyncio
    client = OnnaClient(host="192.168.10.3", onna_id="TEST")
    client._schedule_ready = MagicMock()

    bad_ws = _FakeWS(handshake_exc=asyncio.TimeoutError())
    good_ws = _FakeWS()

    with patch("custom_components.onna.client.websockets") as mock_wss:
        mock_wss.connect.return_value = _AsyncIter([bad_ws, good_ws])
        await client.connect()

    # The second connection completed its handshake and sent READ_CONFIGURATION.
    assert any(f.startswith("421") for f in good_ws.sent)


@pytest.mark.anyio
async def test_run_continues_processing_after_callback_exception():
    """One failing entity callback must not abort the receive loop."""
    client = OnnaClient(host="192.168.10.3", onna_id="TEST")
    client._schedule_ready = MagicMock()

    async def bad_cb(value):
        raise ValueError("entity bug")

    good_cb = AsyncMock()
    client.register_address_callback("1_0_1", bad_cb)
    client.register_address_callback("1_0_2", good_cb)

    ws = _FakeWS(frames=[
        '42["SET_ADDRESS_VALUE_FROM_SERVER",{"id":"1_0_1","value":1}]',
        '42["SET_ADDRESS_VALUE_FROM_SERVER",{"id":"1_0_2","value":22.5}]',
    ])
    await client._run(ws)

    good_cb.assert_called_once_with(22.5)


@pytest.mark.anyio
async def test_connection_change_callback_fires_true_then_false():
    """on_connection_change reports True after handshake, False after the loop ends."""
    client = OnnaClient(host="192.168.10.3", onna_id="TEST")
    client._schedule_ready = MagicMock()
    events = []
    client.on_connection_change = events.append

    with patch("custom_components.onna.client.websockets") as mock_wss:
        mock_wss.connect.return_value = _AsyncIter([_FakeWS()])
        await client.connect()

    assert events == [True, False]
    assert client.connected is False


@pytest.mark.anyio
async def test_connected_is_true_after_handshake():
    client = OnnaClient(host="192.168.10.3", onna_id="TEST")
    client._schedule_ready = MagicMock()
    assert client.connected is False
    await client._run(_FakeWS())
    assert client.connected is True


# ---------------------------------------------------------------------------
# Write-path error handling
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_set_address_value_raises_homeassistant_error_when_disconnected():
    """Service calls while disconnected must surface as HomeAssistantError."""
    from homeassistant.exceptions import HomeAssistantError
    client = OnnaClient(host="192.168.10.3", onna_id="TEST")
    with pytest.raises(HomeAssistantError):
        await client.async_set_address_value("1_0_2", 22.5)


# ---------------------------------------------------------------------------
# Ready-timer task management
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_async_shutdown_cancels_pending_ready_timer():
    client = OnnaClient(host="192.168.10.3", onna_id="TEST")
    client._schedule_ready()
    assert client._ready_task is not None
    await client.async_shutdown()
    assert client._ready_task is None
    assert not client.initial_ready.is_set()


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


@pytest.mark.anyio
async def test_async_fetch_config_propagates_unexpected_errors():
    """Programming errors must not be masked as cannot_connect."""
    mock_ws = AsyncMock()
    mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
    mock_ws.__aexit__ = AsyncMock(return_value=False)
    mock_ws.recv = AsyncMock(side_effect=RuntimeError("bug in our code"))
    mock_ws.send = AsyncMock()

    with patch("custom_components.onna.client.websockets") as mock_wss:
        mock_wss.connect.return_value = mock_ws
        with pytest.raises(RuntimeError):
            await OnnaClient.async_fetch_config("192.168.1.1", "abc123")


@pytest.mark.anyio
async def test_async_fetch_config_raises_cannot_connect_when_websockets_missing():
    """A missing websockets dependency yields CannotConnect, not AttributeError."""
    from custom_components.onna.client import CannotConnect

    with patch("custom_components.onna.client.websockets", None):
        with pytest.raises(CannotConnect):
            await OnnaClient.async_fetch_config("192.168.1.1", "abc123")


def test_onna_id_exposed_as_public_property():
    client = OnnaClient(host="192.168.10.3", onna_id="TEST")
    assert client.onna_id == "TEST"


# ---------------------------------------------------------------------------
# URL construction — credentials must be URL-encoded
# ---------------------------------------------------------------------------

def test_build_url_quotes_onna_id():
    """An onna_id with URL metacharacters must not inject query parameters."""
    url = OnnaClient._build_url("192.168.10.3", 4001, "abc&admin=1#x")
    assert "&admin=1" not in url
    assert "#" not in url
    assert "abc%26admin%3D1%23x" in url


def test_build_url_quotes_host():
    """A host with a path separator must not alter the URL structure."""
    url = OnnaClient._build_url("evil.host/path", 4001, "TEST")
    assert "/path" not in url.split("?")[0].replace("ws://", "").rsplit("/socket.io/", 1)[0] or "%2F" in url


def test_build_url_plain_values_unchanged():
    url = OnnaClient._build_url("192.168.10.3", 4001, "ONNA_ID")
    assert url == "ws://192.168.10.3:4001/socket.io/?EIO=3&transport=websocket&onnaId=ONNA_ID"


@pytest.mark.anyio
async def test_connect_uses_encoded_url():
    client = OnnaClient(host="192.168.10.3", onna_id="A&B")
    client._schedule_ready = MagicMock()
    with patch("custom_components.onna.client.websockets") as mock_wss:
        mock_wss.connect.return_value = _AsyncIter([])
        await client.connect()
    url = mock_wss.connect.call_args.args[0]
    assert "A%26B" in url and "A&B" not in url


@pytest.mark.anyio
async def test_connect_does_not_log_onna_id(caplog):
    """The onna_id is the device's only credential — keep it out of logs."""
    import logging
    client = OnnaClient(host="192.168.10.3", onna_id="SECRETID")
    client._schedule_ready = MagicMock()
    with caplog.at_level(logging.DEBUG, logger="custom_components.onna.client"):
        with patch("custom_components.onna.client.websockets") as mock_wss:
            mock_wss.connect.return_value = _AsyncIter([])
            await client.connect()
    assert "SECRETID" not in caplog.text


# ---------------------------------------------------------------------------
# EIO v3 keepalive — the *client* must ping every pingInterval
# ---------------------------------------------------------------------------

def test_parse_ping_interval_from_open_frame():
    frame = '0{"sid":"abc","pingInterval":10000,"pingTimeout":5000}'
    assert OnnaClient._parse_ping_interval(frame) == 10.0


def test_parse_ping_interval_defaults_when_malformed():
    assert OnnaClient._parse_ping_interval("0") == 5.0
    assert OnnaClient._parse_ping_interval("0garbage") == 5.0
    assert OnnaClient._parse_ping_interval('0{"pingTimeout":5000}') == 5.0


class _TimedFakeWS(_FakeWS):
    """Fake WS whose receive loop stays open for a fixed wall-clock time,
    announcing a 100 ms pingInterval in the EIO open frame."""

    def __init__(self, open_for=0.35):
        super().__init__(handshake=['0{"pingInterval":100,"pingTimeout":50}', "40"])
        self._open_for = open_for

    async def __anext__(self):
        import asyncio
        if self._open_for is not None:
            stay, self._open_for = self._open_for, None
            await asyncio.sleep(stay)
        raise StopAsyncIteration


@pytest.mark.anyio
async def test_run_sends_eio_pings_at_announced_interval():
    """Without client pings the Onna server drops the session every
    pingInterval+pingTimeout (observed: every 15 s in production)."""
    client = OnnaClient(host="192.168.10.3", onna_id="TEST")
    client._schedule_ready = MagicMock()
    ws = _TimedFakeWS(open_for=0.35)
    await client._run(ws)
    # interval 100 ms, open ~350 ms → at least 2 pings must have been sent
    assert ws.sent.count("2") >= 2


@pytest.mark.anyio
async def test_ping_loop_stops_when_run_exits():
    import asyncio
    client = OnnaClient(host="192.168.10.3", onna_id="TEST")
    client._schedule_ready = MagicMock()
    ws = _TimedFakeWS(open_for=0.25)
    await client._run(ws)
    sent_after_run = ws.sent.count("2")
    await asyncio.sleep(0.25)
    assert ws.sent.count("2") == sent_after_run
