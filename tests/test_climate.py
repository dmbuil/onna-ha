"""Tests for OnnaClimate, OnnaFancoilClimate and OnnaGeneralClimate."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.onna.climate import (
    OnnaClimate,
    OnnaGeneralClimate,
)
from unittest.mock import patch
from custom_components.onna.coordinator import SIGNAL_ADDRESS_UPDATE


def _make_coordinator(data=None):
    coord = MagicMock()
    coord.data = data or {}
    coord.client._onna_id = "TESTID"
    coord.client.async_set_address_value = AsyncMock()
    return coord


def _make_zone(data=None):
    coord = _make_coordinator(data)
    return OnnaClimate(
        coord, "Salón+Cocina",
        "1_0_4", "1_0_3", "1_0_2",
        "1_0_1", "1_0_0", "1_0_7",
    )



# ---------------------------------------------------------------------------
# OnnaClimate — initial state
# ---------------------------------------------------------------------------

def test_climate_current_temp_from_coordinator():
    zone = _make_zone({"1_0_4": 21.5})
    assert zone.current_temperature == 21.5


def test_climate_target_temp_from_coordinator():
    zone = _make_zone({"1_0_3": 22.0})
    assert zone.target_temperature == 22.0


def test_climate_hvac_mode_off_when_zone_off():
    from custom_components.onna.climate import HVACMode
    zone = _make_zone({"1_0_1": False})
    assert zone.hvac_mode == HVACMode.OFF


def test_climate_hvac_mode_heat_when_on_and_winter():
    from custom_components.onna.climate import HVACMode
    zone = _make_zone({"1_0_1": True, "0_0_7": True})
    assert zone.hvac_mode == HVACMode.HEAT


def test_climate_hvac_mode_cool_when_on_and_summer():
    from custom_components.onna.climate import HVACMode
    zone = _make_zone({"1_0_1": True, "0_0_7": False})
    assert zone.hvac_mode == HVACMode.COOL


def test_climate_hvac_action_off_when_zone_off():
    from custom_components.onna.climate import HVACAction
    zone = _make_zone({"1_0_1": False})
    assert zone.hvac_action == HVACAction.OFF


def test_climate_hvac_action_idle_when_on_no_demand():
    from custom_components.onna.climate import HVACAction
    zone = _make_zone({"1_0_1": True, "1_0_7": False, "0_0_7": True})
    assert zone.hvac_action == HVACAction.IDLE


def test_climate_hvac_action_heating_when_demand_and_winter():
    from custom_components.onna.climate import HVACAction
    zone = _make_zone({"1_0_1": True, "1_0_7": True, "0_0_7": True})
    assert zone.hvac_action == HVACAction.HEATING


def test_climate_hvac_action_cooling_when_demand_and_summer():
    from custom_components.onna.climate import HVACAction
    zone = _make_zone({"1_0_1": True, "1_0_7": True, "0_0_7": False})
    assert zone.hvac_action == HVACAction.COOLING


# ---------------------------------------------------------------------------
# OnnaClimate — write operations
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_set_temperature_writes_to_setpoint_address():
    zone = _make_zone()
    await zone.async_set_temperature(temperature=23.5)
    zone._coordinator.client.async_set_address_value.assert_called_once_with("1_0_2", 23.5)


@pytest.mark.anyio
async def test_set_hvac_mode_off_writes_zero_to_onoff():
    from custom_components.onna.climate import HVACMode
    zone = _make_zone()
    await zone.async_set_hvac_mode(HVACMode.OFF)
    zone._coordinator.client.async_set_address_value.assert_called_once_with("1_0_0", 0)


@pytest.mark.anyio
async def test_set_hvac_mode_heat_is_noop():
    from custom_components.onna.climate import HVACMode
    zone = _make_zone()
    await zone.async_set_hvac_mode(HVACMode.HEAT)
    zone._coordinator.client.async_set_address_value.assert_not_called()


@pytest.mark.anyio
async def test_set_hvac_mode_cool_is_noop():
    from custom_components.onna.climate import HVACMode
    zone = _make_zone()
    await zone.async_set_hvac_mode(HVACMode.COOL)
    zone._coordinator.client.async_set_address_value.assert_not_called()


# ---------------------------------------------------------------------------
# OnnaClimate — dispatcher updates
# ---------------------------------------------------------------------------

def test_handle_temp_updates_state():
    zone = _make_zone()
    zone.async_write_ha_state = MagicMock()
    zone._handle_temp(23.0)
    assert zone.current_temperature == 23.0
    zone.async_write_ha_state.assert_called_once()


def test_handle_setpoint_updates_state():
    zone = _make_zone()
    zone.async_write_ha_state = MagicMock()
    zone._handle_setpoint(24.0)
    assert zone.target_temperature == 24.0
    zone.async_write_ha_state.assert_called_once()


def test_handle_onoff_switches_mode_to_heat():
    from custom_components.onna.climate import HVACMode
    zone = _make_zone({"1_0_1": False, "0_0_7": True})
    zone.async_write_ha_state = MagicMock()
    zone._handle_onoff(True)
    assert zone.hvac_mode == HVACMode.HEAT
    zone.async_write_ha_state.assert_called_once()


def test_handle_demand_updates_action():
    from custom_components.onna.climate import HVACAction
    zone = _make_zone({"1_0_1": True, "0_0_7": True})
    zone.async_write_ha_state = MagicMock()
    zone._handle_demand(True)
    assert zone.hvac_action == HVACAction.HEATING
    zone.async_write_ha_state.assert_called_once()


def test_handle_winter_switches_action():
    from custom_components.onna.climate import HVACAction
    zone = _make_zone({"1_0_1": True, "1_0_7": True, "0_0_7": True})
    zone.async_write_ha_state = MagicMock()
    zone._handle_winter(False)
    assert zone.hvac_action == HVACAction.COOLING
    zone.async_write_ha_state.assert_called_once()


# ---------------------------------------------------------------------------
# OnnaClimate — metadata
# ---------------------------------------------------------------------------

def test_climate_unique_id_uses_onoff_state_addr():
    zone = _make_zone()
    assert zone.unique_id == "onna_climate_1_0_1"


@pytest.mark.anyio
async def test_async_added_connects_five_signals():
    zone = _make_zone()
    zone.hass = MagicMock()
    zone.async_on_remove = MagicMock()
    with patch(
        "custom_components.onna.climate.async_dispatcher_connect",
        return_value=lambda: None,
    ) as mock_connect:
        await zone.async_added_to_hass()
    assert mock_connect.call_count == 5



# ---------------------------------------------------------------------------
# External temperature override
# ---------------------------------------------------------------------------

def _make_zone_with_override(data=None):
    coord = _make_coordinator(data)
    return OnnaClimate(
        coord, "Salón+Cocina",
        "1_0_4", "1_0_3", "1_0_2",
        "1_0_1", "1_0_0", "1_0_7",
        external_temp_entity_id="sensor.sonoff_ths_2_temperature",
    )


def test_override_onna_probe_still_subscribed():
    zone = _make_zone_with_override({"1_0_4": 19.0})
    subs = zone._subscriptions()
    assert any(addr == "1_0_4" for addr, _ in subs)


def test_override_uses_external_when_available():
    zone = _make_zone_with_override({"1_0_4": 19.0})
    zone._ext_temp = 22.5
    zone._ext_available = True
    assert zone.current_temperature == 22.5


def test_override_falls_back_to_onna_when_external_unavailable():
    zone = _make_zone_with_override({"1_0_4": 19.0})
    zone._onna_temp = 19.0
    zone._ext_available = False
    assert zone.current_temperature == 19.0


def test_handle_external_temp_updates_and_marks_available():
    zone = _make_zone_with_override()
    zone.hass = MagicMock()
    zone.async_write_ha_state = MagicMock()
    event = MagicMock()
    event.data = {"new_state": MagicMock(state="22.3")}
    zone._handle_external_temp(event)
    assert zone._ext_temp == 22.3
    assert zone._ext_available is True
    assert zone.current_temperature == 22.3
    zone.async_write_ha_state.assert_called_once()


def test_handle_external_temp_unavailable_falls_back_to_onna():
    zone = _make_zone_with_override({"1_0_4": 19.0})
    zone._onna_temp = 19.0
    zone._ext_temp = 22.3
    zone._ext_available = True
    zone.async_write_ha_state = MagicMock()
    event = MagicMock()
    event.data = {"new_state": MagicMock(state="unavailable")}
    zone._handle_external_temp(event)
    assert zone._ext_available is False
    assert zone.current_temperature == 19.0
    zone.async_write_ha_state.assert_called_once()


def test_handle_onna_probe_updates_fallback_value():
    zone = _make_zone_with_override()
    zone._ext_available = True
    zone._ext_temp = 22.0
    zone._last_written_setpoint = None  # no prior write → no task scheduled
    zone.async_write_ha_state = MagicMock()
    zone._handle_temp(20.5)
    assert zone._onna_temp == 20.5
    # External still takes priority
    assert zone.current_temperature == 22.0


# Setpoint compensation
# ---------------------------------------------------------------------------

def test_compute_onna_setpoint_compensates_offset():
    """ext=27.4, onna=25.4, target=25.5 → compensated = 25.5 - 2.0 = 23.5"""
    zone = _make_zone_with_override({"1_0_4": 25.4, "1_0_3": 25.5})
    zone._onna_temp = 25.4
    zone._ext_temp = 27.4
    zone._ext_available = True
    zone._target_temp = 25.5
    assert zone._compute_onna_setpoint() == 23.5


def test_compute_onna_setpoint_no_external_returns_target():
    zone = _make_zone({"1_0_4": 20.0})
    zone._target_temp = 21.0
    assert zone._compute_onna_setpoint() == 21.0


def test_compute_onna_setpoint_ext_unavailable_returns_target():
    zone = _make_zone_with_override({"1_0_4": 20.0})
    zone._onna_temp = 20.0
    zone._ext_temp = 23.0
    zone._ext_available = False
    zone._target_temp = 22.0
    assert zone._compute_onna_setpoint() == 22.0


def test_compute_onna_setpoint_clamped_to_min():
    zone = _make_zone_with_override({"1_0_4": 10.0})
    zone._onna_temp = 10.0
    zone._ext_temp = 40.0   # huge offset → compensated would be negative
    zone._ext_available = True
    zone._target_temp = 20.0
    assert zone._compute_onna_setpoint() == 7.0  # _attr_min_temp


@pytest.mark.anyio
async def test_set_temperature_writes_compensated_setpoint():
    """When external sensor is active, set_temperature sends compensated value to Onna."""
    zone = _make_zone_with_override({"1_0_4": 25.4})
    zone._onna_temp = 25.4
    zone._ext_temp = 27.4
    zone._ext_available = True
    zone._target_temp = 25.0
    await zone.async_set_temperature(temperature=25.5)
    assert zone._target_temp == 25.5
    zone._coordinator.client.async_set_address_value.assert_called_once_with("1_0_2", 23.5)


@pytest.mark.anyio
async def test_set_temperature_without_override_writes_direct():
    zone = _make_zone({"1_0_4": 20.0})
    await zone.async_set_temperature(temperature=22.0)
    zone._coordinator.client.async_set_address_value.assert_called_once_with("1_0_2", 22.0)


@pytest.mark.anyio
async def test_push_compensated_setpoint_respects_threshold():
    """Second push with delta < 0.5 should not write again."""
    zone = _make_zone_with_override({"1_0_4": 25.4})
    zone._onna_temp = 25.4
    zone._ext_temp = 27.4
    zone._ext_available = True
    zone._target_temp = 25.5
    # First push: writes 23.5
    await zone._push_compensated_setpoint()
    assert zone._last_written_setpoint == 23.5
    zone._coordinator.client.async_set_address_value.assert_called_once_with("1_0_2", 23.5)
    # Second push with negligible offset change (< 0.5°C): no new write
    zone._ext_temp = 27.6  # delta in compensated = 0.2 < 0.5
    await zone._push_compensated_setpoint()
    zone._coordinator.client.async_set_address_value.assert_called_once()  # still once


@pytest.mark.anyio
async def test_push_compensated_setpoint_writes_when_threshold_exceeded():
    zone = _make_zone_with_override({"1_0_4": 25.4})
    zone._onna_temp = 25.4
    zone._ext_temp = 27.4
    zone._ext_available = True
    zone._target_temp = 25.5
    await zone._push_compensated_setpoint()  # writes 23.5
    zone._ext_temp = 28.0  # delta in compensated = 0.6 ≥ 0.5
    await zone._push_compensated_setpoint()  # writes 23.0 (= 25.5 - 2.5)
    assert zone._coordinator.client.async_set_address_value.call_count == 2


def test_handle_setpoint_ignored_when_compensation_active():
    """External available → echo is compensated value, must not overwrite user intent."""
    zone = _make_zone_with_override()
    zone._ext_available = True
    zone._ext_temp = 27.4
    zone._target_temp = 25.5
    zone.async_write_ha_state = MagicMock()
    zone._handle_setpoint(23.5)
    assert zone._target_temp == 25.5


def test_handle_setpoint_ignored_on_restart_stale_echo():
    """External offline but echo matches last compensation write (restart scenario)."""
    zone = _make_zone_with_override()
    zone._target_temp = 25.5        # restored from last HA state
    zone._last_written_setpoint = 23.5  # restored from extra_state_attributes
    zone._ext_available = False
    zone.async_write_ha_state = MagicMock()
    zone._handle_setpoint(23.5)     # Onna echoes our old compensated write
    assert zone._target_temp == 25.5  # user intent preserved


def test_handle_setpoint_accepted_when_external_offline_genuine_change():
    """External offline + echo differs from last write → genuine change from Onna app."""
    zone = _make_zone_with_override()
    zone._target_temp = 25.5
    zone._last_written_setpoint = 23.5
    zone._ext_available = False
    zone.async_write_ha_state = MagicMock()
    zone._handle_setpoint(24.0)     # user changed from Onna's native app
    assert zone._target_temp == 24.0


def test_handle_setpoint_accepted_when_no_prior_write():
    """External offline and no compensated write yet (first startup) → sync from Onna."""
    zone = _make_zone_with_override()
    zone._target_temp = 20.0
    zone._last_written_setpoint = None  # no prior compensation write
    zone._ext_available = False
    zone.async_write_ha_state = MagicMock()
    zone._handle_setpoint(22.0)
    assert zone._target_temp == 22.0


def test_handle_setpoint_updates_when_no_override():
    zone = _make_zone()
    zone.async_write_ha_state = MagicMock()
    zone._handle_setpoint(22.0)
    assert zone._target_temp == 22.0


def test_extra_state_attributes_exposes_compensated_setpoint():
    zone = _make_zone_with_override()
    zone._last_written_setpoint = 23.5
    attrs = zone.extra_state_attributes
    assert attrs == {"_onna_compensated_setpoint": 23.5}


def test_extra_state_attributes_none_before_any_write():
    zone = _make_zone_with_override()
    zone._last_written_setpoint = None
    assert zone.extra_state_attributes is None


@pytest.mark.anyio
async def test_restore_compensated_setpoint_on_added():
    zone = _make_zone_with_override()
    zone.hass = MagicMock()
    zone.async_on_remove = MagicMock()
    last_state = MagicMock()
    last_state.attributes = {"temperature": 25.5, "_onna_compensated_setpoint": 23.5}
    zone.async_get_last_state = AsyncMock(return_value=last_state)
    with patch("custom_components.onna.climate.async_track_state_change_event",
               return_value=lambda: None):
        with patch("custom_components.onna.climate.async_dispatcher_connect",
                   return_value=lambda: None):
            await zone.async_added_to_hass()
    assert zone._target_temp == 25.5
    assert zone._last_written_setpoint == 23.5


@pytest.mark.anyio
async def test_set_temperature_persists_user_intent_via_write_ha_state():
    """async_write_ha_state must be called so RestoreEntity survives HA restarts."""
    zone = _make_zone_with_override({"1_0_4": 25.4})
    zone._onna_temp = 25.4
    zone._ext_temp = 27.4
    zone._ext_available = True
    zone.async_write_ha_state = MagicMock()
    await zone.async_set_temperature(temperature=25.5)
    zone.async_write_ha_state.assert_called()


def test_handle_temp_triggers_compensation_when_prior_write_exists():
    """After a compensated write, Onna-probe changes should schedule re-push."""
    zone = _make_zone_with_override({"1_0_4": 25.4})
    zone._onna_temp = 25.4
    zone._ext_temp = 27.4
    zone._ext_available = True
    zone._target_temp = 25.5
    zone._last_written_setpoint = 23.5  # simulate prior write
    zone.hass = MagicMock()
    zone.async_write_ha_state = MagicMock()
    zone._handle_temp(25.0)
    zone.hass.async_create_task.assert_called_once()


def test_handle_temp_no_task_without_prior_write():
    """First probe update before any user set_temperature must not trigger write."""
    zone = _make_zone_with_override({"1_0_4": 25.4})
    zone._ext_available = True
    zone._last_written_setpoint = None
    zone.hass = MagicMock()
    zone.async_write_ha_state = MagicMock()
    zone._handle_temp(25.0)
    zone.hass.async_create_task.assert_not_called()


def test_handle_external_temp_triggers_task_when_available():
    zone = _make_zone_with_override({"1_0_4": 25.4})
    zone._onna_temp = 25.4
    zone._target_temp = 25.5
    zone.hass = MagicMock()
    zone.async_write_ha_state = MagicMock()
    event = MagicMock()
    event.data = {"new_state": MagicMock(state="27.4")}
    zone._handle_external_temp(event)
    zone.hass.async_create_task.assert_called_once()


@pytest.mark.anyio
async def test_async_added_subscribes_to_external_sensor():
    zone = _make_zone_with_override()
    zone.hass = MagicMock()
    zone.hass.states.get.return_value = MagicMock(state="21.5")
    zone.async_on_remove = MagicMock()
    with patch("custom_components.onna.climate.async_track_state_change_event",
               return_value=lambda: None) as mock_track:
        with patch("custom_components.onna.climate.async_dispatcher_connect",
                   return_value=lambda: None):
            await zone.async_added_to_hass()
    mock_track.assert_called_once_with(
        zone.hass, "sensor.sonoff_ths_2_temperature", zone._handle_external_temp
    )
    assert zone.current_temperature == 21.5


@pytest.mark.anyio
async def test_async_added_without_override_does_not_track_external():
    zone = _make_zone()
    zone.hass = MagicMock()
    zone.async_on_remove = MagicMock()
    with patch("custom_components.onna.climate.async_track_state_change_event") as mock_track:
        with patch("custom_components.onna.climate.async_dispatcher_connect",
                   return_value=lambda: None):
            await zone.async_added_to_hass()
    mock_track.assert_not_called()


@pytest.mark.anyio
async def test_restore_target_temperature_on_added():
    zone = _make_zone()
    zone.hass = MagicMock()
    zone.async_on_remove = MagicMock()
    last_state = MagicMock()
    last_state.attributes = {"temperature": 23.5}
    zone.async_get_last_state = AsyncMock(return_value=last_state)
    with patch("custom_components.onna.climate.async_dispatcher_connect",
               return_value=lambda: None):
        await zone.async_added_to_hass()
    assert zone.target_temperature == 23.5


@pytest.mark.anyio
async def test_restore_skipped_when_no_last_state():
    zone = _make_zone()
    zone.hass = MagicMock()
    zone.async_on_remove = MagicMock()
    zone.async_get_last_state = AsyncMock(return_value=None)
    with patch("custom_components.onna.climate.async_dispatcher_connect",
               return_value=lambda: None):
        await zone.async_added_to_hass()
    assert zone.target_temperature == 20.0  # default unchanged


# ---------------------------------------------------------------------------
# OnnaGeneralClimate
# ---------------------------------------------------------------------------

def test_general_seeds_target_from_zone0_setpoint():
    coord = _make_coordinator({"1_0_3": 21.0})
    general = OnnaGeneralClimate(coord)
    assert general.target_temperature == 21.0


def test_general_current_temperature_is_none():
    coord = _make_coordinator()
    general = OnnaGeneralClimate(coord)
    assert general.current_temperature is None


@pytest.mark.anyio
async def test_general_set_temperature_writes_and_updates_local():
    coord = _make_coordinator()
    general = OnnaGeneralClimate(coord)
    general.async_write_ha_state = MagicMock()
    await general.async_set_temperature(temperature=22.0)
    coord.client.async_set_address_value.assert_called_once_with("0_0_2", 22.0)
    assert general.target_temperature == 22.0


@pytest.mark.anyio
async def test_general_set_hvac_mode_off_writes_zero():
    from custom_components.onna.climate import HVACMode
    coord = _make_coordinator()
    general = OnnaGeneralClimate(coord)
    general.async_write_ha_state = MagicMock()
    await general.async_set_hvac_mode(HVACMode.OFF)
    coord.client.async_set_address_value.assert_called_once_with("0_0_1", 0)
    assert general.hvac_mode == HVACMode.OFF


@pytest.mark.anyio
async def test_general_set_hvac_mode_heat_writes_winter_then_on():
    from custom_components.onna.climate import HVACMode
    from unittest.mock import call
    coord = _make_coordinator()
    general = OnnaGeneralClimate(coord)
    general.async_write_ha_state = MagicMock()
    await general.async_set_hvac_mode(HVACMode.HEAT)
    coord.client.async_set_address_value.assert_has_calls([
        call("0_0_3", 1),
        call("0_0_1", 1),
    ])


@pytest.mark.anyio
async def test_general_set_hvac_mode_cool_writes_summer_then_on():
    from custom_components.onna.climate import HVACMode
    from unittest.mock import call
    coord = _make_coordinator()
    general = OnnaGeneralClimate(coord)
    general.async_write_ha_state = MagicMock()
    await general.async_set_hvac_mode(HVACMode.COOL)
    coord.client.async_set_address_value.assert_has_calls([
        call("0_0_3", 0),
        call("0_0_1", 1),
    ])


@pytest.mark.anyio
async def test_general_restores_hvac_mode_and_temperature():
    from custom_components.onna.climate import HVACMode
    coord = _make_coordinator()
    general = OnnaGeneralClimate(coord)
    general.hass = MagicMock()
    general.async_on_remove = MagicMock()
    last_state = MagicMock()
    last_state.state = "cool"
    last_state.attributes = {"temperature": 19.0}
    general.async_get_last_state = AsyncMock(return_value=last_state)
    with patch("custom_components.onna.climate.async_dispatcher_connect",
               return_value=lambda: None):
        await general.async_added_to_hass()
    assert general.hvac_mode == HVACMode.COOL
    assert general.target_temperature == 19.0


def test_general_handle_winter_updates_action():
    from custom_components.onna.climate import HVACAction, HVACMode
    coord = _make_coordinator({"0_0_7": True})
    general = OnnaGeneralClimate(coord)
    general.async_write_ha_state = MagicMock()
    general._handle_winter(False)
    assert general.hvac_action == HVACAction.COOLING
