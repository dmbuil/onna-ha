"""Config flow for Onna integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow

from .const import CONF_HOST, CONF_ONNA_ID, DOMAIN

_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_ONNA_ID): str,
    }
)


class OnnaConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

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
                return self.async_create_entry(title="Onna", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_SCHEMA,
            errors=errors,
        )
