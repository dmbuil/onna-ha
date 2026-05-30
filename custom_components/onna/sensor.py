"""Onna numeric sensors."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SENSOR_ADDRESSES
from .coordinator import OnnaCoordinator, SIGNAL_ADDRESS_UPDATE


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: OnnaCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for address_id, (name, unit, device_class, state_class) in SENSOR_ADDRESSES.items():
        coordinator.register_address(address_id)
        entities.append(OnnaSensor(coordinator, address_id, name, unit, device_class, state_class))
    async_add_entities(entities)


class OnnaSensor(RestoreSensor):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: OnnaCoordinator,
        address_id: str,
        name: str,
        unit: str,
        device_class: str | None,
        state_class: str,
    ) -> None:
        self._coordinator  = coordinator
        self._address_id   = address_id
        self._attr_name    = name
        self._attr_native_unit_of_measurement = unit
        self._attr_unique_id = f"onna_{address_id}"
        if device_class:
            self._attr_device_class = SensorDeviceClass(device_class)
        self._attr_state_class = SensorStateClass(state_class)
        self._attr_native_value: Any = coordinator.data.get(address_id)

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._coordinator.client._onna_id)},
            "name": "Onna",
            "manufacturer": "Opendomo Things S.L.",
            "model": "Onna M Lite",
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()  # required for RestoreSensor internals
        if (last := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = last.native_value
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_ADDRESS_UPDATE.format(address_id=self._address_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self, value: Any) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()
