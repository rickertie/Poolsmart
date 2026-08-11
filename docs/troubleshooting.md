[← Back to README](../README.md) • [Architecture](architecture.md) • [Planning](planning.md) • [Learning](learning.md) • [Heating](heating.md) • [Filtration](filtration.md) • [Chemistry](chemistry.md) • [Hardware](hardware.md) • [ESPHome](esphome.md) • [Sensors](SENSORS.md) • [Logging](logging.md) • [Entities](entities.md) • [Panel](panel.md) • [Configuration](configuration.md) • [Troubleshooting](troubleshooting.md) • [Defaults](DEFAULTS.md)

---

# Troubleshooting

This document covers what to check when something goes wrong, how faults are
isolated, and how to share diagnostics. For the full decision trace, see
[logging.md](logging.md). For the management panel's Diagnostics tab, see
[panel.md](panel.md).

---

## Fault Isolation

The control decision is the only part of a tick that may not fail. Planning,
learning, energy bookkeeping and notifications each run inside their own guard,
so a fault in one of them is logged and skipped rather than taking the whole
integration off the dashboard. Entities stay available as long as a decision
exists, because the decision the pool is actually running on remains valid even
if an optional subsystem hiccuped.

Anything that did fail shows up under Diagnostics in the panel and in the status
sensor's attributes, with the full traceback in the Home Assistant log.

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
timeline, learned values, faults and every derived figure, with no credentials in
it. It is the fastest way to hand someone the whole picture.

---

## See Also

- [logging.md](logging.md) — Logbook entries, notifications, and the full trace
- [panel.md](panel.md) — The management panel's Diagnostics tab
- [architecture.md](architecture.md) — Entity fallback table and operating envelope
- [filtration.md](filtration.md) — Flow adequacy and filter service warnings
