> [← Back to README](../README.md) | [Getting Started](GETTING_STARTED.MD) | [Architecture](ARCHITECTURE.MD) | [Configuration](CONFIGURATION.MD) | [Troubleshooting](TROUBLESHOOTING.MD)

---

# Management Panel

This document covers the PoolSmart sidebar panel at `/poolsmart`. For the
Lovelace dashboards (a separate interface for household members), see
[lovelace/README.md](../lovelace/README.md).

---

## What It Is

A sidebar panel at `/poolsmart` with six tabs: overview, planning, sessions,
learning, settings, and diagnostics. It is written as a plain custom element with
no build step and no external imports, so it keeps working without internet.

The panel is for whoever maintains the system. The Lovelace page in
`docs/lovelace/` is for everyone else, and the two are deliberately not the same
thing.

---

## Tabs Overview

| Tab | What you will find |
|---|---|
| Overview | Current status, mode, temperature, and the reason for the last decision |
| Planning | Heating plan, price forecast, and target time/date |
| Sessions | Session history with learned values, rejection reasons, and manual review controls |
| Learning | Learned heat loss, heating rate, and COP curve with confidence bars; storage stats, maintenance actions, and export/import |
| Settings | Quick access to common settings without opening the full options flow |
| Diagnostics | Full ladder trace, decision log, faults, and export button |

---

## Tab Details & Screenshots

### 1. Overview Tab
Provides a real-time summary of the pool state, active operating mode, live temperatures, and the primary reason behind the decision engine's last action.

<p align="center">
  <img src="images/panel-overview.svg" width="750" alt="PoolSmart Overview Tab">
</p>

---

### 2. Planning Tab
Displays the automated heating schedule, real-time dynamic energy price forecasts, and target temperatures for scheduled swim sessions.

<p align="center">
  <img src="images/panel-planning.svg" width="750" alt="PoolSmart Planning Tab">
</p>

---

### 3. Sessions Tab
Logs past heating and filtration cycles, displaying evaluated metrics, learned parameter updates, and reasons for any rejected runs. Each session carries Auto/Include/Exclude review controls, with a "worth a look" flag on sessions the automatic verdict is likely to have gotten wrong. See [LEARNING.MD](LEARNING.MD#reviewing-a-session).

<p align="center">
  <img src="images/panel-sessions.svg" width="750" alt="PoolSmart Sessions Tab">
</p>

---

### 4. Learning Tab
Visualizes the self-learning engine's performance models, including heat loss calculations, heating rate estimations, and the active COP curve with confidence margins. Below that sits storage statistics, maintenance actions (reprocess history, clear debug traces, clear all history), and export/import, including a selective export and an advanced full-replace option. See [LEARNING.MD](LEARNING.MD#maintenance--exportimport).

<p align="center">
  <img src="images/panel-learning.svg" width="750" alt="PoolSmart Learning Tab">
</p>

---

### 5. Settings Tab
Offers quick access to frequently adjusted operational targets and overrides without needing to open the main Home Assistant integration configuration wizard.

<p align="center">
  <img src="images/panel-settings.svg" width="750" alt="PoolSmart Settings Tab">
</p>

---

### 6. Diagnostics Tab
Exposes full decision ladder traces, detailed event logs, system fault notifications, and an export button for diagnostic data.

<p align="center">
  <img src="images/panel-diagnostics.svg" width="750" alt="PoolSmart Diagnostics Tab">
</p>

---

## See Also

- [lovelace/README.md](../lovelace/README.md) — Lovelace dashboards for household members
- [LOGGING.MD](LOGGING.MD) — Logbook entries and the full trace
- [TROUBLESHOOTING.MD](TROUBLESHOOTING.MD) — What to check when something goes wrong
- [ARCHITECTURE.MD](ARCHITECTURE.MD) — The decision ladder and branch evaluation