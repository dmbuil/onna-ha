"""Tests for Onna config flow."""
import pytest
from unittest.mock import MagicMock

from custom_components.onna.config_flow import OnnaConfigFlow
from custom_components.onna.const import CONF_HOST, CONF_ONNA_ID


def _flow():
    flow = OnnaConfigFlow()
    flow.hass = MagicMock()
    return flow


_VALID = {CONF_HOST: "192.168.10.3", CONF_ONNA_ID: "1HPNi16"}


# ---------------------------------------------------------------------------
# User step — form fields
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_user_step_shows_form_with_host_and_onna_id():
    flow = _flow()
    result = await flow.async_step_user(user_input=None)
    assert result["type"] == "form"
    assert result["step_id"] == "user"
    schema_keys = [str(k) for k in result["data_schema"].schema.keys()]
    assert CONF_HOST in schema_keys
    assert CONF_ONNA_ID in schema_keys


@pytest.mark.anyio
async def test_user_step_title_is_fixed_onna():
    flow = _flow()
    result = await flow.async_step_user(user_input=_VALID)
    assert result["type"] == "create_entry"
    assert result["title"] == "Onna"


@pytest.mark.anyio
async def test_user_step_stores_host_and_onna_id():
    flow = _flow()
    result = await flow.async_step_user(user_input=_VALID)
    assert result["data"][CONF_HOST] == "192.168.10.3"
    assert result["data"][CONF_ONNA_ID] == "1HPNi16"


@pytest.mark.anyio
async def test_user_step_returns_error_when_host_is_empty():
    flow = _flow()
    result = await flow.async_step_user(
        user_input={**_VALID, CONF_HOST: ""}
    )
    assert result["type"] == "form"
    assert CONF_HOST in result.get("errors", {})


@pytest.mark.anyio
async def test_user_step_returns_error_when_onna_id_is_empty():
    flow = _flow()
    result = await flow.async_step_user(
        user_input={**_VALID, CONF_ONNA_ID: ""}
    )
    assert result["type"] == "form"
    assert CONF_ONNA_ID in result.get("errors", {})
