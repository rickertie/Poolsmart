> [Home](index.md) | [Getting Started](getting_started.md) | [Architecture](architecture.md) | [Configuration](configuration.md) | [Troubleshooting](troubleshooting.md)

---

# Hardware & Wiring Guide

This document covers the physical installation: component selection, pinouts,
voltage step-down circuits, and pipe mounting. For the ESPHome YAML
configuration and sensor calibration, see [ESPHome](esphome.md). For mapping
sensors to integration fields, see [Sensors](sensors.md).

---

## Bill of my Materials

| Component | Function | Application ||
| :--- | :---: | :--- | :--- |
| **Seeed XIAO ESP32-C6** | Main microcontroller running ESPHome. | Compact, native Wi-Fi 6 / Bluetooth. |
| **5× DS18B20 probes** | Temperature sensors for pool, pump, heat pump, and outdoor. | Waterproof stainless-steel Dallas 1-Wire probes. |
| **DN50 pulse flow sensor** | Measures volume flow rate through the heat pump loop. | Yanmis DN50 Hall-effect pulse sensor. |
| **4.7 kΩ resistor** | Pull-up resistor for the 1-Wire bus. | Connects between 3.3 V and GPIO22. |
| **10 kΩ + 20 kΩ resistors** | Voltage divider for the flow meter signal. | Steps 5 V pulses down to 3.3 V for GPIO19. |
| **Waterproof enclosure** | IP65+ junction box near the pool pump setup. | Protects ESP32 board and wiring. |
| **Bestway Flowclear** | Circulation filter pump. | Measured at ~3.6 m³/h. |
| **W'eau Mini Power (3 kW)** | Heat pump for water heating. | ~0.58 kW electric input. |
| **Intex Metal Frame** | Pool structure (3,834 L at 66 cm water level). | 300 × 200 × 75 cm. |

The pool itself is a 300 × 200 × 75 cm above-ground Intex Metal Frame pool; at
the 66 cm operating water level it holds 3,834 L.

---

## Pinout & Wiring Diagram

All five Dallas probes share a single 1-Wire bus on **GPIO22** and are identified
by their unique hardware addresses in software.

| Device / Signal | ESP32-C6 Pin | Circuit Requirements |
| :--- | :---: | :--- |
| **1-Wire bus** (5× DS18B20) | `GPIO22` | Requires a 4.7 kΩ pull-up resistor to 3.3 V. |
| **Flow meter signal** | `GPIO19` | **Must use voltage divider** (5 V → 3.3 V). |
| **Status LED** | `GPIO23` | Direct connection (inverted logic). |

### 5 V Hall-Effect Flow Meter Voltage Divider

> **Critical:** Hall-effect flow meters produce **5 V logic pulses**. Connecting
> 5 V directly to an ESP32 GPIO pin will permanently destroy the pin. Use a
> voltage divider:

```text
Meter Signal (5 V pulse)
          │
       [10 kΩ]
          │──────────────► GPIO19 (ESP32)
          │
       [20 kΩ]
          │
         GND
```

The 10 kΩ / 20 kΩ divider reduces the 5 V pulse to approximately **3.3 V**,
making it safe for the ESP32.

---

## Physical Installation & Mounting

| Component | Image | Mounting Details |
| :--- | :---: | :--- |
| **Filter pump** | <img src="images/Bestway_pump.svg" width="160"> | Installed in the main circulation loop. |
| **Heat pump** | <img src="images/w_eau_mini_power_3kw_warmtepomp.svg" width="160"> | Installed downstream of the filter pump, so it only receives filtered water. |
| **Temperature sensors** | <img src="images/Pipe_clamp.svg" width="160"> | DS18B20 probes attached to the PVC pipe using thermal paste and pipe clamps for accurate surface readings. |
| **Flow meter** | <img src="images/Flow_meter.svg" width="160"> | DN50 Hall-effect flow meter installed in the return line from the heat pump. |

Attach each DS18B20 probe flat against the pipe with a thin layer of thermal
paste, secure it with a stainless-steel pipe clamp, and cover the mount with
insulation so ambient air cannot influence the reading.

The flow meter body is marked with an arrow. Mount it so the arrow points in the
direction of water flow — from the heat pump back toward the pool — and wrap the
DN50 threads with PTFE tape to prevent leaks.

---

## Wiring Overview

<p align="center">
  <img src="images/esp32c6_wiring_overview.svg" width="550">
</p>

---

## See Also

- [ESPHome](esphome.md) — ESPHome YAML configuration that matches this wiring.
- [Sensors](sensors.md) — How to calibrate the probes and flow meter after
  installation.
- [esphome/pool_sensors.yaml](esphome/pool_sensors.yaml) — Complete example
  ESPHome configuration with pin assignments and calibration offsets.
- [Configuration](configuration.md) — How to change settings after initial setup.
