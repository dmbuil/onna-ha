# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[1.1.0]: https://github.com/dmbuil/onna-ha/releases/tag/1.1.0
[1.0.0]: https://github.com/dmbuil/onna-ha/releases/tag/1.0.0
