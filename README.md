<p align="center">
  <img src="custom_components/poolsmart/brand/logo.png" width="380" alt="PoolSmart logo">
</p>

<p align="center">
  <em>Intelligent swimming pool controller for Home Assistant — ESPHome measures, HA decides.</em>
</p>

<p align="center">
  <a href="https://hacs.xyz/docs/faq/custom_repositories">
    <img src="https://img.shields.io/badge/HACS-Custom-41BDF5?style=flat-square&logo=homeassistant&logoColor=white" alt="HACS Custom">
  </a>
  <a href="https://github.com/rickertie/Poolsmart/releases">
    <img src="https://img.shields.io/github/v/release/rickertie/Poolsmart?style=flat-square&color=blue" alt="Version">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/license-AGPL--3.0--or--later-orange?style=flat-square" alt="License">
  </a>
</p>

---

PoolSmart turns your pool into a self-optimizing system. Automate filtration scheduling,
heat pump control, solar optimization, and water chemistry dosing — all integrated with
Home Assistant. A priority-based decision engine evaluates your pool state every 30 seconds,
balancing energy costs, swim schedules, and equipment protection.

> 🤖 **_Disclaimer: Co-written with AI. If your pool turns into a foam party, blame the LLM (or check your pH)._**

<p align="center">
  <img src="docs/images/architecture-overview.svg" width="700" alt="PoolSmart System Architecture">
</p>

---

## Features

| | | |
|---|---|---|
| **Smart filtration** — runtime from pool volume and measured flow | **Heat pump control** — plans around dynamic prices and solar surplus | **Self-learning** — learns heat loss, heating rate, and COP, with manual session review |
| **Water chemistry** — pH readings become dosing instructions | **Solar optimization** — heats with free surplus, and learns heat loss from sunny idle periods too, using any irradiance sensor — solar panels not required | **Price-aware scheduling** — works backwards from swim time, with a configurable rule for how a cheap-price signal relates to your maximum price |
| **Compressor protection** — minimum off/run times enforced | **AI advisory** — suggests settings, applies nothing without approval | **Dashboards** — detailed three-tab view and simple household page |

---

## Prerequisites

- [Home Assistant](https://www.home-assistant.io/) 2024.x or later
- [HACS](https://hacs.xyz/) installed
- [ESPHome](https://esphome.io/) add-on (for the sensor board)
- Compatible pool equipment — see [Hardware](docs/hardware.md)

---

## Installation

### Method 1: Easy (One-Click)

1. Click the button below to add PoolSmart to HACS automatically:

   [![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=rickertie&repository=Poolsmart&category=integration)

2. Click **Download** in HACS and restart Home Assistant.
3. Click the button below to configure PoolSmart:

   [![Add Integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=poolsmart)

---

### Method 2: Manual

1. Open **HACS** in your Home Assistant instance.
2. Click **Custom Repositories** (top right) and add `rickertie/Poolsmart` with category **Integration**.
3. Download PoolSmart and restart Home Assistant.
4. Go to **Settings → Devices & Services → Add Integration → PoolSmart**.

> [!NOTE]
> **Full setup** (unlock all features):
> - Map your temperature sensors and flow meter
> - Configure heating source and target temperature
> - Connect a price sensor for cost optimization
> - See [Hardware](docs/hardware.md) and [ESPHome](docs/esphome.md)

---

<p align="center">
  <img src="docs/images/dashboard-mockup.svg" width="700" alt="PoolSmart Dashboard Mockup">
</p>

## Documentation

<details>
<summary><b>Core Concepts</b></summary>

| Topic | Document | Covers |
|---|---|---|
| Architecture & decision core | [Architecture](docs/architecture.md) | Priority ladder, filtration math, AI layer |
| Heating planning & prices | [Planning](docs/planning.md) | Maintenance vs. seasonal mode, price integrations |
| Self-learning model | [Learning](docs/learning.md) | Learned parameters, validation rules, session logging |

</details>

<details>
<summary><b>Subsystems</b></summary>

| Topic | Document | Covers |
|---|---|---|
| Filtration | [Filtration](docs/filtration.md) | Turnover, daily minimum, filter media, delta-T |
| Heating sources | [Heating](docs/heating.md) | Heat pump, electric, solar, gas |
| Water chemistry | [Chemistry](docs/chemistry.md) | Dosing, test intervals, circulation timing |

</details>

<details>
<summary><b>Setup & Configuration</b></summary>

| Topic | Document | Covers |
|---|---|---|
| Hardware & wiring | [Hardware](docs/hardware.md) | Bill of materials, pinouts, voltage divider |
| ESPHome setup | [ESPHome](docs/esphome.md) | Board configuration, probe calibration |
| Sensor mapping | [Sensors](docs/sensors.md) | Sensor placement, calibration procedures |
| Configuration | [Configuration](docs/configuration.md) | Options flow, entity reassignment |
| Pre-filling the wizard | [Defaults](docs/defaults.md) | Starting the wizard with your own figures |

</details>

<details>
<summary><b>Reference</b></summary>

| Topic | Document | Covers |
|---|---|---|
| Entity IDs | [Entities](docs/entities.md) | Fixed IDs, translated names, source sensors |
| Management panel | [Panel](docs/panel.md) | Six-tab sidebar panel at `/poolsmart` |
| Dashboards | [lovelace/README.md](docs/lovelace/README.md) | Installing and customizing Lovelace dashboards |
| Logging & diagnostics | [Logging](docs/logging.md) | Logbook entries, notifications, full trace |
| Troubleshooting | [Troubleshooting](docs/troubleshooting.md) | Common issues, fault isolation, diagnostics |
| Getting started | [Getting Started](docs/getting_started.md) | First-time setup, verifying your installation |
| Development | [Development](docs/development.md) | Running tests, contributing |
| Brand images | [Brand images](docs/brand-image.md) | Integration icon and logo, HACS workaround |
| Changelog | [CHANGELOG.md](CHANGELOG.md) | Release history |

</details>

---

## Quick Links

> [!TIP]
> - 🚀 **First time?** Check out the [Getting Started Guide](docs/getting_started.md)
> - 📈 **COP & Heat loss:** Read about the [Self-Learning Engine](docs/learning.md)
> - 💡 **Dynamic Prices:** Learn how [Price-Aware Heating](docs/planning.md) works
> - 🧪 **Water Quality:** Review [Automated Dosing Math](docs/chemistry.md)
> - 📊 **UI Layout:** Set up your [Lovelace Dashboards](docs/lovelace/README.md)

---

<!-- single-pool limitation: _target_coordinator() in __init__.py only supports one config entry — see issue #25 / docs/troubleshooting.md#single-pool-limitation-for-services -->
## Known Limitations

- **Services require a single pool.** All PoolSmart services (`record_dose`,
  `reset_learned`, `export_learning`, `import_learning`, `replace_learning`,
  `rebuild_learning`, `set_session_review`, `clear_debug_log`,
  `clear_all_history`, `set_setting`) only work when exactly one PoolSmart pool
  is configured. With two or more pools, service calls are refused. See
  [Troubleshooting](docs/troubleshooting.md#single-pool-limitation-for-services).
- **House power limit needs the right sensor.** The demand limiter expects a
  whole-house power sensor (e.g. from your smart meter), not the pool's own
  consumption. A signed "net" reading (negative during solar export, such as
  a Dutch P1 *netto* sensor) works too. See
  [Configuration](docs/configuration.md#house-power-limit).

---

## License

AGPL-3.0-or-later
