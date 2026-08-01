# PoolSmart 0.8.0

First public release.

An intelligent pool controller for Home Assistant: ESPHome measures, Home
Assistant decides, and every decision comes from a single priority ladder that
records why it did what it did.

Built for an Intex frame pool with a W'eau heat pump, but nothing is hardcoded to
that. Volume, pump flow and heat pump figures are entered at setup and everything
else is derived, so a 1000 litre inflatable and a 50000 litre in-ground pool both
work.

## What it does

**Decides when to run.** One ladder of ten branches, walked top to bottom every
30 seconds. The first branch that matches wins and produces a decision with a
plain-language reason attached. Modes (Auto, Boost, Eco, Pump, Stand-by, Off)
enable or disable branches rather than carrying their own logic, so there is
exactly one place where control lives.

**Plans heating around price and sun.** Small top-ups get slotted into the
cheapest hours before your swimming time. A cold pool needs ten to fifteen hours
of running, which does not fit in one day of cheap hours, so that becomes a
multi-day plan and the interface shows a *date* rather than a time it cannot
meet.

**Works out filtration properly.** The daily requirement is the larger of two
rules: turnover (volume-based, defaulting to three passes because filtered water
mixes back in and one pass only cleans about 63% of the pool) and a time-based
daily minimum that rises with water temperature. Skimming and sanitiser contact
depend on hours running, not on how fast the pump is, which is why a faster pump
does not mean less filtering.

**Learns.** Heating rate, heat loss and a COP figure per five degree band of
outdoor temperature, updated after each session. Only cleanly closed sessions are
used, every update is capped so one odd session cannot wreck the model, and
rejected sessions stay in the log with the reason.

**Explains itself.** A sidebar panel with six tabs: overview, planning, sessions,
learning, settings, diagnostics. The decision log is recorded at the moment of
deciding rather than reconstructed afterwards.

**Fails gracefully.** Only the control decision may not fail. Planning, learning,
energy bookkeeping and notifications each run in their own guard, so a hiccup in
one does not take the integration off your dashboard. Every optional entity may
be left blank; the matching feature switches off and says so rather than
erroring.

## Requirements

- Home Assistant 2024.10 or newer (2026.3+ for the integration's own icon)
- A switch for the circulation pump, a switch for the heat pump, and a water
  temperature sensor. Everything else is optional.

## Installing

HACS → three dots → Custom repositories → add this repository as an Integration →
install → restart → Settings → Devices & services → Add integration → PoolSmart.

The wizard is five steps and every field arrives pre-filled with a help line
explaining where to find the real number. To start from your own figures, drop a
`poolsmart_defaults.json` in your configuration directory; see
[docs/DEFAULTS.md](docs/DEFAULTS.md).

A complete three-tab dashboard is in
[docs/lovelace/dashboard.yaml](docs/lovelace/dashboard.yaml) — paste the whole
file into the raw configuration editor.

## Known issues

**HACS shows "icon not available".** The integration ships its own brand images,
which is the mechanism Home Assistant 2026.3 introduced, but the HACS frontend
bundle predates it and still asks the public CDN. Cosmetic only, and it resolves
itself when HACS ships a rebuilt frontend
([hacs/integration#5223](https://github.com/hacs/integration/issues/5223)). The
icon does appear under Settings → Devices & services.

**The AI review needs an AI task entity.** Without one it says so rather than
failing silently. The rest of the integration does not depend on it.

**The management panel is read-only.** Settings are changed through the
integration's own configuration screens.

## Things worth knowing

**Check your flow meter's unit.** Pool meters usually report L/min while heat
pump datasheets quote m³/h — 2 m³/h is 33 L/min. The unit is read from the sensor
where it publishes one, and picked in the wizard otherwise.

**Falling below the datasheet flow minimum is a warning, not a stop.** Datasheet
figures are conservative and the appliance has its own flow switch. If your
installation settles below the quoted number and delta-T looks sensible, set the
minimum to what it actually achieves.

**Set the heat pump's own thermostat above your maximum, not at it.** Two degrees
above is a good rule. Below that you keep full software control; above it the
hardware catches a software failure.

**Tick "measured" if you have a flow meter.** Otherwise the datasheet flow is
derated for filter resistance, and datasheet figures are optimistic.

## Tests

40 acceptance tests covering the decision ladder, filtration, safety, planning,
learning, flow unit handling and the entity id migration. The decision core has
no Home Assistant imports, so it runs standalone:

```bash
cd tests && python run_tests.py
```

## Licence

AGPL-3.0-or-later.
