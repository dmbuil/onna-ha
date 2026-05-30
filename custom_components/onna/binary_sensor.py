"""Onna binary sensors."""
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

from .const import DOMAIN, BINARY_SENSOR_ADDRESSES
from .coordinator import OnnaCoordinator, SIGNAL_ADDRESS_UPDATE


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: OnnaCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for address_id, (name, device_class, inverted) in BINARY_SENSOR_ADDRESSES.items():
        coordinator.register_address(address_id)
        entities.append(OnnaBinarySensor(coordinator, address_id, name, device_class, inverted))
    async_add_entities(entities)


class OnnaBinarySensor(BinarySensorEntity):
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
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_ADDRESS_UPDATE.format(address_id=self._address_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self, value: Any) -> None:
        self._attr_is_on = (not value) if self._inverted else bool(value)
        self.async_write_ha_state()
