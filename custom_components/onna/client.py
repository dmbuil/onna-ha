"""Onna Socket.IO client — socket.io v2 / EIO=3 over WebSocket.

Why manual framing instead of python-socketio
----------------------------------------------
The Onna device speaks Socket.IO v2 (EIO=3).  The python-socketio library
defaults to v5 / EIO=4 and its v2 compatibility mode requires the full
async HTTP polling/upgrade dance that Onna does not support.  Rolling our own
framing is simpler and avoids a heavy dependency.

Wire protocol (EIO=3 / Socket.IO v2)
--------------------------------------
Frame format: <packet_type><namespace_or_ack><JSON_payload>

Relevant packet types we handle:
  "0"  — EIO open     (server → client; first frame after TCP connect)
  "40" — SIO connect  (server → client; signals namespace "/" is ready)
  "42" — SIO event    (bidirectional; carries ["EVENT_NAME", {…}])
  "421nn" — SIO ack   (server → client; "431…" is ack for our READ_CONFIGURATION)
  "2"/"3" — EIO ping/pong.  In EIO v3 the CLIENT pings: we send "2" every
            pingInterval (announced in the open frame) and the server answers
            "3".  Missing pings make the server drop the session after
            pingInterval+pingTimeout (Onna: 10 s + 5 s).

Relevant KNX events:
  SET_ADDRESS_VALUE_FROM_SERVER {id, value} — live push from device to HA
  SET_ADDRESS_VALUE_FROM_CLIENT {id, value} — HA writes a KNX group address
  READ_CONFIGURATION []                     — requests full device state; server
                                              replies with ack "431[…]" that contains
                                              all current KNX values + config_settings
                                              (e.g. internalSensorOffset per zone).
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine
from urllib.parse import quote

try:
    import websockets  # optional dep — only needed at runtime
except ImportError:  # pragma: no cover
    websockets = None  # type: ignore[assignment]

try:
    from homeassistant.exceptions import HomeAssistantError
except ImportError:  # pragma: no cover — recon scripts run outside HA
    class HomeAssistantError(Exception):  # type: ignore[no-redef]
        """Fallback so this module stays importable without Home Assistant."""

_LOGGER = logging.getLogger(__name__)

# Exceptions that async_fetch_config translates into CannotConnect.  Anything
# else (programming errors) propagates so bugs aren't masked as "cannot_connect".
_FETCH_ERRORS: tuple = (OSError, asyncio.TimeoutError, json.JSONDecodeError, ValueError, EOFError)
if websockets is not None:
    _FETCH_ERRORS += (websockets.WebSocketException,)

# Socket.IO v2 packet-type prefixes we build or parse.
_SIO_EVENT_PREFIX = "42"   # regular event frame
_SIO_ACK_PREFIX   = "421"  # ack frame (server acknowledging our request)

AddressCallback = Callable[[Any], Coroutine]


class CannotConnect(Exception):
    """Raised by async_fetch_config when the temporary connection fails."""



class OnnaClient:
    """Async client for the Onna local Socket.IO v2 server.

    Maintains a single persistent WebSocket connection to the Onna M Lite
    device (192.168.10.3:4001) and exposes two operations:

    - ``register_address_callback(addr, cb)`` — subscribe to live KNX push updates.
    - ``async_set_address_value(addr, value)``  — write a KNX group address.

    On connect the client issues READ_CONFIGURATION and waits INIT_COLLECT_S
    seconds before setting ``initial_ready``, allowing all spontaneous pushes
    from the device's ``readOnInit:true`` addresses to be collected and stored
    in coordinator.data before any HA entity is queried for its initial state.

    Usage::

        client = OnnaClient(host="192.168.10.3", onna_id="ONNA_ID")
        client.register_address_callback("1_0_4", my_callback)
        await client.connect()   # blocks — runs the receive loop; auto-reconnects
    """

    # Seconds to collect spontaneous pushes after READ_CONFIGURATION before
    # signalling the coordinator that initial data is ready.
    INIT_COLLECT_S: float = 3.0

    def __init__(self, host: str, onna_id: str, port: int = 4001) -> None:
        self._host    = host
        self._onna_id = onna_id
        self._port    = port
        self._ws: Any = None
        self._callbacks: dict[str, list[AddressCallback]] = defaultdict(list)
        # Set by _schedule_ready after INIT_COLLECT_S seconds; coordinator
        # blocks on this event before creating entities so coordinator.data is
        # fully seeded from READ_CONFIGURATION before the first entity reads it.
        self.initial_ready: asyncio.Event = asyncio.Event()
        # Settings extracted from the READ_CONFIGURATION ack (431 frame).
        # Not live KNX telegrams — populated once per connection.  Used by the
        # coordinator to seed synthetic addresses (e.g. cfg_internal_offset).
        self.config_settings: dict[str, Any] = {}
        # True between a completed handshake and the connection dropping.
        # The coordinator mirrors this into entity availability.
        self.connected: bool = False
        # Optional sync callback fired with the new state on every transition.
        self.on_connection_change: Callable[[bool], None] | None = None
        # Pending INIT_COLLECT_S timer task (see _schedule_ready).
        self._ready_task: asyncio.Task | None = None

    @property
    def onna_id(self) -> str:
        """Public device identifier (used by entities for device_info)."""
        return self._onna_id

    def _set_connected(self, value: bool) -> None:
        """Update the connection flag and notify the coordinator on transitions."""
        if self.connected == value:
            return
        self.connected = value
        if self.on_connection_change is not None:
            self.on_connection_change(value)

    # ------------------------------------------------------------------
    # Static helpers (pure, testable without a live connection)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_url(host: str, port: int, onna_id: str) -> str:
        """Build the Socket.IO WebSocket URL with both inputs URL-encoded.

        The config flow already validates the characters, but encoding here is
        defense in depth: a crafted host or onna_id can never alter the URL
        structure or inject extra query parameters.
        """
        return (
            f"ws://{quote(host, safe='')}:{port}/socket.io/"
            f"?EIO=3&transport=websocket&onnaId={quote(onna_id, safe='')}"
        )

    @staticmethod
    def _parse_ping_interval(open_frame: str) -> float:
        """Extract pingInterval (in seconds) from the EIO open frame ``0{…}``.

        Engine.IO v3 requires the *client* to send a ping ("2") every
        pingInterval; the server replies pong ("3") and drops the session
        after pingInterval+pingTimeout without one (Onna: 10 s + 5 s = the
        15-second disconnect loop observed before this existed).

        Falls back to a conservative 5 s when the frame is malformed —
        pinging too often is harmless, too rarely kills the connection.
        """
        try:
            return float(json.loads(open_frame[1:])["pingInterval"]) / 1000.0
        except (json.JSONDecodeError, KeyError, TypeError, ValueError, IndexError):
            return 5.0

    @staticmethod
    def parse_sio_event(frame: str) -> tuple[str, dict] | None:
        """Parse a raw Socket.IO v2 frame into (event_name, payload).

        Only "42…" event frames with a two-element JSON array and a dict
        payload are accepted; all other frames (EIO control, ack, ping, etc.)
        return None.

        Returns (event_name, payload_dict), or None for unrecognised frames.
        """
        if not frame.startswith(_SIO_EVENT_PREFIX):
            return None
        try:
            data = json.loads(frame[len(_SIO_EVENT_PREFIX):])
        except (json.JSONDecodeError, ValueError):
            return None
        if not isinstance(data, list) or len(data) < 2:
            return None
        event_name, payload = data[0], data[1]
        if not isinstance(payload, dict):
            return None
        return event_name, payload

    @staticmethod
    def build_set_address_value(address_id: str, value: Any) -> str:
        """Build a SET_ADDRESS_VALUE_FROM_CLIENT Socket.IO v2 frame.

        Onna expects: ``42["SET_ADDRESS_VALUE_FROM_CLIENT",{"id":"1_0_2","value":22.5}]``
        """
        return _SIO_EVENT_PREFIX + json.dumps(
            ["SET_ADDRESS_VALUE_FROM_CLIENT", {"id": address_id, "value": value}],
            separators=(",", ":"),
        )

    @staticmethod
    def build_read_configuration(ack_id: int = 1) -> str:
        """Build a READ_CONFIGURATION frame that requests an acknowledgement.

        The ack_id appears as the numeric suffix after "42", e.g. "421".
        Onna responds with "431[…]" (ack packet type "43" + same id "1").
        The response carries the full KNX address state and config_settings
        (including internalSensorOffset values for each zone).
        """
        return f"{_SIO_EVENT_PREFIX}{ack_id}" + json.dumps(
            ["READ_CONFIGURATION"],
            separators=(",", ":"),
        )

    @classmethod
    async def async_fetch_config(
        cls, host: str, onna_id: str, port: int = 4001, timeout: float = 10.0
    ) -> dict:
        """One-shot config fetch for use during ConfigFlow setup.

        Opens a temporary WebSocket, sends READ_CONFIGURATION, waits for the
        full 431 ack payload, and closes the connection.  Does NOT start the
        background receive loop used during normal operation.

        Raises CannotConnect on timeout or any connection error.
        """
        if websockets is None:
            raise CannotConnect("the 'websockets' library is not installed")
        url = cls._build_url(host, port, onna_id)
        try:
            async with websockets.connect(url) as ws:
                await asyncio.wait_for(ws.recv(), timeout=timeout)   # EIO open
                await asyncio.wait_for(ws.recv(), timeout=timeout)   # SIO namespace
                await ws.send(cls.build_read_configuration())
                while True:
                    frame = await asyncio.wait_for(ws.recv(), timeout=timeout)
                    if frame == "2":
                        await ws.send("3")
                        continue
                    if frame.startswith("431"):
                        payload = json.loads(frame[3:])
                        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
                            return payload[0]
                        return {}
        except _FETCH_ERRORS as exc:
            raise CannotConnect(str(exc)) from exc

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------

    def register_address_callback(self, address_id: str, cb: AddressCallback) -> None:
        """Register an async callback that fires whenever ``address_id`` is updated.

        Multiple callbacks may be registered for the same address; all are
        called in registration order on each incoming push.
        """
        self._callbacks[address_id].append(cb)

    # ------------------------------------------------------------------
    # Internal dispatch
    # ------------------------------------------------------------------

    async def _dispatch_address_update(self, address_id: str, value: Any) -> None:
        """Invoke all callbacks registered for address_id with the new value."""
        for cb in self._callbacks.get(address_id, []):
            await cb(value)

    async def _process_frame(self, frame: str) -> None:
        """Route one incoming WebSocket frame to the appropriate handler.

        Two frame types are handled:

          "431…" — READ_CONFIGURATION ack (server acknowledging our request).
              Carries the full KNX address state AND device settings.  We extract
              ``settings.internalSensorOffset`` and store it in config_settings
              for the coordinator to use.  We also dispatch it as a virtual address
              update so any already-running sensor entity (e.g. on reconnect)
              receives the value live without waiting for a KNX telegram.
              Two-path design: coordinator seeds coordinator.data before entity
              setup (first boot), and the dispatch here updates running entities
              (reconnect / post-setup delivery via dispatch_config_data).

          "42…" SET_ADDRESS_VALUE_FROM_SERVER — live KNX push.
              Dispatched to all registered address callbacks.

          All other frames (EIO handshake, ping/pong, other SIO events) are
          silently dropped.
        """
        if frame.startswith("431"):
            try:
                payload = json.loads(frame[3:])
                if isinstance(payload, list) and payload and isinstance(payload[0], dict):
                    settings = payload[0].get("settings", {})
                    offset = settings.get("internalSensorOffset")
                    if offset is not None:
                        value = float(offset)
                        self.config_settings["internalSensorOffset"] = value
                        await self._dispatch_address_update("cfg_internal_offset", value)
            except (json.JSONDecodeError, ValueError, TypeError, IndexError):
                pass
            return

        result = self.parse_sio_event(frame)
        if result is None:
            return
        event_name, payload = result
        if event_name == "SET_ADDRESS_VALUE_FROM_SERVER":
            addr = payload.get("id")
            val  = payload.get("value")
            if addr is not None:
                await self._dispatch_address_update(addr, val)

    # ------------------------------------------------------------------
    # Connection & send
    # ------------------------------------------------------------------

    async def async_set_address_value(self, address_id: str, value: Any) -> None:
        """Write ``value`` to the KNX group address ``address_id`` via Onna.

        Raises HomeAssistantError if called before a WebSocket connection is
        open, so HA service calls surface a proper user-facing error.
        """
        if self._ws is None:
            raise HomeAssistantError("Onna is not connected — cannot write KNX value")
        frame = self.build_set_address_value(address_id, value)
        await self._ws.send(frame)

    async def connect(self) -> None:
        """Open the WebSocket to Onna and run the receive loop; auto-reconnects.

        The URL includes ``?EIO=3&transport=websocket`` to request Socket.IO v2
        directly over WebSocket (no HTTP polling upgrade needed).
        ``onnaId`` is the device's unique identifier used for session routing.

        Loops forever via ``websockets.connect``'s reconnect iterator; each
        connection loss is logged and the loop restarts automatically.

        Any exception from a single connection lifetime (handshake timeout,
        connection closed, a bug in a frame handler) is logged and the loop
        moves on to the next connection attempt — only task cancellation
        (integration unload) escapes.
        """
        url = self._build_url(self._host, self._port, self._onna_id)
        # Deliberately not logging the full URL: the onnaId query parameter is
        # the device's only credential.
        _LOGGER.debug("Connecting to Onna at %s:%s", self._host, self._port)

        async for ws in websockets.connect(url):
            self._ws = ws
            try:
                await self._run(ws)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — transport must outlive any error
                _LOGGER.warning("Onna connection lost (%s: %s) — reconnecting",
                                type(exc).__name__, exc)
            finally:
                self._ws = None
                self._set_connected(False)

    def _schedule_ready(self) -> None:
        """Fire initial_ready after INIT_COLLECT_S seconds in the background.

        Called once after READ_CONFIGURATION is sent.  The delay lets all
        ``readOnInit:true`` push messages (flow sensors, setpoints, on/off
        states, etc.) arrive and populate coordinator.data before HA entities
        are set up and query their initial state.
        """
        async def _set_ready() -> None:
            await asyncio.sleep(self.INIT_COLLECT_S)
            self.initial_ready.set()

        self._ready_task = asyncio.ensure_future(_set_ready())

    async def async_shutdown(self) -> None:
        """Cancel the pending ready timer (called on integration unload)."""
        if self._ready_task is not None and not self._ready_task.done():
            self._ready_task.cancel()
            try:
                await self._ready_task
            except asyncio.CancelledError:
                pass
        self._ready_task = None

    async def _ping_loop(self, ws: Any, interval: float) -> None:
        """EIO v3 keepalive: send a ping ("2") every pingInterval seconds.

        Without this the server drops the session after
        pingInterval+pingTimeout (Onna: every 15 s).  A failed send means the
        connection is going down — exit quietly and let the receive loop
        handle the reconnect.
        """
        try:
            while True:
                await asyncio.sleep(interval)
                await ws.send("2")
        except Exception:  # noqa: BLE001 — connection teardown races are expected here
            return

    async def _run(self, ws: Any) -> None:
        """Inner receive loop for a single WebSocket connection lifetime.

        Handshake sequence expected by Onna (EIO=3):
          1. Server sends EIO "0{…}" open frame (session id, ping interval, etc.)
          2. Server sends SIO "40" namespace-connect frame for "/" namespace.
          3. We send READ_CONFIGURATION (ack frame "421[…]"); Onna replies
             with "431[…]" carrying the full device state.
          4. Normal operation: server pushes "42[…]" event frames.  We send an
             EIO ping ("2") every pingInterval (client pings in EIO v3) and
             answer any server ping with a pong ("3") for good measure.
        """
        # Step 1: consume the EIO open frame (contains session id, ping interval).
        open_frame = await asyncio.wait_for(ws.recv(), timeout=5)
        _LOGGER.debug("EIO open: %s", open_frame[:80])
        ping_interval = self._parse_ping_interval(open_frame)

        # Step 2: server sends "40" (SIO namespace connect) automatically.
        ns_frame = await asyncio.wait_for(ws.recv(), timeout=5)
        _LOGGER.debug("Namespace: %s", ns_frame)

        # Step 3: request full device state; start the ready timer concurrently.
        await ws.send(self.build_read_configuration())
        self._schedule_ready()
        self._set_connected(True)

        # Step 4: normal receive loop.  A failing frame handler (e.g. an entity
        # callback choking on an unexpected payload) must not tear down the
        # connection, so per-frame errors are logged and swallowed here.
        ping_task = asyncio.ensure_future(self._ping_loop(ws, ping_interval))
        try:
            async for raw in ws:
                if raw == "2":  # server ping (defensive — EIO v3 servers shouldn't)
                    await ws.send("3")
                    continue
                if raw == "3":  # pong answering our ping — keepalive confirmed
                    continue
                try:
                    await self._process_frame(raw)
                except Exception:  # noqa: BLE001 — one bad frame must not kill the loop
                    _LOGGER.exception("Error processing Onna frame: %s", raw[:120])
        finally:
            ping_task.cancel()
            try:
                await ping_task
            except asyncio.CancelledError:
                pass
