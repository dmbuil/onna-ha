"""Onna integration — entry-point for Home Assistant.

This module wires together the three main pieces of the integration:

  1. OnnaClient  — the raw Socket.IO / WebSocket transport to the Onna device.
  2. OnnaCoordinator — stores the latest KNX address values and dispatches HA
     dispatcher signals to all registered entity listeners.
  3. Platform modules — sensor, binary_sensor, valve, fan, climate, switch.

Setup flow
----------
async_setup_entry is called by HA when the config entry is loaded:

  1. Seed coordinator.device_config from entry.data["device_config"].
  2. Create client + coordinator.
  3. async_start() opens the WebSocket in a background task and waits up to
     ~8 s for the READ_CONFIGURATION ack, which seeds coordinator.data with
     the device's current state before any entity is created.
  4. async_forward_entry_setups() creates all entity objects; each entity
     reads coordinator.data / coordinator.device_config in __init__ so it
     starts in the correct state instead of "unknown".

Migration
---------
VERSION 1 entries (pre-discovery) have no device_config in entry.data.
async_migrate_entry builds it from the hardcoded legacy constants and
upgrades the entry to VERSION 2, keeping all entity unique-IDs unchanged.
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


def _legacy_device_config() -> dict:
    """Build device_config from hardcoded constants for VERSION 1 migration."""
    from .const import (
        SENSOR_ADDRESSES, BINARY_SENSOR_ADDRESSES,
        VALVE_ADDRESSES, VALVE_POSITION_ADDRESSES,
        CLIMATE_ADDRESSES, SWITCH_ADDRESSES, FAN_ADDRESSES,
    )
    fan_addresses: dict = {}
    for fan_id, info in FAN_ADDRESSES.items():
        fan_addresses[fan_id] = list(info) + ["1_0_1"]

    return {
        "sensor_addresses":         {k: list(v) for k, v in SENSOR_ADDRESSES.items()},
        "binary_sensor_addresses":  {k: list(v) for k, v in BINARY_SENSOR_ADDRESSES.items()},
        "valve_addresses":          {k: list(v) for k, v in VALVE_ADDRESSES.items()},
        "valve_position_addresses": {k: list(v) for k, v in VALVE_POSITION_ADDRESSES.items()},
        "climate_addresses":        {k: list(v) for k, v in CLIMATE_ADDRESSES.items()},
        "switch_addresses":         {k: list(v) for k, v in SWITCH_ADDRESSES.items()},
        "fan_addresses":            fan_addresses,
    }


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entries from VERSION 1 (no device_config) to VERSION 2."""
    if entry.version == 1:
        new_data = {**entry.data, "device_config": _legacy_device_config()}
        hass.config_entries.async_update_entry(entry, data=new_data, version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the Onna integration from a config entry."""
    client = OnnaClient(
        host=entry.data[CONF_HOST],
        onna_id=entry.data[CONF_ONNA_ID],
    )
    coordinator = OnnaCoordinator(hass, client)
    coordinator.device_config = entry.data["device_config"]
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

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
