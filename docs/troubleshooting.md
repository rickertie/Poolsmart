> [← Back to README](../README.md) | [Getting Started](GETTING_STARTED.MD) | [Architecture](architecture.md) | [Configuration](configuration.md) | [Troubleshooting](troubleshooting.md)

---

# Troubleshooting

---

This document covers common problems, how to diagnose them, and how to share
diagnostics when you need help. For the full decision trace, see [logging.md](logging.md).
For the management panel's Diagnostics tab, see [panel.md](panel.md).

---

## Common Issues

### Pump or Heating Not Running

| Symptom | Likely Cause | Fix |
|---|---|---|
| Status shows `idle` during expected filtration | No demand at this time | Normal — check next scheduled block on the panel |
| "Waiting for cheaper electricity" all day | Price sensor missing or no forecast data | Verify your price sensor has `forecast` attributes |
| Heating never starts in cold weather | Heat pump below minimum air temperature | Normal — envelope gate prevents operation below the heat pump's rated minimum |
| Pump runs but no flow detected | Flow meter not mapped or filter clogged | Check flow meter sensor; clean filter if delta-T is high |
| Flow warning despite adequate flow | Datasheet minimum too high for your plumbing | Enable "Verified for this installation" in configuration |

### Sensor Issues

| Symptom | Likely Cause | Fix |
|---|---|---|
| Temperature shows `unavailable` | Sensor entity not mapped or offline | Check sensor mapping in Configure → Sensors |
| Temperature reading seems wrong | Wrong sensor mapped or offset needed | Remap in options; check probe calibration in [sensors.md](sensors.md) |
| Water and air temperature swapped | Sensors mapped to wrong fields | Swap in Configure → Sensors and switches |
| Flow meter shows zero when pump is running | Pulse counter not connected or miscalibrated | Run the bucket test (see [sensors.md](sensors.md)) |

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

---

## Fault Isolation

The control decision is the only part of a tick that may not fail. Planning,
learning, energy bookkeeping, and notifications each run inside their own guard,
so a fault in one of them is logged and skipped rather than taking the whole
integration off the dashboard. Entities stay available as long as a decision
exists, because the decision the pool is actually running on remains valid even
if an optional subsystem hiccuped.

![Heat pump operating envelope showing temperature thresholds](docs/images/operating-envelope.svg)

Anything that did fail shows up under Diagnostics in the panel and in the status
sensor's attributes, with the full traceback in the Home Assistant log.

---

## Using the Diagnostics Tab

The management panel (`/poolsmart`) has a **Diagnostics** tab that shows:

- **Full ladder trace** — Which branch evaluated to `true` and why
- **Decision log** — Recent decisions with timestamps and reasons
- **Derived figures** — Calculated values (COP, heat loss, daily runtime)
- **Active faults** — Any subsystem that failed in the last tick

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

- [logging.md](logging.md) — Logbook entries, notifications, and the full trace
- [panel.md](panel.md) — The management panel's Diagnostics tab
- [architecture.md](architecture.md) — Entity fallback table and operating envelope
- [filtration.md](filtration.md) — Flow adequacy and filter service warnings
- [sensors.md](sensors.md) — Sensor calibration procedures
- [GETTING_STARTED.MD](GETTING_STARTED.MD) — First-time setup guide
