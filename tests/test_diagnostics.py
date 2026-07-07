"""Tests for the Onna diagnostics platform."""
import pytest
from unittest.mock import MagicMock

from custom_components.onna.const import DOMAIN, CONF_HOST, CONF_ONNA_ID


def _make_setup():
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.version = 3
    entry.data = {
        CONF_HOST: "192.168.10.3",
        CONF_ONNA_ID: "ONNA_ID",
        "device_config": {"climate_addresses": {"zone_0": ["Salón"]}},
    }
    entry.options = {"climate_temp_override": {"zone_0": "sensor.ext"}}

    coordinator = MagicMock()
    coordinator.connected = True
    coordinator.data = {"1_0_4": 21.5, "0_0_7": 1}
    coordinator.device_config = entry.data["device_config"]
    coordinator.client.config_settings = {"internalSensorOffset": -0.4}

    hass.data = {DOMAIN: {entry.entry_id: coordinator}}
    return hass, entry, coordinator


@pytest.mark.anyio
async def test_diagnostics_redacts_host_and_onna_id():
    from custom_components.onna.diagnostics import async_get_config_entry_diagnostics

    hass, entry, _ = _make_setup()
    diag = await async_get_config_entry_diagnostics(hass, entry)

    assert diag["entry"]["data"][CONF_HOST] == "**REDACTED**"
    assert diag["entry"]["data"][CONF_ONNA_ID] == "**REDACTED**"


@pytest.mark.anyio
async def test_diagnostics_includes_device_config_and_options():
    from custom_components.onna.diagnostics import async_get_config_entry_diagnostics

    hass, entry, _ = _make_setup()
    diag = await async_get_config_entry_diagnostics(hass, entry)

    assert diag["entry"]["data"]["device_config"] == entry.data["device_config"]
    assert diag["entry"]["options"] == entry.options
    assert diag["entry"]["version"] == 3


@pytest.mark.anyio
async def test_diagnostics_includes_live_state():
    from custom_components.onna.diagnostics import async_get_config_entry_diagnostics

    hass, entry, coordinator = _make_setup()
    diag = await async_get_config_entry_diagnostics(hass, entry)

    assert diag["connected"] is True
    assert diag["data"] == coordinator.data
    assert diag["config_settings"] == {"internalSensorOffset": -0.4}
