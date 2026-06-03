"""Fan platform for Onna — fancoil entity with manual override support.

The fancoil (Salón+Cocina) is driven automatically by Onna: it starts when the zone
demands cooling/heating and its speed is set by Onna's PI algorithm.

Write methods (turn_on, turn_off, set_percentage) perform a manual override: they write
to address 1_7_2 (speed write) and set _override_active = True.  Onna's AND-gate logic
then updates the valve automatically.  The override clears when the Salón+Cocina
thermostat ON/OFF state (1_0_1) receives a push from the device.

Live Onna pushes to 1_7_1 (valve state) and 1_7_3 (speed state) always update the
displayed state, even during an active override — Onna's automatic control is always
reflected in the entity.

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
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, FAN_ADDRESSES
from .coordinator import OnnaCoordinator, SIGNAL_ADDRESS_UPDATE


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create an OnnaFan entity for every fancoil in FAN_ADDRESSES."""
    coordinator: OnnaCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for _, (name, valve_addr, speed_addr, speed_write_addr) in FAN_ADDRESSES.items():
        coordinator.register_address(valve_addr)
        coordinator.register_address(speed_addr)
        entities.append(OnnaFan(coordinator, name, valve_addr, speed_addr, speed_write_addr))
    coordinator.register_address("1_0_1")
    async_add_entities(entities)


class OnnaFan(FanEntity, RestoreEntity):
    """Fancoil entity with manual override support.

    During normal operation, the fancoil is activated and speed-controlled by
    Onna's PI algorithm whenever the Salón+Cocina thermostat demands heating or
    cooling.  The displayed state always reflects live Onna pushes.

    Write methods (turn_on, turn_off, set_percentage) write to the speed address
    and set _override_active = True.  The override clears when the thermostat's
    ON/OFF state (1_0_1) fires a dispatcher push.

    To enable/disable the fancoil for the season, use the companion switch
    entity (address 1_7_10) — Onna respects that flag and zeroes speed when
    disabled.
    """

    _attr_should_poll = False
    _attr_supported_features = FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF | FanEntityFeature.SET_SPEED

    def __init__(self, coordinator: OnnaCoordinator, name: str, valve_address: str, speed_address: str, speed_write_address: str) -> None:
        self._coordinator = coordinator
        self._attr_name = name
        # valve_address (1_7_1): fancoil on/off state — Onna sets this based on demand.
        self._valve_address = valve_address
        # speed_address (1_7_3): fancoil speed 0-100 % — Onna's PI output.
        self._speed_address = speed_address
        # speed_write_address (1_7_2): written by HA during manual override.
        self._speed_write_address = speed_write_address
        self._is_on: bool = bool(coordinator.data.get(valve_address, False))
        raw = coordinator.data.get(speed_address)
        self._percentage: int | None = int(raw) if raw is not None else None
        self._override_active: bool = False

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
    def _handle_thermostat_onoff(self, value: Any) -> None:
        if self._override_active:
            self._override_active = False
            self.async_write_ha_state()

    @callback
    def _handle_valve_update(self, value: Any) -> None:
        """Accept a fancoil on/off push from Onna and refresh state."""
        self._is_on = bool(value)
        self.async_write_ha_state()

    @callback
    def _handle_speed_update(self, value: Any) -> None:
        """Accept a fancoil speed push from Onna and refresh state."""
        self._percentage = int(value) if value is not None else None
        self.async_write_ha_state()

    async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs) -> None:
        speed = percentage if percentage is not None else (self._percentage if self._percentage else 50)
        await self._coordinator.client.async_set_address_value(self._speed_write_address, speed)
        self._override_active = True
        self._is_on = True
        self._percentage = speed
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self._coordinator.client.async_set_address_value(self._speed_write_address, 0)
        self._override_active = True
        self._is_on = False
        self._percentage = 0
        self.async_write_ha_state()

    async def async_set_percentage(self, percentage: int) -> None:
        await self._coordinator.client.async_set_address_value(self._speed_write_address, percentage)
        self._override_active = True
        self._is_on = percentage > 0
        self._percentage = percentage
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore last known state and subscribe to valve and speed dispatcher signals."""
        if (last := await self.async_get_last_state()) is not None:
            if last.state not in ("unavailable", "unknown"):
                self._is_on = last.state == "on"
            if (pct := last.attributes.get("percentage")) is not None:
                self._percentage = int(pct)
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
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_ADDRESS_UPDATE.format(address_id="1_0_1"),
                self._handle_thermostat_onoff,
            )
        )
