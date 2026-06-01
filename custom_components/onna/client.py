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
  "2"  — EIO ping     (server → client; we must respond with "3")

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

_LOGGER = logging.getLogger(__name__)

# Socket.IO v2 packet-type prefixes we build or parse.
_SIO_EVENT_PREFIX = "42"   # regular event frame
_SIO_ACK_PREFIX   = "421"  # ack frame (server acknowledging our request)

AddressCallback = Callable[[Any], Coroutine]


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

        client = OnnaClient(host="192.168.10.3", onna_id="1HPNi16")
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

    # ------------------------------------------------------------------
    # Static helpers (pure, testable without a live connection)
    # ------------------------------------------------------------------

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

        Raises RuntimeError if called before a WebSocket connection is open.
        """
        if self._ws is None:
            raise RuntimeError("Not connected")
        frame = self.build_set_address_value(address_id, value)
        await self._ws.send(frame)

    async def connect(self) -> None:
        """Open the WebSocket to Onna and run the receive loop; auto-reconnects.

        The URL includes ``?EIO=3&transport=websocket`` to request Socket.IO v2
        directly over WebSocket (no HTTP polling upgrade needed).
        ``onnaId`` is the device's unique identifier used for session routing.

        Loops forever via ``websockets.connect``'s reconnect iterator; each
        connection loss is logged and the loop restarts automatically.
        """
        import websockets  # optional dep — only needed at runtime

        url = (
            f"ws://{self._host}:{self._port}/socket.io/"
            f"?EIO=3&transport=websocket&onnaId={self._onna_id}"
        )
        _LOGGER.debug("Connecting to %s", url)

        async for ws in websockets.connect(url):
            self._ws = ws
            try:
                await self._run(ws)
            except websockets.ConnectionClosed:
                _LOGGER.warning("Onna connection closed — reconnecting")
                self._ws = None

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

        asyncio.ensure_future(_set_ready())

    async def _run(self, ws: Any) -> None:
        """Inner receive loop for a single WebSocket connection lifetime.

        Handshake sequence expected by Onna (EIO=3):
          1. Server sends EIO "0{…}" open frame (session id, ping interval, etc.)
          2. Server sends SIO "40" namespace-connect frame for "/" namespace.
          3. We send READ_CONFIGURATION (ack frame "421[…]"); Onna replies
             with "431[…]" carrying the full device state.
          4. Normal operation: server pushes "42[…]" event frames; we respond
             to "2" (EIO ping) with "3" (EIO pong) to keep the connection alive.
        """
        # Step 1: consume the EIO open frame (contains session id, ping interval).
        open_frame = await asyncio.wait_for(ws.recv(), timeout=5)
        _LOGGER.debug("EIO open: %s", open_frame[:80])

        # Step 2: server sends "40" (SIO namespace connect) automatically.
        ns_frame = await asyncio.wait_for(ws.recv(), timeout=5)
        _LOGGER.debug("Namespace: %s", ns_frame)

        # Step 3: request full device state; start the ready timer concurrently.
        await ws.send(self.build_read_configuration())
        self._schedule_ready()

        # Step 4: normal receive loop.
        async for raw in ws:
            if raw == "2":  # EIO ping — must pong within ping_timeout or server disconnects
                await ws.send("3")
                continue
            await self._process_frame(raw)
