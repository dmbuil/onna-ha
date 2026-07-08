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
    zone = _make_zone({"1_0_1": True})  # zone on → pure setpoint write
    await zone.async_set_temperature(temperature=23.5)
    zone._coordinator.client.async_set_address_value.assert_called_once_with("1_0_2", 23.5)


@pytest.mark.anyio
async def test_set_hvac_mode_off_writes_zero_to_onoff():
    from custom_components.onna.climate import HVACMode
    zone = _make_zone()
    await zone.async_set_hvac_mode(HVACMode.OFF)
    zone._coordinator.client.async_set_address_value.assert_called_once_with("1_0_0", 0)


@pytest.mark.anyio
async def test_set_hvac_mode_heat_turns_zone_on():
    from custom_components.onna.climate import HVACMode
    zone = _make_zone()
    await zone.async_set_hvac_mode(HVACMode.HEAT)
    zone._coordinator.client.async_set_address_value.assert_called_once_with("1_0_0", 1)


@pytest.mark.anyio
async def test_set_hvac_mode_cool_turns_zone_on():
    from custom_components.onna.climate import HVACMode
    zone = _make_zone()
    await zone.async_set_hvac_mode(HVACMode.COOL)
    zone._coordinator.client.async_set_address_value.assert_called_once_with("1_0_0", 1)


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
    zone = _make_zone_with_override({"1_0_4": 25.4, "1_0_1": True})
    zone._onna_temp = 25.4
    zone._ext_temp = 27.4
    zone._ext_available = True
    zone._target_temp = 25.0
    await zone.async_set_temperature(temperature=25.5)
    assert zone._target_temp == 25.5
    zone._coordinator.client.async_set_address_value.assert_called_once_with("1_0_2", 23.5)


@pytest.mark.anyio
async def test_set_temperature_without_override_writes_direct():
    zone = _make_zone({"1_0_4": 20.0, "1_0_1": True})
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


def test_handle_setpoint_ignored_when_echo_matches_last_write_online():
    """Echo of our own compensated write while external is online → ignored."""
    zone = _make_zone_with_override()
    zone._ext_available = True
    zone._ext_temp = 27.4
    zone._target_temp = 25.5
    zone._last_written_setpoint = 23.5   # we wrote this compensated value
    zone.async_write_ha_state = MagicMock()
    zone._handle_setpoint(23.5)          # Onna echoes it back
    assert zone._target_temp == 25.5     # user intent preserved


def test_handle_setpoint_accepts_general_change_when_compensation_active():
    """General thermostat changes setpoint while external is online → accepted."""
    zone = _make_zone_with_override()
    zone._ext_available = True
    zone._ext_temp = 27.4
    zone._target_temp = 25.5
    zone._last_written_setpoint = 23.5   # previous compensation
    zone.async_write_ha_state = MagicMock()
    zone._handle_setpoint(26.0)          # General changed to 26
    assert zone._target_temp == 26.0
    assert zone._last_written_setpoint is None  # cleared so compensation recalculates


def test_handle_setpoint_accepts_first_sync_when_no_prior_write_online():
    """No prior compensated write (startup) while external online → sync accepted."""
    zone = _make_zone_with_override()
    zone._ext_available = True
    zone._last_written_setpoint = None
    zone._target_temp = 20.0
    zone.async_write_ha_state = MagicMock()
    zone._handle_setpoint(25.0)
    assert zone._target_temp == 25.0


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
    from custom_components.onna.climate import HVACMode
    coord = _make_coordinator()
    general = OnnaGeneralClimate(coord)
    general.async_write_ha_state = MagicMock()
    general._hvac_mode = HVACMode.HEAT  # already on → pure setpoint broadcast
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
    general._hvac_mode = HVACMode.COOL  # action only reported while not OFF
    general._handle_winter(False)
    assert general.hvac_action == HVACAction.COOLING


# ---------------------------------------------------------------------------
# Window open / close — thermostat pause
# ---------------------------------------------------------------------------

def _make_zone_with_window(data=None):
    coord = _make_coordinator(data)
    return OnnaClimate(
        coord, "Dorm. 2",
        "1_2_4", "1_2_3", "1_2_2",
        "1_2_1", "1_2_0", "1_2_7",
        window_sensor_entity_id="binary_sensor.window_dorm_2",
    )


def test_window_initial_state_false():
    zone = _make_zone_with_window()
    assert zone._window_open is False
    assert zone._window_pause_active is False


def test_extra_attrs_expose_window_state():
    zone = _make_zone_with_window()
    attrs = zone.extra_state_attributes
    assert attrs["window_open"] is False
    assert attrs["window_pause_active"] is False


def test_window_change_open_starts_timer():
    zone = _make_zone_with_window()
    zone.hass = MagicMock()
    zone.async_write_ha_state = MagicMock()

    with patch("custom_components.onna.climate.async_call_later") as mock_timer:
        event = MagicMock()
        event.data = {"new_state": MagicMock(state="on")}
        zone._handle_window_change(event)

    assert zone._window_open is True
    mock_timer.assert_called_once_with(zone.hass, 600, zone._handle_window_delay_elapsed)


def test_window_change_close_cancels_timer():
    zone = _make_zone_with_window()
    zone.hass = MagicMock()
    zone.async_write_ha_state = MagicMock()
    cancel_mock = MagicMock()
    zone._window_open = True
    zone._window_cancel_timer = cancel_mock

    event = MagicMock()
    event.data = {"new_state": MagicMock(state="off")}
    zone._handle_window_change(event)

    cancel_mock.assert_called_once()
    assert zone._window_cancel_timer is None


def test_window_delay_elapsed_pauses_when_on():
    zone = _make_zone_with_window({"1_2_1": True})
    zone._is_on = True
    zone._window_open = True
    zone.hass = MagicMock()
    zone.async_write_ha_state = MagicMock()

    zone._handle_window_delay_elapsed(None)

    assert zone._window_pause_active is True
    zone.hass.async_create_task.assert_called_once()


def test_window_delay_elapsed_noop_when_already_off():
    zone = _make_zone_with_window()
    zone._is_on = False
    zone._window_open = True
    zone.hass = MagicMock()
    zone.async_write_ha_state = MagicMock()

    zone._handle_window_delay_elapsed(None)

    assert zone._window_pause_active is False
    zone.hass.async_create_task.assert_not_called()


def test_window_close_resumes_when_pause_active():
    zone = _make_zone_with_window()
    zone._window_open = True
    zone._window_pause_active = True
    zone.hass = MagicMock()
    zone.async_write_ha_state = MagicMock()

    event = MagicMock()
    event.data = {"new_state": MagicMock(state="off")}
    zone._handle_window_change(event)

    assert zone._window_pause_active is False
    zone.hass.async_create_task.assert_called_once()  # turn ON


def test_window_close_no_resume_when_pause_not_active():
    zone = _make_zone_with_window()
    zone._window_open = True
    zone._window_pause_active = False
    zone.hass = MagicMock()
    zone.async_write_ha_state = MagicMock()

    event = MagicMock()
    event.data = {"new_state": MagicMock(state="off")}
    zone._handle_window_change(event)

    zone.hass.async_create_task.assert_not_called()


def test_window_spurious_open_close_cancels_before_delay():
    """Window opens then closes within 1 min — no pause should occur."""
    zone = _make_zone_with_window()
    zone._is_on = True
    zone.hass = MagicMock()
    zone.async_write_ha_state = MagicMock()
    cancel_mock = MagicMock()

    with patch("custom_components.onna.climate.async_call_later", return_value=cancel_mock):
        open_event = MagicMock()
        open_event.data = {"new_state": MagicMock(state="on")}
        zone._handle_window_change(open_event)

    close_event = MagicMock()
    close_event.data = {"new_state": MagicMock(state="off")}
    zone._handle_window_change(close_event)

    cancel_mock.assert_called_once()        # timer was cancelled
    assert zone._window_pause_active is False  # no pause triggered


@pytest.mark.anyio
async def test_turn_on_clears_window_pause():
    zone = _make_zone_with_window()
    zone._window_pause_active = True
    await zone.async_turn_on()
    assert zone._window_pause_active is False


@pytest.mark.anyio
async def test_turn_off_clears_window_pause():
    zone = _make_zone_with_window()
    zone._window_pause_active = True
    await zone.async_turn_off()
    assert zone._window_pause_active is False


@pytest.mark.anyio
async def test_async_added_subscribes_to_window_sensor():
    zone = _make_zone_with_window()
    zone.hass = MagicMock()
    zone.hass.states.get.return_value = MagicMock(state="off")
    zone.async_on_remove = MagicMock()
    with patch("custom_components.onna.climate.async_track_state_change_event",
               return_value=lambda: None) as mock_track:
        with patch("custom_components.onna.climate.async_dispatcher_connect",
                   return_value=lambda: None):
            await zone.async_added_to_hass()
    calls = [c.args[1] for c in mock_track.call_args_list]
    assert "binary_sensor.window_dorm_2" in calls


@pytest.mark.anyio
async def test_async_added_seeds_window_open_state():
    zone = _make_zone_with_window()
    zone.hass = MagicMock()
    # Window is currently open
    zone.hass.states.get.side_effect = lambda eid: (
        MagicMock(state="on") if eid == "binary_sensor.window_dorm_2" else None
    )
    zone.async_on_remove = MagicMock()
    with patch("custom_components.onna.climate.async_track_state_change_event",
               return_value=lambda: None):
        with patch("custom_components.onna.climate.async_dispatcher_connect",
                   return_value=lambda: None):
            await zone.async_added_to_hass()
    assert zone._window_open is True


# ---------------------------------------------------------------------------
# OnnaGeneralClimate — initial mode must be a valid, selectable mode
# ---------------------------------------------------------------------------

def test_general_initial_hvac_mode_is_in_supported_modes():
    general = OnnaGeneralClimate(_make_coordinator())
    assert general.hvac_mode in general._attr_hvac_modes


# ---------------------------------------------------------------------------
# Window pause survives HA restarts
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_window_pause_restored_when_window_still_open():
    """Restart while paused + window still open → stay paused, resume on close."""
    zone = _make_zone_with_window()
    zone.hass = MagicMock()
    zone.hass.states.get.return_value = MagicMock(state="on")  # window open
    zone.async_on_remove = MagicMock()
    last_state = MagicMock()
    last_state.attributes = {"window_pause_active": True, "window_open": True}
    zone.async_get_last_state = AsyncMock(return_value=last_state)
    with patch("custom_components.onna.climate.async_track_state_change_event",
               return_value=lambda: None), \
         patch("custom_components.onna.climate.async_dispatcher_connect",
               return_value=lambda: None):
        await zone.async_added_to_hass()
    assert zone._window_pause_active is True
    zone._coordinator.client.async_set_address_value.assert_not_called()


@pytest.mark.anyio
async def test_window_pause_resumes_zone_when_window_closed_during_downtime():
    """Restart while paused + window now closed → resume the zone immediately."""
    zone = _make_zone_with_window()
    zone.hass = MagicMock()
    zone.hass.states.get.return_value = MagicMock(state="off")  # window closed
    zone.async_on_remove = MagicMock()
    last_state = MagicMock()
    last_state.attributes = {"window_pause_active": True, "window_open": True}
    zone.async_get_last_state = AsyncMock(return_value=last_state)
    with patch("custom_components.onna.climate.async_track_state_change_event",
               return_value=lambda: None), \
         patch("custom_components.onna.climate.async_dispatcher_connect",
               return_value=lambda: None):
        await zone.async_added_to_hass()
    assert zone._window_pause_active is False
    zone._coordinator.client.async_set_address_value.assert_called_once_with("1_2_0", 1)


# ---------------------------------------------------------------------------
# Configurable hysteresis and window delay
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_custom_hysteresis_allows_smaller_repush():
    """With hysteresis 0.2, a 0.3 °C compensated shift must trigger a write
    (the default 0.5 hysteresis would have suppressed it)."""
    coord = _make_coordinator({"1_0_4": 25.4})
    zone = OnnaClimate(
        coord, "Salón+Cocina",
        "1_0_4", "1_0_3", "1_0_2",
        "1_0_1", "1_0_0", "1_0_7",
        external_temp_entity_id="sensor.ext",
        setpoint_hysteresis=0.2,
    )
    zone._onna_temp = 25.4
    zone._ext_temp = 27.4
    zone._ext_available = True
    zone._target_temp = 25.5
    await zone._push_compensated_setpoint()           # writes 23.5
    zone._ext_temp = 27.7                             # compensated delta = 0.3
    await zone._push_compensated_setpoint()
    assert zone._coordinator.client.async_set_address_value.call_count == 2


@pytest.mark.anyio
async def test_zero_hysteresis_writes_any_change_but_not_identical():
    """With hysteresis 0.0 every compensated change is pushed, however small,
    but an unchanged setpoint must not be rewritten on each sensor update."""
    coord = _make_coordinator({"1_0_4": 25.4})
    zone = OnnaClimate(
        coord, "Salón+Cocina",
        "1_0_4", "1_0_3", "1_0_2",
        "1_0_1", "1_0_0", "1_0_7",
        external_temp_entity_id="sensor.ext",
        setpoint_hysteresis=0.0,
    )
    zone._onna_temp = 25.4
    zone._ext_temp = 27.4
    zone._ext_available = True
    zone._target_temp = 25.5
    await zone._push_compensated_setpoint()           # writes 23.5
    await zone._push_compensated_setpoint()           # no change: must not rewrite
    assert zone._coordinator.client.async_set_address_value.call_count == 1
    zone._ext_temp = 27.5                             # compensated delta = 0.1
    await zone._push_compensated_setpoint()
    assert zone._coordinator.client.async_set_address_value.call_count == 2


def test_custom_window_delay_used_for_pause_timer():
    coord = _make_coordinator()
    zone = OnnaClimate(
        coord, "Dorm. 2",
        "1_2_4", "1_2_3", "1_2_2",
        "1_2_1", "1_2_0", "1_2_7",
        window_sensor_entity_id="binary_sensor.window_dorm_2",
        window_open_delay=120,
    )
    zone.hass = MagicMock()
    zone.async_write_ha_state = MagicMock()
    event = MagicMock()
    event.data = {"new_state": MagicMock(state="on")}
    with patch("custom_components.onna.climate.async_call_later") as mock_timer:
        zone._handle_window_change(event)
    mock_timer.assert_called_once_with(zone.hass, 120, zone._handle_window_delay_elapsed)


@pytest.mark.anyio
async def test_setup_entry_passes_tuning_options_to_zones():
    from custom_components.onna.climate import async_setup_entry
    from custom_components.onna.const import DOMAIN

    coord = _make_coordinator()
    coord.device_config = {
        "climate_addresses": {
            "zone_0": ["Salón+Cocina", "1_0_4", "1_0_3", "1_0_2", "1_0_1", "1_0_0", "1_0_7"],
        }
    }
    hass = MagicMock()
    hass.data = {DOMAIN: {"eid": coord}}
    entry = MagicMock()
    entry.entry_id = "eid"
    entry.options = {"setpoint_hysteresis": 0.3, "window_open_delay": 300}
    added = []
    await async_setup_entry(hass, entry, lambda ents: added.extend(ents))

    zone = added[0]
    assert zone._setpoint_hysteresis == 0.3
    assert zone._window_open_delay == 300


@pytest.mark.anyio
async def test_setup_entry_defaults_tuning_options():
    from custom_components.onna.climate import async_setup_entry
    from custom_components.onna.const import DOMAIN

    coord = _make_coordinator()
    coord.device_config = {
        "climate_addresses": {
            "zone_0": ["Salón+Cocina", "1_0_4", "1_0_3", "1_0_2", "1_0_1", "1_0_0", "1_0_7"],
        }
    }
    hass = MagicMock()
    hass.data = {DOMAIN: {"eid": coord}}
    entry = MagicMock()
    entry.entry_id = "eid"
    entry.options = {}
    added = []
    await async_setup_entry(hass, entry, lambda ents: added.extend(ents))

    zone = added[0]
    assert zone._setpoint_hysteresis == 0.5
    assert zone._window_open_delay == 600


# ---------------------------------------------------------------------------
# Setpoint 7.0 °C ⇄ OFF equivalence
# (spec: docs/superpowers/specs/2026-07-07-setpoint-min-off-design.md)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_set_temperature_min_turns_zone_off():
    """Setting min_temp (7.0) while on → off write, no setpoint write, target kept."""
    zone = _make_zone({"1_0_1": True})
    zone._target_temp = 22.0
    await zone.async_set_temperature(temperature=7.0)
    zone._coordinator.client.async_set_address_value.assert_called_once_with("1_0_0", 0)
    assert zone._target_temp == 22.0


@pytest.mark.anyio
async def test_set_temperature_min_while_off_writes_off_again():
    """Setting 7.0 while already off → idempotent off write, target kept."""
    zone = _make_zone({"1_0_1": False})
    zone._target_temp = 21.0
    await zone.async_set_temperature(temperature=7.0)
    zone._coordinator.client.async_set_address_value.assert_called_once_with("1_0_0", 0)
    assert zone._target_temp == 21.0


@pytest.mark.anyio
async def test_set_temperature_min_clears_window_pause():
    """7.0 goes through async_turn_off → user override clears the pause flag."""
    zone = _make_zone_with_window({"1_2_1": True})
    zone._window_pause_active = True
    await zone.async_set_temperature(temperature=7.0)
    assert zone._window_pause_active is False


@pytest.mark.anyio
async def test_set_temperature_above_min_while_off_turns_zone_on():
    """Setting >7.0 while off → setpoint write followed by on write."""
    from unittest.mock import call
    zone = _make_zone({"1_0_1": False})
    zone.async_write_ha_state = MagicMock()
    await zone.async_set_temperature(temperature=22.0)
    zone._coordinator.client.async_set_address_value.assert_has_calls([
        call("1_0_2", 22.0),
        call("1_0_0", 1),
    ])
    assert zone._target_temp == 22.0


@pytest.mark.anyio
async def test_set_temperature_above_min_while_off_clears_window_pause():
    """>7.0 while off goes through async_turn_on → pause flag cleared (user wins)."""
    zone = _make_zone_with_window({"1_2_1": False})
    zone._window_pause_active = True
    zone.async_write_ha_state = MagicMock()
    await zone.async_set_temperature(temperature=22.0)
    assert zone._window_pause_active is False


@pytest.mark.anyio
async def test_set_temperature_above_min_while_on_no_onoff_write():
    """Regression: setting >7.0 while on stays a pure setpoint write."""
    zone = _make_zone({"1_0_1": True})
    zone.async_write_ha_state = MagicMock()
    await zone.async_set_temperature(temperature=22.0)
    zone._coordinator.client.async_set_address_value.assert_called_once_with("1_0_2", 22.0)


@pytest.mark.anyio
async def test_general_set_temperature_min_broadcasts_off():
    """7.0 on the general thermostat → installation OFF broadcast, target kept."""
    from custom_components.onna.climate import HVACMode
    coord = _make_coordinator()
    general = OnnaGeneralClimate(coord)
    general.async_write_ha_state = MagicMock()
    general._hvac_mode = HVACMode.HEAT
    general._target_temp = 21.0
    await general.async_set_temperature(temperature=7.0)
    coord.client.async_set_address_value.assert_called_once_with("0_0_1", 0)
    assert general.target_temperature == 21.0
    assert general.hvac_mode == HVACMode.OFF


@pytest.mark.anyio
async def test_general_set_temperature_above_min_while_off_turns_on_winter():
    """>7.0 while off → setpoint broadcast then ON; mode follows winter flag."""
    from custom_components.onna.climate import HVACMode
    from unittest.mock import call
    coord = _make_coordinator({"0_0_7": True})
    general = OnnaGeneralClimate(coord)
    general.async_write_ha_state = MagicMock()
    general._hvac_mode = HVACMode.OFF
    await general.async_set_temperature(temperature=22.0)
    coord.client.async_set_address_value.assert_has_calls([
        call("0_0_2", 22.0),
        call("0_0_1", 1),
    ])
    assert general.hvac_mode == HVACMode.HEAT
    assert general.target_temperature == 22.0


@pytest.mark.anyio
async def test_general_set_temperature_above_min_while_off_turns_on_summer():
    from custom_components.onna.climate import HVACMode
    coord = _make_coordinator({"0_0_7": False})
    general = OnnaGeneralClimate(coord)
    general.async_write_ha_state = MagicMock()
    general._hvac_mode = HVACMode.OFF
    await general.async_set_temperature(temperature=22.0)
    assert general.hvac_mode == HVACMode.COOL


# ---------------------------------------------------------------------------
# hvac state survives reloads (demand telegrams only fire on *changes*)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_restore_is_on_and_demand_when_no_live_data():
    """After a reload, Onna won't re-send 1_X_7/1_X_1 until they change —
    restore them from the recorder so hvac_action isn't stuck on IDLE."""
    from custom_components.onna.climate import HVACAction
    zone = _make_zone()  # coordinator.data empty
    zone.hass = MagicMock()
    zone.async_on_remove = MagicMock()
    last_state = MagicMock()
    last_state.state = "heat"
    last_state.attributes = {"temperature": 21.0, "hvac_action": "heating"}
    zone.async_get_last_state = AsyncMock(return_value=last_state)
    with patch("custom_components.onna.climate.async_dispatcher_connect",
               return_value=lambda: None):
        await zone.async_added_to_hass()
    assert zone._is_on is True
    assert zone._demand is True
    assert zone.hvac_action == HVACAction.HEATING


@pytest.mark.anyio
async def test_restore_off_state_when_no_live_data():
    zone = _make_zone()
    zone.hass = MagicMock()
    zone.async_on_remove = MagicMock()
    last_state = MagicMock()
    last_state.state = "off"
    last_state.attributes = {"hvac_action": "off"}
    zone.async_get_last_state = AsyncMock(return_value=last_state)
    with patch("custom_components.onna.climate.async_dispatcher_connect",
               return_value=lambda: None):
        await zone.async_added_to_hass()
    assert zone._is_on is False
    assert zone._demand is False


@pytest.mark.anyio
async def test_restore_does_not_override_live_coordinator_values():
    """If live values already arrived, the (older) recorder state must lose."""
    zone = _make_zone({"1_0_1": 0, "1_0_7": 0})  # live: zone off, no demand
    zone.hass = MagicMock()
    zone.async_on_remove = MagicMock()
    last_state = MagicMock()
    last_state.state = "heat"
    last_state.attributes = {"hvac_action": "heating"}
    zone.async_get_last_state = AsyncMock(return_value=last_state)
    with patch("custom_components.onna.climate.async_dispatcher_connect",
               return_value=lambda: None):
        await zone.async_added_to_hass()
    assert zone._is_on is False
    assert zone._demand is False
