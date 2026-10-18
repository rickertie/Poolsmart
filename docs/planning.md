> [Home](index.md) | [Getting Started](getting_started.md) | [Architecture](architecture.md) | [Configuration](configuration.md) | [Troubleshooting](troubleshooting.md)

---

# Heating Planning & Price Optimization

This document covers how PoolSmart plans heating sessions to minimize cost while
reaching your target temperature on time. For the decision ladder that executes
these plans, see [Architecture](architecture.md). For the self-learning model
that supplies the COP curve and heat loss figures the planner relies on, see
[Learning](learning.md).

---

## Maintenance vs. Seasonal Mode

<p align="center">
  <img src="images/heating-timeline.svg" width="600" alt="Heating planning timeline showing maintenance vs seasonal mode">
</p>

Depending on the difference between the target temperature and current water
temperature, the optimizer operates in one of two distinct modes:

| Mode | Trigger / Condition | How It Works | Expected Result |
| :--- | :--- | :--- | :--- |
| **Maintenance** | Compensating a day's heat loss (ΔT ≤ ~2 °C). | The optimizer picks the cheapest intervals before the next swimming time. | Reports a **target time** (e.g., *"Ready today at 14:30"*). |
| **Seasonal** | Bringing a cold pool up to temperature (ΔT > 2 °C). | Requires long continuous runs (10–15+ hours). Projects budget across multiple days. | Reports a **target date** (e.g., *"Ready on Saturday 16:00"*). |

> **Thermal equilibrium warning:** If heat loss equals or exceeds the maximum
> thermal output of your heat pump (e.g., during cold nights without a cover),
> Seasonal mode will explicitly notify you that the temperature cannot be
> reached instead of outputting an impossible target date. With a weather
> entity mapped, this can now fire ahead of the cold snap itself: the heat
> loss the projection uses is scaled by tomorrow's forecast (see
> [Learning](learning.md)), so a cold front that has not arrived yet already
> shows up in the plan rather than only once it is measured.

---

## Swim Time

Everything above answers "how long will heating take"; this is where "by
when" comes from.

**Static fields.** `swim_time` (and an optional `swim_time_2`, for a second
window on the same days) under **When to heat** set a fixed time of day, and
**Days** picks which weekdays they apply to.

**Dashboard helper.** `swim_time_entity` points at an `input_datetime`
helper and, when it holds a usable value, replaces both static fields
rather than adding to them — so anyone in the house can set today's time
from the dashboard without opening this integration's options. It reads two
different ways depending on what the helper has turned on:

| Helper has | Reads as | Applies |
| :--- | :--- | :--- |
| Time only | A time of day, same as `swim_time` | On the configured **Days**, every week |
| Date **and** time | A one-off appointment | Only on that date, regardless of **Days** — and stops applying once the date has passed |

The one-off form is for the household that does not swim on a fixed weekly
rhythm: turning on both date and time on the helper and picking, say, next
Wednesday at 14:00, heats for that occasion alone without permanently
adding Wednesday to the recurring schedule. Nobody has to remember to clear
it afterwards — a date that has passed is simply stale and falls back to
the static fields, exactly like an empty helper.

`swim_skip_entity`, an `input_boolean`, excludes today from every source —
entity or static, recurring or one-off — when turned on, for "not swimming
today" without touching the schedule itself.

**Seeing what was picked up.** The deadline a plan was actually computed
against, whichever source supplied it, is not only acted on:

- `sensor.<name>_swim_deadline` shows it directly.
- `sensor.<name>_ready_at`'s attributes add `deadline` and an `on_time`
  flag, so "will it make it in time" has a visible answer next to "when
  will it be ready".
- The panel's Planning tab shows swim time next to Ready at, with an
  on-track/won't-make-it note.

---

## Dynamic Electricity Price Integrations

PoolSmart parses hourly price attributes automatically from popular Home
Assistant integrations (such as Nordpool, EnergyZero, Frank Energie, ENTSO-E,
or custom template sensors).

### Price Optimization Logic

1. **Window selection:** The optimizer maps the required heat-up duration
   against upcoming price slots before the scheduled swim time.
2. **COP-weighted cost:** It adjusts the effective cost per thermal kWh using the
   self-learning COP curve. A slightly higher electricity price at 22 °C air
   temperature might actually be cheaper per thermal kWh than a lower price at
   12 °C air due to higher heat pump COP.

![COP-weighted cost comparison showing effective cost per thermal kWh](images/cop-weighted-cost.svg)

3. **Fallback mode:** If no valid price entity or forecast attribute is found,
   PoolSmart falls back to **heating on demand** whenever temperature drops
   below hysteresis.

---

## Solar Surplus

Above a threshold of surplus solar power, heating is treated as free and the
price limit is ignored. The threshold is not a fixed number, because the right
value is a property of the installation: it has to be at least what the heat pump
and circulation pump draw together. For a 3 kW heat pump taking 580 W with a
100 W pump that is 680 W, plus a margin so a passing cloud does not start and
stop a session.

Leave the setting empty and it is calculated. Set it too low and you consume more
than you generate; set it too high and you decline free heat on moderately sunny
afternoons.

`sensor.<name>_solar_surplus` shows the current figure with the threshold, the
shortfall and the equipment draw as attributes, so "is this enough" has a visible
answer.

![Solar surplus threshold concept showing when heating is treated as free](images/solar-surplus.svg)

---

## Demand / Power Limiter

The complementary gate to the solar threshold above: a house-power cap above
which heating pauses, regardless of price or solar surplus. Map a smart-meter
or energy-dashboard sensor reading total household power under **Weather and
price**, and set a cap in watts under **When to heat** — leave either blank
and the limiter is simply absent.

Where solar surplus is a floor that allows heating regardless of price, the
limiter is a ceiling that forbids it regardless of anything else, including
Boost: it exists to protect a hard electrical or contract limit (a peak
tariff, a kWh contract, a 3-phase breaker), not to optimise cost, so a
manual override should not be able to blow through it. It pauses a session
that is already running just as readily as it blocks one from starting, if
the rest of the house's draw climbs over the cap mid-session — a
notification fires on both the pause and the resume.

---

## See Also

- [Architecture](architecture.md) — How the heat pump's operating envelope
  gates heating sessions (Branch 6 of the decision ladder).
- [Learning](learning.md) — How the COP curve per temperature band and
  thermal loss rates are learned over time and fed into the planner.
- [Sensors](sensors.md) — How to map your price sensor and solar sensors.
- [Heating](heating.md) — Heating sources and how solar collectors are handled.
