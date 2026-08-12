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
  <a href="https://github.com/rickertie/Poolsmart/releases">
    <img src="https://img.shields.io/github/downloads/rickertie/Poolsmart/total?style=flat-square&color=brightgreen" alt="Downloads">
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
| **Smart filtration** — runtime from pool volume and measured flow | **Heat pump control** — plans around dynamic prices and solar surplus | **Self-learning** — learns heat loss, heating rate, and COP |
| **Water chemistry** — pH readings become dosing instructions | **Solar optimization** — heats with free surplus | **Price-aware scheduling** — works backwards from swim time |
| **Compressor protection** — minimum off/run times enforced | **AI advisory** — suggests settings, applies nothing without approval | **Dashboards** — detailed three-tab view and simple household page |

---

## Prerequisites

- [Home Assistant](https://www.home-assistant.io/) 2024.x or later
- [HACS](https://hacs.xyz/) installed
- [ESPHome](https://esphome.io/) add-on (for the sensor board)
- Compatible pool equipment — see [HARDWARE.MD](docs/HARDWARE.MD)

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
> - See [HARDWARE.MD](docs/HARDWARE.MD) and [ESPHOME.MD](docs/ESPHOME.MD)

---

<p align="center">
  <img src="docs/images/dashboard-mockup.svg" width="700" alt="PoolSmart Dashboard Mockup">
</p>

## Documentation

<details>
<summary><b>Core Concepts</b></summary>

| Topic | Document | Covers |
|---|---|---|
| Architecture & decision core | [ARCHITECTURE.MD](docs/ARCHITECTURE.MD) | Priority ladder, filtration math, AI layer |
| Heating planning & prices | [PLANNING.MD](docs/PLANNING.MD) | Maintenance vs. seasonal mode, price integrations |
| Self-learning model | [LEARNING.MD](docs/LEARNING.MD) | Learned parameters, validation rules, session logging |

</details>

<details>
<summary><b>Subsystems</b></summary>

| Topic | Document | Covers |
|---|---|---|
| Filtration | [FILTRATION.MD](docs/FILTRATION.MD) | Turnover, daily minimum, filter media, delta-T |
| Heating sources | [HEATING.MD](docs/HEATING.MD) | Heat pump, electric, solar, gas |
| Water chemistry | [CHEMISTRY.MD](docs/CHEMISTRY.MD) | Dosing, test intervals, circulation timing |

</details>

<details>
<summary><b>Setup & Configuration</b></summary>

| Topic | Document | Covers |
|---|---|---|
| Hardware & wiring | [HARDWARE.MD](docs/HARDWARE.MD) | Bill of materials, pinouts, voltage divider |
| ESPHome setup | [ESPHOME.MD](docs/ESPHOME.MD) | Board configuration, probe calibration |
| Sensor mapping | [SENSORS.MD](docs/SENSORS.MD) | Sensor placement, calibration procedures |
| Configuration | [CONFIGURATION.MD](docs/CONFIGURATION.MD) | Options flow, entity reassignment |
| Pre-filling the wizard | [DEFAULTS.MD](docs/DEFAULTS.MD) | Starting the wizard with your own figures |

</details>

<details>
<summary><b>Reference</b></summary>

| Topic | Document | Covers |
|---|---|---|
| Entity IDs | [ENTITIES.MD](docs/ENTITIES.MD) | Fixed IDs, translated names, source sensors |
| Management panel | [PANEL.MD](docs/PANEL.MD) | Six-tab sidebar panel at `/poolsmart` |
| Dashboards | [lovelace/README.md](docs/lovelace/README.md) | Installing and customizing Lovelace dashboards |
| Logging & diagnostics | [LOGGING.MD](docs/LOGGING.MD) | Logbook entries, notifications, full trace |
| Troubleshooting | [TROUBLESHOOTING.MD](docs/TROUBLESHOOTING.MD) | Common issues, fault isolation, diagnostics |
| Getting started | [GETTING_STARTED.MD](docs/GETTING_STARTED.MD) | First-time setup, verifying your installation |
| Development | [DEVELOPMENT.MD](docs/DEVELOPMENT.MD) | Running tests, contributing |
| Brand images | [BRAND-IMAGE.MD](docs/BRAND-IMAGE.MD) | Integration icon and logo, HACS workaround |
| Changelog | [CHANGELOG.md](CHANGELOG.md) | Release history |

</details>

---

## Quick Links

> [!TIP]
> - 🚀 **First time?** Check out the [Getting Started Guide](docs/GETTING_STARTED.MD)
> - 📈 **COP & Heat loss:** Read about the [Self-Learning Engine](docs/LEARNING.MD)
> - 💡 **Dynamic Prices:** Learn how [Price-Aware Heating](docs/PLANNING.MD) works
> - 🧪 **Water Quality:** Review [Automated Dosing Math](docs/CHEMISTRY.MD)
> - 📊 **UI Layout:** Set up your [Lovelace Dashboards](docs/lovelace/README.md)

---

## License

AGPL-3.0-or-later