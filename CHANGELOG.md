# Changelog

All notable changes to PoolSmart. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/).

Every release gets a title naming what it was actually about. Read from the
bottom up, they tell the story of a system slowly learning to stop believing its
own paperwork.

## [1.2.3] — Tablets Are Counted — 2026-08-06

### Fixed
- **The panel header ignored the theme.** A fixed navy block looked right in a
  dark mockup and wrong on a light Home Assistant, which is most installations.
  It now tints the accent colour, giving the same emphasis either way
- **"Add 11 g of chlorine tablet" is not an instruction anyone can follow.**
  Tablets come in fixed sizes, cannot usefully be halved, and take days to
  dissolve — which makes them the wrong product for a reading that is low right
  now. The recommendation is a whole number of tablets, says how that compares
  with the weight actually needed, and points at granules or liquid when the
  pool needs chlorine today
- **Staleness warnings on the outdoor probe.** Fifteen minutes is aggressive for
  a sensor that legitimately holds the same value overnight. Outdoor air and
  pool water now get four times the patience of a fast-moving probe. A warning
  nobody can act on is how people learn to ignore the ones that matter

### Added
- Tablet size as a setting, since 20 g, 200 g and 500 g are all common and the
  difference between them is the difference between one tablet and a quarter of
  one

## [1.2.2] — Executed, Not Parsed — 2026-08-05

### Fixed
- Setup crashed on restart: the COP backfill reached for `cop_by_air_bucket` on
  the store, while those values live on the store's `learned` object. The test
  written for it had built a stand-in with the fields hung directly off it —
  encoding the same wrong mental model that produced the bug, and passing for
  exactly that reason

### Added
- The storage layer is now **executed** by the tests rather than only parsed,
  using stub Home Assistant modules thin enough not to become their own
  maintenance burden. Two setup-breaking bugs in three releases went through the
  gap between "this file is grammatical" and "this file works": a method calling
  one that was never written, and a method reading fields off the wrong object
- A test that walks the storage source for any remaining field reached for on
  the wrong object, and one confirming learned values survive a save and reload
- `tools/verify_package.py` runs the storage layer against the built archive too

## [1.2.1] — Defined Before Used — 2026-08-05

### Fixed
- **1.2.0 would not load at all.** `const.py` built a tuple from names declared
  seventy lines further down, and Python executes a module top to bottom. Every
  syntax check passed, because `ast.parse` proves a file is grammatical and says
  nothing about whether its names resolve
- A package verification script now imports every module that carries no Home
  Assistant dependency, rather than only parsing it, and checks manifest key
  order, translation key format and panel string parity in the built archive
  before it goes out

## [1.2.0] — Seven Readings and a Ceiling — 2026-08-05

### Fixed
- **A learned heating rate of 1.02 °C/h on a pool whose maximum is 0.67.**
  Nothing checked the measured rise against what the appliance can physically
  deliver, so a session where the pump stirred stratified water read as
  spectacular heating. Because the learned rate is trusted ahead of any COP
  calculation, that single session drove every later estimate: two hours
  predicted for a rise that really takes fourteen, so heating started far too
  late. Sessions above the appliance's own ceiling are now rejected
- **The measured COP was never used.** `cop_by_air_bucket` has existed since
  0.9; the counter gating it arrived in 1.1, so anyone who upgraded had learned
  values with a count of zero — sitting behind a gate that could never open no
  matter how many sessions produced them. Counts are now recovered from the
  session log on startup
- The chemistry cycle ran for one fixed duration regardless of product. Adding
  a 20 g tablet and circulating for a few minutes is not a treatment

### Added
- **Unit system.** Metric or US customary, chosen at setup, changing how volumes
  and doses are presented. Calculation stays metric throughout
- **Circulation time per product**, from published guidance: 30 minutes for
  non-chlorine shock, an hour for pH adjustment, four hours for a maintenance
  chlorine dose, ten for chlorine shock, a full day for algaecide, and none at
  all for a tablet in a floater
- **The whole AquaChek strip.** Total chlorine, bromine, alkalinity, cyanuric
  acid, hardness, and salt for electrolysis systems, each judged against its
  ideal range with two levels of wrong rather than one — a pH of 7.7 wants
  attention this week, 8.6 wants it now
- **Combined chlorine**, derived from total minus free. The one figure a strip
  gives you that answers "should I shock", and it only exists if two columns are
  subtracted
- **Conclusions that need several readings together**: stabiliser high enough
  that adding chlorine achieves nothing, pH and alkalinity both adrift with
  alkalinity as the one to fix first, chlorine judged against the stabiliser
  level rather than a fixed range
- **Sanitiser type** at setup, so a chlorine pool is not shown bromine fields
- **Near misses**, tallied across the day. One tick's trace answers "why not
  now"; this answers "why not today", and twenty refusals on price is a setting
  worth revisiting where one is a passing expensive hour
- Expected against actual rise during a session, previous sessions to compare
  it with, confidence bars on each learned value, and a `reset_learned` service
  to clear one figure without discarding the rest
- Panel restyled: the dense monospace readouts of one direction with the card
  shell and hero block of another

### Changed
- The Pool Chem recommendation is gone; it turned out not to do what was wanted.
  The boundary is still stated plainly — this is not a water chemistry
  integration — but pointing at a specific alternative that did not suit is
  worse than describing the limit

## [1.1.2] — Where Does This Sensor Go — 2026-08-04

### Fixed
- **Setup failed with `AttributeError: no attribute '_bridge'`.** `_read` called
  a method that was never actually written — an edit that reported success and
  landed nowhere. It only surfaced the first time a sensor went unavailable,
  which on a system whose probes live on an ESP is a matter of when rather than
  whether. A test now checks every `self._x()` call in the coordinator against
  the methods that genuinely exist
- **The panel never updated in the browser.** It is served as a static file
  with no version in its URL, so the cached copy was kept indefinitely: the
  Water tab was in the code and not on screen, and the integration looked like
  it had silently failed to update. The URL now carries the manifest version
- **The panel is now translated.** Entity names follow Home Assistant's
  language, the panel was hardcoded English, and that gap was the real
  inconsistency — not the Dutch entity names, which are what appear on
  dashboards, in automations and in the logbook and should stay translated. So
  the panel was localised rather than the entities un-translated
- The pH and chlorine entity pickers were restricted to `domain="sensor"`,
  which hid every `input_number` helper from the list. A water test strip has
  no sensor of its own, so those readings are as often a manually-updated
  helper as a real sensor — the helper existed, the picker just would not show
  it. Both pickers now accept `sensor` and `input_number`
- **Pump outlet is now its own field**, separate from heat pump inlet. The
  first attempt at this fix only reworded the "Heat pump inlet temperature"
  label to mention "your pump outlet sensor" — but that assumed everyone's
  plumbing folds the two into one physical point, which is only true for a
  pool with nothing between the pump and the heat pump. A filter housing, a
  longer run, or any other layout has two real points to measure, and forcing
  them into one field was wrong for that installation regardless of how
  clearly it was labelled. There are four distinct optional fields now — pump
  inlet, pump outlet, heat pump inlet, heat pump outlet — and alias detection,
  already used for water/pump-inlet, was generalised to cover all of them: an
  installation where pump outlet and heat pump inlet genuinely are one probe
  configures the same entity in both fields, and the integration recognises
  that as one measurement rather than comparing a probe against itself

## [1.1.1] — Sorted, Not Underscored — 2026-08-04

### Fixed
- hassfest CI failed on two things at once: `manifest.json` keys were not
  sorted (domain, name, then alphabetical is their rule, not a suggestion), and
  the `gpm_` translation key ended in an underscore, which their validator
  rejects even though it matched the broader pattern this project's own checks
  used. The trailing underscore existed only to avoid colliding with an
  already-present `gpm` key in the same lookup table; both now simply share that
  key, since they mapped to the same conversion factor anyway
- Two tests added pinning hassfest's actual rules, not an approximation of them,
  since the approximation is exactly what let this through

## [1.1.0] — Where The Heat Goes — 2026-08-03

### Added
- **Live session figures.** Elapsed time, temperature gained, energy and cost
  while the session runs, with the achieved rise per hour set against the
  expected one. The recorder was already collecting all of it and keeping it to
  itself until the session finished, which is precisely when nobody needs it
- **Heat balance.** How much of the heat pump's output the pool actually keeps.
  On the installation this was built for: 0.427 °C/h in, 0.281 °C/h straight
  back out to the air, so two thirds is lost and a two degree rise takes
  fourteen hours instead of five. No amount of price optimisation changes that
  — a cover does, and the figure says so
- **Cover support.** Point the integration at a cover sensor, switch or
  input_boolean. Heat loss is then learned separately for covered and uncovered,
  because a cover typically halves it and one averaged number would be wrong in
  both states. An idle period during which the cover changed is discarded rather
  than attributed to either
- Live measurements on the dashboard's energy tab, and a session card plus heat
  balance card in the panel

## [1.0.1] — Slash-Free Slugs — 2026-08-03

### Fixed
- The flow unit selector stored values like `L/min` while Home Assistant
  translation keys cannot contain a slash or a superscript, so the labels never
  resolved. Both the stored slug (`l_min`) and the unit a sensor publishes
  (`L/min`) now convert, and an unrecognised unit refuses the reading instead of
  falling back to a factor of 1.0 — that fallback would have read 17 L/min as
  17 m³/h and put every figure derived from flow out by a factor of seventeen
  while nothing looked broken
- Corrected the `gmp` typo in the gallons-per-minute option

### Added
- Tests that cross-check every selector option against both translation files
  and against the conversion table, so a key can no longer drift from its label

## [1.0.0] — Knowledge, Not Storage — 2026-08-03

First stable release.

### Fixed
- **Two learned values were never used.** The measured COP curve and the heating
  rate were recorded after every session, stored, displayed — and read by no
  calculation. Planning ran on the datasheet instead. On the installation this
  was found on, that meant estimating 1h29 per degree where the measurements
  said 2h17: 54% optimistic, so heating started too late and the pool was cold at
  swimming time. Both are now used, in order of directness: measured heating rate
  first, then measured COP, then the datasheet
- A brief sensor outage no longer stops heating. An ESP reboot takes ten seconds
  and made every probe on it unavailable; the last reading is now carried
  forward for up to three minutes, which is far closer to the truth than no
  reading at all
- Probes that only matter while the heat pump runs no longer report staleness
  while it is off. "The heat pump outlet has not been reported for 37 minutes"
  was true and uninteresting: nothing was changing, so nothing was published
- The probe calibration check waits for the pump to have mixed the water.
  Standing water stratifies — warm at the surface, cool at the intake — and that
  is physics, not a miscalibrated probe

### Added
- **Learning tab that names the consumer.** Each learned value shows its
  confidence, how many sessions are behind it, what it falls back to, and which
  decision reads it
- A confidence gate on learned COP: three sessions in a temperature band before
  it is trusted for planning, because a wrong learned value is harder to spot
  than a wrong published one
- **Water chemistry.** Dosing calculated from your pool volume, a test interval
  that follows water temperature, and a dose log that learns how your pool
  actually responds. A `poolsmart.record_dose` service and a "tested just now"
  button close the loop
- Expanded diagnostics: the numbers behind each branch verdict, what would have
  to change for a branch to win, and how much of the day each branch spent in
  charge
- Heartbeat filters throughout the example ESPHome configuration, so silence
  from a probe means the probe really has stopped

### Notes
- For saturation indices, alkalinity and calcium hardness, use
  [ha-poolchem](https://github.com/joyfulhouse/ha-poolchem). PoolSmart
  deliberately does not reimplement it

## [0.13.2] — Eco Means Eco — 2026-08-03

### Added
- Regression tests covering Eco mode at an expensive moment. Eco tightens the
  ceiling to 70% of the configured limit, and a system reported heating at
  0.317/kWh against an effective ceiling of 0.14 — the fallback-plan bug fixed
  in 0.13.1. Eco is the mode people choose precisely to avoid that, so it is
  now pinned by tests rather than only by the fix

## [0.13.1] — No Forecast Is Not a Blank Cheque — 2026-08-02

### Fixed
- **A missing price forecast was licensing heating at any price.** Without a
  forecast the planner falls back to "heat on demand", and the ladder treated
  that fallback as a plan, which overrides the price limit. The result was
  heating at 0.338 against a ceiling of 0.200 while the reason line said in the
  same breath that no forecast was available. A fallback now means "heat when
  allowed", not "heat regardless" — only Boost, a negative price, the cheap
  period signal, or a genuine cheapest-slot plan override the limit

### Added
- More attribute shapes recognised when reading a price forecast, and a warning
  naming the list attributes actually present when none is recognised. The
  difference between "no price sensor" and "a shape I do not know" is the
  difference between a setup mistake and a gap in that list
- The status sensor reports whether price optimisation is active and how many
  forecast intervals were read

## [0.13.0] — Stop Chasing the Datasheet — 2026-08-02

### Changed
- Flow is judged by the temperature rise across the heat pump rather than
  against a datasheet minimum. The rise measures directly what a flow figure
  stands for, and a genuine problem shows up as a *high* rise, not a low flow
  number. Measured on a real installation: raising flow 25% lowered delta-T 19%
  and left thermal output unchanged, which is what an installation that was never
  flow-limited looks like
- The AI review is told this explicitly and instructed not to recommend chasing
  a datasheet figure. It was previously advising owners to reach a number their
  plumbing cannot produce

### Added
- `sensor.<name>_flow_adequacy`, reporting healthy, marginal or starved with the
  numbers behind the verdict. Visible when the answer is "fine", not only when
  something is wrong
- A "verified for this installation" setting that silences the datasheet warning
  once the owner has confirmed the system moves heat properly below it

## [0.12.6] — The Fifth Probe Earns Its Keep — 2026-08-01

### Added
- Optional pump inlet probe, used as a calibration cross-check. It measures the
  same water as the pool probe, so a disagreement beyond the tolerance means a
  probe needs calibrating, the pool is stratified, or a probe is not in the
  water. Nothing else in the system can notice a reading that is simply wrong
- Configurable tolerance for that check, defaulting to 0.6 °C, a little above
  the accuracy of a DS18B20

## [0.12.5] — Do Not Claim What You Cannot Prove — 2026-08-01

### Fixed
- The system claimed "it is the cheapest time still available" while running at
  0.248 on a day whose low was 0.13. Without a price forecast the planner falls
  back to heating on demand, and that fallback was being described as a chosen
  cheap moment. It now says no usable forecast is available and suggests
  checking the price sensor. A claim that cannot be backed is worse than no claim

### Added
- Optional cheap-price period signal: an on/off sensor from a dynamic tariff
  integration saying whether now is a good moment. It outranks the fixed price
  ceiling, which cannot tell a cheap hour from an expensive day — with a limit
  of 0.20 and a day whose cheapest hour is 0.22, nothing would ever heat
- The plan records the lowest and highest prices it actually saw, so a claim
  about cheapness can be checked rather than taken on trust

## [0.12.4] — The Sentence That Read Backwards — 2026-08-01

### Fixed
- "Heating because price 0.248/kWh exceeds the limit of 0.200" read as though
  the logic were inverted. The heating was justified by the plan; the price
  sentence was the rejection reason being printed as though it were the
  justification. A planned interval over the limit now says that it is part of
  the plan and the cheapest time still available

### Added
- The plan records when it had to exceed the price limit to meet a deadline, and
  says so in its reason. Arriving cold at swimming time is a worse failure than
  paying a couple of cents over a self-imposed ceiling, but it should not happen
  silently either way

## [0.12.3] — The Board Measures, Nothing More — 2026-08-01

### Changed
- The example ESPHome configuration no longer calculates delta-T, thermal power
  or COP. Those figures only existed for people running ESPHome, and a
  calibration offset changed on one side left two numbers disagreeing. The
  integration already computes all three from whatever sensors it is given
- Temperature probes are read internally and published through a template that
  applies a calibration offset, so there is one temperature per probe rather
  than a raw and a corrected one

### Added
- Calibration offsets as number entities on the board: adjustable without
  reflashing, and they survive a restart
- A running pulse total, so the flow meter can be calibrated with a bucket
- `docs/SENSORS.md`, covering probe calibration, flow calibration and which
  sensor maps to which field

### Fixed
- The example had two different flow divisors applied in two places,
  disagreeing by a factor of two and a half. There is now one, with the
  arithmetic behind the datasheet figure written out and a sanity check for
  spotting a wrong one

## [0.12.2] — Forty-Seven Minutes, Not 0.78 Hours — 2026-08-01

### Changed
- Durations read as hours and minutes instead of decimal hours. "0.78 h" is a
  number you have to convert before it means anything; "47 min" is not
- Every duration sensor carries a `readable` attribute, so a custom card does
  not have to repeat the arithmetic
- The filtration card on the Energy tab shows the window pressure warning when
  the daily requirement fills nearly the whole window

## [0.12.1] — Let the Compressor Breathe — 2026-08-01

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

## [0.12.0] — Off Means Off — 2026-08-01

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

## [0.11.0] — Why Is It Not Heating? — 2026-08-01

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

## [0.10.0] — The Pump Was Running Anyway — 2026-08-01

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

## [0.9.0] — Measure It, Do Not Assume It — 2026-08-01

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

## [0.8.0] — First Contact With Water — 2026-08-01

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

[1.2.3]: https://github.com/rickertie/Poolsmart/releases/tag/v1.2.3
[1.2.2]: https://github.com/rickertie/Poolsmart/releases/tag/v1.2.2
[1.2.1]: https://github.com/rickertie/Poolsmart/releases/tag/v1.2.1
[1.2.0]: https://github.com/rickertie/Poolsmart/releases/tag/v1.2.0
[1.1.2]: https://github.com/rickertie/Poolsmart/releases/tag/v1.1.2
[1.1.1]: https://github.com/rickertie/Poolsmart/releases/tag/v1.1.1
[1.1.0]: https://github.com/rickertie/Poolsmart/releases/tag/v1.1.0
[1.0.1]: https://github.com/rickertie/Poolsmart/releases/tag/v1.0.1
[1.0.0]: https://github.com/rickertie/Poolsmart/releases/tag/v1.0.0
[0.13.2]: https://github.com/rickertie/Poolsmart/releases/tag/v0.13.2
[0.13.1]: https://github.com/rickertie/Poolsmart/releases/tag/v0.13.1
[0.13.0]: https://github.com/rickertie/Poolsmart/releases/tag/v0.13.0
[0.12.6]: https://github.com/rickertie/Poolsmart/releases/tag/v0.12.6
[0.12.5]: https://github.com/rickertie/Poolsmart/releases/tag/v0.12.5
[0.12.4]: https://github.com/rickertie/Poolsmart/releases/tag/v0.12.4
[0.12.3]: https://github.com/rickertie/Poolsmart/releases/tag/v0.12.3
[0.12.2]: https://github.com/rickertie/Poolsmart/releases/tag/v0.12.2
[0.12.1]: https://github.com/rickertie/Poolsmart/releases/tag/v0.12.1
[0.12.0]: https://github.com/rickertie/Poolsmart/releases/tag/v0.12.0
[0.11.0]: https://github.com/rickertie/Poolsmart/releases/tag/v0.11.0
[0.10.0]: https://github.com/rickertie/Poolsmart/releases/tag/v0.10.0
[0.9.0]: https://github.com/rickertie/Poolsmart/releases/tag/v0.9.0
[0.8.0]: https://github.com/rickertie/Poolsmart/releases/tag/v0.8.0
