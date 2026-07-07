"""Onna numeric sensor platform.

Each entry in SENSOR_ADDRESSES maps a KNX group address to an HA sensor entity
(power, voltage, water volume, temperature, etc.).  One synthetic address
(``cfg_internal_offset``) is also included — it is populated from the
READ_CONFIGURATION ack rather than from live KNX telegrams (see coordinator.py
and client.py for the two-path delivery mechanism).

Restore strategy
----------------
OnnaSensor uses RestoreSensor so numeric values survive HA restarts.

  1. ``async_get_last_sensor_data()`` reads the lightweight extra-stored-data
     store RestoreSensor maintains separately from the recorder.  If data is
     present and non-None it overwrites the coordinator seed so that, for example,
     an energy meter's ``total_increasing`` accumulator never jumps backwards.

  2. Fallback to ``async_get_last_state()`` (recorder DB) handles first boot
     after enabling restore, or when the lightweight store has been cleared.

  3. Both restore paths guard against overwriting a good coordinator seed with a
     stored None (sensor was "unknown" when last persisted).

Flow sensor staleness timeout
------------------------------
Onna marks all flow sensors ``readOnInit:true``, so on every reconnect it
broadcasts the last *stored* flow value — even if the tap closed hours ago.
A Riemann-sum integration helper in HA would then accumulate phantom litres until
the next live telegram.  To prevent this, any sensor with
``device_class=volume_flow_rate`` arms a 60-second inactivity timer whenever its
value is non-zero.  If no update arrives before the timer fires, the sensor resets
to 0.0.  Real flow updates arrive every ~10 s during actual flow, so legitimate
readings are never cut off.
"""
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
from homeassistant.helpers.event import async_call_later

from .const import DOMAIN
from .coordinator import OnnaCoordinator, SIGNAL_ADDRESS_UPDATE
from .entity import OnnaEntity

# Seconds of silence before a flow sensor is reset to 0.
# Must be comfortably longer than Onna's ~10 s update cadence during active flow.
_FLOW_STALENESS_TIMEOUT = 60


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one OnnaSensor for every address in coordinator.device_config."""
    coordinator: OnnaCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for address_id, info in coordinator.device_config["sensor_addresses"].items():
        name, unit, device_class, state_class = info
        coordinator.register_address(address_id)
        entities.append(OnnaSensor(coordinator, address_id, name, unit, device_class, state_class))
    async_add_entities(entities)


class OnnaSensor(OnnaEntity, RestoreSensor):
    """Numeric KNX sensor mirroring a single Onna group address.

    Inherits RestoreSensor to survive HA restarts.  The value is also seeded
    from coordinator.data on construction so it is correct from the very first
    state write, without waiting for the first live KNX push.
    """

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
        # Seed from coordinator.data so the entity is not "unknown" on first render.
        # coordinator.data was populated from READ_CONFIGURATION before entities are created.
        self._attr_native_value: Any = coordinator.data.get(address_id)
        # Flow sensors get a staleness timer; all others leave these as-is.
        self._is_flow_sensor: bool = (device_class == "volume_flow_rate")
        self._flow_stale_cancel: Any = None

    async def async_added_to_hass(self) -> None:
        """Restore last known value and subscribe to dispatcher updates.

        super() is required for RestoreSensor's internal bookkeeping (registers
        the entity with the restore registry so future saves are tracked).

        Restore overwrites the coordinator seed so that accumulating sensors
        (e.g. energy kWh, water m³) keep their HA-tracked total across restarts
        rather than re-seeding from Onna's potentially older value.  The None
        guard prevents a previously-stored None (sensor was "unknown" at last
        save) from erasing a good value already in coordinator.data.
        """
        await super().async_added_to_hass()  # required for RestoreSensor internals
        if (last_sensor := await self.async_get_last_sensor_data()) is not None:
            # Prefer the lightweight RestoreSensor store (fast, always current).
            # Guard: only restore if the stored value is actually known.
            if last_sensor.native_value is not None:
                self._attr_native_value = last_sensor.native_value
        elif (last_state := await self.async_get_last_state()) is not None:
            # Fallback: recorder DB — populated on first boot after enabling restore,
            # or when the lightweight store was cleared.
            if last_state.state not in ("unavailable", "unknown"):
                try:
                    self._attr_native_value = float(last_state.state)
                except (ValueError, TypeError):
                    pass

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_ADDRESS_UPDATE.format(address_id=self._address_id),
                self._handle_update,
            )
        )
        self._subscribe_connection_signal()
        if self._is_flow_sensor:
            self.async_on_remove(self._cancel_flow_timer)
            self._arm_flow_timer()

    # --- Flow sensor staleness timer ---

    @callback
    def _arm_flow_timer(self) -> None:
        """Start (or restart) the staleness countdown if flow is currently non-zero."""
        self._cancel_flow_timer()
        if self._attr_native_value:
            self._flow_stale_cancel = async_call_later(
                self.hass, _FLOW_STALENESS_TIMEOUT, self._handle_flow_stale
            )

    @callback
    def _cancel_flow_timer(self) -> None:
        """Cancel any pending staleness timer."""
        if self._flow_stale_cancel is not None:
            self._flow_stale_cancel()
            self._flow_stale_cancel = None

    @callback
    def _handle_flow_stale(self, _now: Any) -> None:
        """No update received within the staleness window — assume flow has stopped."""
        self._flow_stale_cancel = None
        self._attr_native_value = 0.0
        self.async_write_ha_state()

    @callback
    def _handle_update(self, value: Any) -> None:
        """Accept a live KNX push, refresh HA state, and rearm the staleness timer."""
        self._attr_native_value = value
        self.async_write_ha_state()
        if self._is_flow_sensor:
            self._arm_flow_timer()
