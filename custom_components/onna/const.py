"""Constants for the Onna integration.

KNX address naming convention used in this file
-------------------------------------------------
Addresses follow the pattern ``<area>_<line>_<device>`` where the three
numbers map to Onna's internal KNX topology:

  area 0 — installation-wide (electrical, water meters, alarms, global mode)
  area 1 — per-zone heating/cooling (zone index = line, 0=Salón … 4=Dorm.4)
  zone X (line 0–4) addresses:
    1_X_0  write ON/OFF (actuate)       1_X_1  read ON/OFF state
    1_X_2  write setpoint               1_X_3  read setpoint state
    1_X_4  real temperature (probe)     1_X_6  actuator head state
    1_X_7  heating/cooling demand       1_X_8  PI demand 0–100 %

All values on the wire are plain Python numbers (int or float).  Boolean KNX
DPT 1.001 addresses arrive and are sent as 1/0 integers.
"""
DOMAIN = "onna"

CONF_HOST    = "host"
CONF_ONNA_ID = "onna_id"

# KNX address map: id → (name, unit, device_class, state_class)
# Sensors (numeric)
SENSOR_ADDRESSES = {
    "0_5_3":  ("Potencia",               "W",    "power",              "measurement"),
    "0_5_2":  ("Tensión",                "V",    "voltage",            "measurement"),
    "0_5_4":  ("Intensidad",             "mA",   "current",            "measurement"),
    "0_5_5":  ("Energía consumida",      "kWh",  "energy",             "total_increasing"),
    "0_5_6":  ("Caudal Agua Fría",       "L/h",  None,                 "measurement"),
    "0_5_7":  ("Agua Fría consumida",    "m³",   "water",              "total_increasing"),
    "0_5_8":  ("Caudal Agua Caliente",   "L/h",  "volume_flow_rate",   "measurement"),
    "0_5_9":  ("Agua Caliente consumida","m³",   "water",              "total_increasing"),
    "0_5_10": ("Caudal Agua Suelo",      "m³/h", "volume_flow_rate",   "measurement"),
    "0_5_11": ("Agua Suelo consumida",   "m³",   "water",              "total_increasing"),
    "0_5_12": ("Temp. Impulsión Suelo",  "°C",   "temperature",        "measurement"),
    "0_5_14": ("Temp. Retorno Suelo",    "°C",   "temperature",        "measurement"),
    "0_0_8":  ("Temperatura Exterior",   "°C",   "temperature",        "measurement"),
    # Thermostat zones — real temp
    "1_0_4":  ("Salón+Cocina Temp Real",       "°C", "temperature", "measurement"),
    "1_1_4":  ("Dorm. Principal Temp Real",    "°C", "temperature", "measurement"),
    "1_2_4":  ("Dorm. 2 Temp Real",           "°C", "temperature", "measurement"),
    "1_3_4":  ("Dorm. 3 Temp Real",           "°C", "temperature", "measurement"),
    "1_4_4":  ("Dorm. 4 Temp Real",           "°C", "temperature", "measurement"),
    # Thermostat zones — setpoint state (read from feedback)
    "1_0_3":  ("Salón+Cocina Consigna",        "°C", "temperature", "measurement"),
    "1_1_3":  ("Dorm. Principal Consigna",     "°C", "temperature", "measurement"),
    "1_2_3":  ("Dorm. 2 Consigna",            "°C", "temperature", "measurement"),
    "1_3_3":  ("Dorm. 3 Consigna",            "°C", "temperature", "measurement"),
    "1_4_3":  ("Dorm. 4 Consigna",            "°C", "temperature", "measurement"),
}

# Binary sensors (boolean KNX addresses)
BINARY_SENSOR_ADDRESSES = {
    "0_4_2": ("Alarma Inundación",       "moisture",   False),
    "0_4_3": ("Alarma Incendio",         "smoke",      False),
    "0_0_7": ("Modo Invierno",           None,         False),
    "0_5_13":("Error Sonda Impulsión",   "problem",    False),
    # Thermostat ON/OFF states
    "1_0_1": ("Salón+Cocina ON/OFF",     "running",    False),
    "1_1_1": ("Dorm. Principal ON/OFF",  "running",    False),
    "1_2_1": ("Dorm. 2 ON/OFF",         "running",    False),
    "1_3_1": ("Dorm. 3 ON/OFF",         "running",    False),
    "1_4_1": ("Dorm. 4 ON/OFF",         "running",    False),
}

# Valve entities (boolean KNX address, read-only state)
VALVE_ADDRESSES = {
    "0_0_5": ("EV Suelo Radiante",  "water"),
    "0_0_6": ("Válvulas Colector",  "water"),
}

# Per-zone underfloor heating valves: position_addr → (name, device_class, actuator_addr)
# position_addr (1_X_8): PI demand 0-100 % (DPT 5.001) → current_valve_position
# actuator_addr (1_X_6): zone actuator head open/closed (DPT 1.001) → is_closed
# These are read-only from HA — the zone thermostats drive them automatically.
VALVE_POSITION_ADDRESSES = {
    "1_0_8": ("Salón+Cocina Demanda Suelo",    "water", "1_0_6"),
    "1_1_8": ("Dorm. Principal Demanda Suelo", "water", "1_1_6"),
    "1_2_8": ("Dorm. 2 Demanda Suelo",         "water", "1_2_6"),
    "1_3_8": ("Dorm. 3 Demanda Suelo",         "water", "1_3_6"),
    "1_4_8": ("Dorm. 4 Demanda Suelo",         "water", "1_4_6"),
}

# Climate zones: id → (name, temp_addr, setpoint_r, setpoint_w, onoff_r, onoff_w, demand_addr)
# temp_addr   (1_X_4): real temperature (probe)       → current_temperature
# setpoint_r  (1_X_3): setpoint state (read-back)     → target_temperature
# setpoint_w  (1_X_2): setpoint write                 → write setpoint
# onoff_r     (1_X_1): thermostat ON/OFF state         → hvac_mode (read)
# onoff_w     (1_X_0): thermostat ON/OFF               → write ON/OFF (HEAT/COOL are global)
# demand_addr (1_X_7): underfloor demand state         → hvac_action
CLIMATE_ADDRESSES = {
    "zone_0": ("Salón+Cocina",    "1_0_4", "1_0_3", "1_0_2", "1_0_1", "1_0_0", "1_0_7"),
    "zone_1": ("Dorm. Principal", "1_1_4", "1_1_3", "1_1_2", "1_1_1", "1_1_0", "1_1_7"),
    "zone_2": ("Dorm. 2",         "1_2_4", "1_2_3", "1_2_2", "1_2_1", "1_2_0", "1_2_7"),
    "zone_3": ("Dorm. 3",         "1_3_4", "1_3_3", "1_3_2", "1_3_1", "1_3_0", "1_3_7"),
    "zone_4": ("Dorm. 4",         "1_4_4", "1_4_3", "1_4_2", "1_4_1", "1_4_0", "1_4_7"),
}

# Switch entities: id → (name,)
# 1_7_10: Fancoil Salón Habilitar/Deshabilitar (write-only, DPT 1.001, no read-back)
SWITCH_ADDRESSES = {
    "1_7_10": ("Fancoil Salón Habilitado",),
}

# External HA sensor overrides for current_temperature per zone.
#
# Purpose: Onna's built-in probes sit inside the KNX thermostat housings and can read
# significantly lower than the actual room air temperature (cold wall, floor placement, etc.).
# Configuring an external sensor here fixes both the display and the control loop:
#
#   • current_temperature in HA shows the external sensor value.
#   • The setpoint written to the KNX bus is offset-compensated so that Onna's own probe
#     triggers heating/cooling when the room (measured by the external sensor) reaches the
#     user's target.  See the module docstring in climate.py for the formula.
#
# Fallback: if the external sensor goes "unavailable" or "unknown", the integration
# automatically falls back to Onna's own probe for both display and control (no compensation).
# Any setpoint changes made from Onna's native app during the offline window are still picked
# up and reflected in HA.
#
# To add a new zone override, add an entry below using the zone_X key from CLIMATE_ADDRESSES
# and the full HA entity_id of the sensor (must expose a numeric state in °C).
# To remove an override for a zone, simply delete its entry — no code changes needed.
CLIMATE_TEMP_OVERRIDE: dict[str, str] = {
    "zone_0": "sensor.sonoff_ths_2_temperature",
    "zone_1": "sensor.sonoff_ths_1_temperature",
    "zone_2": "sensor.tuya_ths_3_temperature",
    "zone_3": "sensor.tuya_ths_4_temperature",
    # "zone_4": "sensor.your_sensor_entity_id",  # Dorm. 4 — add if needed
}

# Window sensor overrides per zone.
# When a sensor reports "on" (open) for longer than _WINDOW_OPEN_DELAY seconds,
# the zone thermostat is automatically turned off to save energy.  It resumes as soon
# as the window is closed again.  Zones that were already OFF are unaffected.
#
# Use HA binary_sensor entity_ids (door/window contact sensors, etc.).
# To add a new zone, add an entry below using the zone_X key from CLIMATE_ADDRESSES.
CLIMATE_WINDOW_SENSOR: dict[str, str] = {
    "zone_0": "binary_sensor.0xa4c138f41f68d504_contact",   # Salón+Cocina
    "zone_1": "binary_sensor.0xa4c13897e98a6881_contact",   # Dorm. Principal
    # "zone_2": "binary_sensor.window_dorm_2",
    # "zone_3": "binary_sensor.window_dorm_3",
    # "zone_4": "binary_sensor.window_dorm_4",
}

# Fan entities: id → (name, valve_address, speed_address, speed_write_address)
# valve_address       (1_7_1): Fancoil ON/OFF state — Onna sets automatically based on demand.
# speed_address       (1_7_3): Fancoil speed 0-100 % — Onna-controlled (PI output).
# speed_write_address (1_7_2): Speed write address — used by HA for manual override.
# The valve is NOT written directly; Onna's AND-gate logic sets it from speed state automatically.
FAN_ADDRESSES = {
    "fancoil_salon": ("Fancoil Salón", "1_7_1", "1_7_3", "1_7_2"),
}
