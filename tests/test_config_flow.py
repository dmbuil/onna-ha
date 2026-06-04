"""Tests for Onna config flow."""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from custom_components.onna.config_flow import OnnaConfigFlow
from custom_components.onna.const import CONF_HOST, CONF_ONNA_ID

_FIXTURE = Path(__file__).parent.parent / "out.onna.txt"


def _flow():
    flow = OnnaConfigFlow()
    flow.hass = MagicMock()
    return flow


def _valid_payload():
    return json.loads(_FIXTURE.read_text())


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
    with patch(
        "custom_components.onna.config_flow.OnnaClient.async_fetch_config",
        return_value=_valid_payload(),
    ):
        result = await flow.async_step_user(user_input=_VALID)
    assert result["type"] == "create_entry"
    assert result["title"] == "Onna"


@pytest.mark.anyio
async def test_user_step_stores_host_and_onna_id():
    flow = _flow()
    with patch(
        "custom_components.onna.config_flow.OnnaClient.async_fetch_config",
        return_value=_valid_payload(),
    ):
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


# ---------------------------------------------------------------------------
# Discover step — happy path
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_step_discover_creates_entry_with_device_config():
    """step_discover stores device_config in entry.data on success."""
    import json
    from pathlib import Path
    from unittest.mock import patch

    payload = json.loads((Path(__file__).parent.parent / "out.onna.txt").read_text())

    flow = _flow()
    with patch(
        "custom_components.onna.config_flow.OnnaClient.async_fetch_config",
        return_value=payload,
    ):
        result = await flow.async_step_user(user_input=_VALID)

    assert result["type"] == "create_entry"
    assert "device_config" in result["data"]
    assert "climate_addresses" in result["data"]["device_config"]


# ---------------------------------------------------------------------------
# Discover step — error paths
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_step_discover_returns_form_error_on_cannot_connect():
    """step_discover re-renders the user form with 'cannot_connect' on failure."""
    from unittest.mock import patch
    from custom_components.onna.client import CannotConnect

    flow = _flow()
    with patch(
        "custom_components.onna.config_flow.OnnaClient.async_fetch_config",
        side_effect=CannotConnect("timeout"),
    ):
        result = await flow.async_step_user(user_input=_VALID)

    assert result["type"] == "form"
    assert result["errors"].get("base") == "cannot_connect"


@pytest.mark.anyio
async def test_step_discover_returns_form_error_on_empty_config():
    """step_discover re-renders the user form with 'no_devices_found' when
    the payload parses to an empty climate_addresses dict."""
    from unittest.mock import patch

    flow = _flow()
    with patch(
        "custom_components.onna.config_flow.OnnaClient.async_fetch_config",
        return_value={"addresses": [], "configuration": []},
    ):
        result = await flow.async_step_user(user_input=_VALID)

    assert result["type"] == "form"
    assert result["errors"].get("base") == "no_devices_found"
