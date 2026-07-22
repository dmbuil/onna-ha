"""Config flow and options flow for the Onna integration."""
from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .client import CannotConnect, OnnaClient
from .config_parser import parse_device_config
from .const import (
    CONF_HOST,
    CONF_ONNA_ID,
    DEFAULT_PRESET_TEMPS,
    DEFAULT_SETPOINT_HYSTERESIS,
    DEFAULT_WINDOW_OPEN_DELAY,
    DOMAIN,
    PRESET_KEYS,
)

_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_ONNA_ID): str,
    }
)

# IP addresses or hostnames (e.g. onna.local) — no URL metacharacters, so the
# value can never alter the WebSocket URL structure built in client.py.
_HOST_RE = re.compile(r"^[A-Za-z0-9.-]+$")
# Device IDs are alphanumeric (e.g. "ONNA_ID"); allow - and _ to be safe.
_ONNA_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class OnnaConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 3

    def __init__(self) -> None:
        self._pending_host: str = ""
        self._pending_onna_id: str = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input.get(CONF_HOST, "").strip()
            onna_id = user_input.get(CONF_ONNA_ID, "").strip()
            if not _HOST_RE.match(host):
                errors[CONF_HOST] = "invalid_host"
            elif not _ONNA_ID_RE.match(onna_id):
                errors[CONF_ONNA_ID] = "invalid_onna_id"
            else:
                self._pending_host = host
                self._pending_onna_id = onna_id
                # The onna_id uniquely identifies the device — abort if an
                # entry for it already exists instead of creating a duplicate.
                await self.async_set_unique_id(self._pending_onna_id)
                self._abort_if_unique_id_configured()
                return await self.async_step_discover()

        return self.async_show_form(
            step_id="user",
            data_schema=_SCHEMA,
            errors=errors,
        )

    async def async_step_discover(self) -> dict[str, Any]:
        """Connect to device, fetch full config, create entry (no form shown)."""
        try:
            raw = await OnnaClient.async_fetch_config(
                self._pending_host, self._pending_onna_id
            )
        except CannotConnect:
            return self.async_show_form(
                step_id="user",
                data_schema=_SCHEMA,
                errors={"base": "cannot_connect"},
            )

        device_config = parse_device_config(raw)
        if not device_config.get("climate_addresses"):
            return self.async_show_form(
                step_id="user",
                data_schema=_SCHEMA,
                errors={"base": "no_devices_found"},
            )

        return self.async_create_entry(
            title="Onna",
            data={
                CONF_HOST: self._pending_host,
                CONF_ONNA_ID: self._pending_onna_id,
                "device_config": device_config,
            },
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return OnnaOptionsFlow()


class OnnaOptionsFlow(OptionsFlow):
    """Options flow: a menu leading to per-zone sensor overrides or general tuning."""

    def __init__(self) -> None:
        # config_entry is set by HA's framework on _config_entry; do NOT assign here.
        self._selected_zone: str | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return self.async_show_menu(
            step_id="init",
            menu_options=["zone_picker", "general", "presets"],
        )

    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Installation-wide tuning: setpoint hysteresis and window-open delay."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    **dict(self.config_entry.options),
                    "setpoint_hysteresis": float(user_input["setpoint_hysteresis"]),
                    "window_open_delay": int(user_input["window_open_delay"]),
                }
            )

        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    "setpoint_hysteresis",
                    default=opts.get("setpoint_hysteresis", DEFAULT_SETPOINT_HYSTERESIS),
                ): NumberSelector(NumberSelectorConfig(
                    min=0.0, max=5.0, step=0.1,
                    unit_of_measurement="°C", mode=NumberSelectorMode.BOX,
                )),
                vol.Optional(
                    "window_open_delay",
                    default=opts.get("window_open_delay", DEFAULT_WINDOW_OPEN_DELAY),
                ): NumberSelector(NumberSelectorConfig(
                    min=10, max=3600, step=10,
                    unit_of_measurement="s", mode=NumberSelectorMode.BOX,
                )),
            }
        )
        return self.async_show_form(step_id="general", data_schema=schema)

    async def async_step_presets(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Global preset (heat, cool) pairs, shared by every zone.

        `heat` is used in winter (target_temp_low), `cool` in summer
        (target_temp_high).  Enforces heat <= cool for every preset.
        """
        errors: dict[str, str] = {}
        stored = self.config_entry.options.get("preset_temps", {})

        def _pair(key: str) -> tuple[float, float]:
            if key in stored:
                lo, hi = stored[key]
                return float(lo), float(hi)
            return DEFAULT_PRESET_TEMPS[key]

        if user_input is not None:
            preset_temps: dict[str, list[float]] = {}
            for key in PRESET_KEYS:
                heat = float(user_input[f"{key}_heat"])
                cool = float(user_input[f"{key}_cool"])
                if heat > cool:
                    errors["base"] = "preset_heat_gt_cool"
                preset_temps[key] = [heat, cool]
            if not errors:
                return self.async_create_entry(
                    data={
                        **dict(self.config_entry.options),
                        "preset_temps": preset_temps,
                    }
                )

        fields: dict[Any, Any] = {}
        for key in PRESET_KEYS:
            heat_default, cool_default = _pair(key)
            fields[vol.Optional(f"{key}_heat", default=heat_default)] = NumberSelector(
                NumberSelectorConfig(
                    min=7.0, max=35.0, step=0.5,
                    unit_of_measurement="°C", mode=NumberSelectorMode.BOX,
                )
            )
            fields[vol.Optional(f"{key}_cool", default=cool_default)] = NumberSelector(
                NumberSelectorConfig(
                    min=7.0, max=35.0, step=0.5,
                    unit_of_measurement="°C", mode=NumberSelectorMode.BOX,
                )
            )
        return self.async_show_form(
            step_id="presets", data_schema=vol.Schema(fields), errors=errors
        )

    async def async_step_zone_picker(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if user_input is not None:
            self._selected_zone = user_input["zone"]
            return await self.async_step_zone_detail()

        climate_zones: dict = (
            self.config_entry.data.get("device_config", {}).get("climate_addresses", {})
        )
        zone_options = {zone_id: info[0] for zone_id, info in climate_zones.items()}
        schema = vol.Schema({vol.Required("zone"): vol.In(zone_options)})
        return self.async_show_form(step_id="zone_picker", data_schema=schema)

    async def async_step_zone_detail(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if user_input is not None:
            current = dict(self.config_entry.options)
            temp_overrides = dict(current.get("climate_temp_override", {}))
            win_sensors = dict(current.get("climate_window_sensor", {}))

            zone = self._selected_zone
            temp = (user_input.get("temp_sensor") or "").strip()
            win  = (user_input.get("window_sensor") or "").strip()

            if temp:
                temp_overrides[zone] = temp
            else:
                temp_overrides.pop(zone, None)

            if win:
                win_sensors[zone] = win
            else:
                win_sensors.pop(zone, None)

            return self.async_create_entry(
                data={
                    **current,
                    "climate_temp_override": temp_overrides,
                    "climate_window_sensor": win_sensors,
                }
            )

        zone_id = self._selected_zone
        current_opts = self.config_entry.options
        # suggested_value (not default=) so a cleared picker stays absent from
        # the submitted data instead of being refilled with the stored entity.
        schema = vol.Schema(
            {
                vol.Optional(
                    "temp_sensor",
                    description={
                        "suggested_value": current_opts.get(
                            "climate_temp_override", {}
                        ).get(zone_id)
                    },
                ): EntitySelector(EntitySelectorConfig(domain="sensor")),
                vol.Optional(
                    "window_sensor",
                    description={
                        "suggested_value": current_opts.get(
                            "climate_window_sensor", {}
                        ).get(zone_id)
                    },
                ): EntitySelector(EntitySelectorConfig(domain="binary_sensor")),
            }
        )
        return self.async_show_form(step_id="zone_detail", data_schema=schema)
