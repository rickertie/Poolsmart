[← Back to README](../README.md) • [Architecture](architecture.md) • [Planning](planning.md) • [Learning](learning.md) • [Hardware](hardware.md) • [ESPHome](esphome.md) • **Defaults**
***

# 📋 Pre-filling Setup Wizard Defaults

When configuring PoolSmart for the first time, every field in the setup wizard comes pre-filled with reasonable defaults for a generic, mid-sized pool setup. 

If you re-install often or want to skip typing your hardware specs manually, you can override these built-in defaults by creating a JSON file.

---

## ⚙️ How It Works

Drop a file named **`poolsmart_defaults.json`** directly inside your main Home Assistant configuration directory (the same folder that contains `configuration.yaml`).

When the setup wizard opens, PoolSmart automatically reads this file and pre-fills the setup fields with your custom values.

> 💡 **Ready-made Template:** A reference example is available at [`docs/poolsmart_defaults.example.json`](poolsmart_defaults.example.json)[cite: 6].

---

## 📄 Example `poolsmart_defaults.json`

```json
{
  "volume_l": 3834,
  "depth_m": 0.66,
  "target_temp": 28.0,
  "max_temp": 32.0,

  "pump_flow_m3h": 3.596,
  "pump_flow_measured": true,
  "pump_power_kw": 0.10,

  "hp_input_kw": 0.58,
  "hp_thermal_kw": 3.0,
  "hp_cop_ref_temp": 26.0,
  "hp_cop_low_temp": 15.0,
  "hp_air_temp_min": 11.0,
  "hp_air_temp_max": 43.0,
  "hp_flow_min_m3h": 2.0
}