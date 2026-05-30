"""Fan platform for Onna — read-only fancoil status entities.

The fancoil (Salón+Cocina) is driven entirely by Onna: it starts automatically when the
zone demands cooling/heating and its speed is set by Onna's PI algorithm.  HA cannot and
should not override this — attempting to turn the fancoil on/off or set its speed from HA
would conflict with Onna's control loop.

For this reason, async_turn_on, async_turn_off, and async_set_percentage are intentional
no-ops.  The TURN_ON, TURN_OFF, and SET_SPEED features are declared only so that HA renders
the fan card correctly (with an on/off toggle and a speed slider for visual feedback).

To enable or disable the fancoil entirely (e.g. for the off-season), use the companion
OnnaSwitch entity ("Fancoil Salón Habilitado", address 1_7_10) in switch.py.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, FAN_ADDRESSES
from .coordinator import OnnaCoordinator, SIGNAL_ADDRESS_UPDATE


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: OnnaCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for _, (name, valve_addr, speed_addr) in FAN_ADDRESSES.items():
        coordinator.register_address(valve_addr)
        coordinator.register_address(speed_addr)
        entities.append(OnnaFan(coordinator, name, valve_addr, speed_addr))
    async_add_entities(entities)


class OnnaFan(FanEntity):
    _attr_should_poll = False
    _attr_supported_features = FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF | FanEntityFeature.SET_SPEED

    def __init__(self, coordinator: OnnaCoordinator, name: str, valve_address: str, speed_address: str) -> None:
        self._coordinator = coordinator
        self._attr_name = name
        self._valve_address = valve_address
        self._speed_address = speed_address
        self._is_on: bool = bool(coordinator.data.get(valve_address, False))
        raw = coordinator.data.get(speed_address)
        self._percentage: int | None = int(raw) if raw is not None else None

    @property
    def unique_id(self) -> str:
        return f"onna_{self._valve_address}"

    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def percentage(self) -> int | None:
        return self._percentage

    @property
    def percentage_step(self) -> float:
        return 1

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._coordinator.client._onna_id)},
            "name": "Onna",
            "manufacturer": "Opendomo Things S.L.",
            "model": "Onna M Lite",
        }

    @callback
    def _handle_valve_update(self, value: Any) -> None:
        self._is_on = bool(value)
        self.async_write_ha_state()

    @callback
    def _handle_speed_update(self, value: Any) -> None:
        self._percentage = int(value) if value is not None else None
        self.async_write_ha_state()

    async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs) -> None:
        """Fancoil is controlled automatically by Onna — enable via the switch entity."""

    async def async_turn_off(self, **kwargs) -> None:
        """Fancoil is controlled automatically by Onna — disable via the switch entity."""

    async def async_set_percentage(self, percentage: int) -> None:
        """Speed is set automatically by Onna based on demand."""

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_ADDRESS_UPDATE.format(address_id=self._valve_address),
                self._handle_valve_update,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_ADDRESS_UPDATE.format(address_id=self._speed_address),
                self._handle_speed_update,
            )
        )
