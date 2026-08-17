> [Home](index.md) | [Getting Started](getting_started.md) | [Architecture](architecture.md) | [Configuration](configuration.md) | [Troubleshooting](troubleshooting.md)

---

# Self-Learning Heating & Efficiency Model

This document covers how PoolSmart learns your pool's actual thermal behavior
over time. For how these learned values feed into heating schedules, see
[Planning](planning.md). For the decision ladder that produces the sessions
being learned from, see [Architecture](architecture.md).

---

## What Is Learned?

After each heating session, PoolSmart updates three core parameters:

1. **Heating rate (°C/h):** How fast your pool water warms up per hour of
   active heating.
2. **Heat loss rate (°C/h):** How quickly your pool loses heat to ambient air
   and evaporation. Measured from idle periods -- no pump, no heat pump, just
   the pool cooling (or, on a sunny day, warming) on its own. How much of an
   idle period's temperature change was the sun rather than heat loss is
   worked out, in order of preference: a direct irradiance sensor (W/m²) if
   one is mapped; failing that, a solar-production sensor scaled by its peak
   wattage; failing that, a conservative time-of-day estimate. Whichever
   source is available, a sunny afternoon teaches the model too, instead of
   being discarded as "warmed up on its own." A cover change mid-period still
   voids the observation, and the estimate used without a sensor is never
   generous enough to invent heat loss that did not happen -- a strongly
   sunny period with neither sensor mapped is still set aside, exactly as
   before. See [Sensors](sensors.md) for where to map these.

   The learned figure is a snapshot of whatever the water-to-air gap
   typically was while it was being measured. With a weather entity mapped
   under **Weer en prijs**, the planner (see [Planning](planning.md)) no
   longer uses that figure unscaled: it is stretched or shrunk by how much
   colder or warmer the forecast air temperature is than today's, on the
   reasoning that twice the gap is roughly twice the loss. A forecast
   suggesting less loss than usual is trusted only down to 60% of the
   learned figure -- under-estimating loss is what actually shows up as a
   cold pool at swim time -- while a colder forecast is allowed to scale it
   up to 2.5x, since over-estimating only starts the plan early. Without a
   weather entity mapped, or without both a water and an air reading
   available, the learned figure is used exactly as measured.
3. **COP curve (per 5 °C air band):** Thermal efficiency measured per 5 °C
   outdoor temperature bracket (e.g., 10–15 °C, 15–20 °C, 20–25 °C). Because
   non-inverter heat pumps operate at fixed output, one COP value per temperature
   band is sufficient.

<p align="center">
  <img src="images/cop-curve.svg" width="550" alt="COP curve showing how efficiency varies with outdoor temperature">
</p>

![Self-learning feedback loop showing how sessions improve the model](images/learning-feedback-loop.svg)

---

## The Three Rules That Keep the Model Honest

To prevent corrupted sensors, hardware glitches, or open pool covers from
ruining your baseline, PoolSmart enforces three strict validation rules:

> **Rule 1: Clean sessions only**  
> Interrupted sessions, safety trips, manual cut-offs, or sessions under the
> minimum measurement duration are logged and flagged, but **never used for
> learning**.

> **Rule 2: Weighted moving average (exponential smoothing)**  
> Every valid update is capped at a small fraction of the existing value. A
> single unusual session (e.g., an exceptionally windy day) will only slightly
> nudge the model rather than overwrite it.

> **Rule 3: Physical outlier rejection**  
> Data is rejected based on physical boundaries rather than purely statistical
> deviations. For example:
> - A measured COP exceeding the heat pump's physical bounds.
> - Water failing to warm up while the pump was reported active.

---

## Diagnostics & Session Logging

Rejected sessions are not deleted; they remain stored in the log history along
with the explicit reason for rejection.

If the planning target dates stop updating or seem inaccurate, checking the
**Learning** tab in the `/poolsmart` panel for rejected sessions is the first
step in troubleshooting.

### Reviewing a Session

The automatic accept/reject verdict is usually right, but it cannot know a
probe glitched or the pool was topped up mid-session. The **Sessions** tab in
the `/poolsmart` panel flags a session **"worth a look"** when it ran long
enough to hold real data but was rejected outright, or when it was accepted
despite a fault having occurred during it — never the other way around; the
flag only ever points at a case a human might read differently, it never makes
the automatic verdict more confident on its own.

Each session offers three states: **Auto** (the automatic verdict stands),
**Include** (count it regardless of the verdict, as long as it still carries a
raw measurement), and **Exclude** (never count it). Changing a session's state
recomputes the heating rate and COP curve immediately from every session that
currently counts — it is not a one-off nudge, so a correction made after the
fact actually changes what the model believes. Heat loss and measured flow are
untouched by this, since those are learned from idle periods and flow readings
rather than sessions. The same override is available as the
`poolsmart.set_session_review` service, for use from automations or scripts.

### Backing Up Learned History

After every finished session, PoolSmart writes a rolling
`poolsmart_learning_backup.<entry_id>.json` file to the Home Assistant config
directory — the same shape `poolsmart.export_learning` produces, kept current
automatically rather than depending on someone having run that service
beforehand. Restore from it (or from any manual export) with
`poolsmart.import_learning`.

### Maintenance & Export/Import

The bottom of the **Learning** tab covers storage and bulk history operations.

**Storage** shows counts (sessions, doses, decisions logged, near misses
tracked) and the on-disk file size, refreshed on request rather than on every
panel load, since the size check is a disk read.

**Maintenance:**

| Action | Service | What it does |
|---|---|---|
| Process now | `poolsmart.rebuild_learning` | Recomputes the heating rate and COP curve from the whole session log, and recovers COP session counts. Same effect as reviewing a session, but for the whole log at once — useful after a batch of reviews or an import. |
| Clear debug traces | `poolsmart.clear_debug_log` | Empties the decision log and the near-miss tally. Diagnostics only; never touches learned values, sessions, or doses. Always safe. |
| Clear all history | `poolsmart.clear_all_history` | Permanently deletes every learned value, session, dose, and log entry. Today's live filtration progress and current mode/target are left alone. **Cannot be undone**, and requires a `confirm: true` field — the panel button asks twice before sending it. |

**Export / Import:**

- **Quick export** (`poolsmart.export_learning` with no `sections`) writes
  everything: learned values, session log, dose log, last water test.
- **Choosing what to export** narrows that with the `sections` field —
  useful for carrying only the learned figures across without the raw session
  log, for example.
- **Import** (`poolsmart.import_learning`) merges: a value this pool has
  already measured for itself is kept over the imported one.
- **Advanced: replace** (`poolsmart.replace_learning`) overwrites instead of
  merging — what this pool has already measured for itself is discarded in
  favour of the file. Also `sections`-aware, and also requires `confirm: true`.
  For recovering a backup exactly as it was, not routine use.

---

## See Also

- [Planning](planning.md) — How the learned COP curve feeds directly into
  price optimization and heat scheduling.
- [Architecture](architecture.md) — Entity fallback behavior when heat pump
  inlet/outlet sensors are missing.
- [Sensors](sensors.md) — How to calibrate the probes that feed the learning
  model.
- [Heating](heating.md) — Heating sources and how pool construction affects heat loss.
