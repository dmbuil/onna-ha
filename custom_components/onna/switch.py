"""Switch platform for Onna — write-only KNX switches.

Currently covers a single switch:
  1_7_10 — Fancoil Salón Habilitar/Deshabilitar (DPT 1.001, write-only)

Why write-only
--------------
Address 1_7_10 has no read-back equivalent in Onna's KNX map: the device
accepts writes but never echoes the current state back.  This means:

  • We cannot register the address with the coordinator (no push to receive).
  • State is tracked locally after each write and persisted across
    restarts via RestoreEntity (OnnaSwitch inherits both SwitchEntity and
    RestoreEntity; the mixin provides async_get_last_state).

Current behaviour: _is_on starts as None ("unknown") on first boot.  After
the first turn_on/turn_off call, state is known and persisted in HA's recorder
so subsequent restarts can reflect the last known position.

Effect of the switch on Onna
-----------------------------
When 1_7_10 is written to 0 (disabled):
  • Onna's internal logic immediately zeroes the fancoil speed (1_7_3 → 0).
  • The fancoil valve closes (1_7_1 → 0).
  • The OnnaFan entity reflects these live pushes automatically.

When 1_7_10 is written to 1 (enabled):
  • Onna resumes normal PI control; the fancoil activates on demand.
"""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .coordinator import OnnaCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one OnnaSwitch for every address in coordinator.device_config."""
    coordinator: OnnaCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        OnnaSwitch(coordinator, address_id, info[0])
        for address_id, info in coordinator.device_config["switch_addresses"].items()
    ]
    async_add_entities(entities)


class OnnaSwitch(SwitchEntity, RestoreEntity):
    """Write-only KNX switch — state tracked locally after each write.

    Onna does not echo write-only addresses back, so this entity cannot use
    coordinator.data or dispatcher signals.  Instead, _is_on is updated
    optimistically on every turn_on/turn_off call and HA's recorder stores the
    last known value across restarts.

    Starts as None (unknown) on first boot before any write has been issued.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: OnnaCoordinator, address_id: str, name: str) -> None:
        self._coordinator    = coordinator
        self._address_id     = address_id
        self._attr_name      = name
        self._attr_unique_id = f"onna_switch_{address_id}"
        # None = unknown state (no write issued yet and no read-back available).
        self._is_on: bool | None = None

    async def async_added_to_hass(self) -> None:
        """Restore last known state on HA restart (no KNX read-back available)."""
        if (last := await self.async_get_last_state()) is not None:
            if last.state not in ("unavailable", "unknown"):
                self._is_on = last.state == "on"

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
        """Enable the fancoil — Onna resumes PI control on next demand cycle."""
        await self._coordinator.client.async_set_address_value(self._address_id, 1)
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Disable the fancoil — Onna zeroes speed and closes the valve."""
        await self._coordinator.client.async_set_address_value(self._address_id, 0)
        self._is_on = False
        self.async_write_ha_state()
