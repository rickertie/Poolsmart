# PoolSmart

An intelligent swimming pool controller for Home Assistant. ESPHome measures,
Home Assistant decides, and every decision comes from a single priority ladder.

Works with any pool: volume, pump flow and heat pump specification are entered at
setup, and filtration duration, heating time and the energy budget are derived
from them. A 1000 litre inflatable and a 30000 litre in-ground pool both work
without touching code.

## Why it is built this way

The design solves four problems that YAML automations cannot:

| Problem | How PoolSmart handles it |
|---|---|
| A running timer is lost on restart | Filtration runtime is stored as closed intervals, not a counter |
| Learned values get corrupted by odd sessions | Updates are capped per step and outliers are skipped |
| Threshold comparisons oscillate | Blocks are states with an end time, not thresholds |
| "Why is it doing that?" | The reason is recorded at the moment of deciding, not reconstructed |

## The decision ladder

Every 30 seconds the ladder is walked from the top. The first branch that matches
wins, and lower branches are not evaluated.

| # | Branch | Ignores night quiet |
|---|---|---|
| 0 | Emergency stop | yes |
| 1 | Frost and minimum-temperature protection | yes |
| 2 | Manual control | yes |
| 3 | Chemistry cycle | yes |
| 4 | Filtration deadline | yes |
| 5 | Free electricity (price below zero) | yes |
| 6 | Heating session | no |
| 7 | Scheduled filtration block | no |
| 8 | Pump rundown | no |
| 9 | Idle | — |

Modes do not carry their own logic; they enable or disable branches.

**Off means off.** Nothing runs, including frost protection. An earlier version
kept protection alive on the reasoning that an off switch should not cause
damage, but the pool may have been drained and dismantled for the winter, and a
system that starts a pump against an explicit instruction is worse than one that
lets an unattended pool freeze. Frost protection lives in **Stand-by**, which is
the mode meaning "not swimming, but the pool is still there".

In front of branches 5 and 6 sits a gate: the heat pump's operating envelope.
Below its minimum air temperature nothing can heat the pool, not even a negative
price and not even the minimum-temperature protection. That protection can only
circulate, which is enough, because moving water does not freeze.

## Installation

1. Add this repository to HACS as a custom repository and install PoolSmart.
2. Restart Home Assistant.
3. Settings → Devices & Services → Add Integration → PoolSmart.
4. Work through the steps. How many there are depends on how the water is
   heated: each step asks only what that heating source can answer, and a pool
   with no heating skips the heating step entirely. Only the last two steps ask
   for entities, and of those only the pump switch and the pool water
   temperature are always required — a heat pump adds its own switch, and a
   collector on a manual valve adds none.

Every field arrives with a value already in it and a help line underneath
explaining where to find the real number, with a worked example. Water surface
may be left blank; it is calculated from volume and depth.

The built-in values describe a generic mid-sized pool, not anyone's actual one.
To start the wizard from your own figures instead, put a
`poolsmart_defaults.json` in your configuration directory — see
[docs/DEFAULTS.md](docs/DEFAULTS.md), which includes a ready-made example.

### Changing things afterwards

Nothing is locked in. Settings → Devices & Services → PoolSmart → **Configure**
opens a menu of subjects:

| Section | Contains |
|---|---|
| Sensors and switches | Every switch and sensor, including the required ones. The heat pump's own sensors and the collector sensor only appear when the heating source has them |
| Pool and pump | Volume, depth, pump flow, pump power, units, sanitiser, filter medium |
| Heating appliance | The heating source and everything that follows from it: heat pump figures, the efficiency curve, the operating envelope, the solar collector. A source without a heat pump is not asked about one |
| When to heat | Target temperature, price ceiling, solar surplus, swimming time |
| Filtration | Turnover, quiet hours, pump rundown |
| Water treatment | Sanitiser, chemistry products, doses |
| Notifications | Which message goes to which device |
| Advanced | Timings and tolerances for when a measurement misbehaves |

Picking the wrong temperature sensor during setup is easy to do, so the entity
choices live in options where they can be corrected rather than in the entry data
where they could not.

Every optional entity may be left blank. The matching capability is switched off
and listed in diagnostics rather than failing.

| Left blank | What stops working |
|---|---|
| Outdoor temperature | Operating envelope check; falls back to the weather entity |
| Heat pump inlet or outlet | Delta-T and COP learning |
| Flow meter | Flow protection and self-correcting block duration |
| Power sensors | Energy, cost and measured COP |
| Price sensor | Price optimisation, including the free-electricity branch |
| Solar sensors | Solar optimisation |

### A recommendation about the heat pump thermostat

Set the heat pump's own thermostat to the highest temperature you would ever want
plus about two degrees. If your maximum is 32 °C, set it to 34 °C. Below that you
keep full software control over any target, and above it the hardware intervenes
if the software ever fails to switch off. The setup wizard shows this suggestion
with your own numbers filled in.

## Filtration

Two rules decide the daily runtime, and the requirement is the larger of them.
Using only the first understates the runtime badly on pools with a generous pump.

**Turnover** is volume-based:

```
turnover runtime = pool volume x turnover factor / effective pump flow
```

Filtered water mixes back in with unfiltered water, so one turnover does not
clean the pool once — it cleans about 63% of it. Two turnovers reach 86%, three
reach 95%, four reach 98%. Three is where the gains flatten, so that is the
default.

**A daily minimum** is time-based, and turnover cannot substitute for it. A
skimmer only catches the leaves, pollen and insects that land on the surface
while it is actually running; sanitiser needs contact time; and water that sits
still for twenty hours grows algae however thoroughly it was filtered in the
other four. The familiar rule of thumb — about an hour of running per 10 °F of
temperature — is really this minimum in disguise, which is why it does not scale
down when you fit a faster pump.

The minimum rises with water temperature, from half the configured value in cold
water to one and a half times it above 30 °C.

Which rule is currently setting the requirement is shown in the panel, so the
daily figure is never an unexplained number.

### Worked examples

| Pool | Pump | Turnover | Minimum at 28 °C | Requirement |
|---|---|---|---|---|
| 3800 L | 3.6 m³/h | 3.2 h | 5 h | **5 h**, set by the minimum |
| 50000 L | 8 m³/h | 18.8 h | 5 h | **18.8 h**, set by turnover |

### Filter media

The medium in the filter changes how much of the rated pump flow actually
arrives. It is only used to estimate flow for people without a flow meter; with
one connected the real figure is used instead.

| Medium | Typical share of rated flow | Filters down to |
|---|---|---|
| Cartridge | 60% | 20–40 micron |
| Sand | 70% | 20–40 micron |
| Glass | 72% | 3–5 micron |
| Filter balls | 80% | 5–15 micron |

Filter balls are the one to watch. They flow more freely than sand when fresh,
but they compress and mat together over time, and a matted bed chokes the flow
far worse than sand ever does. A sustained drop in measured flow is the signal to
pull them out, wash them and fluff them up — the integration raises the filter
service warning for exactly this.

### Flow meters and units

A flow meter's unit is read from the sensor itself where it publishes one, and
otherwise from the setting in the wizard. Pool meters usually report **litres per
minute**, while the heat pump's datasheet minimum is quoted in **m³/h**, and the
two are easy to confuse: 2 m³/h is 33 L/min.

### Judging flow by delta-T, not by the datasheet

Flow in m³/h is a proxy. The temperature rise across the heat pump is the thing
the proxy stands for, and it can be measured directly.

A heat pump rejecting a fixed amount of heat into a stream of water raises it by
`kW / (flow × 1.163)` degrees. Halve the flow and the rise doubles. Starve it
further and the condensing temperature climbs until the appliance derates or
trips. So a genuine flow problem has a signature, and the signature is a **high**
delta-T — not a low number against a datasheet.

`sensor.<name>_flow_adequacy` reports the verdict: healthy under about 3 °C,
marginal to 5 °C, starved above that.

Worked example from a real installation: 1.05 m³/h against a 2.0 datasheet
minimum, delta-T 1.56 °C, output 1.9 kW. Opening the diverter valve raised flow
to 1.30 m³/h; delta-T fell to 1.27 °C and output stayed at 1.9 kW. The extra flow
bought nothing, because the system was never flow-limited. Chasing the datasheet
figure would have been chasing nothing.

If your installation reads healthy below the quoted minimum, tick **verified for
this installation** under Configure → Pool and equipment. That silences a warning
which otherwise repeats a number your plumbing cannot produce — and stops the AI
review recommending it.

Falling below the datasheet minimum is a **warning**, not a stop. Datasheet
figures are conservative and the appliance has its own flow switch, so plenty of
installations run below the quoted number without trouble — what matters is
whether the water carries the heat away, which shows up as a sensible delta-T. At
1 m³/h a 3 kW heat pump produces about 2.5 °C of rise, which is perfectly normal.

If your installation settles somewhere below the quoted figure, set the minimum
to what it actually achieves. The warning stops and the real protection — zero
flow, and the appliance's own switch — stays in place.

### Filter resistance

Manufacturers specify pump flow without a filter installed; with one in line
roughly 60-75% remains and it drops as the filter fouls. If you tick "measured"
the figure is used as it is; otherwise it is derated. With a flow meter connected
the block duration corrects itself as the filter ages, and a sustained decline
raises a service notification.

Heating sessions run the pump too, so that runtime counts towards the quota.
Without that credit the system would filter far more than needed on heating days.

## Development

The decision core in `custom_components/poolsmart/core/` has no Home Assistant
imports, so it runs and is tested standalone:

```bash
cd tests && python run_tests.py
```

The suite covers twenty-two acceptance cases, including regression tests for the
two bugs that prompted this rewrite: the pump sitting idle while the filtration
window closed, and the pump oscillating once the daily quota was met.

## Status

Version 1.0. Running daily on the installation it was built for, with 85
automated tests covering the decision core.

Still to come: pool cover support needs a sensor to learn from, and the chemistry
module covers pH and chlorine but not alkalinity or hardness — Pool Chem is the
answer for those.

## Planning

Heating is planned in one of two ways, and the difference is visible in the
interface.

**Maintenance** compensates a day's heat loss. The optimizer picks the cheapest
intervals before the next swimming time and reports a time.

**Seasonal** brings a cold pool up to temperature. That can be ten to fifteen
hours of running, which does not fit in one day of cheap hours, so the optimizer
projects across days and reports a **date**. If the pool loses heat as fast as
the heat pump can add it, it says so instead of producing a date it cannot meet.

The price limit is a preference, not a rule. If nothing under it is available
before the swimming time, the planner takes the cheapest intervals there are and
says so — arriving cold is a worse failure than paying a couple of cents over a
self-imposed ceiling. Without a deadline behind it, an expensive interval is
simply declined and it waits.

Price forecasts are read from whatever integration you use. Several attribute
shapes are recognised; if none is, planning falls back to heating on demand — and
says so, rather than describing the fallback as a chosen cheap moment.

Most dynamic tariff integrations also publish a **cheap period** binary sensor.
Point the integration at it and it outranks the fixed ceiling, because a ceiling
cannot tell a cheap hour from an expensive day: with a limit of 0.20 and a day
whose cheapest hour is 0.22, nothing would ever heat.

## What heats your pool

Setup asks three things before anything else: how the pool is built, what heats
it, and whether there is a solar collector alongside. Those answers decide which
of the later questions make sense at all.

| Source | What it has |
|---|---|
| Heat pump | Efficiency curve, minimum air temperature, compressor protection |
| Electric heater | None of those — always as efficient, works in any weather |
| Solar collector | Usually a manual valve, so the integration advises rather than switches |
| Gas heater | Fixed efficiency, no air temperature limit |
| No heating | Filtration, water chemistry and frost protection only |

These are not simplifications of a heat pump's behaviour; they are the absence
of things a heat pump has. Asking an element owner for a COP curve produces a
field they have to guess at, and a guess is worse than a default.

**A solar collector is advised, not controlled.** Almost every one is plumbed
through a manual three-way valve. The integration compares the collector against
the pool and says when opening it is free heat — and, just as usefully, when the
collector is colder than the pool and water sent through it would lose heat
rather than gain it.

**Pool construction sets a starting heat loss**, from 0.30 °C/h for an
uninsulated inflatable to 0.08 for a built-in pool. It is only a starting point,
replaced by measurement within days, but those first days are when someone is
deciding whether this works at all.

## Two dashboards

`docs/lovelace/dashboard.yaml` is the detailed one, with three tabs and every
figure the integration produces.

`docs/lovelace/simple.yaml` is for everyone else in the house. It answers three
questions — is it warm enough, is the water fine, when can I get in — and asks
nothing. Nothing on it changes a setting, because a page someone consults on the
way outside should not present them with decisions.

It also says whether electricity is cheap right now, judged against today's own
range rather than a fixed number: 0.24 is a bargain in January and daylight
robbery in a sunny week, and the figure alone does not say which.

## Settings

Eight topics rather than four sections and a bin marked "general". Saving
returns to the menu instead of closing, so changing three things is one visit.

**Advanced** is deliberately separate. Of the settings here, perhaps a third are
ones anybody adjusts on purpose; the rest exist for when a measurement
misbehaves. Mixing them made the first third harder to find.

## Learned history survives a reinstall

Removing an integration and adding it back gives it a new entry id, and the
storage key is built from that id — so weeks of measured heat loss, a COP curve
and a session history end up on disk under a key nothing reads any more.

Setup now looks for it and offers to adopt it, describing what it found: *14
sessions, heat loss 0.23 °C/h, last written 3 August.* Values this pool has
already measured for itself are kept, because those were measured on the actual
installation. The session and dose logs come across too — adopting a figure
without the evidence behind it leaves a number nothing can check or improve.

For backups and moving between systems there are `poolsmart.export_learning` and
`poolsmart.import_learning`. An export deliberately leaves out today's quota and
the current mode: those describe a moment rather than a pool.

## Units

One setting at installation, metric or US customary, changes how volumes and
doses are presented. Calculations stay metric throughout either way — doing it
the other way round would mean two sets of formulas and two sets of rounding
errors to keep in step. Temperatures are converted by Home Assistant itself.

## Solar

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

## Sensors

PoolSmart does not require ESPHome. It reads whatever temperature, flow and
power sensors you point it at, and calculates delta-T, thermal power and COP
itself from those readings.

That last part changed in 0.12.2. The example ESPHome configuration used to
calculate those three on the board, which meant they only existed for people
running ESPHome, and a calibration offset changed on one side left two numbers
disagreeing with no way to tell which was right. They now live in one place.

`docs/SENSORS.md` covers calibrating the probes, calibrating the flow meter with
a bucket, and which sensor to map to which field. The flow calibration is the one
worth being fussy about: filtration duration is calculated directly from flow, so
an error there becomes an error in how long the pump runs every day.

## Water chemistry

PoolSmart handles the part of water chemistry that needs the pool's own numbers:
turning a reading into an amount, scheduling the next test, and circulating
afterwards.

**A dose, not a number.** A pH of 7.82 becomes "18 ml of pH-minus". The
calculation uses the volume you entered at setup, so it is your pool's dose
rather than a figure from a chart. Corrections larger than 0.4 pH are truncated
and said so: pH is buffered by alkalinity in a way this arithmetic does not
model, and attempting a whole point in one go overshoots.

**A test interval that follows the temperature.** Chlorine burns off faster in
warm water and algae grow faster in it, so a fixed three-day reminder is too
often in spring and not often enough in a heatwave. The pool already knows its
own temperature: five days below 20 °C, down to daily above 30 °C.

**Circulation that matches the product.** One fixed duration was always going to
be wrong, because the products are not comparable: non-chlorine shock is done in
half an hour, a maintenance dose of chlorine wants four hours, chlorine shock
wants a full night so it reaches every corner and gets pulled through the filter,
and an algae treatment runs until the water is visibly clear. Stopping early
leaves undissolved product on the floor bleaching the liner. A tablet gets no
cycle at all — it dissolves over days in a floater, so there is nothing to
circulate now.

Chemistry sits above the filtration branches in the ladder, so a day whose
filtration quota is already met cannot suppress it. Dosing in the evening still
gets its circulation.

**A dose log that learns.** Record what you added; the next test records what it
achieved. After a few doses the recommendation is corrected for how your pool
actually responds — alkalinity, stabiliser and the age of your chemicals all
shift it, and none of them is modelled. Measuring beats pretending.

### What this is not

This is not a water chemistry integration, and it does not try to become one.
There is no saturation index, no calcium hardness dosing, no alkalinity
correction. What is here is the part that needs the pool's own numbers — a dose
worked out from your volume, a test interval that follows water temperature, and
the pump running afterwards for as long as that particular product needs.

Every reading an AquaChek strip produces can be recorded and judged against its
ideal range, including the ones nothing is calculated from: alkalinity, cyanuric
acid, hardness, and salt for electrolysis systems. Keeping the record and saying
plainly when a figure has drifted is worth doing even where a dose is not.

The conclusions that need several readings together are drawn as well, because
those are the ones a column of numbers hides: combined chlorine high enough that
shocking beats topping up, stabiliser high enough that adding chlorine achieves
nothing, pH and alkalinity both adrift with alkalinity as the one to fix first.

## Compressor protection

Minimum off and run times for the heat pump are enforced separately from the
ordinary decision hold, and no branch can override them. A hold protects a
decision and may be broken when waiting would be worse; a compressor needs its
refrigerant pressures to equalise before restarting, and that is not negotiable
by any rule about filtration deadlines.

Reaching the target temperature is the one thing that still stops heating
immediately — a minimum run time must never keep heating a pool that is done.

## Self-learning

Learned after each session: heating rate, heat loss, and a COP value per five
degree band of outdoor temperature. Because the heat pump does not modulate, one
value per band is sufficient.

Three rules keep the model honest:

1. Only cleanly closed sessions are used. Interrupted ones, ones with faults, and
   ones too short to measure are recorded and marked, not learned from.
2. Every update is capped at a fraction of the current value, so one strange
   session can nudge the model but never replace it.
3. Outliers are rejected on physical grounds -- a COP outside the appliance's own
   clamps, water that did not warm up while heating -- rather than statistically.

Rejected sessions stay in the log with the reason. When the model stops
improving, that is the first place to look.

## Entity ids

Entity ids are fixed in code rather than derived from the displayed name, so they
read the same on a Dutch and an English install: `sensor.pool_status`,
`binary_sensor.pool_heating`, `select.pool_mode`, where the prefix is the slug of
the name you gave the integration.

Displayed names are still translated. You see "Klaar om" in the interface while
the id stays `sensor.pool_ready_at` — names are for reading, ids are for
referring to. Home Assistant normally derives one from the other, which produced
`sensor.pool_klaar_om` on a Dutch system: fine for one person, useless in a
dashboard or automation anyone else might paste in.

Installed before 0.7.0? The ids are renamed once on startup and every rename is
written to the log.

Source sensors are not copied. The water and outdoor temperatures ride along as
attributes on `sensor.<name>_status` so a card can show them next to the reason,
but a graph should point at your own sensor.

## Dashboard

`docs/lovelace/dashboard.yaml` is a complete three-tab dashboard, ready to paste
into the raw configuration editor. See `docs/lovelace/README.md`.

## The management panel

A sidebar panel at `/poolsmart` with six tabs: overview, planning, sessions,
learning, settings and diagnostics. It is written as a plain custom element with
no build step and no external imports, so it keeps working without internet.

The panel is for whoever maintains the system. The Lovelace page in
`docs/lovelace/` is for everyone else, and the two are deliberately not the same
thing.

## Logs

Three kinds of entry appear in the standard Home Assistant **Logbook**, alongside
everything else that happened in the house. That context is most of the value: a
pump switching off at 20:00 means one thing alone and another next to "the shed
door opened at 19:58".

**Decisions.** What changed, the reason recorded at the moment of deciding, and
how long the previous state lasted. A branch change is logged even when the
switches do not move — the pump staying on for a different reason is still a
change of reasoning, and it used to be invisible.

**Obstacles.** What the ladder wanted to do but could not: the price was too
high, the mode excludes it, the heat pump is outside its limits, the night window
blocks it. This is the answer to "why is it not heating", and it is rate limited
so a pool waiting all evening for a cheaper price does not fill the logbook with
the same sentence.

**Faults.** Raised and cleared, so the duration is visible rather than inferred
from timestamps.

### Notifications you can answer

Notifications to a mobile app carry buttons. "Heating postponed" offers *Heat now
anyway* and *Do not heat today*; a flow fault offers *Circulate only* and *Switch
everything off*; the weekly review offers *Apply the suggestion*. Tapping one
acts immediately. Other notify platforms ignore the extra data and receive the
text as normal.

### The full trace

The panel's Diagnostics tab shows every branch of the ladder for the current
tick, with a verdict for each: chosen, price, outside limits, mode, night, not
applicable, or not reached. The ladder stops at the first match, so branches
below the winner genuinely were not evaluated — saying "not reached" is a fact
about how it works, not an omission.

### Sharing a problem

Settings → Devices & services → PoolSmart → the three dots → **Download
diagnostics**. That file has the trace, the decision log, a plain-sentence
timeline, learned values, faults and every derived figure, with no credentials in
it. It is the fastest way to hand someone the whole picture.

## When something goes wrong

The control decision is the only part of a tick that may not fail. Planning,
learning, energy bookkeeping and notifications each run inside their own guard,
so a fault in one of them is logged and skipped rather than taking the whole
integration off the dashboard. Entities stay available as long as a decision
exists, because the decision the pool is actually running on remains valid even
if an optional subsystem hiccuped.

Anything that did fail shows up under Diagnostics in the panel and in the status
sensor's attributes, with the full traceback in the Home Assistant log.

The heat pump's minimum flow is a **warning** by default rather than a stop.
Datasheet minima are conservative and the appliance has its own flow switch as a
hardware backstop, so overriding the owner on the strength of a brochure figure
is the wrong default. There is a toggle if you would rather it stopped. Zero flow
with the pump running is a different matter and does stop everything.

## The AI layer

Optional and advisory. It reads the session history, produces a summary and at
most a handful of suggested settings changes, and waits. Nothing is applied
without pressing accept.

Suggestions are validated against a fixed list of adjustable settings with hard
ranges; anything outside it is discarded. A safety limit cannot be suggested away.
If the AI is unavailable the pool behaves exactly as it otherwise would, because
this layer sits outside the control tick entirely.

## Brand images

The integration ships its own icon and logo in `custom_components/poolsmart/brand/`,
which is the mechanism Home Assistant 2026.3 introduced for custom integrations.
Nothing has to be submitted anywhere.

The icon appears under Settings → Devices & services. HACS still shows "icon not
available" because its frontend bundle predates this feature and asks the public
CDN instead of Home Assistant; that is
[a known HACS bug](https://github.com/hacs/integration/issues/5223) and resolves
itself when HACS ships a rebuilt frontend. See `docs/BRAND_IMAGES.md`.

## Elsewhere

- [`docs/SENSORS.md`](docs/SENSORS.md) — probe and flow meter calibration
- [`docs/DEFAULTS.md`](docs/DEFAULTS.md) — pre-filling the setup wizard
- [`docs/BRAND_IMAGES.md`](docs/BRAND_IMAGES.md) — the icon placeholder
- [`docs/lovelace/`](docs/lovelace/) — a complete dashboard
- [`docs/esphome/`](docs/esphome/) — example board configuration

## Licence

AGPL-3.0-or-later.
