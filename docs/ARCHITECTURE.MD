> [? Back to README](../README.md) | [Getting Started](GETTING_STARTED.MD) | [Architecture](architecture.md) | [Configuration](configuration.md) | [Troubleshooting](troubleshooting.md)

---

# Architecture & Decision Core

This document covers how PoolSmart evaluates decisions, calculates daily
filtration, and manages component failure. For the heating planner that consumes
these decisions, see [planning.md](planning.md). For the self-learning model
that improves predictions over time, see [learning.md](learning.md).

---

## The Priority Decision Ladder

![Priority Decision Ladder flowchart](images/priority-ladder.svg)

Every 30 seconds, PoolSmart evaluates the current state of your pool against a
strict priority ladder. The evaluation walks from the top down; **the first
condition that matches wins**, and all lower branches are ignored.

| Priority | Branch / Condition | Ignores Night Quiet? | Description |
| :---: | :--- | :---: | :--- |
| **0** | Emergency stop | Yes | Global manual kill-switch or safety interlock triggered. |
| **1** | Frost protection | Yes | Temp drops below safe threshold; forces circulation. |
| **2** | Manual override | Yes | User manually forced the pump ON/OFF in Home Assistant. |
| **3** | Chemistry cycle | Yes | Scheduled chemical dosing or shock treatment. |
| **4** | Filtration deadline | Yes | Ensures minimum turnover is met before the day ends. |
| **5** | Free electricity | Yes | Triggered when electricity price is negative (< 0). |
| **6** | Heating session | **No** | Dynamic heating session active based on COP and prices. |
| **7** | Scheduled filtration | **No** | Regular background filtration block. |
| **8** | Pump rundown | **No** | Cool-down period after heating before turning pump off. |
| **9** | Idle | — | No action required; pump and heating remain off. |

> **Safety interlock:** Branches 0, 1, and 4 stay active even if the integration
> is turned OFF. An off-switch must never be able to cause pipe freeze or damaged
> equipment.

### Heat Pump Operating Envelope

In front of branches **5 (Free Electricity)** and **6 (Heating)** sits an
operating envelope gate. If the outdoor air temperature drops below the heat
pump's minimum operating limit (e.g., < 11 °C), heating is disabled. In this
state, Frost Protection (Branch 1) will only trigger simple **water circulation**,
which is sufficient to prevent freezing.

---

## Filtration Calculation

Filtration runtime is calculated dynamically based on physical metrics rather
than hardcoded timers:

```
Daily Runtime (hours) = Pool Volume (L) × Turnover Factor / Effective Pump Flow (L/h)
Block Duration        = Daily Runtime / Number of Scheduled Blocks
```

### Key Filtration Behaviors

- **Derating factor:** If pump flow is unmeasured (taken from a spec sheet), it is
  automatically derated by 25–40% to account for filter resistance.
- **Self-correcting blocks:** If a flow meter is installed, block durations
  automatically adjust as filter pressure changes over time.
- **Heating session credit:** Any time spent running the pump during heating
  sessions counts directly towards your daily filtration quota, preventing
  redundant pump runtime.

---

## Entity Mapping & Fallbacks

All sensors and switches can be updated anytime under **Settings → Devices &
Services → PoolSmart → Configure**.

Every optional entity may be left blank. The matching capability switches off
cleanly and reports in diagnostics without breaking the integration:

| Unmapped Entity | Consequence / Fallback |
| :--- | :--- |
| **Outdoor temperature** | Disables envelope check; falls back to default HA weather integration. |
| **Heat pump in / out** | Disables live delta-T calculation and COP performance learning. |
| **Flow meter** | Disables flow alarms; falls back to estimated pump spec flow. |
| **Power sensors** | Disables real-time energy cost calculations and measured COP. |
| **Price / solar sensors** | Disables price/solar slot optimization (runs on default scheduled blocks). |

> **Heat pump thermostat tip:** Set your heat pump's physical thermostat 2 °C
> higher than your highest desired Home Assistant target (e.g., set physical
> dial to 34 °C if target is 32 °C). This ensures full software control while
> retaining hardware safety shutdown.

---

## AI Advisory Layer

The optional AI layer acts strictly as a **non-blocking advisor**:

1. Analyzes historical session logs and efficiency metrics.
2. Proposes parameter tweaks (e.g., adjusting filtration turnover or target temps).
3. **Applies nothing automatically.** Suggestions must be manually approved by the user.
4. Out-of-bounds parameters suggested by AI are discarded by a strict validation filter.

If the AI is unavailable the pool behaves exactly as it otherwise would, because
this layer sits outside the control tick entirely.

---

## Compressor Protection

Minimum off and run times for the heat pump are enforced separately from the
ordinary decision hold, and no branch can override them. A hold protects a
decision and may be broken when waiting would be worse; a compressor needs its
refrigerant pressures to equalise before restarting, and that is not negotiable
by any rule about filtration deadlines.

Reaching the target temperature is the one thing that still stops heating
immediately — a minimum run time must never keep heating a pool that is done.

---

## Developer & Standalone Testing

The core decision logic in `custom_components/poolsmart/core/` has **zero Home
Assistant dependencies**. It can be tested standalone:

```bash
cd tests && python run_tests.py
```

---

## See Also

- [planning.md](planning.md) — How the heating planner uses the decision ladder
  and learned COP values to optimize heating schedules.
- [learning.md](learning.md) — How heating rate, heat loss, and COP are learned
  from each session and fed back into planning.
- [hardware.md](hardware.md) — Physical installation, wiring, and component
  selection for the sensor board.
- [esphome.md](esphome.md) — ESPHome configuration and calibration procedures.
- [sensors.md](sensors.md) — How to map and calibrate your temperature probes
  and flow meter.
- [heating.md](heating.md) — Heating sources, solar collectors, and pool construction.
- [configuration.md](configuration.md) — How to adjust settings after setup.
