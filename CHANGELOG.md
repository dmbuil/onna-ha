# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-09-19

### Added
- **Smart thermostat layer** for the climate zones. It is opt-in: out of the box
  nothing changes.
  - **Overshoot damping.** Radiant floors keep heating (or cooling) after the
    actuator closes. For zones with an external room sensor, the integration
    learns that coast per zone and per season and pre-dampens the written
    setpoint so the room settles closer to target. Damping applies once the
    learned value reaches 0.2 °C and is capped at 2 °C. Learned values survive
    restarts. The Onna controller toggles demand on and off in bursts of
    under a minute, so a coast is only sampled after demand stays off for a
    settle period (5 min by default).
  - **Seasonal gating.** With an outdoor temperature source configured, zones
    pause while heating is not needed in winter or cooling is not needed in
    summer, based on a 48-hour outdoor average with hysteresis. The pause
    behaves like the window-open pause.
- **Smart features options step**: outdoor source, winter/summer gating
  thresholds, and the overshoot coast window and settle period.
- **Smart thermostat switch** (`switch.onna_smart_thermostat`). It turns off
  overshoot damping and seasonal gating across all zones at once, leaving plain
  thermostats that keep presets, external-sensor compensation and the
  window-open pause. Learned values are kept, and the switch position survives
  restarts.
- **Monitoring sensors**: *Media Exterior* (the 48-hour outdoor average) and a
  per-zone *Inercia Aprendida* (the learned overshoot for the active season).

### Fixed
- **Climate entities showed the wrong season after a restart.** Onna only
  announces changes, never the current state, so the winter/summer address
  (which flips twice a year) was unknown after every restart. Zones then
  reported `heating` all summer. The last known value of every KNX address is
  now saved in Home Assistant storage and restored on startup.
- The integration's documentation and issue-tracker links now point to the
  correct repository (`onna-ha`).

## [1.1.0] - 2026-07-22

### Added
- **Dual-setpoint climate control.** Zone thermostats are now `HEAT_COOL` range
  entities that expose independent low and high targets
  (`target_temp_low` / `target_temp_high`) instead of a single setpoint, so a
  comfort band can be defined per zone.
- **Native preset modes** on every zone — `away`, `eco`, `sleep` and `comfort` —
  selectable directly from the Home Assistant climate card.
- **Global preset temperatures** configurable from the integration options and
  applied to all zones. The heat target is validated so it can never exceed the
  cool target.

### Changed
- The options flow gained a dedicated step to configure the global preset
  temperatures.

## [1.0.0] - Initial public release

- First public release of the Onna integration for Home Assistant.

[1.2.0]: https://github.com/dmbuil/onna-ha/releases/tag/1.2.0
[1.1.0]: https://github.com/dmbuil/onna-ha/releases/tag/1.1.0
[1.0.0]: https://github.com/dmbuil/onna-ha/releases/tag/1.0.0
