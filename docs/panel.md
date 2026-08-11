> [? Back to README](../README.md) | [Getting Started](GETTING_STARTED.MD) | [Architecture](architecture.md) | [Configuration](configuration.md) | [Troubleshooting](troubleshooting.md)

---

# Management Panel

This document covers the PoolSmart sidebar panel at `/poolsmart`. For the
Lovelace dashboards (a separate interface for household members), see
[lovelace/README.md](../lovelace/README.md).

---

## What It Is

A sidebar panel at `/poolsmart` with six tabs: overview, planning, sessions,
learning, settings and diagnostics. It is written as a plain custom element with
no build step and no external imports, so it keeps working without internet.

The panel is for whoever maintains the system. The Lovelace page in
`docs/lovelace/` is for everyone else, and the two are deliberately not the same
thing.

---

## Tabs

| Tab | What you will find |
|---|---|
| Overview | Current status, mode, temperature, and the reason for the last decision |
| Planning | Heating plan, price forecast, and target time/date |
| Sessions | Session history with learned values and rejection reasons |
| Learning | Learned heat loss, heating rate, and COP curve with confidence bars |
| Settings | Quick access to common settings without opening the full options flow |
| Diagnostics | Full ladder trace, decision log, faults, and export button |

---

## See Also

- [lovelace/README.md](../lovelace/README.md) — Lovelace dashboards for household members
- [logging.md](logging.md) — Logbook entries and the full trace
- [troubleshooting.md](troubleshooting.md) — What to check when something goes wrong
- [architecture.md](architecture.md) — The decision ladder and branch evaluation
