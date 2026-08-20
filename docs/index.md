<div class="ps-hero" markdown>

<span class="ps-hero__kicker">HACS · ESPHome · Home Assistant 2024+</span>

PoolSmart turns your pool into a self-optimizing system. Automate filtration scheduling,
heat pump control, solar optimization, and water chemistry dosing — all integrated with
Home Assistant. A priority-based decision engine evaluates your pool state every 30 seconds,
balancing energy costs, swim schedules, and equipment protection.

> 🤖 **_Disclaimer: Co-written with AI. If your pool turns into a foam party, blame the LLM (or check your pH)._**

<div class="ps-hero__actions" markdown>
[Get started :material-arrow-right:](getting_started.md){ .ps-btn .ps-btn--primary }
[View on GitHub :material-github:](https://github.com/rickertie/Poolsmart){ .ps-btn .ps-btn--secondary }
</div>

<div class="ps-hero__meta" markdown>
<span class="ps-badge">:material-puzzle: HACS Custom</span>
<span class="ps-badge">:material-license: AGPL-3.0-or-later</span>
<span class="ps-badge">:material-timer-outline: 30 s decision tick</span>
<span class="ps-badge">:material-translate: EN · NL entities</span>
</div>

</div>

<div class="ps-grid ps-grid--3" markdown>

<div class="ps-card ps-card--accent" markdown>
<div class="ps-card__icon">:material-pump:</div>
<p class="ps-card__title">Smart filtration</p>
<p class="ps-card__text">Runtime from pool volume × turnover ÷ measured flow. Self-corrects as filter pressure rises; heating runtime counts toward the quota.</p>
</div>

<div class="ps-card" markdown>
<div class="ps-card__icon">:material-heat-pump-outline:</div>
<p class="ps-card__title">Price- & solar-aware heating</p>
<p class="ps-card__text">Picks the cheapest COP-weighted hours before swim time. Heats on free solar surplus or negative prices, pauses on house-power cap.</p>
</div>

<div class="ps-card" markdown>
<div class="ps-card__icon">:material-brain:</div>
<p class="ps-card__title">Self-learning</p>
<p class="ps-card__text">Learns heat loss, heating rate, and COP per 5 °C band. Manual session review with weighted smoothing and outlier rejection.</p>
</div>

<div class="ps-card" markdown>
<div class="ps-card__icon">:material-test-tube:</div>
<p class="ps-card__title">Water chemistry</p>
<p class="ps-card__text">pH readings become dosing instructions. Intervals scale with water temperature; logs and reminders included.</p>
</div>

<div class="ps-card" markdown>
<div class="ps-card__icon">:material-solar-power-variant:</div>
<p class="ps-card__title">Solar optimization</p>
<p class="ps-card__text">Uses any irradiance or solar-production sensor — panels not required. Sunny idle periods teach heat loss instead of being discarded.</p>
</div>

<div class="ps-card" markdown>
<div class="ps-card__icon">:material-shield-check-outline:</div>
<p class="ps-card__title">Equipment protection</p>
<p class="ps-card__text">Compressor minimum off/run times, frost protection, flow adequacy by delta-T, and emergency stop — none negotiable by schedule.</p>
</div>

</div>

> 🤖 **Co-written with AI.** If your pool turns into a foam party, blame the LLM — or check your pH.

<figure markdown>
  ![PoolSmart System Architecture — ESPHome sensors feed Home Assistant, the decision engine evaluates every 30 s, and controls pump, heat pump, and dosing](images/architecture-overview.svg){ width="700" loading="lazy" }
  <figcaption>ESPHome → Home Assistant → Decision Engine → pool equipment. One tick, one winner.</figcaption>
</figure>

---

## Install in two minutes

### Option A — One-click (recommended)

1. Add PoolSmart to HACS:

    [![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=rickertie&repository=Poolsmart&category=integration)

2. Click **Download** in HACS and restart Home Assistant.
3. Add the integration:

    [![Add Integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=poolsmart)

### Option B — Manual

1. In HACS → **Custom repositories**, add `rickertie/Poolsmart` as **Integration**.
2. Download, restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration → PoolSmart**.

!!! note "Unlock all features after install"
    - Map temperature probes and flow meter
    - Choose heating source and target temperature
    - Connect a price sensor for cost optimization
    - See [Hardware](hardware.md) and [ESPHome setup](esphome.md)

<figure markdown>
  ![PoolSmart Dashboard — three-tab Lovelace view for household members, management panel at /poolsmart for maintainers](images/dashboard-mockup.svg){ width="700" loading="lazy" }
  <figcaption>Household dashboard (Lovelace) vs maintainer panel at <code>/poolsmart</code> — deliberately separate.</figcaption>
</figure>

---

## Explore the docs

### Start here

**[Getting Started](getting_started.md)** — 15 minutes from fresh install to first verified decision.

### Core concepts

| Topic | Document | Covers |
|---|---|---|
| Architecture & decision core | [Architecture](architecture.md) | Priority ladder, filtration math, AI layer |
| Heating planning & prices | [Planning](planning.md) | Maintenance vs seasonal mode, price integrations |
| Self-learning model | [Learning](learning.md) | Learned parameters, validation rules, session logging |

### Subsystems

| Topic | Document | Covers |
|---|---|---|
| Filtration | [Filtration](filtration.md) | Turnover, daily minimum, filter media, delta-T |
| Heating sources | [Heating](heating.md) | Heat pump, electric, solar, gas |
| Water chemistry | [Chemistry](chemistry.md) | Dosing, test intervals, circulation timing |

### Setup & configuration

| Topic | Document | Covers |
|---|---|---|
| Hardware & wiring | [Hardware](hardware.md) | Bill of materials, pinouts, voltage divider |
| ESPHome setup | [ESPHome](esphome.md) | Board configuration, probe calibration |
| Sensor mapping | [Sensors](sensors.md) | Sensor placement, calibration procedures |
| Configuration | [Configuration](configuration.md) | Options flow, entity reassignment, house power limit |
| Pre-filling the wizard | [Defaults](defaults.md) | Starting the wizard with your own figures |

### Reference

| Topic | Document | Covers |
|---|---|---|
| Entity IDs | [Entities](entities.md) | Fixed IDs, translated names, source sensors |
| Management panel | [Panel](panel.md) | Six-tab sidebar panel at `/poolsmart` |
| Lovelace dashboards | [Lovelace dashboards](lovelace/README.md) | Installing and customizing Lovelace dashboards |
| Logging & diagnostics | [Logging](logging.md) | Logbook entries, notifications, full trace |
| Troubleshooting | [Troubleshooting](troubleshooting.md) | Common issues, fault isolation, diagnostics |
| Development | [Development](development.md) | Running tests, contributing |
| Changelog | [CHANGELOG](https://github.com/rickertie/Poolsmart/blob/main/CHANGELOG.md) | Release history |

---

## The management panel

PoolSmart ships a full panel at `/poolsmart` with six tabs: **Overview, Planning, Sessions, Learning, Settings, Diagnostics**.
It visualizes the decision ladder, shows why the last decision was made, and exposes the self-learning engine.
See [Panel](panel.md) for the full reference. For everyday household use, install the [Lovelace dashboard](lovelace/README.md).

---

## Quick links

!!! tip "Where to next?"
    - :material-rocket-launch: **First time?** [Getting Started](getting_started.md)
    - :material-chart-line: **COP & heat loss:** [Self-Learning Engine](learning.md)
    - :material-currency-eur: **Dynamic prices:** [Price-Aware Heating](planning.md)
    - :material-test-tube: **Water quality:** [Automated Dosing](chemistry.md)
    - :material-view-dashboard: **UI layout:** [Lovelace Dashboards](lovelace/README.md)

---

## Known limitations

- **Services require a single pool.** All PoolSmart services (dose recording, history import/export, learning reset, etc.) only work when exactly one PoolSmart pool is configured. With two or more pools, service calls are refused. See [Troubleshooting](troubleshooting.md#single-pool-limitation-for-services).
- **House power limit needs the right sensor.** The demand limiter expects a whole-house power sensor (e.g. from your smart meter), not the pool's own consumption. See [Configuration](configuration.md#house-power-limit).

---

## License

AGPL-3.0-or-later. See [LICENSE](https://github.com/rickertie/Poolsmart/blob/main/LICENSE) on GitHub.
