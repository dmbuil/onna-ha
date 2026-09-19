"""Push-based coordinator for Onna — no polling.

Design notes
------------
Onna is a push-only device: it sends KNX group-address updates whenever a
value changes (and on connect for addresses marked ``readOnInit:true``).  There
is no need for periodic polling, so this coordinator does not inherit from
DataUpdateCoordinator.

``coordinator.data`` is a plain dict keyed by KNX address string (e.g.
``"1_0_4"``).  It is populated in two ways:

  1. Before entity setup — async_restore_data() loads the last known value of
     every KNX address from HA storage.  This is not an optimisation: Onna
     announces *changes* only.  There is no protocol event to read an address's
     current value, and the READ_CONFIGURATION ack carries metadata (address
     names, types, links) without a single value.  So an address that does not
     change is invisible to HA forever after a restart — 0_0_7 (winter/summer)
     flips twice a year, and until it does every entity would silently use its
     constructor default.  Entities read coordinator.data in their __init__,
     so the restore has to happen before async_forward_entry_setups.

  2. After entity setup — live KNX pushes call _on_update, which updates
     coordinator.data, persists the new snapshot AND fires an HA dispatcher
     signal.  Each entity subscribes to its address signals in
     async_added_to_hass and calls async_write_ha_state on each update.

The stored snapshot is inevitably stale if the installation changes while HA is
down; it is corrected by the first telegram after reconnect.  That is strictly
better than the alternative, which is defaulting blind.

Signal names follow the pattern ``onna_address_update_{address_id}`` and are
used exclusively between the coordinator and entity listeners.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import (
    async_dispatcher_send,
    async_dispatcher_connect,
)
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store

from .client import OnnaClient
from .const import (
    DOMAIN,
    DEFAULT_HEAT_OFF_ABOVE,
    DEFAULT_COOL_OFF_BELOW,
    SEASONAL_HYSTERESIS,
)
from .seasonal import OutdoorEMA, evaluate_gate

_LOGGER = logging.getLogger(__name__)

# Each registered KNX address gets its own dispatcher signal so entities only
# wake up on changes to the specific addresses they care about.
SIGNAL_ADDRESS_UPDATE = f"{DOMAIN}_address_update_{{address_id}}"

# Fired with a bool whenever the WebSocket connection to Onna comes up or
# drops; entities use it to refresh their ``available`` state.
SIGNAL_CONNECTION = f"{DOMAIN}_connection_update"

# Fired with a bool whenever the installation-wide seasonal gate opens/closes;
# every zone entity listens and pauses/resumes exactly like the window pause.
SIGNAL_SEASONAL_GATE = f"{DOMAIN}_seasonal_gate"

# Persistence of the last known KNX values (see the module docstring).
STORAGE_VERSION = 1
# Debounce: telegrams for a busy address (0_5_3 power) arrive continuously, and
# the snapshot only has to survive a restart, not every write.
SNAPSHOT_SAVE_DELAY_S = 30

# coordinator.data also holds synthetic keys (outdoor_ema, overshoot_*,
# cfg_internal_offset).  Those are owned by other restore paths — entity
# attributes — so persisting them here would create a competing source of truth.
_KNX_ADDRESS_RE = re.compile(r"^\d+_\d+_\d+$")


class OnnaCoordinator:
    """Manages a single OnnaClient connection and dispatches HA signals.

    All entity platforms call ``register_address`` for each KNX address they
    need; the coordinator then wires the client callback → data store →
    dispatcher signal pipeline for that address.
    """

    def __init__(
        self, hass: HomeAssistant, client: OnnaClient, entry_id: str | None = None
    ) -> None:
        self.hass   = hass
        self.client = client
        # One store per config entry.  entry_id (not onna_id) keys the file:
        # the Onna ID is a credential and must not end up in a filename.
        self._store: Store | None = (
            Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}")
            if entry_id is not None
            else None
        )
        # Latest value for every registered KNX address; entities seed from here.
        self.data: dict[str, Any] = {}
        # Entity address maps derived from the device's READ_CONFIGURATION payload.
        # Set by async_setup_entry from entry.data["device_config"].
        self.device_config: dict = {}
        self._task: asyncio.Task | None = None
        # Tracks which addresses have already been registered to prevent
        # duplicate client callbacks from the same address being registered
        # by multiple entities (e.g. _WINTER_ADDR is shared by all zones).
        self._registered: set[str] = set()
        # --- Seasonal gating (installation-wide) ---
        self._outdoor_entity: str | None = None
        self._heat_off_above = DEFAULT_HEAT_OFF_ABOVE
        self._cool_off_below = DEFAULT_COOL_OFF_BELOW
        self._ema = OutdoorEMA()
        self._gate_active = False
        self._last_outdoor_reading: float | None = None
        # Cleanup handles for the live trackers wired in async_start_seasonal.
        self._seasonal_unsubs: list = []
        client.on_connection_change = self._handle_connection_change

    @property
    def connected(self) -> bool:
        """True while the WebSocket to the Onna device is up."""
        return self.client.connected

    @callback
    def _handle_connection_change(self, connected: bool) -> None:
        """Relay client connection transitions to all entities via dispatcher."""
        if not connected:
            _LOGGER.warning("Onna connection lost — entities marked unavailable")
        async_dispatcher_send(self.hass, SIGNAL_CONNECTION, connected)

    def _make_signal(self, address_id: str) -> str:
        """Return the HA dispatcher signal name for a KNX address."""
        return SIGNAL_ADDRESS_UPDATE.format(address_id=address_id)

    def _snapshot(self) -> dict[str, Any]:
        """The subset of coordinator.data worth persisting (KNX values only)."""
        return {
            addr: value
            for addr, value in self.data.items()
            if _KNX_ADDRESS_RE.match(addr)
        }

    def _persist(self) -> None:
        """Queue a debounced write of the current snapshot.

        Store flushes any pending delayed save on EVENT_HOMEASSISTANT_FINAL_WRITE,
        so a restart never loses more than the values that changed in-flight.
        """
        if self._store is not None:
            self._store.async_delay_save(self._snapshot, SNAPSHOT_SAVE_DELAY_S)

    async def async_restore_data(self) -> None:
        """Load the last known KNX values into coordinator.data.

        Must run before async_forward_entry_setups: entities read
        coordinator.data in their __init__, and anything missing there silently
        becomes a constructor default.
        """
        if self._store is None:
            return
        stored = await self._store.async_load()
        if not stored:
            return
        # Restored values lose to anything already live from this session.
        for addr, value in stored.items():
            self.data.setdefault(addr, value)

    def register_address(self, address_id: str) -> None:
        """Wire address_id into the coordinator pipeline (idempotent).

        Creates a client callback that:
          1. Stores the latest value in coordinator.data.
          2. Fires the per-address HA dispatcher signal so all listening
             entities update their state.

        Safe to call multiple times for the same address (e.g. _WINTER_ADDR
        is registered once per climate zone but the callback is only wired
        once).
        """
        if address_id in self._registered:
            return
        self._registered.add(address_id)

        async def _on_update(value: Any) -> None:
            self.data[address_id] = value
            self._persist()
            async_dispatcher_send(self.hass, self._make_signal(address_id), value)

        self.client.register_address_callback(address_id, _on_update)

    def configure_seasonal(
        self,
        outdoor_entity_id: str | None,
        heat_off_above: float,
        cool_off_below: float,
    ) -> None:
        """Store the seasonal-gating configuration (called before entity setup)."""
        self._outdoor_entity = outdoor_entity_id or None
        self._heat_off_above = float(heat_off_above)
        self._cool_off_below = float(cool_off_below)

    def seed_outdoor_ema(self, value: float | None, updated_at: float | None) -> None:
        """Restore a persisted EMA (called by the general thermostat on restore)."""
        self._ema = OutdoorEMA(value=value, updated_at=updated_at)
        # Mirror into the synthetic address so the monitoring sensor seeds too.
        if value is not None:
            self.data["outdoor_ema"] = value

    def outdoor_ema_snapshot(self) -> tuple:
        """Return (value, updated_at) for persistence / diagnostics."""
        return self._ema.value, self._ema.updated_at

    @property
    def seasonal_gate_active(self) -> bool:
        return self._gate_active

    def _apply_reading(self, now: float, reading: float) -> None:
        """Fold a new outdoor reading into the EMA and re-evaluate the gate."""
        self._last_outdoor_reading = reading
        self._ema.update(now, reading)
        # Publish the EMA as a synthetic address so the monitoring sensor tracks
        # it live (same mechanism as cfg_internal_offset).
        self.data["outdoor_ema"] = self._ema.value
        async_dispatcher_send(
            self.hass,
            self._make_signal("outdoor_ema"),
            self._ema.value,
        )
        self._reevaluate()

    @callback
    def _reevaluate(self) -> None:
        """Recompute the gate; dispatch only on a change."""
        is_winter = bool(self.data.get("0_0_7", True))
        new_gate = evaluate_gate(
            is_winter,
            self._ema.value,
            self._heat_off_above,
            self._cool_off_below,
            self._gate_active,
            SEASONAL_HYSTERESIS,
        )
        if new_gate != self._gate_active:
            self._gate_active = new_gate
            async_dispatcher_send(self.hass, SIGNAL_SEASONAL_GATE, new_gate)

    def _read_outdoor(self, state) -> float | None:
        """Extract a numeric outdoor temperature from a HA state object."""
        if state is None or state.state in ("unavailable", "unknown"):
            return None
        # weather entities carry the temperature as an attribute, not the state.
        if getattr(state, "domain", None) == "weather" or str(
            self._outdoor_entity or ""
        ).startswith("weather."):
            temp = state.attributes.get("temperature")
            return float(temp) if temp is not None else None
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return None

    async def async_start_seasonal(self) -> None:
        """Wire the live outdoor trackers (called after entity setup)."""
        if not self._outdoor_entity:
            return

        # Seed from the current state so the gate is meaningful immediately.
        state = self.hass.states.get(self._outdoor_entity)
        reading = self._read_outdoor(state)
        if reading is not None:
            self._apply_reading(time.time(), reading)

        @callback
        def _on_outdoor_change(event) -> None:
            new_reading = self._read_outdoor(event.data.get("new_state"))
            if new_reading is not None:
                self._apply_reading(time.time(), new_reading)

        @callback
        def _on_winter(_value) -> None:
            self._reevaluate()

        @callback
        def _hourly_tick(_now) -> None:
            # Re-fold the last known reading so the EMA keeps decaying toward it
            # even when the source state is not changing.
            if self._last_outdoor_reading is not None:
                self._apply_reading(time.time(), self._last_outdoor_reading)

        self._seasonal_unsubs = [
            async_track_state_change_event(
                self.hass, self._outdoor_entity, _on_outdoor_change
            ),
            async_dispatcher_connect(
                self.hass,
                self._make_signal("0_0_7"),
                _on_winter,
            ),
            async_track_time_interval(
                self.hass, _hourly_tick, timedelta(hours=1)
            ),
        ]

    async def async_start(self) -> None:
        """Start the WebSocket connection and wait for initial device state.

        Runs client.connect() as a background HA task (so HA can cancel it on
        integration unload) and then blocks until initial_ready fires or the
        timeout expires.  The timeout is generous (INIT_COLLECT_S + 5 s) to
        handle slow LAN links; if it expires the integration still loads but
        entities may start as "unknown".
        """
        self._task = self.hass.async_create_background_task(
            self.client.connect(),
            name="onna_client",
        )
        try:
            await asyncio.wait_for(
                self.client.initial_ready.wait(),
                timeout=self.client.INIT_COLLECT_S + 5,
            )
        except asyncio.TimeoutError:
            _LOGGER.warning("Onna: initial data window timed out — entities may start as unknown")

        # Seed config-derived synthetic addresses so sensor entities read them
        # from coordinator.data on first boot (before any KNX telegram arrives).
        offset = self.client.config_settings.get("internalSensorOffset")
        if offset is not None:
            self.data["cfg_internal_offset"] = offset

        _LOGGER.debug("Onna coordinator started")

    @callback
    def dispatch_config_data(self) -> None:
        """Fire dispatcher signals for config-derived synthetic addresses.

        Called from __init__.py AFTER async_forward_entry_setups so all entity
        dispatcher subscriptions are guaranteed to be registered.  This is the
        reliable delivery path for values like cfg_internal_offset that arrive
        from the READ_CONFIGURATION ack before entities exist — the coordinator
        seeds coordinator.data during async_start (fast path), and this method
        fires the live signal after setup (slow path / reconnect safety net).
        """
        offset = self.client.config_settings.get("internalSensorOffset")
        if offset is not None:
            self.data["cfg_internal_offset"] = offset
            async_dispatcher_send(
                self.hass,
                SIGNAL_ADDRESS_UPDATE.format(address_id="cfg_internal_offset"),
                offset,
            )

    async def async_stop(self) -> None:
        """Cancel the background connection task and clean up."""
        if self._store is not None:
            # An options change reloads the entry and throws this coordinator
            # away; flush now rather than leaving the delayed save to expire.
            await self._store.async_save(self._snapshot())
        for unsub in self._seasonal_unsubs:
            unsub()
        self._seasonal_unsubs = []
        await self.client.async_shutdown()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        _LOGGER.debug("Onna coordinator stopped")
