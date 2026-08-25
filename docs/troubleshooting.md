> [Home](index.md) | [Getting Started](getting_started.md) | [Architecture](architecture.md) | [Configuration](configuration.md) | [Troubleshooting](troubleshooting.md)

---

# Troubleshooting

This document covers common problems, how to diagnose them, and how to share
diagnostics when you need help. For the full decision trace, see [Logging](logging.md).
For the management panel's Diagnostics tab, see [Panel](panel.md).

---

## Common Issues

### Pump or Heating Not Running

| Symptom | Likely Cause | Fix |
|---|---|---|
| Status shows `idle` during expected filtration | No demand at this time | Normal — check next scheduled block on the panel |
| "Waiting for cheaper electricity" all day | Price sensor missing or no forecast data | Verify your price sensor has recognised forecast attributes (see below) — or map a cheap-period signal instead |
| Heating never starts in cold weather | Heat pump below minimum air temperature | Normal — envelope gate prevents operation below the heat pump's rated minimum |
| Pump runs but no flow detected | Flow meter not mapped or filter clogged | Check flow meter sensor; clean filter if delta-T is high |
| Flow warning despite adequate flow | Datasheet minimum too high for your plumbing | Enable "Verified for this installation" in configuration |

#### "No usable price forecast" with hass.tibber_prices

If heating's decision reason mentions no usable price forecast and your price
sensor comes from [hass.tibber_prices](https://github.com/jpawlowski/hass.tibber_prices),
this is expected, not a misconfiguration to chase: that integration splits
price data across dozens of narrow sensors (`current_interval_price`,
`lowest_price_today`, `next_avg_3h`, ...) instead of attaching a raw
today/tomorrow interval list to any one entity, which is the shape PoolSmart's
forecast parser looks for. Pointing `price_sensor` at
`current_interval_price` still gets you the current price correctly — it just
never produces a forecast.

The supported path for this integration is the cheap-period signal, not the
forecast:

- **Cheap price period signal** → `binary_sensor.<name>_best_price_period`
- **Cheap price time remaining** (optional) → `sensor.<name>_best_price_remaining_minutes`,
  shown in the friendly name as something like "Best Price Remaining Time".
  Purely informational: it reads 0 whenever no cheap period is active, so it
  cannot substitute for a forecast, but it shows up in heating's decision
  reason while a cheap period is active.

See [Dynamic Electricity Price Integrations](planning.md#dynamic-electricity-price-integrations)
for how the cheap-period signal interacts with the fixed price ceiling.

### Sensor Issues

| Symptom | Likely Cause | Fix |
|---|---|---|
| Temperature shows `unavailable` | Sensor entity not mapped or offline | Check sensor mapping in Configure → Sensors |
| Temperature reading seems wrong | Wrong sensor mapped or offset needed | Remap in options; check probe calibration in [Sensors](sensors.md) |
| Water and air temperature swapped | Sensors mapped to wrong fields | Swap in Configure → Sensors and switches |
| Flow meter shows zero when pump is running | Pulse counter not connected or miscalibrated | Run the bucket test (see [Sensors](sensors.md)) |

### Chemistry

| Symptom | Likely Cause | Fix |
|---|---|---|
| Chemistry dose shows `—` | No water temperature reading | Temperature is required for dose calculations |
| Dose seems too large or small | Pool volume incorrect | Verify volume in Configure → Pool and pump |
| "Test water" notification repeats | Dose not logged after application | Record the dose in the panel's Chemistry tab |

### Integration Issues

| Symptom | Likely Cause | Fix |
|---|---|---|
| Integration shows `unavailable` after restart | ESPHome device not reachable | Check ESPHome device status; verify WiFi |
| Configuration changes have no effect | Options not saved | Click "Submit" and reload the integration |
| Entities disappeared after upgrade | Entity ID migration | Check the log for rename messages; update automations |
| Pump runs a full filtration block again right after a Home Assistant update or restart | Two separate causes, both fixed: state is flushed to disk before shutdown as of 1.12.2, and a single unreadable stored interval no longer wipes the whole day's credit as of 1.12.5 | Update to 1.12.5 or later; if it still happens, check `PoolSmart state restored` in the log or the diagnostics file's `persistence` section (see [below](#using-the-diagnostics-tab)) for what the last restart actually found on disk |

### Single-Pool Limitation for Services

All PoolSmart services (`record_dose`, `reset_learned`, `export_learning`,
`import_learning`, `replace_learning`, `rebuild_learning`,
`set_session_review`, `clear_debug_log`, `clear_all_history`,
`set_setting`) only work when **exactly one** PoolSmart config entry is loaded.

If you set up two or more pools and call a service, it is refused with an error
like:

> Cannot record a dose: 2 PoolSmart pools are set up and this service cannot
> yet target one of them specifically.

This is a safety measure. The services were written for a single pool, and
running them against every coordinator would, for example, log a dose recorded
for one pool against all of them, or let an export overwrite itself once per pool
— leaving only the last pool's history on disk.

**Workaround:** Use only one PoolSmart config entry for now. Multi-pool service
targeting is planned for a future release.

### House Power Limit Notifications

If you see notifications like:

> Heating paused — house draw 2500 W + 1000 W for pump/heat pump = 3500 W,
> above the 3000 W limit.

but the heat pump is **not currently running**, this is expected behaviour. The
demand limiter uses a **look-ahead** to prevent exceeding your household
electrical cap:

- When the pool pump and/or heat pump are **off**, their rated power draw is
  **added** to the current household reading before comparing against the limit.
- This prevents the meter from briefly showing a spike the moment the equipment
  switches on — at which point it is too late to prevent tripping a breaker or
  exceeding a contract cap.
- Once the equipment is **running**, the meter reading already includes it, so
  no extra is added and the system uses the real figure.

**Common causes of false positives:**

| Symptom | Likely Cause | Fix |
|---|---|---|
| Heating paused while everything else is off | Limit set too low | Raise `power_limit_w` — see [Configuration](configuration.md#house-power-limit) for how to calculate a realistic value |
| Notifications during peak household usage | House draw legitimately high | Normal — the limiter is protecting your electrical cap; raise the limit or wait for usage to drop |
| No `grid_power_sensor` configured | Sensor not mapped | Map your smart meter sensor in Configure → Sensors |

See [Configuration — House Power Limit](configuration.md#house-power-limit) for
details on choosing the right sensor and setting a realistic limit.

---

## Fault Isolation

The control decision is the only part of a tick that may not fail. Planning,
learning, energy bookkeeping, and notifications each run inside their own guard,
so a fault in one of them is logged and skipped rather than taking the whole
integration off the dashboard. Entities stay available as long as a decision
exists, because the decision the pool is actually running on remains valid even
if an optional subsystem hiccuped.

<p align="center">
  <img src="images/operating-envelope.svg" width="500" alt="Heat pump operating envelope showing temperature thresholds">
</p>

Anything that did fail shows up under Diagnostics in the panel and in the status
sensor's attributes, with the full traceback in the Home Assistant log.

---

## Using the Diagnostics Tab

The management panel (`/poolsmart`) has a **Diagnostics** tab that shows:

- **Full ladder trace** — Which branch evaluated to `true` and why
- **Decision log** — Recent decisions with timestamps and reasons
- **Derived figures** — Calculated values (COP, heat loss, daily runtime)
- **Active faults** — Any subsystem that failed in the last tick
- **Persistence** — What the last restart actually found on disk: quota
  date, filtration hours credited, interval count, whether the pump had an
  interval still open, and when the last write reached disk. The same
  numbers are logged once at INFO level on every restore as `PoolSmart
  state restored: ...`, visible in the log with no debug logging needed —
  useful for a "lost today's filtration credit" report without asking
  anyone to enable debug logging first.

This is the first place to look when something unexpected happens.

---

## Flow Warnings

The heat pump's minimum flow is a **warning** by default rather than a stop.
Datasheet minima are conservative and the appliance has its own flow switch as a
hardware backstop, so overriding the owner on the strength of a brochure figure
is the wrong default. There is a toggle if you would rather it stopped. Zero flow
with the pump running is a different matter and does stop everything.

---

## Sharing a Problem

Settings → Devices & services → PoolSmart → the three dots → **Download
diagnostics**. That file has the trace, the decision log, a plain-sentence
timeline, learned values, faults, and every derived figure, with no credentials in
it. It is the fastest way to hand someone the whole picture.

When sharing, include:

1. The diagnostics file
2. A description of what you expected vs. what happened
3. Your pool volume and heating source type

---

## See Also

- [Logging](logging.md) — Logbook entries, notifications, and the full trace
- [Panel](panel.md) — The management panel's Diagnostics tab
- [Architecture](architecture.md) — Entity fallback table and operating envelope
- [Filtration](filtration.md) — Flow adequacy and filter service warnings
- [Sensors](sensors.md) — Sensor calibration procedures
- [Getting Started](getting_started.md) — First-time setup guide
