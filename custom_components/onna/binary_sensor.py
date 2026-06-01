"""Onna binary sensor platform.

Covers alarms (flood, fire) and per-zone thermostat ON/OFF state.

Why RestoreEntity
-----------------
Most of these addresses have ``readOnInit:true`` in Onna's configuration, so
Onna broadcasts their value on every reconnect and coordinator.data is already
populated before entities are set up.  RestoreEntity is still used here as a
safety net:

  • Alarms: if HA restarts during an active alarm event and Onna has not yet
    pushed a new update, we want the alarm entity to start as "on" rather
    than "unknown" until the next device push arrives.

  • Zone ON/OFF (1_X_1): Onna broadcasts this on connect, but the readOnInit
    update and the entity setup race.  RestoreEntity ensures a brief "unknown"
    flash never appears in the UI on restart.

The inverted flag is reserved for future addresses where KNX DPT semantics
are active-low (none of the current addresses use it, but the infrastructure
is in place).
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, BINARY_SENSOR_ADDRESSES
from .coordinator import OnnaCoordinator, SIGNAL_ADDRESS_UPDATE


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one OnnaBinarySensor for every address in BINARY_SENSOR_ADDRESSES."""
    coordinator: OnnaCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for address_id, (name, device_class, inverted) in BINARY_SENSOR_ADDRESSES.items():
        coordinator.register_address(address_id)
        entities.append(OnnaBinarySensor(coordinator, address_id, name, device_class, inverted))
    async_add_entities(entities)


class OnnaBinarySensor(BinarySensorEntity, RestoreEntity):
    """Binary KNX sensor that mirrors a single Onna group address.

    Supports optional value inversion for active-low KNX addresses.
    Restores its last known state on HA restart so alarm and zone ON/OFF
    entities never show an "unknown" flash while waiting for the first push.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: OnnaCoordinator,
        address_id: str,
        name: str,
        device_class: str | None,
        inverted: bool,
    ) -> None:
        self._coordinator = coordinator
        self._address_id  = address_id
        self._attr_name   = name
        self._attr_unique_id = f"onna_{address_id}"
        self._inverted    = inverted
        if device_class:
            self._attr_device_class = BinarySensorDeviceClass(device_class)
        # Seed from coordinator data (populated from READ_CONFIGURATION on connect).
        raw = coordinator.data.get(address_id, False)
        self._attr_is_on = (not raw) if inverted else bool(raw)

    @property
    def is_on(self) -> bool:
        return self._attr_is_on

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._coordinator.client._onna_id)},
            "name": "Onna",
            "manufacturer": "Opendomo Things S.L.",
            "model": "Onna M Lite",
        }

    async def async_added_to_hass(self) -> None:
        """Restore last known state and subscribe to dispatcher updates.

        Restored state is ignored if it was "unavailable" or "unknown" —
        we only carry forward a definitive on/off value.
        """
        if (last := await self.async_get_last_state()) is not None:
            if last.state not in ("unavailable", "unknown"):
                self._attr_is_on = last.state == "on"
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_ADDRESS_UPDATE.format(address_id=self._address_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self, value: Any) -> None:
        """Accept a live KNX push and refresh the HA state."""
        self._attr_is_on = (not value) if self._inverted else bool(value)
        self.async_write_ha_state()
