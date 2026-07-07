"""Shared base behavior for all Onna entities.

OnnaEntity is a mixin providing the two things every platform repeats:

  • device_info — all entities belong to the single Onna M Lite device.
  • available  — mirrors the live WebSocket connection state so entities go
    unavailable (instead of showing stale values) when the device drops off
    the network, and recover automatically on reconnect.

Subclasses must set ``self._coordinator`` in ``__init__`` and call
``_subscribe_connection_signal()`` from ``async_added_to_hass``.
"""
from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN
from .coordinator import OnnaCoordinator, SIGNAL_CONNECTION


class OnnaEntity:
    """Mixin: common device registry info and connection-based availability."""

    _coordinator: OnnaCoordinator

    @property
    def available(self) -> bool:
        """Entities are available only while the WebSocket to Onna is up."""
        return self._coordinator.connected

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self._coordinator.client.onna_id)},
            "name": "Onna",
            "manufacturer": "Opendomo Things S.L.",
            "model": "Onna M Lite",
        }

    def _subscribe_connection_signal(self) -> None:
        """Refresh HA state on every connection up/down transition."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_CONNECTION, self._handle_connection_change
            )
        )

    @callback
    def _handle_connection_change(self, _connected: bool) -> None:
        self.async_write_ha_state()
