# Changelog

All notable changes to PoolSmart. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/).

## [0.9.0] - 2026-08-01

### Fixed
- The filter service warning compared measured flow against the configured
  figure, so it fired permanently on any system whose real flow sits below its
  datasheet number. It now tracks decline from a learned baseline
- Filtration duration is calculated from measured flow where a meter exists,
  instead of from the configured value. A datasheet figure the pump never
  reaches produced a daily requirement far below what the pool needs

### Added
- The measured flow baseline is learned continuously while the pump runs
- A warning when the configured flow clearly contradicts what is measured,
  because every derived figure depends on it
- Sensors that are legitimately blank now explain why in an
  `unavailable_because` attribute: heat pump not running, no inlet and outlet
  sensors, both roles pointing at the same entity, no price source, nothing
  learned yet

## [0.8.0] - 2026-08-01

First public release. Versions below this were development iterations and were
never published, so everything listed there is part of this release.

### Added
- Decision ladder with ten branches producing one decision per 30 second tick,
  each carrying a plain-language reason
- Six operating modes that enable or disable branches rather than duplicating
  logic
- Filtration requirement derived from turnover and a temperature-dependent daily
  minimum, whichever is larger
- Heating planner with separate maintenance and multi-day seasonal modes
- Price optimisation, including a branch that heats regardless when electricity
  is priced below zero
- Self-learning heating rate, heat loss and per-temperature COP curve, with
  capped updates and outlier rejection
- Sidebar management panel with overview, planning, sessions, learning, settings
  and diagnostics tabs
- Advisory AI layer, strictly outside the control path, with suggestions
  validated against a fixed list of adjustable settings
- Per-event notification routing with escalating repeats for unresolved faults
- Flow meter unit detection and conversion
- Filter medium selection affecting the estimated real flow
- Chemistry cycle and pool cover modules as working placeholders
- Brand images shipped inside the integration
- Complete three-tab dashboard and an example ESPHome configuration
- 40 acceptance tests against a Home Assistant free decision core

### Fixed during development
- Sensor liveness measured from `last_reported` rather than `last_updated`, so a
  steady temperature is no longer mistaken for a dead sensor
- Sensor faults block heating instead of stopping everything; circulation
  continues
- Flow meter readings converted from their own unit instead of being taken as
  m³/h
- Optional subsystems isolated so one failure cannot mark every entity
  unavailable
- Entity ids fixed in code rather than derived from translated names, with a
  one-time migration for existing installations
- Seasonal planning no longer treats a short price forecast as a whole day of
  capacity

[0.9.0]: https://github.com/rickertie/Poolsmart/releases/tag/v0.9.0
[0.8.0]: https://github.com/rickertie/Poolsmart/releases/tag/v0.8.0
