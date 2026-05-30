"""Onna valve entities (read-only KNX state)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.valve import ValveDeviceClass, ValveEntity, ValveEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, VALVE_ADDRESSES, VALVE_POSITION_ADDRESSES
from .coordinator import OnnaCoordinator, SIGNAL_ADDRESS_UPDATE


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: OnnaCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[ValveEntity] = []
    for address_id, (name, device_class) in VALVE_ADDRESSES.items():
        coordinator.register_address(address_id)
        entities.append(OnnaValve(coordinator, address_id, name, device_class))
    for position_addr, (name, device_class, cabezal_addr) in VALVE_POSITION_ADDRESSES.items():
        coordinator.register_address(position_addr)
        coordinator.register_address(cabezal_addr)
        entities.append(OnnaPositionValve(coordinator, position_addr, cabezal_addr, name, device_class))
    async_add_entities(entities)


class OnnaValve(ValveEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_reports_position = False

    def __init__(
        self,
        coordinator: OnnaCoordinator,
        address_id: str,
        name: str,
        device_class: str,
    ) -> None:
        self._coordinator = coordinator
        self._address_id  = address_id
        self._attr_name   = name
        self._attr_unique_id = f"onna_{address_id}"
        self._attr_device_class = ValveDeviceClass(device_class)
        self._is_open: bool = bool(coordinator.data.get(address_id, False))

    @property
    def is_closed(self) -> bool:
        return not self._is_open

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._coordinator.client._onna_id)},
            "name": "Onna",
            "manufacturer": "Opendomo Things S.L.",
            "model": "Onna M Lite",
        }

    async def async_added_to_hass(self) -> None:
        if (last := await self.async_get_last_state()) is not None:
            if last.state not in ("unavailable", "unknown"):
                self._is_open = last.state == "open"
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_ADDRESS_UPDATE.format(address_id=self._address_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self, value: Any) -> None:
        self._is_open = bool(value)
        self.async_write_ha_state()


class OnnaPositionValve(ValveEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_reports_position = True
    _attr_supported_features = ValveEntityFeature.SET_POSITION

    def __init__(
        self,
        coordinator: OnnaCoordinator,
        position_address: str,
        cabezal_address: str,
        name: str,
        device_class: str,
    ) -> None:
        self._coordinator     = coordinator
        self._position_address = position_address
        self._cabezal_address  = cabezal_address
        self._attr_name       = name
        self._attr_unique_id  = f"onna_{position_address}"
        self._attr_device_class = ValveDeviceClass(device_class)
        raw = coordinator.data.get(position_address)
        self._position: int | None = int(raw) if raw is not None else None
        self._cabezal_open: bool = bool(coordinator.data.get(cabezal_address, False))

    @property
    def current_valve_position(self) -> int | None:
        return self._position

    @property
    def is_closed(self) -> bool:
        return not self._cabezal_open

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._coordinator.client._onna_id)},
            "name": "Onna",
            "manufacturer": "Opendomo Things S.L.",
            "model": "Onna M Lite",
        }

    async def async_added_to_hass(self) -> None:
        if (last := await self.async_get_last_state()) is not None:
            if last.state not in ("unavailable", "unknown"):
                self._cabezal_open = last.state == "open"
            if (pos := last.attributes.get("current_position")) is not None:
                self._position = int(pos)
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_ADDRESS_UPDATE.format(address_id=self._position_address),
                self._handle_position_update,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_ADDRESS_UPDATE.format(address_id=self._cabezal_address),
                self._handle_cabezal_update,
            )
        )

    async def async_set_valve_position(self, position: int) -> None:
        """Move the valve to a specific position."""

    @callback
    def _handle_position_update(self, value: Any) -> None:
        self._position = int(value) if value is not None else None
        self.async_write_ha_state()

    @callback
    def _handle_cabezal_update(self, value: Any) -> None:
        self._cabezal_open = bool(value)
        self.async_write_ha_state()
