"""Diagnostics support for Onna.

Downloadable from the device page in HA (⋮ → Download diagnostics).  Includes
everything needed to debug a report from another installation:

  • entry data/options — the discovered device_config (address maps per
    platform) and the user's zone sensor overrides.
  • connected          — whether the WebSocket to the device is currently up.
  • config_settings    — settings extracted from the READ_CONFIGURATION ack.
  • data               — the latest value of every registered KNX address.

The host IP and onna_id are redacted: the onna_id is the only credential the
device has, and diagnostics files are routinely attached to public issues.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_HOST, CONF_ONNA_ID, DOMAIN
from .coordinator import OnnaCoordinator

TO_REDACT = {CONF_HOST, CONF_ONNA_ID}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: OnnaCoordinator = hass.data[DOMAIN][entry.entry_id]

    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
            "version": entry.version,
        },
        "connected": coordinator.connected,
        "config_settings": dict(coordinator.client.config_settings),
        "data": dict(coordinator.data),
    }
