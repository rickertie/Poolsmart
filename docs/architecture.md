[← Back to README](../README.md) • **Architecture** • [Planning](planning.md) • [Learning](learning.md) • [Hardware](hardware.md) • [ESPHome](esphome.md) • [Defaults](defaults.md)
***

# 🏗️ Architecture & Decision Core

This document covers how PoolSmart evaluates decisions, calculates daily filtration, and manages component failure. 

---

## 🪜 The Priority Decision Ladder

Every 30 seconds, PoolSmart evaluates the current state of your pool against a strict priority ladder. The evaluation walks from the top down; **the first condition that matches wins**, and all lower branches are ignored.

| Priority | Branch / Condition | Ignores Night Quiet? | Description |
| :---: | :--- | :---: | :--- |
| **0** | 🚨 **Emergency Stop** | Yes | Global manual kill-switch or safety interlock triggered[cite: 5]. |
| **1** | ❄️ **Frost Protection** | Yes | Temp drops below safe threshold; forces circulation[cite: 5]. |
| **2** | 🕹️ **Manual Override** | Yes | User manually forced the pump ON/OFF in Home Assistant[cite: 5]. |
| **3** | 🧪 **Chemistry Cycle** | Yes | Scheduled chemical dosing or shock treatment[cite: 5]. |
| **4** | ⏰ **Filtration Deadline** | Yes | Ensures minimum turnover is met before the day ends[cite: 5]. |
| **5** | 📉 **Free Electricity** | Yes | Triggered when electricity price is negative ($< 0$)[cite: 5]. |
| **6** | 🔥 **Heating Session** | **No** | Dynamic heating session active based on COP & prices[cite: 5]. |
| **7** | 🌀 **Scheduled Filtration** | **No** | Regular background filtration block[cite: 5]. |
| **8** | ⏳ **Pump Rundown** | **No** | Cool-down period after heating before turning pump off[cite: 5]. |
| **9** | 💤 **Idle** | — | No action required; pump and heating remain off[cite: 5]. |

> 🔒 **Safety Interlock:** Branches **0, 1, and 4 stay active even if the integration is turned OFF**[cite: 5]. An off-switch must never be able to cause pipe freeze or damaged equipment[cite: 5].

### 🌡️ Heat Pump Operating Envelope
In front of branches **5 (Free Electricity)** and **6 (Heating)** sits an operating envelope gate[cite: 5]. If the outdoor air temperature drops below the heat pump's minimum operating limit (e.g., $< 11\text{°C}$), heating is disabled[cite: 5]. In this state, Frost Protection (Branch 1) will only trigger simple **water circulation**, which is sufficient to prevent freezing[cite: 5].

---

## 🌀 Filtration Calculation

Filtration runtime is calculated dynamically based on physical metrics rather than hardcoded timers[cite: 5]:

$$\text{Daily Runtime (hours)} = \frac{\text{Pool Volume (L)} \times \text{Turnover Factor}}{\text{Effective Pump Flow (L/h)}}$$

$$\text{Block Duration} = \frac{\text{Daily Runtime}}{\text{Number of Scheduled Blocks}}$$

### Key Filtration Behaviors:
* **Derating Factor:** If pump flow is unmeasured (taken from a spec sheet), it is automatically derated by $25\text{--}40\%$ to account for filter resistance[cite: 5].
* **Self-Correcting Blocks:** If a flow meter is installed, block durations automatically adjust as filter pressure changes over time[cite: 5].
* **Heating Session Credit:** Any time spent running the pump during heating sessions counts directly towards your daily filtration quota, preventing redundant pump runtime[cite: 5].

---

## ⚙️ Entity Mapping & Fallbacks

All sensors and switches can be updated anytime under **Settings → Devices & Services → PoolSmart → Configure**[cite: 5].

Every optional entity may be left blank[cite: 5]. The matching capability switches off cleanly and reports in diagnostics without breaking the integration[cite: 5]:

| Unmapped Entity | Consequence / Fallback |
| :--- | :--- |
| **Outdoor Temperature** | Disables envelope check; falls back to default HA weather integration[cite: 5]. |
| **Heat Pump In / Out** | Disables live $\Delta T$ calculation and COP performance learning[cite: 5]. |
| **Flow Meter** | Disables flow alarms; falls back to estimated pump spec flow[cite: 5]. |
| **Power Sensors** | Disables real-time energy cost calculations and measured COP[cite: 5]. |
| **Price / Solar Sensors** | Disables price/solar slot optimization (runs on default scheduled blocks)[cite: 5]. |

> 💡 **Heat Pump Thermostat Tip:** Set your heat pump's physical thermostat 2°C higher than your highest desired Home Assistant target (e.g., set physical dial to 34°C if target is 32°C)[cite: 5]. This ensures full software control while retaining hardware safety shutdown[cite: 5].

---

## 🤖 AI Advisory Layer

The optional AI layer acts strictly as a **non-blocking advisor**[cite: 5]:
1. Analyzes historical session logs and efficiency metrics[cite: 5].
2. Proposes parameter tweaks (e.g., adjusting filtration turnover or target temps)[cite: 5].
3. **Applies nothing automatically.** Suggestions must be manually approved by the user[cite: 5].
4. Out-of-bounds parameters suggested by AI are discarded by a strict validation filter[cite: 5].

---

## 🧪 Developer & Standalone Testing

The core decision logic in `custom_components/poolsmart/core/` has **zero Home Assistant dependencies**[cite: 5]. It can be tested standalone:

```bash
cd tests
python run_tests.py