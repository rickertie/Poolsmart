# 🏊 PoolSmart

![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)
![License](https://img.shields.io/badge/license-AGPL--3.0--or--later-blue.svg)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Integration-41BDF5.svg)

> Smart swimming pool for Home Assistant.
> Smarter filtration, cheaper heating, and a lot less manual tinkering.

PoolSmart is a Home Assistant integration that runs your swimming pool for
you. It continuously balances filtration, heating, electricity prices,
weather and how often you actually swim — so the pool is ready when you want
it, using as little energy as possible.

Whether you have a small inflatable pool or a 30,000 litre in-ground pool
with a heat pump, PoolSmart adapts to your setup instead of making you edit
YAML every time something changes.

---

> ⚠️ **AI Notice**
>
> PoolSmart was developed with significant assistance from AI.(I Know :-)) The
> architecture, algorithms and safety logic have been reviewed and
> tested by me, but bugs may still be around.
>

## ✨ Features

✔ Intelligent filtration scheduling
✔ Heat pump optimisation
✔ Dynamic electricity price optimisation
✔ Weather-aware heating
✔ Self-learning heating model
✔ Automatic runtime calculation
✔ Frost protection
✔ Safety-first decision engine
✔ Optional AI recommendations
✔ Zero YAML automations

## Why PoolSmart?

My first pool automations was built from dozens of separate YAML automations.

That works... until Home Assistant restarts.
...until a timer gets lost.
...until heating and filtration start fighting each other.
...until you find yourself wondering:
> "Why did the pump suddenly turn on?"

I would try to have PoolSmart solves that by replacing the automations with a decision engine that always knows **why** it made a decision and
can most important tell me/you what the hell happend.

## How it works

Every 30 seconds, PoolSmart checks a fixed priority ladder — from emergency
stop and frost protection at the top, down to scheduled filtration and idle
at the bottom. The first rule that applies wins, and nothing below it runs.

A gate in front of the heating branches also checks the heat pump's
operating envelope: below its minimum air temperature, nothing can heat the
pool, not a negative price, not even frost protection, which falls back to
simple circulation instead. Moving water.

Filtration time, heating sessions and the energy budget are all calculated
from your pool's own volume, pump flow and heat pump specs not hardcoded,
so a small inflatable pool and a large in-ground pool both just work.

📖 Full details on the decision ladder, filtration formula and configuration
options live in [`docs/architecture.md`](docs/architecture.md).

## Installation

1. Add this repository to HACS as a custom repository and install PoolSmart.
2. Restart Home Assistant.
3. Settings → Devices & Services → Add Integration → PoolSmart.
4. Work through the five setup steps. Only the last two ask for entities,
   and only three of those are actually required.

Every field has a help line with a worked example. Nothing is locked in
afterwards everything can be changed later under **Configure**, including
entities, pool and equipment specs, prices, and swimming times.

## 🔧 Example setup

My own pool, for my Kids and me ;-) : 
 
**Intex Metal Frame pool (3,834 L)** Pool
**Bestway Flowclear** filter pump
**W'eau Mini** heat pump

**Seeed XIAO ESP32C6** running ESPHome
	five Dallas temperature sensors (pool, pump in/out, heat pump in/out, outdoor) and a pulse-based
	flow meter to the Heatpump. 

The ESP32 does the light, fast local math delta-T, measured
and predicted COP, heating rate and hands numbers to Home Assistant,
where this intergration takes it from there.

📖 The full ESPHome configuration, wiring notes and calibration steps live in
[`docs/esphome.md`](docs/esphome.md).

## 📸 Dashboard

![Dashboard](docs/images/dashboard.png)

The dashboard shows:

- Current operating mode
- Today's filtration progress
- Planned heating sessions
- Energy usage
- AI recommendations
- Diagnostics

A sidebar panel at `/poolsmart` gives you six tabs — overview, planning,
sessions, learning, settings and diagnostics — for anyone who wants to dig
deeper than the dashboard shows.

## Designed for

🏡 Home Assistant
⚡ Dynamic energy prices
🌞 Solar owners
❄️ Cold climates
🏊 Heat pump pools
❤️ ESPHome Sensors

## 📚 Documentation

For the technical thingie dingies:

- [`docs/architecture.md`](docs/architecture.md) — the decision ladder, filtration
  formula, entities and configuration options, and developer/test setup
- [`docs/planning.md`](docs/planning.md) — how maintenance vs. seasonal heating
  planning works
- [`docs/learning.md`](docs/learning.md) — how the self-learning heating model
  works and stays honest
- [`docs/esphome.md`](docs/esphome.md) — a real ESPHome hardware example, sensors
  and calibration steps
  
## Status

- [x] Foundation: config flow, storage, models
- [ ] Control core: coordinator, ladder, filtration, safety, entities
- [ ] Planning and learning: optimizer, session recorder, COP curve
- [ ] Notifications and Lovelace page
- [ ] Sidebar management panel
- [ ] AI advisor
- [ ] chemistry and cover modules

## Contributing :tada:

/

## FAQ

**Do I need a flow meter, power sensors, or a price sensor?**
No: every optional entity can be left blank. The matching feature just
switches itself off and shows up clearly in diagnostics instead of failing.

## Licence

AGPL-3.0-or-later.

---
*Built for the Home Assistant community ❤️*