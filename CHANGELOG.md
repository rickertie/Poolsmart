[? Back to README](index.md) • **Changelog**

---

# Changelog

All notable changes to PoolSmart. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/).

Every release gets a title naming what it was actually about. Read from the
bottom up, they tell the story of a system slowly learning to stop believing its
own paperwork.

## [1.11.0] — A Dashboard Tile, a Hard Limit, and a Model That Remembers

### Fixed

- **Notification action buttons could silently vanish.** `notify.py` built
  the `data.actions`/`tag` payload for every event that carries buttons, but
  the entity-based `notify.send_message` dispatch path — what current-
  generation Companion app registrations use — never forwarded it, unlike
  the legacy per-device service call. Addresses
  [#19](https://github.com/rickertie/Poolsmart/issues/19): buttons now reach
  every target either path can reach. (On iOS specifically, a long-press or
  swipe to reveal them is separate, standard platform behaviour, now
  documented alongside this fix.)

### Added

- **Swim time, as a dashboard tile.** Addresses
  [#17](https://github.com/rickertie/Poolsmart/issues/17): an
  `input_datetime` helper and an `input_boolean` "not swimming today"
  helper, checked ahead of the static swim-time fields under **When to
  heat** and falling back to them cleanly when unset, so anyone in the
  house can set today's time from the existing Lovelace dashboard instead
  of opening this integration's options flow.
- **`weather_entity` now actually is the documented outdoor-temperature
  fallback.** Addresses [#16](https://github.com/rickertie/Poolsmart/issues/16):
  the docs and both translation files promised this since before it was
  ever wired up. A pool with only a weather entity mapped stops silently
  losing its operating-envelope check and frost protection.
- **A demand/power limiter.** Addresses
  [#13](https://github.com/rickertie/Poolsmart/issues/13): map a
  smart-meter or energy-dashboard sensor and set a house-power cap under
  **When to heat**, and heating pauses whenever current draw would exceed
  it — a ceiling independent of price or solar surplus, respected even by
  Boost, since it exists to protect a hard electrical or contract limit
  rather than to optimise cost. Pauses an already-running session just as
  readily as it blocks a new one, with a notification on both the pause and
  the resume.
- **The AI advisor now follows up on what it suggested.** Addresses
  [#10](https://github.com/rickertie/Poolsmart/issues/10): accepting a
  suggestion snapshots a few current metrics; a week later the same
  snapshot is compared and turned into a plain-language outcome, shown in
  the panel and fed into the next review — so a suggestion that did not
  help is visible instead of quietly repeated. Still suggests only; nothing
  is ever applied automatically.

## [1.10.0] — Trusting the Whole File, and Watching the Sky

### Fixed

- **A single bad timestamp in the storage file could silently wipe
  sessions, doses and mode/target_temp while learned values survived.**
  `PoolStore.async_load` parsed every field inside one `try`, so hitting a
  malformed value partway through left later fields (Sessions/Doses, the
  active mode) stuck at their fresh defaults while earlier ones (heat
  loss, COP, heating rate) kept whatever they had already been assigned —
  the log even claimed a full reset when it was only ever a partial one.
  Addresses [#20](https://github.com/rickertie/Poolsmart/issues/20): the
  Storage card no longer disagrees with the learned counters above it.
  Addresses [#18](https://github.com/rickertie/Poolsmart/issues/18): each
  field group now parses and commits independently, so one corrupt value
  resets only itself and says so. Setup now also warns when an orphaned
  storage file from a removed-and-re-added install is sitting unread, since
  that is a second, distinct way options and history can look lost after
  an update.

### Added

- **The dose log finally learns.** `docs/CHEMISTRY.MD` promised it since
  before 1.0; the missing piece was that a dose's *expected* effect was
  never actually recorded, so the correction factor had nothing to learn
  from. Addresses [#9](https://github.com/rickertie/Poolsmart/issues/9):
  each dose now carries what the uncorrected formula predicted for the
  amount actually administered, and once the next test closes it off, the
  result blends into a persisted per-pool pH/chlorine correction — capped
  and outlier-guarded, the same update rule heating learning already uses
  for heat loss and COP. Shows up on the Learning tab with a confidence
  label and its own reset, and starts scaling every dose recommendation
  once two dose-then-test pairs exist.
- **PoolSmart notices rain, with an existing weather entity.** Addresses
  [#7](https://github.com/rickertie/Poolsmart/issues/7): the water tab
  gets a "test soon" nudge and a shortened test interval for twelve hours
  after rain was last observed; an idle period rained on during it is
  excluded from heat-loss learning the same way a cover change already
  voids one, instead of teaching the baseline a number that belonged to
  the weather; and the solar-collector advice — wired up as a sensor for
  the first time, having existed unused since the collector-margin setting
  was added — now stops recommending the valve be opened while it's
  raining on it.

## [1.9.2] — Rooms of Its Own, and a Look at Tomorrow

### Fixed

- **The options flow's "Sensoren en schakelaars" step was one flat list of
  everything.** Pump and heat pump wiring, the eight water-chemistry sensors,
  and every weather/price/solar entity all sat under one heading, with the
  chemistry sensors duplicated in spirit against the product questions on a
  completely different screen. The pool's own water-temperature sensor lived
  there too, apart from every other pool figure. Addresses
  [#15](https://github.com/rickertie/Poolsmart/issues/15): `water_temp_sensor`
  moved to **Zwembad en pomp**, the chemistry sensors moved next to the
  product questions under **Waterbehandeling**, and weather, price and solar
  entities got a new **Weer en prijs** step of their own — "Sensoren en
  schakelaars" is hardware wiring now, and nothing else. Clearing an optional
  entity field back to blank, which silently did nothing, now actually clears
  it.

### Added

- **The heating plan now looks at tomorrow's forecast, not just today's air.**
  The learned heat-loss figure used to be applied unscaled regardless of what
  was coming: a cold front started the plan too late, a warm spell over-heated
  for no reason. Addresses
  [#8](https://github.com/rickertie/Poolsmart/issues/8): with a weather entity
  mapped under **Weer en prijs**, the learned figure is stretched or shrunk by
  how the forecast air temperature ahead compares to today's, bounded so a
  single forecast reading can move it down to 60% or up to 2.5x — asymmetric
  on purpose, since starting a plan too late is the failure that actually
  shows up as a cold pool at swim time. Both Maintenance mode's run-time
  estimate and Seasonal mode's days-to-ready projection pick this up
  automatically, including the thermal-equilibrium warning firing ahead of a
  forecast cold snap rather than only once it arrives.

## [1.9.1] — The Sun Sensor Nobody Could Actually Configure

v1.9.0's solar-gain-during-idle feature had a sensor pathway that could never
switch on: `_irradiance()` needs a configured peak wattage to scale a solar
power sensor into W/m², and that setting existed only as a constant, with no
field anywhere in the config flow. Mapping "Current solar production" alone
could never produce an irradiance estimate -- the feature always ran on the
conservative time-of-day fallback, however good the sensor was.

### Fixed

- **The missing "Solar panel peak power" field**, now under **When to
  heat**, so the solar-power-sensor pathway 1.9.0 shipped can actually be
  configured instead of silently always falling back to the estimate.

### Added

- **A direct irradiance sensor.** A new "Solar irradiance" field accepts any
  sensor already reading in W/m² -- a weather station's pyranometer, a
  KNMI-style solar-radiation entity, and so on -- and is preferred over the
  solar-power estimate wherever both are mapped, since it measures the sky
  rather than a proxy for it. This also means a pool with no solar panels of
  its own can now benefit from the same learning, using outdoor sunlight
  instead.

## [1.9.0] — A Sunny Afternoon Finally Teaches the Model Something

`heat_loss_from_idle` discarded any idle period in which the water warmed up,
on the reasoning that warming meant sunshine, not heat loss. That reasoning is
right, but its consequence was that heat loss could only ever be learned at
night or under cloud -- exactly the hours a pool is idle *and* sunny were
thrown away, which is most of them. Addresses
[#12](https://github.com/rickertie/Poolsmart/issues/12).

### Added

- **Solar gain is modelled during idle periods, not just discarded.** Where a
  solar-power sensor is mapped, its measured average over the idle period is
  used to work out how much of the observed warming was the sun; the heat
  loss the sun was masking still comes through once that is subtracted out.
  Without a sensor, a conservative time-of-day estimate stands in instead --
  low enough that it can only recover mildly-sunny periods, never generous
  enough to invent heat loss that never happened. A strongly sunny period with
  no solar sensor mapped is still set aside, exactly as before: this unlocks
  more of the data that was always there, without loosening the honesty rules
  that keep a wrong measurement from teaching the model anything.
- Idle-period tracking now samples irradiance on every tick while idle, the
  same way a heating session already does, rather than only at the moment the
  period is judged.

## [1.8.0] — A Season Doesn't Fit in 60 Sessions

The session log holds 60 entries and the daily runtime summaries hold 90 days;
past those caps the oldest raw data was simply dropped. That is fine for
noticing a sudden fault, but it made a slow drift over months — a heat pump's
COP sagging, a filter fouling gradually, one season behaving differently from
the last — invisible by the time enough sessions had rolled off the end to
notice it. Addresses [#11](https://github.com/rickertie/Poolsmart/issues/11).

### Added

- **Monthly trend retention.** A new, unbounded second tier keeps one row per
  calendar month — running mean/min/max for heating rate, heat loss (covered
  and uncovered), and COP per outdoor-temperature band, plus the runtime,
  energy, and cost the daily summaries already tracked. None of it is ever
  dropped by the session or daily caps, so it survives them indefinitely.
- **Trend detection.** Each metric's monthly means are fitted with a simple
  regression to say whether it has been improving, degrading, or holding
  steady over the last several months, and by roughly how much per month.
- **Long-term trends card.** The Learning tab shows a table of recent months
  alongside a trend badge for anything actually moving, so a drift shows up on
  the panel long before it would otherwise be noticed.
- **The AI advisor now sees trends too.** A clear multi-month drift is passed
  to the weekly review so it can be called out in plain language — "COP has
  been falling roughly 4%/month since June" — instead of being buried in 20
  individual sessions.

## [1.7.3] — Settings Stopped Racing Themselves, and the COP Window Is Now Yours to Set

### Fixed

- **Saving several settings in one visit could permanently wipe the session
  log.** The options flow saves each section immediately and returns to its
  menu instead of closing, so filling in a few values in one sitting fires
  Home Assistant's update listener -- and therefore a full unload/setup cycle
  -- once per save, each as its own background task. Nothing serialised those
  against each other: two saves made close together could each start
  reloading the integration while the other was still mid-flight, and
  whichever coordinator finished setting up last kept running in the
  background and eventually persisted its own, older session log over the
  good one -- discarding everything logged in between. `async_reload_entry`
  now holds a per-entry lock, so reloads for the same pool always run one at
  a time.

### Added

- **The COP plausibility window is now a setting.** `cop_clamp_min` and
  `cop_clamp_max` have driven the COP curve and the automatic session verdict
  since early on, but neither config flow ever asked for them, so every
  installation was stuck with the 3.0-6.0 default regardless of what its heat
  pump actually does. A heat pump running outside that band had every
  session's COP measurement rejected by the automatic verdict -- left sitting
  as "auto" and excluded from learning -- until someone noticed and set it to
  Included by hand. **Settings -> Advanced** now has "Lowest/highest
  plausible COP" fields. This only affects sessions logged from here on;
  sessions already in the log keep the verdict they were given at the time,
  so an existing rejection still needs a manual review to be included.

## [1.7.2] — A Restart Loses Less, and Import Isn't a Blank Field Anymore

### Fixed

- **A restart used to discard an entire running filtration interval, not just
  the gap.** `_close_open_interval` closed a dangling open interval at its own
  `start`, crediting it nothing at all -- so a pump that had been running for
  hours before a routine Home Assistant restart lost every one of those
  hours, not "at worst one tick" as it was meant to. Saves now record a
  `synced_at` timestamp; a restart closes a dangling interval there instead,
  so only the genuinely unsaved tail (at most one save interval) is lost.
  Files from before this change, or a `synced_at` that is somehow older than
  the interval itself, fall back to the original conservative behaviour
  unchanged.

### Changed

- **Import and Replace default to this pool's own backup.** The panel's
  Import and Advanced-replace path fields are now pre-filled with this pool's
  automatic safety-net snapshot (`poolsmart_learning_backup.<entry id>.json`)
  instead of an empty field, so pressing the button no longer just says
  "Enter a file path to import."

## [1.7.1] — Sessions Stopped Teaching the Model

**Regression in 1.7.0, fixed here.** The new safety-net snapshot
(`_write_learning_snapshot`, added in 1.6.0) was called before the learned-value
update in `_finish_session`, with nothing catching a failure in it. Any
exception there aborted the rest of the function, so a session was still
logged to the Sessions tab but never actually updated the heating rate, COP
curve, or session count -- every finished session since upgrading to 1.6.0
silently taught the model nothing, without any error visible in the panel.

### Fixed

- **Learning silently stopped after 1.6.0.** The snapshot write now runs last
  and can never take the learned-value update down with it, on top of its own
  existing internal guard.

### Recovering sessions caught by this

No data was lost -- every session is still in the log with its measurements
intact, just never applied. After upgrading, press **Process now** on the
Learning tab (or call `poolsmart.rebuild_learning`) once to recompute the
heating rate and COP curve from the full session log in one go.

## [1.7.0] — Storage Stats, Maintenance & Bulk Export/Import

Rounds out 1.6.0's session review with the tools to act on history in bulk,
inspired by how WashData handles its own training data: reprocess after a
batch of changes, see what's actually on disk, and export or import exactly
the parts you want instead of all-or-nothing.

### Added

- **Storage stats.** The Learning tab now shows session/dose/decision counts,
  how many near-misses are tracked, and the on-disk file size — refreshed on
  request, since the size check is a disk read.
- **Maintenance actions.** `poolsmart.rebuild_learning` reprocesses the whole
  session log in one go (same effect as reviewing a session, applied to
  everything at once). `poolsmart.clear_debug_log` empties the decision log
  and near-miss tally — diagnostics only, always safe. `poolsmart.clear_all_history`
  permanently deletes every learned value, session, dose, and log entry;
  requires an explicit `confirm: true` and the panel asks twice before
  sending it.
- **Selective export and advanced replace.** `poolsmart.export_learning`
  takes an optional `sections` field to export only some of learned
  values/session log/dose log/last water test. New `poolsmart.replace_learning`
  overwrites instead of merging — for restoring a backup exactly as it was,
  not routine use — also `sections`-aware and `confirm`-gated.

### Fixed

- **Export could crash on real data.** `export_payload` handed the session
  and dose logs to the JSON encoder as-is; both are `deque`s, which the
  standard encoder cannot serialize. Never triggered by the test suite
  because nothing exercised it with real, non-empty logs. Exports now convert
  them explicitly.
- **A history import missing "learned" was silently dropped.** `adopt()`
  bailed out before looking at the session log, dose log, or last water test
  if the import had no learned values — which a sections-only export now
  legitimately can. It now processes each part independently.

## [1.6.0] — Session Review & the Reload That Wasn't a Restart

A dashboard tweak was reloading the whole integration and quietly discarding
whatever the pool was in the middle of doing. Fixed at the source, and turned
the same investigation into a way to correct what the learning model
remembers.

### Added

- **Session review.** Each finished heating session can be confirmed as
  Auto/Include/Exclude from the **Sessions** tab, or via the new
  `poolsmart.set_session_review` service. A "worth a look" flag surfaces
  sessions the automatic verdict likely got wrong — long enough to hold real
  data but rejected outright, or accepted despite a fault during it — without
  ever second-guessing a verdict it agrees with. A correction rebuilds the
  heating rate and COP curve from the whole session log immediately, instead
  of only shaping sessions from that point on.
- **Automatic learning backups.** A rolling `poolsmart_learning_backup.<entry
  id>.json` is now written after every finished session, so recovering
  learned history no longer depends on someone having run
  `poolsmart.export_learning` beforehand.

### Changed

- **Decision ladder order.** Free electricity and Heating now sit above
  Filtration deadline, so a free or already-planned heating opportunity gets
  first refusal. A critical deadline still wins outright whenever heating
  doesn't apply, since the deadline branch is reached right after.

### Fixed

- **Reload wiped in-progress state.** Changing **Max price** or **Solar
  threshold** from the dashboard reloaded the entire integration. That closed
  the currently-running filtration interval at its own start — crediting it
  nothing and making filtration appear to restart from scratch — and silently
  dropped whatever heating session was in progress, emptying the Sessions
  tab. Those two entities now update live instead of triggering a reload; a
  genuine restart still keeps its existing, deliberately conservative
  handling of a dangling interval. The in-progress session itself is now
  persisted and restored across a real reload, too.

## [1.5.4] — Version Sync

Keeps the published version in sync with the release tag so HACS displays the
same version as the GitHub release. No functional changes.

## [1.5.3] — Service Handlers & Multi-Pool Cleanup

Service handlers no longer overwrite or mix data across multiple pools, and the
pool session Lovelace card got a UI refresh.

### Fixed

- **Service calls now target the right pool.** Fixed handlers overwriting or
  mixing data across multiple pools
- **Recovery and store cleanup.** Stale state no longer bleeds between entries

### Changed

- **Pool session card UI.** Enhanced the pool session Lovelace card with a
  cleaner layout

## [1.5.2] — Resilience Fixes

Hardened storage and test tooling after issues reported by users.

### Fixed

- **Missing version key on load.** A stored state without its version key no
  longer crashes the integration; it is logged, reset, and rebuilt
- **`select.py` shadowing.** Avoided a circular import caused by `select`
  shadowing in `load()`

### Changed

- **Setup wizard copy.** Improved the "pool kind" description in Dutch and
  English — an uninsulated inflatable loses heat several times faster than a
  built-in pool, and the real figure is measured within days
- **Test suite.** UTF-8 handling and HA stubs hardened for reliable CI runs

## [1.5.1] — Setup Wizard Clarity

User-reported UI improvements to the installation wizard (Dutch and English).

### Changed

- **Shorter step descriptions.** Pool type, pump, heating, and optional entities
  descriptions trimmed to the essential — no more paragraphs where a sentence
  does the job
- **Pool type options show their meaning.** Each construction type (inflatable,
  frame, above ground, in ground) now carries a one-line description in the
  dropdown itself, instead of one unreadable block at the bottom
- **Optional entities menu labels.** The four sub-steps (Core sensors, Water
  chemistry, Solar and price, Done) now show what each contains, instead of
  bare technical names
- **Optional sub-step field labels and help.** Core sensors, Water chemistry, and
  Solar and price steps now have proper human-readable labels and per-field
  descriptions — no more raw `_` field names with no explanation
- **"Brochureminimum geverifieerd" label clarified.** Renamed to "Minimaal debiet
  geverifieerd op deze installatie" / "Minimum flow verified for this
  installation"; description shortened to the practical meaning
- **Summary step clarified.** Now tells the user to click 'Save' to activate and
  that changes can be made later via Configure
- **Optional finish step clarified.** Now explains that everything is set up and
  leads to the review step

## [1.5.0] — Resilience, Performance & User Control

Based on comprehensive code review. See
[docs/.AI_RECOMMENDATIONS/CODE_REVIEW_RECOMMENDATIONS.md](.AI_RECOMMENDATIONS/CODE_REVIEW_RECOMMENDATIONS.md)
for the full analysis.

### Added

- **Config entry migration framework.** Added `async_migrate_entry` to
  `__init__.py` with stepwise version handling, so future ConfigFlow version
  upgrades no longer break existing installations
- **Atomic state writes.** `store.py` now uses a temp-file-then-rename pattern
  via `_async_save_atomic`, preventing JSON corruption on crash mid-write
- **Switch state verification.** The coordinator now tracks desired switch states
  and verifies actual states on subsequent ticks. After 3 consecutive
  mismatches (90s), raises `pump_switch_unresponsive` or
  `heat_pump_switch_unresponsive` fault
- **Sensor value range validation.** Implausible readings (e.g., water temp
  outside -5°C to 55°C) are now rejected at ingestion in `_read()` and trigger
  bridging from the last good value
- **Import value range validation.** `validate_import` in `recovery.py` now
  rejects exports with physically impossible learned values (heat loss >2 °C/h,
  COP outside 1–10, etc.)
- **NearMissLog persistence.** Near-miss tallies are now persisted in the store
  and survive restarts
- **Daily runtime summaries.** Day roll now captures a compact summary
  (runtime, energy, cost) before clearing intervals. Capped at 90 days,
  accessible via `store.daily_summary()`
- **Internal data schema versioning.** Store now includes `data_version` field
  with `_migrate_data()` method for future schema migrations
- **AI privacy tiers.** Added configurable `privacy_level` (minimal/standard/full)
  to control what operational data is shared with the external LLM advisor
- **WebSocket management API.** Added `poolsmart/set_mode`,
  `poolsmart/set_target`, and `poolsmart/reset_learning` commands for direct
  panel control without service calls
- **DAILY_SUMMARY_MAX_DAYS constant.** Controls how many daily summaries are
  retained (default: 90)

### Changed

- **Chemistry caching.** `water_chemistry` property in coordinator now caches
  its result per-tick, invalidated at tick start and on dose/water-test events.
  Eliminates redundant rebuilds when accessed by multiple sensors
- **Runtime tracking O(1).** `runtime_hours()` now uses `_closed_hours` running
  total instead of iterating all intervals, reducing from O(n) to O(1)
- **Learning value decay.** `capped_update` in `core/learning.py` now applies
  age-based decay (half-life: 90 days), allowing faster adaptation when learned
  values are outdated
- **COP confidence threshold.** Increased from 3 to 5 sessions per bucket before
  trusting a measured COP value for planning
- **Deque-based log rotation.** Decision, session, and dose logs now use
  `collections.deque` with `maxlen` for O(1) appends and automatic bounds
  management
- **Config flow deduplication.** Extracted `_core_environmental_fields()` and
  `_chemistry_fields()` helpers to eliminate schema duplication between setup
  wizard and options flow

### Fixed

- **Block window unpacking crash.** Added length validation before unpacking
  time pairs in `_build_state()`, preventing `ValueError` on malformed config
- **Service unit selector mismatch.** `services.yaml` now offers all units
  accepted by the handler (ml, g, l, kg)
- **Duplicate panel JS removed.** Removed root-level `poolsmart-panel.js`
  (outdated 16 KB version); active file remains `www/poolsmart-panel.js` (47 KB)
- **Panel render error boundary.** `_renderTab` now catches render errors and
  displays a localized error banner instead of breaking the entire panel

### Security

- **WebSocket admin protection.** Existing `ws_clear_log` already required admin;
  new management commands (`set_mode`, `set_target`, `reset_learning`) follow
  the same pattern

---

## [1.4.0] — No More "Submit And Pray"

### Added
- **Setup now says where you are.** A progress indicator shows "Step X of Y" on
  every wizard screen, so you know how much is left before you commit. A final
  review step lets you check your selections before the entry is created
- **Optional sensors are grouped by purpose.** The single overwhelming screen of
  twenty-odd fields is replaced by four focused menus: core sensors, water
  chemistry, solar, and a finish step. Each asks only about hardware you actually
  have, and every field may still be left blank
- **Notifications can reach more than one person.** Each event type now accepts
  multiple targets: select everyone who should hear about a fault, and they all
  get the message
- **Skeleton loading in the management panel.** While data is being fetched the
  panel now shows shimmer placeholders instead of a blank page, so it is clear
  something is happening
- **Keyboard navigation in the panel.** Tabs can be reached with arrow keys,
  Home and End, following the WAI-ARIA tablist pattern. Focus is visible, managed
  on tab switch, and never trapped
- **Accessible error states.** When the snapshot cannot be loaded the panel shows
  a clear banner with a retry button, announced to screen readers, rather than a
  small red line of text
- **Loading and empty states on the dashboards.** The Lovelace views now handle
  "unknown" entities gracefully: a spinner replaces the temperature readout, and
  a placeholder card says data is loading instead of showing a broken template
- **Improved dashboards** with better responsive layout, consistent status colors,
  and conditional sections that appear only when relevant
- **Shorter notification button labels.** "Heat now anyway" is now "Heat now",
  "One degree warmer" is "+1° warmer" -- mobile notification buttons truncate
  long labels, so they now fit and remain readable

### Changed
- **Going back no longer leaves stale data behind.** Changing the heating source or
  pool construction in the first step now clears all downstream answers that no
  longer apply, so you never end up with a heat pump configuration for a pool with
  no heating
- **Action buttons in the panel** show a busy state while their service call is in
  flight, so you know your tap was registered even before the data refreshes
- **Notification descriptions updated** to explain that multiple recipients are
  now supported per event type

### Fixed
- **"Entity is neither a valid entity ID nor a valid UUID" when saving
  notifications.** The notify target picker now accepts multiple entity selections
  and stores them as a list, so a valid selection is no longer rejected
- **The setup wizard showed no progress.** Seven sequential forms with no
  indication of how many steps remain, which made the process feel longer than it
  was
- **Optional sensors were a wall of fields.** Presenting twenty fields at once,
  many of them technical, overwhelmed users into skipping the step entirely
- **A heat pump configuration survived removing the heat pump.** Going back and
  changing the heating source left the old heating data in place, producing a
  configuration that contradicted itself
- **The panel was silent during loads.** No loading state, no error feedback
  beyond a single line of red text -- just nothing, which reads as broken

### Added
- **Setup now says where you are.** A progress indicator shows "Step X of Y" on
  every wizard screen, so you know how much is left before you commit. A final
  review step lets you check your selections before the entry is created
- **Optional sensors are grouped by purpose.** The single overwhelming screen of
  twenty-odd fields is replaced by four focused menus: core sensors, water
  chemistry, solar, and a finish step. Each asks only about hardware you actually
  have, and every field may still be left blank
- **Skeleton loading in the management panel.** While data is being fetched the
  panel now shows shimmer placeholders instead of a blank page, so it is clear
  something is happening
- **Keyboard navigation in the panel.** Tabs can be reached with arrow keys,
  Home and End, following the WAI-ARIA tablist pattern. Focus is visible, managed
  on tab switch, and never trapped
- **Accessible error states.** When the snapshot cannot be loaded the panel shows
  a clear banner with a retry button, announced to screen readers, rather than a
  small red line of text
- **Loading and empty states on the dashboards.** The Lovelace views now handle
  "unknown" entities gracefully: a spinner replaces the temperature readout, and
  a placeholder card says data is loading instead of showing a broken template
- **Improved dashboards** with better responsive layout, consistent status colors,
  and conditional sections that appear only when relevant

### Changed
- **Going back no longer leaves stale data behind.** Changing the heating source or
  pool construction in the first step now clears all downstream answers that no
  longer apply, so you never end up with a heat pump configuration for a pool with
  no heating
- **The options "Sensors and switches" screen** is unchanged in what it offers but
  now groups fields the same way the setup wizard does, for consistency
- **Action buttons in the panel** show a busy state while their service call is in
  flight, so you know your tap was registered even before the data refreshes

### Fixed
- **The setup wizard showed no progress.** Seven sequential forms with no
  indication of how many steps remain, which made the process feel longer than it
  was
- **Optional sensors were a wall of fields.** Presenting twenty fields at once,
  many of them technical, overwhelmed users into skipping the step entirely
- **A heat pump configuration survived removing the heat pump.** Going back and
  changing the heating source left the old heating data in place, producing a
  configuration that contradicted itself
- **The panel was silent during loads.** No loading state, no error feedback
  beyond a single line of red text -- just nothing, which reads as broken

### Fixed
- **A heat pump existed at "No heating".** The heating source decided what was
  required but stopped there: the setup wizard's optional step and the options
  "Sensors and switches" screen still asked for the heat pump's inlet, outlet
  and power sensors — and for a collector sensor — even when there was no heat
  pump or no collector to hang them on. Those now follow the heating source
  everywhere, like the heat pump switch already did, so picking "none" or a
  solar collector stops the questions about hardware that is not installed
- **The heating step was a screen of nothing.** A pool without heating was
  walked through a "Heating appliance" step that asked no questions, which made
  it look as if something was missing; the step is now skipped for such a pool.
  The step's translation also carried words for fields that step never asks, so
  it showed raw keys and no title. Both languages now describe exactly what the
  step asks, including the thermostat recommendation filled in with the pool's
  own numbers

## [1.3.2] — One Answer Per Import — 2026-08-10

### Fixed
- **The test suite passed locally and failed on CI**, for a reason that took a
  while to see. This machine has no Home Assistant, so the stand-in modules in
  `tests/ha_stubs.py` were always used; the runner installs the real package, so
  the two collided. The failure surfaced as a circular import inside `asyncio`,
  nowhere near the cause. The stubs now stand aside entirely when the real
  package is importable, and never replace a module already present
- `unittest.mock` is imported only when stubbing actually happens, so a runner
  with the real package does not drag it in for nothing

### Changed
- CI runs the suite **twice**: once with no dependencies at all, and again
  against the real Home Assistant. Only one of those paths was ever being
  checked, which is exactly how the collision went unnoticed
- `tests/requirements-test.txt` documents that everything in it is optional

## [1.3.1] — Words For Every Field — 2026-08-08

### Fixed
- **Two settings screens were blank and one showed raw keys.** Reworking the
  menu moved fields between steps and left their words behind. The tests checked
  that dropdown *options* were translated and never that the steps holding them
  were, so nothing caught it. Four new tests now cross-check every step and every
  field against both languages
- **Advanced settings crashed**, referring to a learning setting that had a
  default in the model but was never registered as a config key
- **Reading the manifest blocked the event loop.** The cache-busting version
  added in 1.1.2 read a file from disk during setup, which Home Assistant reports
  as a stability problem. The version was already in memory a function call away
- **A solar collector no longer demands a heat pump switch.** Required entities
  follow the heating source: a manual three-way valve has nothing to switch, and
  a pool with no heating still benefits from filtration and water chemistry
- **Sessions were being thrown away for succeeding.** A stable heating session
  holds delta-T almost constant, so the probes either side of the heat pump stop
  publishing — and after fifteen minutes were called stale. The better the
  heating ran, the more certainly the session was discarded
- **Sunshine counts.** The plausibility ceiling on a learned heating rate
  ignored solar gain, so two real sessions of 0.99 and 0.87 °C/h were rejected as
  impossible. Six square metres of water under an August sun takes in two to
  three kilowatts, comparable to the heat pump itself. The ceiling now allows for
  it, measured where a solar sensor exists and generously assumed in daylight
  where none does

### Changed
- **Each measurement is judged on its own.** One fault used to discard a whole
  session, and seven out of seven were lost on a real installation — several
  holding perfectly good evidence of how fast the pool warms, ruined by a probe
  that spoils the efficiency figure and says nothing about the temperature rise.
  The session list now reports what a session taught, not only why it fell short

### Added
- **A simple dashboard** for everyone who did not set this up: warm enough, water
  fine, when can I swim. Nothing on it changes a setting
- **A price verdict** in words, judged against today's own range rather than a
  fixed ceiling
- Every field in setup now carries a short explanation, including what actually
  distinguishes a frame pool from an above-ground one

## [1.3.0] — Not Everyone Has a Heat Pump — 2026-08-06

### Added
- **Heating source at setup.** Heat pump, electric heater, solar collector, gas,
  or none at all. The questions that follow adapt: an immersion element has no
  efficiency curve and no minimum outdoor temperature, so those are skipped
  rather than asked and guessed at. Compressor protection and the operating
  envelope apply only where they exist
- **Solar collectors are advised, not controlled.** Almost every one is on a
  manual three-way valve, so the integration compares collector against pool and
  says when opening it is free heat — and when the collector is colder and water
  sent through it would lose heat instead
- **Pool construction** sets a believable starting heat loss, from 0.30 °C/h for
  an uninsulated inflatable to 0.08 for a built-in pool
- **Learned history survives a reinstall.** A new entry id meant a new storage
  key, leaving weeks of measurement on disk under a key nothing read. Setup finds
  it and offers to adopt it, describing what it found. Locally measured values
  win over adopted ones; the session and dose logs come across too
- `export_learning` and `import_learning` services for backups and moving
  between systems

### Changed
- **Settings reorganised into eight topics**: sensors, pool, heating, when to
  heat, filtration, water, notifications, advanced. The old "general" screen held
  twenty-eight unrelated settings, which is not a category but what was left over
  after categorising everything else
- **Saving returns to the menu** instead of closing the dialog. Changing three
  things used to mean opening Configure three times
- Advanced settings are separate on purpose: roughly a third of the settings here
  are ones anybody changes deliberately, and mixing them with the rest made those
  harder to find

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
- `docs/sensors.md`, covering probe calibration, flow calibration and which
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

[1.3.2]: https://github.com/rickertie/Poolsmart/releases/tag/v1.3.2
[1.3.1]: https://github.com/rickertie/Poolsmart/releases/tag/v1.3.1
[1.3.0]: https://github.com/rickertie/Poolsmart/releases/tag/v1.3.0
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
