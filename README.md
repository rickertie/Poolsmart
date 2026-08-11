# :swimmer: PoolSmart

> Intelligent swimming pool controller for Home Assistant — ESPHome measures, HA decides.

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-blue.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![Version](https://img.shields.io/github/v/release/rickertie/Poolsmart.svg)](https://github.com/rickertie/Poolsmart/releases)
[![License](https://img.shields.io/badge/license-AGPL--3.0--or--later-orange.svg)](LICENSE)

PoolSmart turns your pool into a self-optimizing system. A single priority ladder
evaluates every 30 seconds, the first matching branch wins, and every decision
comes with a plain-language reason. Works for a 1000 L inflatable and a 50000 L
in-ground pool alike — enter volume, pump flow, and heat pump specs at setup,
and everything else is derived.

---

## :white_check_mark: Features

- :recycle: **Smart filtration** — runtime from pool volume and measured flow, not a fixed timer
- :thermometer: **Heat pump control** — plans heating around dynamic prices and solar surplus
- :chart_with_upwards_trend: **Self-learning** — learns heat loss, heating rate, and COP from every session
- :droplet: **Water chemistry** — turns pH readings into doses using your pool's volume
- :sunny: **Solar optimization** — heats with free surplus, advises on manual collector valves
- :calendar: **Price-aware scheduling** — works backwards from when you want to swim
- :shield: **Compressor protection** — minimum off/run times enforced independently
- :robot: **AI advisory** — suggests settings, applies nothing without approval
- :bell: **Actionable notifications** — "heat now anyway", "circulate only", "apply suggestion"
- :desktop_computer: **Dashboards** — detailed three-tab view and simple household page

---

## :wrench: Installation

1. Add this repository to HACS as a **custom repository** and install PoolSmart
2. Restart Home Assistant
3. **Settings → Devices & Services → Add Integration → PoolSmart**
4. Work through the wizard — every field arrives pre-filled with a help line

> :information_source: To start the wizard with your own figures, see
> [docs/DEFAULTS.md](docs/DEFAULTS.md).

---

## :page_facing_up: Documentation

| Topic | Document | What you will find |
|---|---|---|
| Architecture & decision core | [docs/architecture.md](docs/architecture.md) | Priority ladder, filtration math, entity fallbacks, AI layer, compressor protection |
| Heating planning & prices | [docs/planning.md](docs/planning.md) | Maintenance vs. seasonal mode, price integrations, COP-weighted cost |
| Self-learning model | [docs/learning.md](docs/learning.md) | Learned parameters, three validation rules, session logging |
| Filtration | [docs/filtration.md](docs/filtration.md) | Turnover, daily minimum, filter media, flow meters, delta-T |
| Heating sources | [docs/heating.md](docs/heating.md) | Heat pump, electric, solar, gas; pool construction; solar surplus |
| Water chemistry | [docs/chemistry.md](docs/chemistry.md) | Dosing, test intervals, circulation timing, dose log |
| Logging & diagnostics | [docs/logging.md](docs/logging.md) | Logbook entries, notifications, full trace, diagnostics export |
| Entity IDs | [docs/entities.md](docs/entities.md) | Fixed IDs, translated names, source sensors |
| Management panel | [docs/panel.md](docs/panel.md) | Six-tab sidebar panel at `/poolsmart` |
| Configuration | [docs/configuration.md](docs/configuration.md) | Options flow, entity reassignment, thermostat recommendation |
| Hardware & wiring | [docs/hardware.md](docs/hardware.md) | Bill of materials, pinouts, voltage divider |
| ESPHome setup | [docs/esphome.md](docs/esphome.md) | Board configuration, probe calibration, flow meter bucket test |
| Sensor mapping | [docs/SENSORS.md](docs/SENSORS.md) | Which sensor goes where, calibration procedures |
| Dashboards | [docs/lovelace/README.md](docs/lovelace/README.md) | Installing and customizing the Lovelace dashboards |
| Pre-filling the wizard | [docs/DEFAULTS.md](docs/DEFAULTS.md) | Starting the wizard with your own figures |
| Brand images | [docs/BRAND_IMAGES.md](docs/BRAND_IMAGES.md) | Integration icon and logo, HACS workaround |
| Troubleshooting | [docs/troubleshooting.md](docs/troubleshooting.md) | Fault isolation, flow warnings, sharing diagnostics |
| Development | [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Running tests, project status, contributing |
| Changelog | [CHANGELOG.md](CHANGELOG.md) | Every release from v0.8.0 to present |

---

## :gear: Configuration

**Configure** opens eight topics: sensors, pool, heating, when to heat,
filtration, water, notifications, advanced. Nothing is locked in. Optional
entities may be left blank; the matching capability switches off cleanly.

> :page_with_curl: [docs/configuration.md](docs/configuration.md)

---

## :chart_with_upwards_trend: Self-Learning

Learns heat loss, heating rate, and COP per 5 °C outdoor band from every cleanly
closed session. Three rules keep it honest: clean sessions only, capped updates,
physical outlier rejection. Learned history survives a reinstall.

> :page_with_curl: [docs/learning.md](docs/learning.md)

---

## :calendar: Planning & Heating

**Maintenance** compensates daily heat loss (reports a time); **seasonal** warms a
cold pool (reports a date). Reads price forecasts, weights cost by COP, falls back
to heating on demand. Supports heat pump, electric, solar, gas, or none.

> :page_with_curl: [docs/planning.md](docs/planning.md) |
> Sources: [docs/heating.md](docs/heating.md)

---

## :droplet: Water Chemistry

Turns pH 7.82 into "add 18 ml of pH-minus" using your volume. Test intervals
follow temperature: five days below 20 °C, daily above 30 °C. Circulation
matches the product: 30 min for non-chlorine shock, a full night for chlorine
shock, none for tablets in a floater.

> :page_with_curl: [docs/chemistry.md](docs/chemistry.md)

---

## :desktop_computer: Dashboards

`dashboard.yaml` — three tabs, every figure. `simple.yaml` — is it warm, is the
water fine, when can I swim. Both in `docs/lovelace/`.

> :page_with_curl: [docs/lovelace/README.md](docs/lovelace/README.md)

---

## :shield: Safety

The control decision is the only part of a tick that may not fail. Compressor
minimum off/run times are enforced separately; no branch can override them.

> :page_with_curl: [docs/architecture.md](docs/architecture.md)

---

## :robot: AI Layer

Optional and advisory. Reads session history, suggests settings changes, waits.
Nothing applied without pressing accept. Validated against hard ranges — a safety
limit cannot be suggested away.

> :page_with_curl: [docs/architecture.md#ai-advisory-layer](docs/architecture.md)

---

## :bug: Troubleshooting

Faults are isolated per subsystem. Everything that failed shows up in Diagnostics
and the status sensor's attributes. Heat pump minimum flow is a warning, not a
stop. Download diagnostics from the device menu.

> :page_with_curl: [docs/troubleshooting.md](docs/troubleshooting.md)

---

## :balance_scale: License

AGPL-3.0-or-later
