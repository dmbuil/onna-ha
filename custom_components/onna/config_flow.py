"""Config flow and options flow for the Onna integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig

from .client import CannotConnect, OnnaClient
from .config_parser import parse_device_config
from .const import CONF_HOST, CONF_ONNA_ID, DOMAIN

_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_ONNA_ID): str,
    }
)


class OnnaConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 2

    def __init__(self) -> None:
        self._pending_host: str = ""
        self._pending_onna_id: str = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        errors: dict[str, str] = {}

        if user_input is not None:
            if not user_input.get(CONF_HOST, "").strip():
                errors[CONF_HOST] = "invalid_host"
            elif not user_input.get(CONF_ONNA_ID, "").strip():
                errors[CONF_ONNA_ID] = "invalid_onna_id"
            else:
                self._pending_host = user_input[CONF_HOST].strip()
                self._pending_onna_id = user_input[CONF_ONNA_ID].strip()
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
        return OnnaOptionsFlow(config_entry)


class OnnaOptionsFlow(OptionsFlow):
    """Two-step options flow: pick a zone, then configure its sensor overrides."""

    def __init__(self, config_entry) -> None:
        self.config_entry = config_entry
        self._selected_zone: str | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return await self.async_step_zone_picker(user_input)

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
        schema = vol.Schema(
            {
                vol.Optional(
                    "temp_sensor",
                    default=current_opts.get("climate_temp_override", {}).get(zone_id, ""),
                ): EntitySelector(EntitySelectorConfig(domain="sensor")),
                vol.Optional(
                    "window_sensor",
                    default=current_opts.get("climate_window_sensor", {}).get(zone_id, ""),
                ): EntitySelector(EntitySelectorConfig(domain="binary_sensor")),
            }
        )
        return self.async_show_form(step_id="zone_detail", data_schema=schema)
