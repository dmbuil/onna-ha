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


@pytest.mark.anyio
async def test_options_zone_detail_cleared_fields_remove_overrides():
    """Clearing both entity pickers must remove the zone's overrides.

    The frontend omits cleared optional fields entirely, and FlowManager runs
    the submitted data through the step schema before calling the handler —
    so the schema must not re-inject the stored values as defaults.
    """
    existing = {
        "climate_temp_override": {"zone_0": "sensor.old_temp"},
        "climate_window_sensor": {"zone_0": "binary_sensor.old_win"},
    }
    flow = _options_flow(current_options=existing)
    flow._selected_zone = "zone_0"

    form = await flow.async_step_zone_detail(user_input=None)
    validated = form["data_schema"]({})  # both fields cleared → keys omitted

    result = await flow.async_step_zone_detail(user_input=validated)
    data = result["data"]
    assert "zone_0" not in data.get("climate_temp_override", {})
    assert "zone_0" not in data.get("climate_window_sensor", {})


@pytest.mark.anyio
async def test_options_zone_detail_form_suggests_current_values():
    """The form still pre-fills stored overrides (as suggested values)."""
    existing = {
        "climate_temp_override": {"zone_0": "sensor.cur_temp"},
        "climate_window_sensor": {"zone_0": "binary_sensor.cur_win"},
    }
    flow = _options_flow(current_options=existing)
    flow._selected_zone = "zone_0"
    form = await flow.async_step_zone_detail(user_input=None)
    suggested = {
        str(k): (k.description or {}).get("suggested_value")
        for k in form["data_schema"].schema
    }
    assert suggested["temp_sensor"] == "sensor.cur_temp"
    assert suggested["window_sensor"] == "binary_sensor.cur_win"


# ---------------------------------------------------------------------------
# General settings — hysteresis and window-open delay
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_options_init_shows_menu_with_zones_and_general():
    flow = _options_flow()
    result = await flow.async_step_init(user_input=None)
    assert result["type"] == "menu"
    assert "zone_picker" in result["menu_options"]
    assert "general" in result["menu_options"]


@pytest.mark.anyio
async def test_options_zone_picker_step_shows_form():
    flow = _options_flow()
    result = await flow.async_step_zone_picker(user_input=None)
    assert result["type"] == "form"
    assert result["step_id"] == "zone_picker"


@pytest.mark.anyio
async def test_options_general_shows_form_with_defaults():
    flow = _options_flow()
    result = await flow.async_step_general(user_input=None)
    assert result["type"] == "form"
    assert result["step_id"] == "general"
    defaults = {str(k): k.default for k in result["data_schema"].schema}
    assert defaults["setpoint_hysteresis"] == 0.5
    assert defaults["window_open_delay"] == 600


@pytest.mark.anyio
async def test_options_general_shows_current_values():
    flow = _options_flow({"setpoint_hysteresis": 0.3, "window_open_delay": 120})
    result = await flow.async_step_general(user_input=None)
    defaults = {str(k): k.default for k in result["data_schema"].schema}
    assert defaults["setpoint_hysteresis"] == 0.3
    assert defaults["window_open_delay"] == 120


@pytest.mark.anyio
async def test_options_general_saves_values_and_preserves_others():
    existing = {"climate_temp_override": {"zone_1": "sensor.zone1_temp"}}
    flow = _options_flow(current_options=existing)
    result = await flow.async_step_general(
        user_input={"setpoint_hysteresis": 0.3, "window_open_delay": 300.0}
    )
    assert result["type"] == "create_entry"
    data = result["data"]
    assert data["setpoint_hysteresis"] == 0.3
    assert data["window_open_delay"] == 300
    assert isinstance(data["window_open_delay"], int)
    assert data["climate_temp_override"]["zone_1"] == "sensor.zone1_temp"
