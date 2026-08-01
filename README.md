# 🏊 PoolSmart

![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)
![License](https://img.shields.io/badge/license-AGPL--3.0--or--later-blue.svg)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Integration-41BDF5.svg)

> Smart swimming pool automation for Home Assistant.
> Smarter filtration, cheaper heating, and a lot less manual tinkering.

PoolSmart is a Home Assistant integration that runs your swimming pool for
you. It continuously balances filtration, heating, electricity prices,
weather and how often you actually swim so the pool is ready when you want
it, using as little energy as possible.

Whether you have a small inflatable pool or a 30,000 litre in-ground pool
with a heat pump, PoolSmart adapts to your setup instead of making you edit
YAML every time something changes.

---

> ⚠️ **AI Notice**
>
> PoolSmart was developed with significant assistance from AI. The
> architecture, algorithms and safety logic have been designed, reviewed and
> tested by the project maintainer, but bugs may still exist.
>
> If you find an issue or have an improvement in mind, please open an Issue
> or Pull Request it's genuinely welcome.

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

Most pool automations are built from dozens of separate YAML automations.

That works... until Home Assistant restarts.
...until a timer gets lost.
...until heating and filtration start fighting each other.
...until you find yourself wondering:

> "Why did the pump suddenly turn on?"

PoolSmart solves that by replacing dozens of independent automations with a
single decision engine that always knows **why** it made a decision and
can tell you.

## How it works

Every 30 seconds, PoolSmart checks a fixed priority ladder from emergency
stop and frost protection at the top, down to scheduled filtration and idle
at the bottom. The first rule that applies wins, and nothing below it runs.
No fighting automations, no race conditions, no mysterious pump starts.

A gate in front of the heating branches also checks the heat pump's
operating envelope: below its minimum air temperature, nothing can heat the
pool not a negative price, not even frost protection, which falls back to
simple circulation instead. Moving water doesn't freeze.

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
afterwards — everything can be changed later under **Configure**, including
entities, pool and equipment specs, prices, and swimming times.

## 🔧 Example setup

PoolSmart doesn't care what's measuring your pool, as long as the entities
exist in Home Assistant but here's a real one, so you have something
concrete to start from.

The author runs it on an **Intex Metal Frame pool (3,834 L)** with a
**Bestway Flowclear** filter pump and a **W'eau Mini** heat pump, all fed by
a single **Seeed XIAO ESP32C6** running ESPHome: five Dallas temperature
sensors (pool, pump in/out, heat pump in/out, outdoor) and a pulse-based
flow meter. The ESP32 does the light, fast local math delta-T, measured
and predicted COP, heating rate and hands clean numbers to Home Assistant,
where PoolSmart takes it from there.

📖 The full ESPHome configuration, wiring notes and calibration steps live in
[`docs/esphome.md`](docs/esphome.md) — parts list, wiring and photos of the
build are in [`docs/hardware.md`](docs/hardware.md).

## 📸 Dashboard

![Dashboard](docs/images/dashboard.png)

The dashboard shows:

- Current operating mode
- Today's filtration progress
- Planned heating sessions
- Energy usage
- AI recommendations
- Diagnostics

A sidebar panel at `/poolsmart` gives you six tabs overview, planning,
sessions, learning, settings and diagnostics for anyone who wants to dig
deeper than the dashboard shows.

## Designed for

🏡 Home Assistant users
⚡ Dynamic energy prices
🌞 Solar owners
❄️ Cold climates
🏊 Heat pump pools
❤️ People who are tired of maintaining twenty automations

## 📚 Documentation

The README stays high-level on purpose. For the technical deep dives:

- [`docs/architecture.md`](docs/architecture.md) — the decision ladder, filtration
  formula, entities and configuration options, and developer/test setup
- [`docs/planning.md`](docs/planning.md) — how maintenance vs. seasonal heating
  planning works
- [`docs/learning.md`](docs/learning.md) — how the self-learning heating model
  works and stays honest
- [`docs/esphome.md`](docs/esphome.md) — a real ESPHome hardware example, sensors
  and calibration steps
- [`docs/hardware.md`](docs/hardware.md) — parts list, wiring and installation
  photos

## Status

| Work package | State |
|---|---|
| Foundation: config flow, storage, models | done |
| Control core: coordinator, ladder, filtration, safety, entities | done |
| Planning and learning: optimizer, session recorder, COP curve | done |
| Notifications and Lovelace page | done |
| Sidebar management panel | done |
| AI advisor, chemistry and cover modules | done |

## Contributing

Ideas, bug reports and Pull Requests are always welcome.

If PoolSmart saves you time — or simply keeps your pool warm without you
thinking about it — consider starring the repository. It really helps the
project grow.

## FAQ

**Do I need a flow meter, power sensors, or a price sensor?**
No — every optional entity can be left blank. The matching feature just
switches itself off and shows up clearly in diagnostics instead of failing.

## Licence

GNU General Public License v3.0

---

*Built for the Home Assistant community ❤️*
