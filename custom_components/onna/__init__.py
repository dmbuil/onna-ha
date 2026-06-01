"""Onna integration — entry-point for Home Assistant.

This module wires together the three main pieces of the integration:

  1. OnnaClient  — the raw Socket.IO / WebSocket transport to 192.168.10.3:4001.
  2. OnnaCoordinator — stores the latest KNX address values and dispatches HA
     dispatcher signals to all registered entity listeners.
  3. Platform modules — sensor, binary_sensor, valve, fan, climate, switch.

Setup flow
----------
async_setup_entry is called by HA when the config entry is loaded:

  1. Create client + coordinator.
  2. async_start() opens the WebSocket in a background task and waits up to
     ~8 s for the READ_CONFIGURATION ack, which seeds coordinator.data with
     the device's current state before any entity is created.
  3. async_forward_entry_setups() creates all entity objects; each entity
     reads coordinator.data in __init__ so it starts in the correct state
     instead of "unknown".

Note: the platform modules are imported at module level (not inside
async_setup_entry) so that HA's import machinery never triggers inside the
event loop on the first call, which would block.
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .client import OnnaClient
from .const import CONF_HOST, CONF_ONNA_ID, DOMAIN
from .coordinator import OnnaCoordinator
# Pre-import platform modules so HA's import_module never runs inside the event loop.
from . import binary_sensor, climate, fan, sensor, switch, valve  # noqa: F401

PLATFORMS = ["sensor", "binary_sensor", "valve", "fan", "climate", "switch"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the Onna integration from a config entry."""
    client = OnnaClient(
        host=entry.data[CONF_HOST],
        onna_id=entry.data[CONF_ONNA_ID],
    )
    coordinator = OnnaCoordinator(hass, client)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Start the WebSocket connection and wait for READ_CONFIGURATION data.
    # All entity address-dispatcher subscriptions are registered during
    # async_forward_entry_setups; coordinator.data is pre-seeded by this point.
    await coordinator.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Tear down entities and close the WebSocket connection."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator: OnnaCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_stop()
    return unloaded
