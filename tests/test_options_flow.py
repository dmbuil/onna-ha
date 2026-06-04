"""Tests for OnnaOptionsFlow."""
import pytest
from unittest.mock import MagicMock

from custom_components.onna.config_flow import OnnaOptionsFlow


def _options_flow(current_options=None):
    flow = OnnaOptionsFlow.__new__(OnnaOptionsFlow)
    flow.hass = MagicMock()
    flow.config_entry = MagicMock()
    flow.config_entry.options = current_options or {}
    flow.config_entry.data = {
        "device_config": {
            "climate_addresses": {
                "zone_0": ["Salón+Cocina", "1_0_4", "1_0_3", "1_0_2", "1_0_1", "1_0_0", "1_0_7"],
                "zone_1": ["Dorm. Principal", "1_1_4", "1_1_3", "1_1_2", "1_1_1", "1_1_0", "1_1_7"],
            }
        }
    }
    flow._selected_zone = None
    return flow


@pytest.mark.anyio
async def test_options_zone_picker_shows_form():
    flow = _options_flow()
    result = await flow.async_step_init(user_input=None)
    assert result["type"] == "form"
    assert result["step_id"] == "zone_picker"


@pytest.mark.anyio
async def test_options_zone_picker_stores_zone_and_advances():
    flow = _options_flow()
    result = await flow.async_step_zone_picker(user_input={"zone": "zone_0"})
    assert result["type"] == "form"
    assert result["step_id"] == "zone_detail"
    assert flow._selected_zone == "zone_0"


@pytest.mark.anyio
async def test_options_zone_detail_saves_overrides():
    flow = _options_flow()
    flow._selected_zone = "zone_0"
    result = await flow.async_step_zone_detail(
        user_input={
            "temp_sensor": "sensor.my_temp",
            "window_sensor": "binary_sensor.my_window",
        }
    )
    assert result["type"] == "create_entry"
    data = result["data"]
    assert data["climate_temp_override"]["zone_0"] == "sensor.my_temp"
    assert data["climate_window_sensor"]["zone_0"] == "binary_sensor.my_window"


@pytest.mark.anyio
async def test_options_zone_detail_preserves_existing_zones():
    """Saving one zone must not erase overrides for other zones."""
    existing = {
        "climate_temp_override":  {"zone_1": "sensor.zone1_temp"},
        "climate_window_sensor":  {"zone_1": "binary_sensor.zone1_win"},
    }
    flow = _options_flow(current_options=existing)
    flow._selected_zone = "zone_0"
    result = await flow.async_step_zone_detail(
        user_input={"temp_sensor": "sensor.zone0_temp", "window_sensor": ""}
    )
    data = result["data"]
    assert data["climate_temp_override"]["zone_1"] == "sensor.zone1_temp"
    assert data["climate_temp_override"]["zone_0"] == "sensor.zone0_temp"
    assert "zone_0" not in data.get("climate_window_sensor", {})
