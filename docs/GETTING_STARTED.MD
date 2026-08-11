> [← Back to README](../README.md) | [Getting Started](GETTING_STARTED.MD) | [Architecture](ARCHITECTURE.MD) | [Configuration](CONFIGURATION.MD) | [Troubleshooting](TROUBLESHOOTING.MD)

---

# Getting Started

---

Welcome to PoolSmart. This guide takes you from a fresh installation to a working,
understood system in about 15 minutes.

---

## Your First 5 Minutes

After installing via HACS and completing the setup wizard, PoolSmart is already
filtering your pool. Here is how to verify everything is working:

### 1. Check the Status Sensor

Go to **Developer Tools → States** and search for `sensor.poolsmart_status`.
The state shows the current decision:

| State | Meaning |
|---|---|
| `idle` | No filtration or heating needed right now |
| `filtration` | Running the filter pump on a schedule |
| `heating` | Actively heating the pool |
| `circulating` | Running for frost protection, chemistry, or pump rundown |
| `emergency_stop` | Manual kill-switch or safety interlock active |

### 2. Open the Management Panel

Navigate to `/poolsmart` in your Home Assistant instance (add it to your sidebar
if you haven't already). The **Overview** tab shows:

- Current pool temperature
- Active mode and reason for the last decision
- Next scheduled action

### 3. Verify the First Decision

On the panel's **Overview** tab, read the "Last decision" reason. It explains *why*
PoolSmart made its current choice. For example:

> "Filtration block: 2 hours remaining to meet today of 3 turnovers"

If the reason mentions a sensor is "unavailable", you likely have a mapping issue.
See [Sensors](#-mapping-your-sensors) below.

---

## Mapping Your Sensors

PoolSmart needs at least two readings to function:

1. **Water temperature** — from your ESPHome probe or any temperature sensor
2. **Flow meter** — from your ESPHome pulse counter (optional for basic filtration)

If you installed the ESPHome board from [ESPHOME.MD](ESPHOME.MD), the sensors
are auto-discovered. Otherwise, map them manually:

**Settings → Devices & Services → PoolSmart → Configure → Sensors and switches**

| Sensor | Required | Purpose |
|---|---|---|
| Water temperature | Yes | Determines heating demand and filtration timing |
| Flow meter | No | Measures actual flow for smart filtration |
| Air temperature | No | Enables COP-based heating optimization |
| Solar collector temperature | No | Enables solar surplus detection |
| Electricity price sensor | No | Enables price-aware scheduling |

> **Tip:** Leave any sensor you don't have blank. PoolSmart disables the matching
> feature gracefully and reports it in Diagnostics.

---

## What to Expect on Day One

| Timeframe | What Happens |
|---|---|
| **First 30 seconds** | PoolSmart evaluates the pool state and makes its first decision |
| **First hour** | You'll see the pump turn on/off according to the filtration schedule |
| **First day** | The status sensor reflects daily filtration blocks and any heating demand |
| **First week** | The self-learning model begins collecting session data |
| **First month** | Heating predictions improve as the model learns your pool's heat loss |

---

## Next Steps

Now that PoolSmart is running, you may want to:

- [Configure heating](PLANNING.MD) — Set target temperature and price ceiling
- [Understand the decision ladder](ARCHITECTURE.MD) — Why PoolSmart makes the choices it does
- [Install a dashboard](lovelace/README.md) — Visual overview for household members
- [Set up notifications](LOGGING.MD) — Get alerted about important events

---

## Common First-Day Questions

**Q: The pump isn't running. Is something wrong?**

Check the status sensor. If it shows `idle`, PoolSmart has determined no filtration
is needed right now. This is normal outside scheduled blocks. To force filtration,
use the manual override switch in Home Assistant.

**Q: How do I know it's filtering enough?**

The panel's **Overview** tab shows today's progress toward the turnover target.
For a typical pool, 1-3 turnovers per day is sufficient.

**Q: Can I change settings without breaking anything?**

Yes. All settings are in the options flow and can be changed at any time. Nothing
is locked in. See [CONFIGURATION.MD](CONFIGURATION.MD).

---

## See Also

- [CONFIGURATION.MD](CONFIGURATION.MD) — Full configuration reference
- [ARCHITECTURE.MD](ARCHITECTURE.MD) — How the priority decision ladder works
- [PANEL.MD](PANEL.MD) — Management panel reference
- [TROUBLESHOOTING.MD](TROUBLESHOOTING.MD) — When something goes wrong
