"""Switch platform for Onna — write-only KNX switches (no read-back address)."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SWITCH_ADDRESSES
from .coordinator import OnnaCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: OnnaCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        OnnaSwitch(coordinator, address_id, name)
        for address_id, (name,) in SWITCH_ADDRESSES.items()
    ]
    async_add_entities(entities)


class OnnaSwitch(SwitchEntity):
    """Write-only switch — state tracked locally after each write."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: OnnaCoordinator, address_id: str, name: str) -> None:
        self._coordinator    = coordinator
        self._address_id     = address_id
        self._attr_name      = name
        self._attr_unique_id = f"onna_switch_{address_id}"
        self._is_on: bool | None = None  # unknown until first write

    @property
    def is_on(self) -> bool | None:
        return self._is_on

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._coordinator.client._onna_id)},
            "name": "Onna",
            "manufacturer": "Opendomo Things S.L.",
            "model": "Onna M Lite",
        }

    async def async_turn_on(self, **kwargs) -> None:
        await self._coordinator.client.async_set_address_value(self._address_id, 1)
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self._coordinator.client.async_set_address_value(self._address_id, 0)
        self._is_on = False
        self.async_write_ha_state()
