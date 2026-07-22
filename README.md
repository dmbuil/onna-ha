# Onna-HA

[![GitHub Release][releases-shield]][releases]
[![GitHub Release Date][release-date-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)
[![hacs][hacsbadge]][hacs]

> [!NOTE]
> This integration is **not affiliated with [Onna](https://onnahome.com)**. It
> is a community project developed by a Home Assistant user.

**Onna-HA** integrates the [Onna M Lite](https://onnahome.com/) home automation
controller by Onna with Home Assistant using the device's local `Socket.IO`
interface — no cloud account or internet connection required.

State updates are **push-based**: the Onna device broadcasts KNX group address
changes in real time, so entities update instantly without polling.

## Table of Contents

* [Requirements](#requirements)
* [Installation](#installation)
  * [HACS Installation](#hacs-installation)
  * [Manual Installation](#manual-installation)
* [Configuration](#configuration)
  * [Finding your Onna ID](#finding-your-onna-id)
* [Entities](#entities)
  * [Sensor](#sensor)
  * [Binary Sensor](#binary-sensor)
  * [Valve](#valve)
  * [Fan](#fan)
  * [Climate](#climate)
* [Smart thermostat](#smart-thermostat)
  * [Presets](#presets)
  * [Overshoot damping](#overshoot-damping)
  * [Seasonal gating](#seasonal-gating)
  * [Monitoring sensors](#monitoring-sensors)
  * [Options](#options)
* [Technical Details](#technical-details)
* [Security model](#security-model)
* [Development](#development)
* [Known Issues](#known-issues)

## Requirements

* Home Assistant 2024.12 or later
* Onna M Lite reachable on the same local network as your Home Assistant instance
* Your Onna device's local IP address and its Onna ID

## Installation

### HACS Installation

In HACS, add this as a custom repository: `https://github.com/dmbuil/onna-ha`

Then go to the HACS integrations page, search for **Onna** and install it. Once
installed, restart Home Assistant.

### Manual Installation

<details>
<summary>Manual installation steps</summary>

Copy the `custom_components/onna` directory into your Home Assistant
`config/custom_components/` folder:

```bash
cp -r custom_components/onna /config/custom_components/onna
```

Restart Home Assistant.

</details>

## Configuration

Go to **Settings → Devices & Services → Add Integration** and search for **Onna**.

| Option  | Required | Description                                                     | Example        |
| ------- | :------: | --------------------------------------------------------------- | -------------- |
| Host    |    ✅     | Local IP address of your Onna device                            | `192.168.10.3` |
| Onna ID |    ✅     | Device identifier used to authenticate the WebSocket connection | `ONNA_ID`      |

After saving, a single **Onna** device appears with all 35 entities.

### Finding your Onna ID

Open the Onna iOS or Android app while connected to your home Wi-Fi (LAN mode).
Go to **Settings → Device info** — the Onna ID is displayed there.

## Entities

All entities are grouped under a single **Onna** device.

### Sensor

> [!NOTE]
> The naming of the entities depends on the Onna deployment and the configuration
> of the KNX group addresses. The names shown here are
> based on _my_ M Lite installation, but feel free to rename them in Home
> Assistant to whatever makes sense for your home.

| Name                      | Unit | Device Class       | State Class      |
| ------------------------- | ---- | ------------------ | ---------------- |
| Potencia                  | W    | `power`            | measurement      |
| Tensión                   | V    | `voltage`          | measurement      |
| Intensidad                | mA   | `current`          | measurement      |
| Energía consumida         | kWh  | `energy`           | total_increasing |
| Caudal Agua Fría          | L/h  | —                  | measurement      |
| Agua Fría consumida       | m³   | `volume`           | total_increasing |
| Caudal Agua Caliente      | L/h  | `volume_flow_rate` | measurement      |
| Agua Caliente consumida   | m³   | `volume`           | total_increasing |
| Caudal Agua Suelo         | m³/h | `volume_flow_rate` | measurement      |
| Agua Suelo consumida      | m³   | `volume`           | total_increasing |
| Temp. Impulsión Suelo     | °C   | `temperature`      | measurement      |
| Temp. Retorno Suelo       | °C   | `temperature`      | measurement      |
| Temperatura Exterior      | °C   | `temperature`      | measurement      |
| Salón+Cocina Temp Real    | °C   | `temperature`      | measurement      |
| Dorm. Principal Temp Real | °C   | `temperature`      | measurement      |
| Dorm. 2 Temp Real         | °C   | `temperature`      | measurement      |
| Dorm. 3 Temp Real         | °C   | `temperature`      | measurement      |
| Dorm. 4 Temp Real         | °C   | `temperature`      | measurement      |
| Salón+Cocina Consigna     | °C   | `temperature`      | measurement      |
| Dorm. Principal Consigna  | °C   | `temperature`      | measurement      |
| Dorm. 2 Consigna          | °C   | `temperature`      | measurement      |
| Dorm. 3 Consigna          | °C   | `temperature`      | measurement      |
| Dorm. 4 Consigna          | °C   | `temperature`      | measurement      |

> [!NOTE]
> sensors report the active thermostat setpoint as broadcast by the device. They
> update automatically when the setpoint is changed from the Onna app or a
> physical thermostat.

### Binary Sensor

| Name                   | Device Class | Notes                                 |
| ---------------------- | ------------ | ------------------------------------- |
| Alarma Inundación      | `moisture`   |                                       |
| Alarma Incendio        | `smoke`      |                                       |
| Modo Invierno          | —            | ON = heating mode, OFF = cooling mode |
| Error Sonda Impulsión  | `problem`    | Flow probe fault                      |
| Salón+Cocina ON/OFF    | `running`    | Thermostat active state               |
| Dorm. Principal ON/OFF | `running`    | Thermostat active state               |
| Dorm. 2 ON/OFF         | `running`    | Thermostat active state               |
| Dorm. 3 ON/OFF         | `running`    | Thermostat active state               |
| Dorm. 4 ON/OFF         | `running`    | Thermostat active state               |

### Valve

| Name              | Device Class | Notes                                                                  |
| ----------------- | ------------ | ---------------------------------------------------------------------- |
| EV Suelo Radiante | `water`      | Read-only: electrovalve state for the underfloor heating circuit       |
| Válvulas Colector | `water`      | Read-only: open/closed state of the underfloor heating manifold valves |

### Fan

| Name          | Properties                    | Notes                                                                                       |
| ------------- | ----------------------------- | ------------------------------------------------------------------------------------------- |
| Fancoil Salón | on/off · percentage (0–100 %) | Read-only — valve state (`1_7_1`) and fan speed (`1_7_3`) combined into a single fan entity |

### Climate

Each heating/cooling zone is exposed as a climate entity, plus a single master
thermostat for the whole installation.

| Name                | Type                          | Notes                                                          |
| ------------------- | ----------------------------- | -------------------------------------------------------------- |
| Salón+Cocina        | Zone thermostat (`HEAT_COOL`) | Dual setpoint + presets                                        |
| Dorm. Principal     | Zone thermostat (`HEAT_COOL`) | Dual setpoint + presets                                        |
| Dorm. 2 / 3 / 4     | Zone thermostat (`HEAT_COOL`) | Dual setpoint + presets                                        |
| Temperatura General | Master thermostat             | Write-only broadcast of setpoint / on-off / mode to all zones |

**Zone thermostats** are dual-setpoint range entities: `target_temp_low` is the
winter/heating setpoint and `target_temp_high` the summer/cooling setpoint. The
hardware tracks only **one** setpoint per zone and the installation has a single
global winter/summer mode (`0_0_7`), so **only the setpoint of the active season
is written to the KNX bus** — the other slider is Home Assistant state until the
season flips, at which point the zone automatically applies the correct setpoint.
`hvac_action` reflects the real underfloor demand (`HEATING` / `COOLING` /
`IDLE` / `OFF`). Each zone supports native **presets** (see below) and can
optionally take an external room sensor and a window sensor (configured under
*Zone sensors* in the options flow).

> [!NOTE]
> Turning a zone off uses the explicit `OFF` HVAC mode — dragging a slider never
> toggles the zone. The **general** thermostat keeps the `7 °C = OFF` shortcut on
> its single slider.

**General thermostat** ("Temperatura General") is a write-only master that
broadcasts a common setpoint and on/off/mode to every zone at once. It has no
current-temperature readback (state is kept locally and restored across
restarts).

## Smart thermostat

Optional, **opt-in** enhancements layered on top of the native control. Out of
the box nothing changes: presets ship with sensible defaults, overshoot damping
only acts on zones that have an external sensor, and seasonal gating stays
inactive until an outdoor source is configured.

### Presets

Every zone exposes four presets — **Away**, **Eco**, **Sleep**, **Comfort** —
plus **Manual** (`none`). Each preset stores a *(heating, cooling)* pair, so when
the installation-wide season flips the zone automatically applies the matching
setpoint without any user action. The preset temperatures are **global** (shared
by all zones) and configured in the options flow. Defaults:

| Preset  | Heating (winter / `low`) | Cooling (summer / `high`) |
| ------- | :----------------------: | :-----------------------: |
| Away    |          16.0 °C         |          30.0 °C          |
| Eco     |          18.0 °C         |          27.0 °C          |
| Sleep   |          19.0 °C         |          26.0 °C          |
| Comfort |          21.0 °C         |          24.0 °C          |

The heating value must be ≤ the cooling value for every preset (validated in the
options flow). Selecting a preset loads both sliders and writes the active-season
value; dragging a slider, or an external setpoint change, drops the zone back to
**Manual**.

### Overshoot damping

Radiant floors have thermal inertia: after a zone stops calling for heat its
actuator closes but the slab keeps releasing (or, in summer, absorbing) stored
energy, so the room coasts past target. When a zone has an **external room
sensor** configured, the integration learns that coast per zone and per season
from the real room temperature and **pre-dampens the written setpoint** so the
room settles closer to target.

* Self-calibrating — an exponential moving average of the observed coast; no
  tuning required.
* Applied only once the learned coast is meaningful (≥ 0.2 °C) and clamped to a
  maximum of 2 °C.
* Works in both heating and cooling, and survives restarts.
* Only affects zones with an external sensor — the Onna probe cannot measure the
  true room overshoot.

**Formulas.** On each *demand-off → coast* cycle a sample is measured, blended
into the per-season learned value, and subtracted from (or, in summer, added to)
the written setpoint:

```text
# 1. Sample the coast over the window (default 90 min), clamped to [0, 3] °C
sample = peak(ext_temp)   − start      # heating  (room overshoots upward)
sample = start − trough(ext_temp)      # cooling  (room undershoots downward)

# 2. Blend into the learned value (EMA, α = 0.3) — per zone, per season
learned = 0.3 × sample + 0.7 × learned

# 3. Damp the written setpoint (only when learned ≥ 0.2 °C, capped at 2 °C)
damping       = min(learned, 2.0)
onna_setpoint = compensated_setpoint − damping     # heating
onna_setpoint = compensated_setpoint + damping     # cooling
```

Where `start` is the room temperature at demand-off, `peak` / `trough` the
extreme reached during the coast window, and `compensated_setpoint` the target
after external-sensor offset compensation. The final `onna_setpoint` is clamped
to the 7–35 °C range before it is written to the bus.

### Seasonal gating

The community system runs one season at a time (heat **or** cool). Seasonal
gating pauses zones when the outdoor climate makes the current mode pointless —
heating during a warm spell, cooling during a cold snap — based on a **48-hour
moving average** of an outdoor source (a `weather` entity or a temperature
`sensor`).

* Winter: pause when the outdoor average rises above the *heat-off* threshold
  (default 20 °C). Summer: pause when it drops below the *cool-off* threshold
  (default 16 °C). A ±0.5 °C hysteresis prevents flapping.
* Pausing turns the affected zones off (and back on when the gate clears),
  exactly like the window-pause; a manual turn on/off always wins.
* Installation-wide and independent of the window-pause — a zone resumes only
  when no pause is active.
* **Fails open**: with no outdoor source available, no gating is applied.

> [!WARNING]
> Seasonal gating physically turns zones on/off over KNX. Set the thresholds to
> match your climate before relying on it, and test with a temporary value first.

### Monitoring sensors

Two optional sensors let you graph how the smart layer adapts over time
(Settings → *History*):

| Name                     | Unit | Created when …                              | Shows                                                                 |
| ------------------------ | ---- | ------------------------------------------- | --------------------------------------------------------------------- |
| Media Exterior           | °C   | an outdoor source is configured             | the 48-hour outdoor EMA that drives seasonal gating                   |
| `<Zone>` Inercia Aprendida | °C | the zone has an external sensor configured  | the learned overshoot for the **active** season (rises as it adapts)  |

> [!NOTE]
> `Inercia Aprendida` reports the *learned* coast so you can watch the adaptation
> continuously; the damping actually applied to the setpoint equals it once it
> passes 0.2 °C (and is 0 below that).

### Options

Configure everything under **Settings → Devices & Services → Onna → Configure**:

| Menu entry     | What it configures                                                              |
| -------------- | ------------------------------------------------------------------------------- |
| Zone sensors   | Per-zone external temperature sensor and window sensor                          |
| General        | Setpoint hysteresis and window-open delay                                       |
| Presets        | The 8 preset temperatures (4 presets × heating/cooling)                         |
| Smart features | Outdoor source, winter/summer gating thresholds, and the overshoot coast window |

Changing any option reloads the integration, so new values apply without
restarting Home Assistant.

## Technical Details

The Onna device runs a **Socket.IO v2** server (Engine.IO v3, `EIO=3`) over
WebSocket on port 4001. The integration communicates directly via raw WebSocket
frames, which avoids incompatibilities with the python-socketio v5 API.

### Protocol events

| Event                           | Direction   | Purpose                                     |
| ------------------------------- | ----------- | ------------------------------------------- |
| `SET_ADDRESS_VALUE_FROM_SERVER` | Device → HA | Real-time push of a KNX group address value |
| `SET_ADDRESS_VALUE_FROM_CLIENT` | HA → Device | Write a value to a KNX group address        |
| `READ_CONFIGURATION`            | HA → Device | Request full state snapshot on (re)connect  |

KNX group addresses are represented as underscore-separated strings (e.g. `1_0_4`).

### Connection lifecycle

On startup the integration:
1. Opens a WebSocket to `ws://<host>:4001/socket.io/?EIO=3&transport=websocket&onnaId=<id>`
2. Sends `READ_CONFIGURATION` to receive the current state of all registered
   addresses
3. Enters a receive loop, sending an EIO heartbeat ping every `pingInterval` (10
   s — in Engine.IO v3 the client pings, the server pongs) and dispatching
   incoming `SET_ADDRESS_VALUE_FROM_SERVER` events to the relevant HA entities

If the connection drops, the client reconnects automatically using the
`websockets` library's built-in reconnect loop.

### Python dependencies

```txt
websockets>=11.0
```

The integration speaks Socket.IO v2 by building raw frames itself, so the
`python-socketio` / `python-engineio` libraries are not required.

## Security model

The Onna device exposes its Socket.IO server over **unencrypted `ws://` with no
authentication beyond the Onna ID**, which is sent as a URL query parameter. This
is a property of the device firmware, not of this integration. Practical implications:

* **Anyone on your LAN who knows (or sniffs) the Onna ID can read and write KNX**
  **addresses** — including turning heating zones on/off and changing setpoints.
  Keep the device on a trusted network segment (e.g. an IoT VLAN that only Home
  Assistant can reach).
* The integration treats the Onna ID as a credential: it is URL-encoded before
  use, never written to logs, and redacted from downloadable diagnostics.
* For remote access, Onna App connects to Onna Cloud Service, which then connects
  to the device over a secure channel.

## Development

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests (no live device or full HA install required)
python -m pytest tests/ -v
```

HA platform base classes (`SensorEntity`, `BinarySensorEntity`, `ValveEntity`,
`ConfigFlow`, etc.) are stubbed in `tests/conftest.py`, so the full test suite
runs in a plain Python environment.

## Known Issues

### Initial state on startup

The Onna device responds to `READ_CONFIGURATION` with a snapshot of all active
KNX addresses, but addresses that have not changed since the device last booted
may not be included. Entities for those addresses will show as `unknown` until
the device next broadcasts an update for them.

### Single-instance only

Only one Onna device per Home Assistant instance is currently supported.

[commits-shield]: https://img.shields.io/github/last-commit/dmbuil/onna-ha?style=for-the-badge
[commits]: https://github.com/dmbuil/onna-ha/commits/main
[hacs]: https://hacs.xyz
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[license-shield]: https://img.shields.io/github/license/dmbuil/onna-ha?label=license&style=for-the-badge
[release-date-shield]: https://img.shields.io/github/release-date/dmbuil/onna-ha?display_date=published_at&style=for-the-badge
[releases-shield]: https://img.shields.io/github/v/release/dmbuil/onna-ha?style=for-the-badge
[releases]: https://github.com/dmbuil/onna-ha/releases
