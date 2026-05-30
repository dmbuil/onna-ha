"""Push-based coordinator for Onna — no polling."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .client import OnnaClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SIGNAL_ADDRESS_UPDATE = f"{DOMAIN}_address_update_{{address_id}}"


class OnnaCoordinator:
    """Manages a single OnnaClient connection and dispatches HA signals."""

    def __init__(self, hass: HomeAssistant, client: OnnaClient) -> None:
        self.hass   = hass
        self.client = client
        self.data: dict[str, Any] = {}
        self._task: asyncio.Task | None = None
        self._registered: set[str] = set()

    def _make_signal(self, address_id: str) -> str:
        return SIGNAL_ADDRESS_UPDATE.format(address_id=address_id)

    def register_address(self, address_id: str) -> None:
        """Subscribe to push updates for a KNX address (idempotent)."""
        if address_id in self._registered:
            return
        self._registered.add(address_id)

        async def _on_update(value: Any) -> None:
            self.data[address_id] = value
            async_dispatcher_send(self.hass, self._make_signal(address_id), value)

        self.client.register_address_callback(address_id, _on_update)

    async def async_start(self) -> None:
        """Start the background connection task and wait for initial data."""
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
        _LOGGER.debug("Onna coordinator started")

    async def async_stop(self) -> None:
        """Cancel the connection task."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        _LOGGER.debug("Onna coordinator stopped")
