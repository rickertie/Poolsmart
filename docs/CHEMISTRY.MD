> [? Back to README](../README.md) | [Getting Started](GETTING_STARTED.MD) | [Architecture](architecture.md) | [Configuration](configuration.md) | [Troubleshooting](troubleshooting.md)

---

# Water Chemistry

This document covers PoolSmart's water chemistry features: dosing calculations,
test scheduling, circulation timing, and the dose log. For the decision ladder
that executes chemistry cycles, see [architecture.md](architecture.md). For
advanced water chemistry (saturation index, alkalinity, calcium hardness), use
a diffrent intergation for that alongside PoolSmart.

---

## What PoolSmart Handles

PoolSmart handles the part of water chemistry that needs the pool's own numbers:
turning a reading into an amount, scheduling the next test, and circulating
afterwards.

### A Dose, Not a Number

A pH of 7.82 becomes "18 ml of pH-minus". The calculation uses the volume you
entered at setup, so it is your pool's dose rather than a figure from a chart.
Corrections larger than 0.4 pH are truncated and said so: pH is buffered by
alkalinity in a way this arithmetic does not model, and attempting a whole point
in one go overshoots.

### A Test Interval That Follows the Temperature

Chlorine burns off faster in warm water and algae grow faster in it, so a fixed
three-day reminder is too often in spring and not often enough in a heatwave.
The pool already knows its own temperature: five days below 20 °C, down to
daily above 30 °C.

![Chemistry test intervals based on water temperature](images/chemistry-intervals.svg)

### Circulation That Matches the Product

One fixed duration was always going to be wrong, because the products are not
comparable: non-chlorine shock is done in half an hour, a maintenance dose of
chlorine wants four hours, chlorine shock wants a full night so it reaches every
corner and gets pulled through the filter, and an algae treatment runs until the
water is visibly clear. Stopping early leaves undissolved product on the floor
bleaching the liner. A tablet gets no cycle at all — it dissolves over days in
a floater, so there is nothing to circulate now.

Chemistry sits above the filtration branches in the ladder, so a day whose
filtration quota is already met cannot suppress it. Dosing in the evening still
gets its circulation.

### A Dose Log That Learns (NOT implemented, yet :-))

Record what you added; the next test records what it achieved. After a few doses
the recommendation is corrected for how your pool actually responds — alkalinity,
stabiliser and the age of your chemicals all shift it, and none of them is
modelled. Measuring beats pretending.

---

## What This Is Not

This is not a water chemistry integration, and it does not try to become one.
There is no saturation index, no calcium hardness dosing, no alkalinity
correction. What is here is the part that needs the pool's own numbers — a dose
worked out from your volume, a test interval that follows water temperature, and
the pump running afterwards for as long as that particular product needs.

Every reading an Check strip produces can be recorded and judged against its
ideal range, including the ones nothing is calculated from: alkalinity, cyanuric
acid, hardness, and salt for electrolysis systems. Keeping the record and saying
plainly when a figure has drifted is worth doing even where a dose is not.

The conclusions that need several readings together are drawn as well, because
those are the ones a column of numbers hides: combined chlorine high enough that
shocking beats topping up, stabiliser high enough that adding chlorine achieves
nothing, pH and alkalinity both adrift with alkalinity as the one to fix first.

---

## See Also

- [architecture.md](architecture.md) — How the chemistry cycle branch (Branch 3) fits in the decision ladder
- [configuration.md](configuration.md) — How to configure sanitiser type, chemistry products, and doses
- [filtration.md](filtration.md) — How chemistry circulation interacts with filtration runtime
