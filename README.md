# 🏊 PoolSmart

![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Integration-41BDF5.svg)

> **Smart swimming pool automation for Home Assistant.**  
> Smarter filtration, cheaper heating, and zero manual tinkering.

PoolSmart is a Home Assistant integration that automates your swimming pool management. It continuously balances filtration, heat pump efficiency, electricity prices, weather forecasts, and your personal swimming habits to keep your pool perfectly ready — using as little energy as possible.

Whether you run a small inflatable setup or a 30,000-liter in-ground pool with a heat pump, PoolSmart dynamically adapts to your hardware without requiring endless YAML tweaks.

---

> ⚠️ **AI Notice**  
> PoolSmart was developed with significant assistance from AI. The architecture, algorithms, and safety logic have been designed, reviewed, and tested by the project maintainer, but bugs may still exist.  
> 
> Found an issue or have an improvement in mind? Opening an **Issue** or **Pull Request** is genuinely appreciated!

---

## ✨ Key Features

* **🧠 Smart Decision Engine** — Prioritizes safety, frost protection, and schedules without race conditions.
* **📈 Self-Learning Heating Model** — Predicts heat loss and measures actual thermal efficiency over time.
* **⚡ Dynamic Electricity Optimization** — Automatically heats during cheap or solar-rich hours.
* **🌡️ Weather-Aware Operation** — Adapts runtimes based on outdoor temperatures and solar gains.
* **❄️ Smart Frost Protection** — Drops back to safe circulation if air temperatures dip too low for heat pumps.
* **🤖 Optional AI Recommendations** — Get high-level advice on filtration, cover usage, and heating windows.
* **🛠️ Zero YAML Required** — Fully configurable via the UI with comprehensive helper text and worked examples.

---

## 🤔 Why PoolSmart?

Most traditional pool setups rely on dozens of fragile YAML rules and loose timers.

That works... until Home Assistant restarts, a timer fails, or heating and filtration fight for control—leaving you wondering: *"Why on earth did the pump just turn on?"*

PoolSmart replaces fragmented rules with a **single, deterministic decision engine**. Every 30 seconds, it steps down a strict priority ladder. The first rule that matches takes control—no fighting, no race conditions.

> 🚨 **1. Emergency Stop & Safety Flags**  
> └─ Hard overrides and manual safety cut-offs.
> 
> ❄️ **2. Frost Protection**  
> └─ Circulates water automatically when ambient temps drop.
> 
> 🔥 **3. Smart Heating Sessions**  
> └─ Runs heat pump during optimal COP and lowest energy price windows.
> 
> 🌀 **4. Daily Filtration**  
> └─ Ensures clean water based on pool volume and temperature.
> 
> 💤 **5. Idle / Off**  
> └─ System enters standby when no active demands exist.

📖 *Deep Dive:* Full details on the decision ladder, formulas, and parameters live in [`docs/architecture.md`](docs/architecture.md)

---

## 🚀 Installation

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=JOUW_GITHUB_GEBRUIKERSNAAM&repository=PoolSmart&category=integration)

1. Click the **HACS** button above (or add this repository manually in HACS as a custom repository).
2. Install **PoolSmart** and restart Home Assistant.
3. Go to **Settings** → **Devices & Services** → **Add Integration** → **PoolSmart**.
4. Follow the setup wizard (only 3 entity fields are strictly required!).

> 💡 **Tip:** Every configuration step includes inline help and realistic examples. Everything — including pool volume, equipment specs, dynamic price sensors, and swim schedules — can be edited later via **Configure**.

---

## 🔧 Real-World Hardware Example

PoolSmart works with any standard Home Assistant entities. You don't need fancy sensors to get started, but to give you an idea of a real setup:

> **Example Setup:**
> * **Pool:** Intex Metal Frame (3,834 L)
> * **Pump:** Bestway Flowclear filter pump
> * **Heating:** W'eau Mini heat pump
> * **Controller:** Single Seeed XIAO ESP32-C6 running ESPHome with 5x Dallas temperature sensors (Pool, Pump In/Out, Heat Pump In/Out, Ambient) + a pulse flow meter.

The ESP32 processes high-frequency local metrics ($\Delta T$, predicted COP, thermal rate) and feeds clean data to Home Assistant, where PoolSmart handles the high-level orchestration.

📖 **Hardware Guides:**  
* [`docs/esphome.md`](docs/esphome.md) — ESPHome configuration, sensor setup, and calibration steps.
* [`docs/hardware.md`](docs/hardware.md) — Parts list, wiring diagrams, and build photos.

---

## 📸 Dashboard & Panel

PoolSmart includes UI components to give you full visibility over your pool's state:

- **Current Operating Mode & Priority Reason**
- **Daily Filtration Progress Tracker**
- **Planned Heating Sessions & Price Matrix**
- **Energy Usage & Efficiency Metrics**
- **AI Advisor Suggestions**

A dedicated sidebar panel (`/poolsmart`) offers 6 detailed views: **Overview**, **Planning**, **Sessions**, **Learning**, **Settings**, and **Diagnostics**.

---

## 📚 Documentation

* [`docs/architecture.md`](docs/architecture.md) — Decision engine, priority ladder, formulas, and dev setup.
* [`docs/planning.md`](docs/planning.md) — Maintenance vs. seasonal heating planning logic.
* [`docs/learning.md`](docs/learning.md) — Self-learning COP and heat loss algorithms.
* [`docs/esphome.md`](docs/esphome.md) — ESPHome configuration and calibration.
* [`docs/hardware.md`](docs/hardware.md) — Bill of Materials (BOM) and physical installation photos.

---

## ❓ FAQ

**Do I need a flow meter, power sensors, or smart price sensors?**  
**No.** All optional entities can be left blank during setup. PoolSmart will automatically disable features tied to missing sensors and fall back to estimated models without breaking or throwing errors.

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---
<p center><i>Built for the Home Assistant community ❤️</i></p>
