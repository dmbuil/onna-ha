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

Then go to the HACS integrations page, search for **Onna** and install it. Once installed, restart Home Assistant.

### Manual Installation

<details>
<summary>Manual installation steps</summary>

Copy the `custom_components/onna` directory into your Home Assistant `config/custom_components/` folder:

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

Open the Onna iOS or Android app while connected to your home Wi-Fi (LAN mode). Go to **Settings → Device info** — the Onna ID is displayed there.

## Entities

All entities are grouped under a single **Onna** device.

### Sensor

> [!NOTE] Naming
> The naming of the entities depends on the Onna deployment and the configuration of the KNX group addresses. The names shown here are
> based on _my_ M Lite installation, but feel free to rename them in Home Assistant to whatever makes sense for your home.

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

> [!NOTE] Consigna
> sensors report the active thermostat setpoint as broadcast by the device. They update automatically when the setpoint is changed from the Onna app or a physical thermostat.

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

## Technical Details

The Onna device runs a **Socket.IO v2** server (Engine.IO v3, `EIO=3`) over WebSocket on port 4001. The integration communicates directly via raw WebSocket frames, which avoids incompatibilities with the python-socketio v5 API.

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
2. Sends `READ_CONFIGURATION` to receive the current state of all registered addresses
3. Enters a receive loop, sending an EIO heartbeat ping every `pingInterval` (10 s — in Engine.IO v3 the client pings, the server pongs) and dispatching incoming `SET_ADDRESS_VALUE_FROM_SERVER` events to the relevant HA entities

If the connection drops, the client reconnects automatically using the `websockets` library's built-in reconnect loop.

### Python dependencies

```
websockets>=11.0
```

The integration speaks Socket.IO v2 by building raw frames itself, so the `python-socketio` / `python-engineio` libraries are not required.

## Security model

The Onna device exposes its Socket.IO server over **unencrypted `ws://` with no authentication beyond the Onna ID**, which is sent as a URL query parameter. This is a property of the device firmware, not of this integration. Practical implications:

* **Anyone on your LAN who knows (or sniffs) the Onna ID can read and write KNX addresses** — including turning heating zones on/off and changing setpoints. Keep the device on a trusted network segment (e.g. an IoT VLAN that only Home Assistant can reach).
* The integration treats the Onna ID as a credential: it is URL-encoded before use, never written to logs, and redacted from downloadable diagnostics.
* For remote access, Onna App connects to Onna Cloud Service, which then connects to the device over a secure channel.

## Development

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests (no live device or full HA install required)
python -m pytest tests/ -v
```

HA platform base classes (`SensorEntity`, `BinarySensorEntity`, `ValveEntity`, `ConfigFlow`, etc.) are stubbed in `tests/conftest.py`, so the full test suite runs in a plain Python environment.

## Known Issues

### Initial state on startup

The Onna device responds to `READ_CONFIGURATION` with a snapshot of all active KNX addresses, but addresses that have not changed since the device last booted may not be included. Entities for those addresses will show as `unknown` until the device next broadcasts an update for them.

### Single-instance only

Only one Onna device per Home Assistant instance is currently supported.

[commits-shield]: https://img.shields.io/github/last-commit/dmbuil/onna-ha?style=for-the-badge
[commits]: https://github.com/dmbuil/onna-ha/commits/main
[hacs]: https://hacs.xyz
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[license-shield]: https://img.shields.io/github/license/dmbuil/onna-ha.svg?style=for-the-badge
[release-date-shield]: https://img.shields.io/github/release-date/dmbuil/onna-ha?display_date=published_at&style=for-the-badge
[releases-shield]: https://img.shields.io/github/v/release/dmbuil/onna-ha?style=for-the-badge
[releases]: https://github.com/dmbuil/onna-ha/releases
