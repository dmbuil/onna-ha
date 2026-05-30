"""Climate platform for Onna — per-zone thermostats and general thermostat.

Two entity types are created:

  OnnaClimate       — one per zone (Salón+Cocina, Dorm. Principal, Dorm. 2…).
                      Reads current temp and ON/OFF state from KNX; writes setpoint and ON/OFF.
                      Optionally accepts an external HA sensor as the temperature source
                      (see CLIMATE_TEMP_OVERRIDE in const.py and the section below).

  OnnaGeneralClimate — a single write-only master thermostat that broadcasts a common
                       setpoint and ON/OFF to the whole installation (addresses 0_0_1/2/3).
                       It has no current-temperature sensor and no read-back; state is local.

--- Window open detection and thermostat pause ---

To save energy, a zone thermostat can be automatically paused when its window
is opened.  Configure a HA binary_sensor (e.g. a door/window sensor that
reports "on" when open) per zone in CLIMATE_WINDOW_SENSOR in const.py.

Behaviour:
  • Window opens  → a 60-second debounce timer starts.  If the window is
                    closed again before the timer fires, nothing happens.
  • Timer fires   → if the zone is ON, it is turned off and
                    _window_pause_active is set.  If the zone was already
                    OFF, no action is taken.
  • Window closes → the timer (if still pending) is cancelled; if the pause
                    was active the zone is immediately turned back ON.
  • User overrides (async_turn_on/off from HA or an automation) always clear
                    the pause flag so the window close does not fight the user.

The current window state and pause flag are exposed as extra_state_attributes
(window_open, window_pause_active) for use in Lovelace cards or automations.

--- External sensor override and setpoint compensation ---

Onna's built-in probes are mounted inside the KNX thermostat housings, which can read
several degrees lower than the actual room temperature (e.g. they face a cold wall or sit
near the floor). To fix this without removing the hardware, configure an external HA sensor
for that zone in CLIMATE_TEMP_OVERRIDE.

When an external sensor is configured:
  • current_temperature shown in HA uses the external sensor.
  • The setpoint written to the Onna KNX bus is *compensated* so that Onna's own probe
    triggers heating/cooling at the correct room temperature:

        onna_setpoint = user_target − (ext_temp − onna_temp)

    Example: user wants 25.5 °C, external reads 27.4, Onna probe reads 25.4
        offset       = 27.4 − 25.4 = 2.0 °C
        onna_setpoint = 25.5 − 2.0  = 23.5 °C

    Onna now cools until its probe reaches 23.5 °C, which corresponds to the room
    being at ~25.5 °C according to the real sensor.

  • Compensation re-triggers automatically whenever either sensor reading shifts by ≥ 0.5 °C.

  • When the external sensor goes offline, current_temperature falls back to Onna's probe
    and the raw user setpoint is written to Onna (no compensation). Any setpoint change
    made from Onna's native app during that offline window is still synced back to HA.

  • The last compensated setpoint written to the bus is persisted in extra_state_attributes
    so that after an HA restart the stale Onna echo (which carries the compensated value,
    not the user's intended value) is correctly identified and ignored.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CLIMATE_ADDRESSES, CLIMATE_TEMP_OVERRIDE, CLIMATE_WINDOW_SENSOR, DOMAIN
from .coordinator import OnnaCoordinator, SIGNAL_ADDRESS_UPDATE

_WINTER_ADDR         = "0_0_7"
_WINDOW_OPEN_DELAY   = 60  # seconds before a sustained open window pauses the thermostat
_GENERAL_SETPOINT_W = "0_0_2"
_GENERAL_ONOFF_W    = "0_0_1"
_GENERAL_MODE_W     = "0_0_3"  # Modo Invierno/Verano General write (1=winter/heat, 0=summer/cool)
_GENERAL_SEED_ADDR  = "1_0_3"  # Salón+Cocina setpoint — seeds initial general value


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: OnnaCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[ClimateEntity] = []

    for zone_id, (name, temp_addr, setpoint_r, setpoint_w, onoff_r, onoff_w, demand_addr) in CLIMATE_ADDRESSES.items():
        coordinator.register_address(temp_addr)
        coordinator.register_address(setpoint_r)
        coordinator.register_address(onoff_r)
        coordinator.register_address(demand_addr)
        coordinator.register_address(_WINTER_ADDR)
        entities.append(OnnaClimate(
            coordinator, name,
            temp_addr, setpoint_r, setpoint_w,
            onoff_r, onoff_w, demand_addr,
            external_temp_entity_id=CLIMATE_TEMP_OVERRIDE.get(zone_id),
            window_sensor_entity_id=CLIMATE_WINDOW_SENSOR.get(zone_id),
        ))

    coordinator.register_address(_WINTER_ADDR)
    entities.append(OnnaGeneralClimate(coordinator))

    async_add_entities(entities)


# ---------------------------------------------------------------------------
# Per-zone thermostat
# ---------------------------------------------------------------------------
# Each zone maps to one physical KNX thermostat.  HA can only turn it ON/OFF
# per-zone; HEAT vs COOL is a global installation setting (address 0_0_7) that
# cannot be changed per-zone without affecting the whole house.  Accordingly,
# set_hvac_mode(HEAT/COOL) is a no-op here — use OnnaGeneralClimate for that.
class OnnaClimate(ClimateEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 7.0
    _attr_max_temp = 35.0

    def __init__(
        self,
        coordinator: OnnaCoordinator,
        name: str,
        temp_addr: str,
        setpoint_r_addr: str,
        setpoint_w_addr: str,
        onoff_r_addr: str,
        onoff_w_addr: str,
        demand_addr: str,
        external_temp_entity_id: str | None = None,
        window_sensor_entity_id: str | None = None,
    ) -> None:
        self._coordinator    = coordinator
        self._attr_name      = name
        self._attr_unique_id = f"onna_climate_{onoff_r_addr}"
        self._temp_addr      = temp_addr
        self._setpoint_r     = setpoint_r_addr
        self._setpoint_w     = setpoint_w_addr
        self._onoff_r        = onoff_r_addr
        self._onoff_w        = onoff_w_addr
        self._demand_addr    = demand_addr
        # Optional HA entity ID of an external temperature sensor for this zone.
        # When set, current_temperature is taken from that sensor instead of Onna's probe,
        # and the setpoint written to KNX is offset-compensated (see module docstring).
        # To add a new zone override, add an entry to CLIMATE_TEMP_OVERRIDE in const.py.
        self._external_temp  = external_temp_entity_id

        data = coordinator.data
        self._onna_temp: float | None    = data.get(temp_addr)
        self._ext_temp: float | None     = None
        self._ext_available: bool        = False
        self._target_temp: float | None  = data.get(setpoint_r_addr, 20.0)
        self._is_on: bool  = bool(data.get(onoff_r_addr, False))
        self._demand: bool = bool(data.get(demand_addr, False))
        self._winter: bool = bool(data.get(_WINTER_ADDR, True))
        # Optional HA entity ID of a window/door binary sensor for this zone.
        # When the sensor reports "on" (open) for longer than _WINDOW_OPEN_DELAY seconds,
        # the thermostat is paused.  It resumes automatically when the window closes.
        # To add a zone, add an entry to CLIMATE_WINDOW_SENSOR in const.py.
        self._window_sensor         = window_sensor_entity_id
        self._window_open: bool     = False
        self._window_pause_active: bool = False
        # Cancellation handle returned by async_call_later; None when no timer is pending.
        self._window_cancel_timer: Any  = None

        # Last setpoint actually written to the Onna KNX bus.  When compensation is active this
        # differs from _target_temp (the user's intent).  Persisted via extra_state_attributes so
        # that after an HA restart we can recognise the stale Onna echo and not overwrite the
        # restored user setpoint with the compensated value.
        self._last_written_setpoint: float | None = None

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._coordinator.client._onna_id)},
            "name": "Onna",
            "manufacturer": "Opendomo Things S.L.",
            "model": "Onna M Lite",
        }

    @property
    def current_temperature(self) -> float | None:
        if self._external_temp and self._ext_available:
            return self._ext_temp
        return self._onna_temp

    @property
    def target_temperature(self) -> float | None:
        return self._target_temp

    @property
    def hvac_mode(self) -> HVACMode:
        if not self._is_on:
            return HVACMode.OFF
        return HVACMode.HEAT if self._winter else HVACMode.COOL

    @property
    def hvac_action(self) -> HVACAction:
        if not self._is_on:
            return HVACAction.OFF
        if not self._demand:
            return HVACAction.IDLE
        return HVACAction.HEATING if self._winter else HVACAction.COOLING

    def _compute_onna_setpoint(self) -> float | None:
        # When external sensor is available, shift the setpoint by the offset between the two
        # probes so that Onna's internal controller reaches the correct room temperature:
        #   offset        = ext_temp − onna_temp
        #   onna_setpoint = user_target − offset
        # Falls back to the raw user target when the external sensor is offline or not configured.
        if (
            self._target_temp is not None
            and self._external_temp
            and self._ext_available
            and self._ext_temp is not None
            and self._onna_temp is not None
        ):
            offset = self._ext_temp - self._onna_temp
            compensated = self._target_temp - offset
            return max(self._attr_min_temp, min(self._attr_max_temp, round(compensated, 1)))
        return self._target_temp

    async def _push_compensated_setpoint(self) -> None:
        # Only write when the value has changed by at least one step (0.5 °C) to avoid
        # flooding the KNX bus on every small sensor fluctuation.
        setpoint = self._compute_onna_setpoint()
        if setpoint is None:
            return
        if (
            self._last_written_setpoint is None
            or abs(setpoint - self._last_written_setpoint) >= 0.5
        ):
            self._last_written_setpoint = setpoint
            await self._coordinator.client.async_set_address_value(self._setpoint_w, setpoint)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            self._target_temp = float(temp)
            self.async_write_ha_state()  # persist user intent — echo may be compensated and ignored
            self._last_written_setpoint = None  # force write even if compensated value unchanged
            await self._push_compensated_setpoint()

    async def async_turn_on(self) -> None:
        self._window_pause_active = False  # user override — window close won't re-pause
        await self._coordinator.client.async_set_address_value(self._onoff_w, 1)

    async def async_turn_off(self) -> None:
        self._window_pause_active = False  # explicit OFF — window close won't auto-resume
        await self._coordinator.client.async_set_address_value(self._onoff_w, 0)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
        # HEAT / COOL are global (0_0_7) — cannot change per-zone without affecting all zones

    async def async_added_to_hass(self) -> None:
        if last_state := await self.async_get_last_state():
            if (temp := last_state.attributes.get("temperature")) is not None:
                self._target_temp = float(temp)
            if self._external_temp:
                sp = last_state.attributes.get("_onna_compensated_setpoint")
                if sp is not None:
                    self._last_written_setpoint = float(sp)

        for addr, handler in self._subscriptions():
            self.async_on_remove(
                async_dispatcher_connect(
                    self.hass,
                    SIGNAL_ADDRESS_UPDATE.format(address_id=addr),
                    handler,
                )
            )
        if self._external_temp:
            # Seed from current HA state
            state = self.hass.states.get(self._external_temp)
            if state and state.state not in ("unavailable", "unknown"):
                try:
                    self._ext_temp = float(state.state)
                    self._ext_available = True
                except ValueError:
                    pass
            # Subscribe to future changes
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    self._external_temp,
                    self._handle_external_temp,
                )
            )

        if self._window_sensor:
            # Seed from current window state
            state = self.hass.states.get(self._window_sensor)
            if state and state.state not in ("unavailable", "unknown"):
                self._window_open = state.state == "on"
            # Subscribe to future window state changes
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    self._window_sensor,
                    self._handle_window_change,
                )
            )
            # Cancel any pending timer when the entity is removed
            self.async_on_remove(self._cancel_window_timer)

    def _subscriptions(self) -> list[tuple[str, Any]]:
        return [
            (self._temp_addr,   self._handle_temp),
            (self._setpoint_r,  self._handle_setpoint),
            (self._onoff_r,     self._handle_onoff),
            (self._demand_addr, self._handle_demand),
            (_WINTER_ADDR,      self._handle_winter),
        ]

    @callback
    def _handle_temp(self, value: Any) -> None:
        self._onna_temp = value
        self.async_write_ha_state()
        # Onna's probe shifted → offset changed → re-push compensated setpoint if active.
        if self._external_temp and self._ext_available and self._last_written_setpoint is not None:
            self.hass.async_create_task(self._push_compensated_setpoint())

    @property
    def extra_state_attributes(self) -> dict | None:
        attrs: dict = {}
        if self._external_temp and self._last_written_setpoint is not None:
            attrs["_onna_compensated_setpoint"] = self._last_written_setpoint
        if self._window_sensor:
            attrs["window_open"] = self._window_open
            attrs["window_pause_active"] = self._window_pause_active
        return attrs or None

    @callback
    def _handle_setpoint(self, value: Any) -> None:
        if self._external_temp and self._ext_available:
            # Compensation active — echo is the compensated value, not the user's intent.
            pass
        elif (
            self._external_temp
            and self._last_written_setpoint is not None
            and round(value, 1) == round(self._last_written_setpoint, 1)
        ):
            # External offline but echo matches our last compensated write — stale echo,
            # not a genuine change (e.g. HA just restarted and Onna echoed the old value).
            pass
        else:
            self._target_temp = value
        self.async_write_ha_state()

    @callback
    def _handle_onoff(self, value: Any) -> None:
        self._is_on = bool(value)
        self.async_write_ha_state()

    @callback
    def _handle_demand(self, value: Any) -> None:
        self._demand = bool(value)
        self.async_write_ha_state()

    @callback
    def _handle_winter(self, value: Any) -> None:
        self._winter = bool(value)
        self.async_write_ha_state()

    @callback
    def _handle_external_temp(self, event: Any) -> None:
        new_state = event.data.get("new_state")
        if new_state and new_state.state not in ("unavailable", "unknown"):
            try:
                self._ext_temp = float(new_state.state)
                self._ext_available = True
            except ValueError:
                self._ext_available = False
        else:
            self._ext_available = False
        self.async_write_ha_state()
        # External temp shifted → offset changed → re-push compensated setpoint.
        if self._ext_available and self._target_temp is not None:
            self.hass.async_create_task(self._push_compensated_setpoint())

    # --- Window open / close handling ---

    @callback
    def _cancel_window_timer(self) -> None:
        if self._window_cancel_timer is not None:
            self._window_cancel_timer()
            self._window_cancel_timer = None

    @callback
    def _handle_window_change(self, event: Any) -> None:
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in ("unavailable", "unknown"):
            return
        is_open = new_state.state == "on"
        if is_open == self._window_open:
            return
        self._window_open = is_open
        self.async_write_ha_state()

        if is_open:
            # Start debounce timer — only pause after a sustained open.
            self._window_cancel_timer = async_call_later(
                self.hass, _WINDOW_OPEN_DELAY, self._handle_window_delay_elapsed
            )
        else:
            # Window closed — cancel any pending timer.
            self._cancel_window_timer()
            if self._window_pause_active:
                self._window_pause_active = False
                self.hass.async_create_task(
                    self._coordinator.client.async_set_address_value(self._onoff_w, 1)
                )
                self.async_write_ha_state()

    @callback
    def _handle_window_delay_elapsed(self, _now: Any) -> None:
        self._window_cancel_timer = None
        # Only pause if the zone is currently on; already-off zones need no action.
        if self._window_open and self._is_on:
            self._window_pause_active = True
            self.hass.async_create_task(
                self._coordinator.client.async_set_address_value(self._onoff_w, 0)
            )
            self.async_write_ha_state()


# ---------------------------------------------------------------------------
# Global/master thermostat
# ---------------------------------------------------------------------------
# Write-only master that controls the whole installation at once:
#   0_0_1  ON/OFF   (1 = on, 0 = off)
#   0_0_2  setpoint (broadcast to all zones)
#   0_0_3  mode     (1 = winter/heat, 0 = summer/cool)
#
# There is no global current-temperature sensor in Onna, so current_temperature
# always returns None.  State (mode, setpoint) is kept locally and persisted via
# RestoreEntity; Onna does not echo back these addresses.
#
# The initial setpoint is seeded from zone 0 (Salón+Cocina, address 1_0_3) because
# it is the largest zone and most representative of the whole installation's state.
class OnnaGeneralClimate(ClimateEntity, RestoreEntity):
    """Write-only master thermostat — broadcasts setpoint/ON-OFF to all zones."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_name = "Temperatura General"
    _attr_unique_id = "onna_climate_general"
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 7.0
    _attr_max_temp = 35.0

    def __init__(self, coordinator: OnnaCoordinator) -> None:
        self._coordinator  = coordinator
        self._target_temp: float | None = coordinator.data.get(_GENERAL_SEED_ADDR, 20.0)
        self._hvac_mode    = HVACMode.HEAT_COOL
        self._winter: bool = bool(coordinator.data.get(_WINTER_ADDR, True))

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._coordinator.client._onna_id)},
            "name": "Onna",
            "manufacturer": "Opendomo Things S.L.",
            "model": "Onna M Lite",
        }

    @property
    def current_temperature(self) -> None:
        return None

    @property
    def target_temperature(self) -> float | None:
        return self._target_temp

    @property
    def hvac_mode(self) -> HVACMode:
        return self._hvac_mode

    @property
    def hvac_action(self) -> HVACAction:
        if self._hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        return HVACAction.HEATING if self._winter else HVACAction.COOLING

    async def async_turn_on(self) -> None:
        await self._coordinator.client.async_set_address_value(_GENERAL_ONOFF_W, 1)

    async def async_turn_off(self) -> None:
        await self._coordinator.client.async_set_address_value(_GENERAL_ONOFF_W, 0)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            self._target_temp = float(temp)
            await self._coordinator.client.async_set_address_value(_GENERAL_SETPOINT_W, float(temp))
            self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self._hvac_mode = hvac_mode
        if hvac_mode == HVACMode.OFF:
            await self._coordinator.client.async_set_address_value(_GENERAL_ONOFF_W, 0)
        else:
            is_winter = hvac_mode == HVACMode.HEAT
            await self._coordinator.client.async_set_address_value(_GENERAL_MODE_W, 1 if is_winter else 0)
            await self._coordinator.client.async_set_address_value(_GENERAL_ONOFF_W, 1)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        if last_state := await self.async_get_last_state():
            if last_state.state in (HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF):
                self._hvac_mode = HVACMode(last_state.state)
            if (temp := last_state.attributes.get("temperature")) is not None:
                self._target_temp = float(temp)

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_ADDRESS_UPDATE.format(address_id=_WINTER_ADDR),
                self._handle_winter,
            )
        )

    @callback
    def _handle_winter(self, value: Any) -> None:
        self._winter = bool(value)
        self.async_write_ha_state()
