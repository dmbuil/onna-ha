"""Stub out homeassistant modules so tests run without the full HA install."""
import sys
import types
from enum import Enum
from unittest.mock import MagicMock


def _make_module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# ---- voluptuous (used by config flows) ----
vol_mod = _make_module("voluptuous")


class _Required(str):
    pass


class _Optional(str):
    pass


class _Schema:
    def __init__(self, schema_dict):
        self.schema = schema_dict

    def __call__(self, data):
        return data


vol_mod.Required = _Required
vol_mod.Optional = _Optional
vol_mod.Schema = _Schema


# ---- homeassistant.core ----
core_mod = _make_module("homeassistant")
core_mod = _make_module("homeassistant.core")
core_mod.HomeAssistant = MagicMock
core_mod.callback = lambda f: f          # identity decorator

# ---- homeassistant.config_entries ----
ce_mod = _make_module("homeassistant.config_entries")
ce_mod.ConfigEntry = MagicMock


class _ConfigFlow:
    """Minimal ConfigFlow stub with flow_id and helper methods."""
    VERSION = 1

    def __init_subclass__(cls, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)

    async def async_step_user(self, user_input=None):
        raise NotImplementedError

    def async_show_form(self, *, step_id, data_schema, errors=None):
        return {"type": "form", "step_id": step_id, "data_schema": data_schema, "errors": errors or {}}

    def async_create_entry(self, *, title, data):
        return {"type": "create_entry", "title": title, "data": data}


ce_mod.ConfigFlow = _ConfigFlow

# ---- homeassistant.helpers ----
_make_module("homeassistant.helpers")
disp_mod = _make_module("homeassistant.helpers.dispatcher")
disp_mod.async_dispatcher_connect = MagicMock()
disp_mod.async_dispatcher_send = MagicMock()
event_mod = _make_module("homeassistant.helpers.event")
event_mod.async_track_state_change_event = MagicMock(return_value=lambda: None)
ep_mod = _make_module("homeassistant.helpers.entity_platform")
ep_mod.AddEntitiesCallback = MagicMock
restore_mod = _make_module("homeassistant.helpers.restore_state")


class _RestoreEntity:
    async def async_get_last_state(self):
        return None


restore_mod.RestoreEntity = _RestoreEntity

# ---- homeassistant.components.sensor ----
_make_module("homeassistant.components")
sensor_mod = _make_module("homeassistant.components.sensor")


class _SensorDeviceClass(str, Enum):
    POWER = "power"
    VOLTAGE = "voltage"
    CURRENT = "current"
    ENERGY = "energy"
    WATER = "water"
    VOLUME = "volume"
    VOLUME_FLOW_RATE = "volume_flow_rate"
    TEMPERATURE = "temperature"


class _SensorStateClass(str, Enum):
    MEASUREMENT = "measurement"
    TOTAL_INCREASING = "total_increasing"


class _SensorEntity:
    _attr_has_entity_name = False
    _attr_should_poll = True
    _attr_name = None
    _attr_native_unit_of_measurement = None
    _attr_unique_id = None
    _attr_device_class = None
    _attr_state_class = None
    _attr_native_value = None

    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def device_class(self):
        return self._attr_device_class

    @property
    def native_value(self):
        return self._attr_native_value

    def async_write_ha_state(self):
        pass


sensor_mod.SensorDeviceClass = _SensorDeviceClass
sensor_mod.SensorStateClass = _SensorStateClass
sensor_mod.SensorEntity = _SensorEntity

# ---- homeassistant.components.binary_sensor ----
bs_mod = _make_module("homeassistant.components.binary_sensor")


class _BinarySensorDeviceClass(str, Enum):
    MOISTURE = "moisture"
    SMOKE = "smoke"
    RUNNING = "running"
    OPENING = "opening"
    PROBLEM = "problem"


class _BinarySensorEntity:
    _attr_has_entity_name = False
    _attr_should_poll = True
    _attr_name = None
    _attr_unique_id = None
    _attr_device_class = None
    _attr_is_on = None

    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def device_class(self):
        return self._attr_device_class

    @property
    def is_on(self):
        return self._attr_is_on

    def async_write_ha_state(self):
        pass


bs_mod.BinarySensorDeviceClass = _BinarySensorDeviceClass
bs_mod.BinarySensorEntity = _BinarySensorEntity

# ---- homeassistant.components.valve ----
valve_mod = _make_module("homeassistant.components.valve")


class _ValveDeviceClass(str, Enum):
    WATER = "water"
    GAS = "gas"


class _ValveEntityFeature(int, Enum):
    OPEN         = 1
    CLOSE        = 2
    SET_POSITION = 4
    STOP         = 8


class _ValveEntity:
    _attr_has_entity_name = False
    _attr_should_poll = True
    _attr_name = None
    _attr_unique_id = None
    _attr_device_class = None
    _attr_reports_position = False
    _attr_supported_features = 0

    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def device_class(self):
        return self._attr_device_class

    @property
    def reports_position(self):
        return self._attr_reports_position

    @property
    def supported_features(self):
        return self._attr_supported_features

    @property
    def is_closed(self):
        raise NotImplementedError

    def async_write_ha_state(self):
        pass


valve_mod.ValveDeviceClass = _ValveDeviceClass
valve_mod.ValveEntityFeature = _ValveEntityFeature
valve_mod.ValveEntity = _ValveEntity

# ---- homeassistant.components.fan ----
fan_mod = _make_module("homeassistant.components.fan")


class _FanEntityFeature(int, Enum):
    SET_SPEED  = 1
    TURN_OFF   = 16
    TURN_ON    = 32


class _FanEntity:
    _attr_has_entity_name = False
    _attr_should_poll = True
    _attr_name = None
    _attr_unique_id = None
    _attr_supported_features = 0

    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def is_on(self):
        raise NotImplementedError

    @property
    def percentage(self):
        return None

    @property
    def percentage_step(self):
        return 1

    def async_write_ha_state(self):
        pass


fan_mod.FanEntityFeature = _FanEntityFeature
fan_mod.FanEntity = _FanEntity

# ---- homeassistant.const ----
hass_const_mod = _make_module("homeassistant.const")


class _UnitOfTemperature(str, Enum):
    CELSIUS    = "°C"
    FAHRENHEIT = "°F"


hass_const_mod.UnitOfTemperature = _UnitOfTemperature
hass_const_mod.ATTR_TEMPERATURE  = "temperature"

# ---- homeassistant.components.climate ----
climate_mod = _make_module("homeassistant.components.climate")


class _HVACMode(str, Enum):
    OFF       = "off"
    HEAT      = "heat"
    COOL      = "cool"
    HEAT_COOL = "heat_cool"
    AUTO      = "auto"
    DRY       = "dry"
    FAN_ONLY  = "fan_only"


class _HVACAction(str, Enum):
    OFF     = "off"
    HEATING = "heating"
    COOLING = "cooling"
    IDLE    = "idle"


class _ClimateEntityFeature(int, Enum):
    TARGET_TEMPERATURE = 1
    PRESET_MODE        = 16
    FAN_MODE           = 8
    TURN_OFF           = 128
    TURN_ON            = 256


class _ClimateEntity:
    _attr_has_entity_name        = False
    _attr_should_poll            = True
    _attr_name                   = None
    _attr_unique_id              = None
    _attr_hvac_modes             = []
    _attr_supported_features     = 0
    _attr_temperature_unit       = "°C"
    _attr_target_temperature_step = 1.0

    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def hvac_mode(self):
        raise NotImplementedError

    @property
    def hvac_action(self):
        return None

    @property
    def current_temperature(self):
        return None

    @property
    def target_temperature(self):
        return None

    def async_write_ha_state(self):
        pass


climate_mod.ClimateEntity        = _ClimateEntity
climate_mod.ClimateEntityFeature = _ClimateEntityFeature
climate_mod.HVACMode             = _HVACMode
climate_mod.HVACAction           = _HVACAction

# ---- homeassistant.components.switch ----
switch_mod = _make_module("homeassistant.components.switch")


class _SwitchEntity:
    _attr_has_entity_name = False
    _attr_should_poll     = True
    _attr_name            = None
    _attr_unique_id       = None

    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def is_on(self):
        return None

    def async_write_ha_state(self):
        pass


switch_mod.SwitchEntity = _SwitchEntity
