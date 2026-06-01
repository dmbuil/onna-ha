"""Push-based coordinator for Onna — no polling.

Design notes
------------
Onna is a push-only device: it sends KNX group-address updates whenever a
value changes (and on connect for addresses marked ``readOnInit:true``).  There
is no need for periodic polling, so this coordinator does not inherit from
DataUpdateCoordinator.

``coordinator.data`` is a plain dict keyed by KNX address string (e.g.
``"1_0_4"``).  It is populated in two ways:

  1. Before entity setup — OnnaClient.INIT_COLLECT_S seconds after
     READ_CONFIGURATION is sent, initial_ready fires and async_start() returns.
     By that time coordinator.data already contains all values pushed by Onna
     on connect (current temperatures, setpoints, alarms, etc.).  Entities read
     coordinator.data in their __init__ so they start in the known state.

  2. After entity setup — live KNX pushes call _on_update, which updates
     coordinator.data AND fires an HA dispatcher signal.  Each entity
     subscribes to its address signals in async_added_to_hass and calls
     async_write_ha_state on each update.

Signal names follow the pattern ``onna_address_update_{address_id}`` and are
used exclusively between the coordinator and entity listeners.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .client import OnnaClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Each registered KNX address gets its own dispatcher signal so entities only
# wake up on changes to the specific addresses they care about.
SIGNAL_ADDRESS_UPDATE = f"{DOMAIN}_address_update_{{address_id}}"


class OnnaCoordinator:
    """Manages a single OnnaClient connection and dispatches HA signals.

    All entity platforms call ``register_address`` for each KNX address they
    need; the coordinator then wires the client callback → data store →
    dispatcher signal pipeline for that address.
    """

    def __init__(self, hass: HomeAssistant, client: OnnaClient) -> None:
        self.hass   = hass
        self.client = client
        # Latest value for every registered KNX address; entities seed from here.
        self.data: dict[str, Any] = {}
        self._task: asyncio.Task | None = None
        # Tracks which addresses have already been registered to prevent
        # duplicate client callbacks from the same address being registered
        # by multiple entities (e.g. _WINTER_ADDR is shared by all zones).
        self._registered: set[str] = set()

    def _make_signal(self, address_id: str) -> str:
        """Return the HA dispatcher signal name for a KNX address."""
        return SIGNAL_ADDRESS_UPDATE.format(address_id=address_id)

    def register_address(self, address_id: str) -> None:
        """Wire address_id into the coordinator pipeline (idempotent).

        Creates a client callback that:
          1. Stores the latest value in coordinator.data.
          2. Fires the per-address HA dispatcher signal so all listening
             entities update their state.

        Safe to call multiple times for the same address (e.g. _WINTER_ADDR
        is registered once per climate zone but the callback is only wired
        once).
        """
        if address_id in self._registered:
            return
        self._registered.add(address_id)

        async def _on_update(value: Any) -> None:
            self.data[address_id] = value
            async_dispatcher_send(self.hass, self._make_signal(address_id), value)

        self.client.register_address_callback(address_id, _on_update)

    async def async_start(self) -> None:
        """Start the WebSocket connection and wait for initial device state.

        Runs client.connect() as a background HA task (so HA can cancel it on
        integration unload) and then blocks until initial_ready fires or the
        timeout expires.  The timeout is generous (INIT_COLLECT_S + 5 s) to
        handle slow LAN links; if it expires the integration still loads but
        entities may start as "unknown".
        """
        self._task = self.hass.async_create_background_task(
            self.client.connect(),
            name="onna_client",
        )
        try:
            await asyncio.wait_for(
                self.client.initial_ready.wait(),
                timeout=self.client.INIT_COLLECT_S + 5,
            )
        except asyncio.TimeoutError:
            _LOGGER.warning("Onna: initial data window timed out — entities may start as unknown")

        # Seed config-derived synthetic addresses so sensor entities read them
        # from coordinator.data on first boot (before any KNX telegram arrives).
        offset = self.client.config_settings.get("internalSensorOffset")
        if offset is not None:
            self.data["cfg_internal_offset"] = offset

        _LOGGER.debug("Onna coordinator started")

    @callback
    def dispatch_config_data(self) -> None:
        """Fire dispatcher signals for config-derived synthetic addresses.

        Called from __init__.py AFTER async_forward_entry_setups so all entity
        dispatcher subscriptions are guaranteed to be registered.  This is the
        reliable delivery path for values like cfg_internal_offset that arrive
        from the READ_CONFIGURATION ack before entities exist — the coordinator
        seeds coordinator.data during async_start (fast path), and this method
        fires the live signal after setup (slow path / reconnect safety net).
        """
        offset = self.client.config_settings.get("internalSensorOffset")
        if offset is not None:
            self.data["cfg_internal_offset"] = offset
            async_dispatcher_send(
                self.hass,
                SIGNAL_ADDRESS_UPDATE.format(address_id="cfg_internal_offset"),
                offset,
            )

    async def async_stop(self) -> None:
        """Cancel the background connection task and clean up."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        _LOGGER.debug("Onna coordinator stopped")
