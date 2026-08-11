[← Back to README](../README.md) • [Architecture](architecture.md) • [Planning](planning.md) • [Learning](learning.md) • [Heating](heating.md) • [Filtration](filtration.md) • [Chemistry](chemistry.md) • [Hardware](hardware.md) • [ESPHome](esphome.md) • [Sensors](SENSORS.md) • [Logging](logging.md) • [Entities](entities.md) • [Panel](panel.md) • [Configuration](configuration.md) • [Troubleshooting](troubleshooting.md) • [Defaults](DEFAULTS.md)

---

# Filtration

This document covers how PoolSmart calculates daily filtration runtime, the two
rules that set the requirement, filter media effects, flow measurement, and
filter resistance. For sensor calibration (including the flow meter bucket test),
see [SENSORS.md](SENSORS.md). For the decision ladder that executes filtration
blocks, see [architecture.md](architecture.md).

---

## The Two Rules

Two rules decide the daily runtime, and the requirement is the **larger** of them.
Using only the first understates the runtime badly on pools with a generous pump.

### Rule 1: Turnover (volume-based)

```
turnover runtime = pool volume × turnover factor / effective pump flow
```

Filtered water mixes back in with unfiltered water, so one turnover does not
clean the pool once — it cleans about 63% of it. Two turnovers reach 86%, three
reach 95%, four reach 98%. Three is where the gains flatten, so that is the
default.

### Rule 2: Daily Minimum (time-based)

A skimmer only catches the leaves, pollen and insects that land on the surface
while it is actually running; sanitiser needs contact time; and water that sits
still for twenty hours grows algae however thoroughly it was filtered in the
other four. The familiar rule of thumb — about an hour of running per 10 °F of
temperature — is really this minimum in disguise, which is why it does not scale
down when you fit a faster pump.

The minimum rises with water temperature, from half the configured value in cold
water to one and a half times it above 30 °C.

Which rule is currently setting the requirement is shown in the panel, so the
daily figure is never an unexplained number.

### Worked Examples

| Pool | Pump | Turnover | Minimum at 28 °C | Requirement |
|---|---|---|---|---|
| 3800 L | 3.6 m³/h | 3.2 h | 5 h | **5 h**, set by the minimum |
| 50000 L | 8 m³/h | 18.8 h | 5 h | **18.8 h**, set by turnover |

---

## Filter Media

The medium in the filter changes how much of the rated pump flow actually
arrives. It is only used to estimate flow for people without a flow meter; with
one connected the real figure is used instead.

| Medium | Typical share of rated flow | Filters down to |
|---|---|---|
| Cartridge | 60% | 20–40 micron |
| Sand | 70% | 20–40 micron |
| Glass | 72% | 3–5 micron |
| Filter balls | 80% | 5–15 micron |

> **Warning:** Filter balls flow more freely than sand when fresh, but they
> compress and mat together over time, and a matted bed chokes the flow far
> worse than sand ever does. A sustained drop in measured flow is the signal to
> pull them out, wash them and fluff them up — the integration raises the filter
> service warning for exactly this.

---

## Flow Meters and Units

A flow meter's unit is read from the sensor itself where it publishes one, and
otherwise from the setting in the wizard. Pool meters usually report **litres per
minute**, while the heat pump's datasheet minimum is quoted in **m³/h**, and the
two are easy to confuse: 2 m³/h is 33 L/min.

---

## Judging Flow by Delta-T, Not by the Datasheet

Flow in m³/h is a proxy. The temperature rise across the heat pump is the thing
the proxy stands for, and it can be measured directly.

A heat pump rejecting a fixed amount of heat into a stream of water raises it by
`kW / (flow × 1.163)` degrees. Halve the flow and the rise doubles. Starve it
further and the condensing temperature climbs until the appliance derates or
trips. So a genuine flow problem has a signature, and the signature is a **high**
delta-T — not a low number against a datasheet.

`sensor.<name>_flow_adequacy` reports the verdict: healthy under about 3 °C,
marginal to 5 °C, starved above that.

### Real-World Example

1.05 m³/h against a 2.0 datasheet minimum, delta-T 1.56 °C, output 1.9 kW.
Opening the diverter valve raised flow to 1.30 m³/h; delta-T fell to 1.27 °C and
output stayed at 1.9 kW. The extra flow bought nothing, because the system was
never flow-limited. Chasing the datasheet figure would have been chasing nothing.

If your installation reads healthy below the quoted minimum, tick **verified for
this installation** under Configure → Pool and equipment. That silences a warning
which otherwise repeats a number your plumbing cannot produce — and stops the AI
review recommending it.

> **Note:** Falling below the datasheet minimum is a **warning**, not a stop.
> Datasheet figures are conservative and the appliance has its own flow switch,
> so plenty of installations run below the quoted number without trouble — what
> matters is whether the water carries the heat away, which shows up as a
> sensible delta-T. At 1 m³/h a 3 kW heat pump produces about 2.5 °C of rise,
> which is perfectly normal.

If your installation settles somewhere below the quoted figure, set the minimum
to what it actually achieves. The warning stops and the real protection — zero
flow, and the appliance's own switch — stays in place.

---

## Filter Resistance

Manufacturers specify pump flow without a filter installed; with one in line
roughly 60–75% remains and it drops as the filter fouls. If you tick "measured"
the figure is used as it is; otherwise it is derated. With a flow meter connected
the block duration corrects itself as the filter ages, and a sustained decline
raises a service notification.

Heating sessions run the pump too, so that runtime counts towards the quota.
Without that credit the system would filter far more than needed on heating days.

---

## See Also

- [SENSORS.md](SENSORS.md) — Flow meter calibration (the bucket test) and probe calibration
- [architecture.md](architecture.md) — The filtration calculation formula and decision ladder
- [configuration.md](configuration.md) — How to adjust turnover, quiet hours, and pump rundown
