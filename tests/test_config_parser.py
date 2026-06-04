"""Tests for config_parser — uses the real out.onna.txt device export as fixture."""
import json
import pytest
from pathlib import Path

FIXTURE = Path(__file__).parent.parent / "out.onna.txt"

@pytest.fixture
def payload():
    return json.loads(FIXTURE.read_text())


# --- Climate zones ---

def test_five_climate_zones_discovered(payload):
    from custom_components.onna.config_parser import parse_device_config
    config = parse_device_config(payload)
    assert set(config["climate_addresses"].keys()) == {
        "zone_0", "zone_1", "zone_2", "zone_3", "zone_4"
    }

def test_climate_zone_0_addresses(payload):
    from custom_components.onna.config_parser import parse_device_config
    config = parse_device_config(payload)
    name, temp_r, setpt_r, setpt_w, onoff_r, onoff_w, demand = config["climate_addresses"]["zone_0"]
    assert name == "Salón+Cocina"
    assert temp_r  == "1_0_4"
    assert setpt_r == "1_0_3"
    assert setpt_w == "1_0_2"
    assert onoff_r == "1_0_1"
    assert onoff_w == "1_0_0"
    assert demand  == "1_0_7"

def test_climate_zone_4_exists(payload):
    from custom_components.onna.config_parser import parse_device_config
    config = parse_device_config(payload)
    assert "zone_4" in config["climate_addresses"]
    name = config["climate_addresses"]["zone_4"][0]
    assert name == "Dormitorio 4"


# --- Fan ---

def test_fan_discovered(payload):
    from custom_components.onna.config_parser import parse_device_config
    config = parse_device_config(payload)
    fans = config["fan_addresses"]
    assert len(fans) >= 1

def test_fan_addresses_correct(payload):
    from custom_components.onna.config_parser import parse_device_config
    config = parse_device_config(payload)
    fan = next(iter(config["fan_addresses"].values()))
    _name, valve_r, speed_r, speed_w, thermo_r = fan
    assert valve_r  == "1_7_1"
    assert speed_r  == "1_7_3"
    assert speed_w  == "1_7_2"
    assert thermo_r == "1_0_1"


# --- Switch ---

def test_switch_1_7_10_discovered(payload):
    from custom_components.onna.config_parser import parse_device_config
    config = parse_device_config(payload)
    assert "1_7_10" in config["switch_addresses"]


# --- Sensors ---

def test_sensor_power(payload):
    from custom_components.onna.config_parser import parse_device_config
    config = parse_device_config(payload)
    assert "0_5_3" in config["sensor_addresses"]
    _name, unit, dc, sc = config["sensor_addresses"]["0_5_3"]
    assert unit == "W"
    assert dc == "power"
    assert sc == "measurement"

def test_sensor_energy_total_increasing(payload):
    from custom_components.onna.config_parser import parse_device_config
    config = parse_device_config(payload)
    assert "0_5_5" in config["sensor_addresses"]
    _name, unit, dc, sc = config["sensor_addresses"]["0_5_5"]
    assert unit == "kWh"
    assert dc == "energy"
    assert sc == "total_increasing"

def test_sensor_exterior_temperature(payload):
    from custom_components.onna.config_parser import parse_device_config
    config = parse_device_config(payload)
    assert "0_0_8" in config["sensor_addresses"]
    _name, unit, dc, _sc = config["sensor_addresses"]["0_0_8"]
    assert unit == "°C"
    assert dc == "temperature"

def test_zone_temp_addrs_not_in_sensors(payload):
    from custom_components.onna.config_parser import parse_device_config
    config = parse_device_config(payload)
    sensors = config["sensor_addresses"]
    for zone in config["climate_addresses"].values():
        assert zone[1] not in sensors  # temp_r
        assert zone[2] not in sensors  # setpt_r


# --- Binary sensors ---

def test_flood_alarm_binary_sensor(payload):
    from custom_components.onna.config_parser import parse_device_config
    config = parse_device_config(payload)
    bs = config["binary_sensor_addresses"]
    assert "0_4_2" in bs
    _name, dc, inv = bs["0_4_2"]
    assert dc == "moisture"
    assert inv is False

def test_modo_invierno_binary_sensor(payload):
    from custom_components.onna.config_parser import parse_device_config
    config = parse_device_config(payload)
    assert "0_0_7" in config["binary_sensor_addresses"]
    _name, dc, _inv = config["binary_sensor_addresses"]["0_0_7"]
    assert dc is None

def test_zone_onoff_states_not_in_binary_sensors(payload):
    from custom_components.onna.config_parser import parse_device_config
    config = parse_device_config(payload)
    bs = config["binary_sensor_addresses"]
    for zone in config["climate_addresses"].values():
        assert zone[4] not in bs  # onoff_r addresses must not appear as binary sensors


# --- Valves ---

def test_ev_suelo_valve(payload):
    from custom_components.onna.config_parser import parse_device_config
    config = parse_device_config(payload)
    assert "0_0_5" in config["valve_addresses"]
    _name, dc = config["valve_addresses"]["0_0_5"]
    assert dc == "water"

def test_bano_cabezal_valves(payload):
    from custom_components.onna.config_parser import parse_device_config
    config = parse_device_config(payload)
    assert "1_5_1" in config["valve_addresses"]
    assert "1_6_1" in config["valve_addresses"]

def test_valve_position_addresses(payload):
    from custom_components.onna.config_parser import parse_device_config
    config = parse_device_config(payload)
    pos = config["valve_position_addresses"]
    assert "1_0_8" in pos
    _name, dc, actuator = pos["1_0_8"]
    assert dc == "water"
    assert actuator == "1_0_6"
    assert len(pos) == 5

def test_actuator_addrs_not_in_valves(payload):
    from custom_components.onna.config_parser import parse_device_config
    config = parse_device_config(payload)
    valves = config["valve_addresses"]
    for info in config["valve_position_addresses"].values():
        assert info[2] not in valves  # actuator_addr must not become a simple valve
