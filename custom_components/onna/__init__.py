"""Onna integration setup."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .client import OnnaClient
from .const import CONF_HOST, CONF_ONNA_ID, DOMAIN
from .coordinator import OnnaCoordinator
from . import binary_sensor, climate, fan, sensor, switch, valve  # pre-import so HA loader never hits import_module inside the event loop

PLATFORMS = ["sensor", "binary_sensor", "valve", "fan", "climate", "switch"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = OnnaClient(
        host=entry.data[CONF_HOST],
        onna_id=entry.data[CONF_ONNA_ID],
    )
    coordinator = OnnaCoordinator(hass, client)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await coordinator.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator: OnnaCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_stop()
    return unloaded
