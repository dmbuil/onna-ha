"""Parse the Onna READ_CONFIGURATION (431 ack) payload into per-entry entity maps."""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from .const import SENSOR_KEYWORD_MAP, SENSOR_UNIT_SUFFIXES


def parse_device_config(payload: dict[str, Any]) -> dict[str, Any]:
    """Return device_config dict from a raw 431 ack payload dict."""
    addresses: list[dict] = payload.get("addresses", [])
    configuration: list[dict] = payload.get("configuration", [])
    addr_by_id: dict[str, dict] = {a["id"]: a for a in addresses if "id" in a}

    climate = _parse_climate(addresses)
    fans = _parse_fans(configuration, addr_by_id)
    switches = _parse_switches(configuration)

    assigned: set[str] = set()
    for zone in climate.values():
        assigned.update(zone[1:])          # temp_r, setpt_r, setpt_w, onoff_r, onoff_w, demand
    for fan in fans.values():
        assigned.update(fan[1:])           # valve_r, speed_r, speed_w, thermo_r
    assigned.update(switches.keys())

    valve_pos = _parse_valve_positions(addresses, assigned)
    assigned.update(valve_pos.keys())
    for info in valve_pos.values():
        assigned.add(info[2])              # actuator_addr

    valves = _parse_valves(addresses, assigned)
    assigned.update(valves.keys())

    return {
        "sensor_addresses":         _parse_sensors(addresses, assigned),
        "binary_sensor_addresses":  _parse_binary_sensors(addresses, assigned),
        "valve_addresses":          valves,
        "valve_position_addresses": valve_pos,
        "climate_addresses":        climate,
        "switch_addresses":         switches,
        "fan_addresses":            fans,
    }


# ---------------------------------------------------------------------------
# Configuration-tree helpers
# ---------------------------------------------------------------------------

def _walk_rooms(nodes: list[dict]):
    """Yield (room_name, device_node) for every leaf device inside a Room node."""
    for node in nodes:
        if node.get("type") == "Room":
            room_name = node.get("name", "")
            for child in node.get("children", []):
                yield room_name, child
        else:
            yield from _walk_rooms(node.get("children", []))


def _slugify(name: str) -> str:
    """ASCII-safe slug: 'Salón' → 'salon'."""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", ascii_str.lower()).strip("_")


# ---------------------------------------------------------------------------
# Per-entity-type parsers
# ---------------------------------------------------------------------------

def _parse_climate(addresses: list[dict]) -> dict[str, list]:
    """Group area-1 addresses by line number to build thermostat zone records."""
    groups: dict[str, dict[str, dict]] = {}
    for addr in addresses:
        addr_id = addr.get("id", "")
        parts = addr_id.split("_")
        if len(parts) != 3 or parts[0] != "1":
            continue
        groups.setdefault(parts[1], {})[parts[2]] = addr

    result: dict[str, list] = {}
    for line, devices in sorted(groups.items(), key=lambda x: int(x[0])):
        if not all(d in devices for d in ["0", "1", "2", "3", "4"]):
            continue
        zone_id = f"zone_{line}"
        name = devices["1"].get("interGroup", zone_id)
        result[zone_id] = [
            name,
            devices["4"]["id"],                       # temp_r       1_X_4
            devices["3"]["id"],                       # setpt_r      1_X_3
            devices["2"]["id"],                       # setpt_w      1_X_2
            devices["1"]["id"],                       # onoff_r      1_X_1
            devices["0"]["id"],                       # onoff_w      1_X_0
            devices.get("7", {}).get("id", ""),       # demand       1_X_7
        ]
    return result


def _parse_fans(
    configuration: list[dict], addr_by_id: dict[str, dict]
) -> dict[str, list]:
    """Detect fancoil device10 nodes in the configuration tree."""
    result: dict[str, list] = {}
    for room_name, device in _walk_rooms(configuration):
        if device.get("type") != "device10":
            continue
        if not (device.get("additionalStage") and device.get("fanState")):
            continue
        valve_r  = device.get("additionalHeatingState1BitAddress", "")
        speed_r  = device.get("fanStateAddress", "")
        thermo_r = device.get("onOffStateAddress", "")
        inter_grp = addr_by_id.get(speed_r, {}).get("interGroup") if speed_r else None
        speed_w = ""
        if inter_grp:
            for a in addr_by_id.values():
                if (
                    a.get("interGroup") == inter_grp
                    and a.get("type") == "5.001"
                    and not a.get("readOnInit", True)
                ):
                    speed_w = a["id"]
                    break
        if not all([valve_r, speed_r, speed_w, thermo_r]):
            continue
        fan_id = f"fancoil_{_slugify(room_name)}"
        result[fan_id] = [f"Fancoil {room_name}", valve_r, speed_r, speed_w, thermo_r]
    return result


def _parse_switches(configuration: list[dict]) -> dict[str, list]:
    """Detect customButton device10 nodes in the configuration tree."""
    result: dict[str, list] = {}
    for _room_name, device in _walk_rooms(configuration):
        if device.get("type") != "device10":
            continue
        if not device.get("customButton"):
            continue
        addr = device.get("customButtonAddress", "")
        name = device.get("customButtonName", "")
        if addr and name:
            result[addr] = [name]
    return result


def _strip_unit_suffix(name: str) -> str:
    return re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()


def _sensor_meta(name: str) -> tuple | None:
    """Return (unit, device_class, state_class) for a sensor address name, or None."""
    for suffix, meta in SENSOR_UNIT_SUFFIXES.items():
        if suffix in name:
            return meta
    for keyword, unit, device_class, state_class in SENSOR_KEYWORD_MAP:
        if keyword.lower() in name.lower():
            return unit, device_class, state_class
    return None


def _parse_sensors(addresses: list[dict], assigned: set[str]) -> dict[str, list]:
    result: dict[str, list] = {}
    for addr in addresses:
        addr_id = addr.get("id", "")
        if addr_id in assigned:
            continue
        if addr.get("type") not in {"9.001", "14.001", "13.001"}:
            continue
        if not addr.get("readOnInit", False):
            continue
        name = addr.get("name", "")
        meta = _sensor_meta(name)
        if meta is None:
            continue
        unit, device_class, state_class = meta
        result[addr_id] = [_strip_unit_suffix(name), unit, device_class, state_class]
    return result


_ALARM_DEVICE_CLASSES = {"Inundación": "moisture", "Incendio": "smoke"}


def _parse_binary_sensors(addresses: list[dict], assigned: set[str]) -> dict[str, list]:
    result: dict[str, list] = {}
    for addr in addresses:
        addr_id = addr.get("id", "")
        if addr_id in assigned:
            continue
        if addr.get("type") != "1.001":
            continue
        inter_grp = addr.get("interGroup", "")
        name = addr.get("name", "")
        if inter_grp == "Alarmas Técnicas":
            dc = next((v for k, v in _ALARM_DEVICE_CLASSES.items() if k in name), "problem")
            result[addr_id] = [name, dc, False]
        elif ("Invierno" in name or "Verano" in name) and addr.get("readOnInit", False):
            result[addr_id] = [name, None, False]
        elif "Error" in name and addr.get("readOnInit", False):
            result[addr_id] = [name, "problem", False]
    return result


_VALVE_KEYWORDS = ("cabezal", "ev ", "válvula", "colector")


def _parse_valves(addresses: list[dict], assigned: set[str]) -> dict[str, list]:
    result: dict[str, list] = {}
    for addr in addresses:
        addr_id = addr.get("id", "")
        if addr_id in assigned:
            continue
        if addr.get("type") != "1.001":
            continue
        if not addr.get("readOnInit", False):
            continue
        name_lower = addr.get("name", "").lower()
        if any(kw in name_lower for kw in _VALVE_KEYWORDS):
            result[addr_id] = [addr.get("name", ""), "water"]
    return result


def _parse_valve_positions(addresses: list[dict], assigned: set[str]) -> dict[str, list]:
    result: dict[str, list] = {}
    for addr in addresses:
        addr_id = addr.get("id", "")
        if addr_id in assigned:
            continue
        if addr.get("type") != "5.001":
            continue
        if not addr.get("readOnInit", False):
            continue
        if "Demanda Suelo PI" not in addr.get("name", ""):
            continue
        parts = addr_id.split("_")
        if len(parts) == 3 and parts[2] == "8":
            actuator_id = f"{parts[0]}_{parts[1]}_6"
            result[addr_id] = [addr.get("name", ""), "water", actuator_id]
    return result
