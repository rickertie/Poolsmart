# Changelog

All notable changes to PoolSmart. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/).

## [0.12.2] - 2026-08-01

### Changed
- Durations read as hours and minutes instead of decimal hours. "0.78 h" is a
  number you have to convert before it means anything; "47 min" is not
- Every duration sensor carries a `readable` attribute, so a custom card does
  not have to repeat the arithmetic
- The filtration card on the Energy tab shows the window pressure warning when
  the daily requirement fills nearly the whole window

## [0.12.1] - 2026-08-01

### Fixed
- **Short cycling.** Priority branches are allowed to break an ordinary hold,
  which is right for the pump — a filtration deadline should not wait ten
  minutes. Once those branches learned to heat alongside in 0.10.0, they dragged
  the compressor through the exception with them, producing off at 20:01 and on
  again at 20:04. Compressor protection is now enforced separately from the
  hold and cannot be overridden by any branch. Reaching the target temperature
  still stops heating immediately
- The default solar threshold of 1500 W was over twice what a typical small
  installation draws, so moderately sunny afternoons were declined while free
  power went unused. It is now calculated from the heat pump and pump draw plus
  a configurable margin

### Added
- A solar surplus sensor showing the current figure against the threshold, the
  shortfall, and what the equipment actually draws
- The solar threshold as a number entity, adjustable without opening settings
- Compressor minimum off and run times as settings
- Solar on the dashboard: a chip, a card explaining how far off the threshold
  is, and a 24 hour graph

## [0.12.0] - 2026-08-01

### Changed
- **Off now means off.** Frost protection no longer runs in this mode; it lives
  in Stand-by. A pool may have been drained and dismantled, and starting a pump
  against an explicit instruction is worse than letting an unattended pool freeze

### Added
- A start-up grace period before flow is judged, so priming the pump after
  switching on no longer reports a fault at the moment someone is watching
- Notification buttons: heat now anyway, do not heat today, circulate only,
  switch everything off, apply the suggestion
- An explanation on the savings sensor for the three situations where zero is
  the honest answer

### Fixed
- Thermal power and delta-T were blanked while the heat pump was off, making a
  working installation look broken. They now report whenever the sensors allow
- Measured COP stays blank while the heat pump is idle, where dividing near-zero
  by near-zero produced a number that meant nothing
- Maximum price defaults to 0.22 instead of being empty, which rendered as
  unknown and broke dashboard templates doing arithmetic on it
- The mismatched-flow warning said the filter needed cleaning. It now says the
  setting is out of date, which is what it actually detected
- Dashboard templates carry defaults on every int and float filter

## [0.11.0] - 2026-08-01

### Added
- Decisions, obstacles and faults now appear in the Home Assistant logbook,
  attached to the pool device
- A full trace of every ladder branch per tick, with a verdict for each, shown
  in the panel's Diagnostics tab. Answers "why is it not heating" directly
  instead of leaving it to be inferred
- Branch changes are logged even when the switches do not move, since a change
  of reasoning is worth recording
- How long the previous state lasted is recorded with each entry
- Faults log both when they appear and when they clear, so duration is visible
- Diagnostics export gained the trace and a plain-sentence timeline

## [0.10.0] - 2026-08-01

### Fixed
- The filtration deadline branch switched the heat pump off, so on a pool
  needing many hours of filtration a day heating almost never ran and Boost
  appeared to do nothing. Circulation branches now heat alongside when heating
  is wanted and allowed — the pump is running either way. Stand-by is
  unaffected, since filtering without heating is its purpose
- Notifications delivered to a notify *entity* failed, because the entity was
  being called as though it were a service. Both kinds of target now work

### Added
- A warning when the daily filtration requirement occupies more than about 80%
  of the configured windows, since the deadline branch then dominates everything
  below it in the ladder

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

[0.12.2]: https://github.com/rickertie/Poolsmart/releases/tag/v0.12.2
[0.12.1]: https://github.com/rickertie/Poolsmart/releases/tag/v0.12.1
[0.12.0]: https://github.com/rickertie/Poolsmart/releases/tag/v0.12.0
[0.11.0]: https://github.com/rickertie/Poolsmart/releases/tag/v0.11.0
[0.10.0]: https://github.com/rickertie/Poolsmart/releases/tag/v0.10.0
[0.9.0]: https://github.com/rickertie/Poolsmart/releases/tag/v0.9.0
[0.8.0]: https://github.com/rickertie/Poolsmart/releases/tag/v0.8.0
