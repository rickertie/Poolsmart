# PoolSmart 1.0.0 — Knowledge, Not Storage

First stable release.

An intelligent pool controller for Home Assistant: ESPHome measures, Home
Assistant decides, and every decision comes from a single priority ladder that
records why it did what it did.

## Why this release is 1.0

Because the learning finally works. Two of the four learned values — the measured
COP curve and the heating rate — were being recorded after every session, stored,
displayed on a dashboard, and read by no calculation at all. Planning ran on the
datasheet.

On the installation this was found on that meant estimating 1h29 per degree where
the measurements said 2h17. Fifty-four percent optimistic: three hours predicted
for a rise that takes four and a half, so heating started too late and the pool
was cold at swimming time.

Both are used now, in order of directness: the measured heating rate first, then
the measured COP for the current temperature band, then the datasheet. Each
learned value names the decision that reads it, because a value nobody reads is
not knowledge, it is storage.

## What is new

**Water chemistry.** A pH reading becomes an amount, calculated from your pool
volume. The test interval follows water temperature — five days below 20 °C, down
to daily above 30 °C, because chlorine burns off faster in warm water. A dose log
records what you added and what it achieved, and corrects future recommendations
for how your pool actually responds.

**Diagnostics that answer the question.** The ladder trace now shows the numbers
behind each verdict, what would have to change for a branch to win, and how much
of the day each branch spent in charge.

**Fewer meaningless warnings.** Probes that only matter while the heat pump runs
stay quiet while it is off. The calibration check waits for the pump to have
mixed the water, because standing water stratifies and that is physics rather
than a fault. A brief sensor outage — an ESP reboot takes ten seconds — no longer
stops a heating session.

## Upgrading

Nothing to do. Entity ids are unchanged since 0.7.0.

If you were running an earlier version, the heating time estimates will change,
probably substantially, once three sessions have been recorded in a temperature
band. That is the point.

## Not included

Saturation indices, alkalinity and calcium hardness. Use
[ha-poolchem](https://github.com/joyfulhouse/ha-poolchem) for those; it does the
job properly and works with any sensor source. PoolSmart handles the part that
needs the pool's own numbers and does not reimplement the rest.

## Tests

85 acceptance tests against a decision core with no Home Assistant imports:

```bash
cd tests && python run_tests.py
```

Most of them exist because something went wrong on a real pool first.

## Licence

AGPL-3.0-or-later.
