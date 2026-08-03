[← Back to README](../README.md) • [Architecture](architecture.md) • [Planning](planning.md) • [Learning](learning.md) • **Hardware** • [ESPHome](esphome.md) • [Defaults](defaults.md)
***

# 🛠️ Hardware & Wiring Guide

This page covers the physical installation: component selection, pinouts, voltage stepped-down circuits, and pipe mounting[cite: 1]. For the ESPHome YAML configuration and sensor calibration, see [`esphome.md`](esphome.md)[cite: 1].

---

## 🛒 Bill of Materials (BOM)

| Component | Function / Application | Notes |
| :--- | :--- | :--- |
| **Seeed XIAO ESP32-C6** | Main microcontroller running ESPHome. | Compact, native Wi-Fi 6 / Bluetooth. |
| **5x DS18B20 Probes** | Temperature sensors for pool, pump, heat pump & outdoor. | Waterproof stainless-steel Dallas 1-Wire probes. |
| **DN50 Pulse Flow Sensor** | Measures volume flow rate through the heat pump loop[cite: 1]. | Yanmis DN50 Hall-effect pulse sensor. |
| **4.7 kΩ Resistor** | Pull-up resistor for the 1-Wire bus[cite: 1]. | Connects between 3.3V and GPIO22[cite: 1]. |
| **10 kΩ + 20 kΩ Resistors** | Voltage divider for the flow meter signal[cite: 1]. | Steps 5V pulses down to 3.3V for GPIO19. |
| **Waterproof Enclosure** | IP65+ junction box near the pool pump setup[cite: 1]. | Protects ESP32 board and wiring[cite: 1]. |
| **Bestway Flowclear** | Circulation filter pump[cite: 1]. | Measured at ~3.6 m³/h[cite: 7]. |
| **W'eau Mini Power (3kW)** | Heat pump for water heating[cite: 1]. | ~0.58 kW electric input[cite: 7]. |
| **Intex Metal Frame** | Pool structure (3,834 L at 66 cm water level)[cite: 1, 7]. | 300 x 200 x 75 cm[cite: 7]. |

---

## 🔌 Pinout & Wiring Diagram

All 5 Dallas probes share a single 1-Wire bus on **GPIO22** and are identified by their unique hardware addresses in software[cite: 1].

| Device / Signal | ESP32-C6 Pin | Circuit Requirements |
| :--- | :---: | :--- |
| **1-Wire Bus** (5x DS18B20) | `GPIO22` | Requires a 4.7 kΩ pull-up resistor to 3.3V[cite: 1]. |
| **Flow Meter Signal** | `GPIO19` | **Must use Voltage Divider** (5V → 3.3V)[cite: 1, 4]. |
| **Status LED** | `GPIO23` | Direct connection (inverted logic)[cite: 1, 7]. |

### ⚡ 5V Hall-Effect Flow Meter Voltage Divider

> ⚠️ **CRITICAL:** Hall-effect flow meters produce **5V logic pulses**[cite: 1, 4]. Connecting 5V directly to an ESP32 GPIO pin will permanently destroy the pin[cite: 4]! Use a voltage divider:

### ⚡ 5V Hall-Effect Flow Meter Voltage Divider

> ⚠️ **CRITICAL:** Hall-effect flow meters output **5V logic pulses**. Never connect the signal directly to an ESP32 GPIO pin. Use a simple voltage divider to reduce the signal to approximately **3.3V**.

```text
Meter Signal (5V Pulse)
          │
       [10 kΩ]
          │──────────────► GPIO19 (ESP32)
          │
       [20 kΩ]
          │
         GND
```

The 10kΩ / 20kΩ divider reduces the 5V pulse to approximately **3.3V**, making it safe for the ESP32.

---

## 📸 Physical Installation & Mounting

| Component | Image | Mounting Details |
| :--- | :---: | :--- |
| **Filter Pump** | <img src="images/Bestway_pump.webp" width="160"> | Installed in the main circulation loop. |
| **Heat Pump** | <img src="images/w_eau_mini_power_3kw_warmtepomp.webp" width="160"> | Installed downstream of the filter pump. |
| **Temperature Sensors** | <img src="images/Pipe_clamp.jpg" width="160"> | DS18B20 probes attached to the PVC pipe using thermal paste and pipe clamps for accurate surface readings. |
| **Flow Meter** | <img src="images/Flow_meter.jpg" width="160"> | DN50 Hall-effect flow meter installed in the return line from the heat pump. |

---

## ⚡ Wiring Overview

<p align="center">
  <img src="images/esp32c6_wiring_overview.png" width="550">
</p>

---

## 🔗 Next Steps & Calibration

After completing the hardware installation:

1. Continue with the **ESPHome configuration** in [`esphome.md`](esphome.md).
2. Calibrate the temperature probes using the stirred-water method.
3. Calibrate the flow meter using a bucket test.
4. Verify that all GPIO inputs report stable values in Home Assistant before enabling automations.
