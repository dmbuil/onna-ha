"""Onna valve platform — read-only KNX valve state entities.

Two valve entity types:

  OnnaValve         — simple boolean (open/closed) for installation-level valves:
                      0_0_5 (underfloor heating EV) and 0_0_6 (collector valves).
                      Controlled automatically by the zone thermostats; HA only
                      monitors them.

  OnnaPositionValve — per-zone underfloor heating valve with two signals:
                      position_addr (1_X_8): PI demand 0-100 % — how open the valve is.
                      cabezal_addr  (1_X_6): cabezal actuator state (open/closed).
                      SET_POSITION is declared so HA renders a position slider, but
                      async_set_valve_position is a no-op — Onna's own PID loop
                      controls the valve position based on zone thermostat demand.

Both entity types use RestoreEntity so that valve state survives HA restarts
without an "unknown" flash while waiting for the next KNX push from Onna.
"""
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
    """Create OnnaValve and OnnaPositionValve entities from const address maps."""
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
    """Simple boolean valve entity (open/closed) for installation-level valves.

    Covers:
      0_0_5 — floor heating electrovalve (EV Suelo Radiante)
      0_0_6 — collector valves (Válvulas Colector)

    These are driven automatically by the zone thermostat logic inside Onna.
    HA only reads their state for monitoring/dashboards; no write support.
    """

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
        """Restore last valve state and subscribe to push updates."""
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
        """Accept a live KNX push and refresh the HA state."""
        self._is_open = bool(value)
        self.async_write_ha_state()


class OnnaPositionValve(ValveEntity, RestoreEntity):
    """Per-zone underfloor heating valve with position and actuator state.

    Tracks two KNX addresses per zone:
      position_addr (1_X_8): PI demand 0-100 % — reported as current_valve_position.
      cabezal_addr  (1_X_6): cabezal actuator open/closed — drives is_closed.

    The position and on/off state are independent: the cabezal can be closed
    (zone off) while the PI demand is still non-zero (zone is warming up or
    the controller hasn't zeroed it yet).

    SET_POSITION is declared (required by HA to render a position slider) but
    the implementation is intentionally a no-op: Onna's own PID loop owns the
    valve position and HA writes would be immediately overwritten.
    """

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
        """Return True when the cabezal actuator is closed (zone off)."""
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
        """Restore last valve state and subscribe to both position and cabezal pushes."""
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
        """No-op — valve position is controlled exclusively by Onna's PID loop.

        Declared so that HA renders the position slider in the UI for monitoring,
        but any write from HA would be immediately overwritten by Onna's controller.
        """

    @callback
    def _handle_position_update(self, value: Any) -> None:
        """Accept a PI demand push (0-100 %) and refresh state."""
        self._position = int(value) if value is not None else None
        self.async_write_ha_state()

    @callback
    def _handle_cabezal_update(self, value: Any) -> None:
        """Accept a cabezal actuator state push and refresh state."""
        self._cabezal_open = bool(value)
        self.async_write_ha_state()
