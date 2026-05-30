"""Onna Socket.IO client — socket.io v2 / EIO=3 over WebSocket."""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine

_LOGGER = logging.getLogger(__name__)

_SIO_EVENT_PREFIX = "42"
_SIO_ACK_PREFIX   = "421"

AddressCallback = Callable[[Any], Coroutine]


class OnnaClient:
    # Seconds to collect spontaneous pushes after READ_CONFIGURATION before
    # signalling the coordinator that initial data is ready.
    INIT_COLLECT_S: float = 3.0
    """Async client for the Onna local socket.io server.

    Usage::

        client = OnnaClient(host="192.168.10.3", onna_id="1HPNi16")
        client.register_address_callback("1_0_4", my_callback)
        await client.connect()          # blocks — runs the receive loop
    """

    def __init__(self, host: str, onna_id: str, port: int = 4001) -> None:
        self._host    = host
        self._onna_id = onna_id
        self._port    = port
        self._ws: Any = None
        self._callbacks: dict[str, list[AddressCallback]] = defaultdict(list)
        self.initial_ready: asyncio.Event = asyncio.Event()

    # ------------------------------------------------------------------
    # Static helpers (pure, testable without a live connection)
    # ------------------------------------------------------------------

    @staticmethod
    def parse_sio_event(frame: str) -> tuple[str, dict] | None:
        """Parse a raw Socket.IO v2 frame.

        Returns (event_name, payload_dict) for SET_ADDRESS_VALUE_FROM_SERVER
        events that carry a dict payload, or None for all other frames.
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
        """Build a SET_ADDRESS_VALUE_FROM_CLIENT socket.io frame."""
        return _SIO_EVENT_PREFIX + json.dumps(
            ["SET_ADDRESS_VALUE_FROM_CLIENT", {"id": address_id, "value": value}],
            separators=(",", ":"),
        )

    @staticmethod
    def build_read_configuration(ack_id: int = 1) -> str:
        """Build a READ_CONFIGURATION frame with acknowledgement."""
        return f"{_SIO_EVENT_PREFIX}{ack_id}" + json.dumps(
            ["READ_CONFIGURATION"],
            separators=(",", ":"),
        )

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------

    def register_address_callback(self, address_id: str, cb: AddressCallback) -> None:
        """Register an async callback for a KNX address."""
        self._callbacks[address_id].append(cb)

    # ------------------------------------------------------------------
    # Internal dispatch
    # ------------------------------------------------------------------

    async def _dispatch_address_update(self, address_id: str, value: Any) -> None:
        for cb in self._callbacks.get(address_id, []):
            await cb(value)

    async def _process_frame(self, frame: str) -> None:
        """Handle one incoming WebSocket frame."""
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
        """Write a value to a KNX group address via the Onna server."""
        if self._ws is None:
            raise RuntimeError("Not connected")
        frame = self.build_set_address_value(address_id, value)
        await self._ws.send(frame)

    async def connect(self) -> None:
        """Connect to the Onna server and run the receive loop forever."""
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
        """Schedule initial_ready to be set after INIT_COLLECT_S seconds."""
        async def _set_ready() -> None:
            await asyncio.sleep(self.INIT_COLLECT_S)
            self.initial_ready.set()

        asyncio.ensure_future(_set_ready())

    async def _run(self, ws: Any) -> None:
        """Inner receive loop for one WebSocket connection."""
        # Consume the EIO open frame
        open_frame = await asyncio.wait_for(ws.recv(), timeout=5)
        _LOGGER.debug("EIO open: %s", open_frame[:80])

        # Server sends namespace connect (40) automatically
        ns_frame = await asyncio.wait_for(ws.recv(), timeout=5)
        _LOGGER.debug("Namespace: %s", ns_frame)

        # Request initial state and start the ready timer
        await ws.send(self.build_read_configuration())
        self._schedule_ready()

        async for raw in ws:
            if raw == "2":          # EIO ping
                await ws.send("3")
                continue
            await self._process_frame(raw)
