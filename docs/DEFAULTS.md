> [? Back to README](../README.md) | [Getting Started](GETTING_STARTED.MD) | [Architecture](architecture.md) | [Configuration](configuration.md) | [Troubleshooting](troubleshooting.md)

---

# Pre-Filling the Setup Wizard

This document explains how to start the PoolSmart setup wizard with your own
figures instead of the built-in defaults. For the full installation walkthrough,
see the [README](../README.md). For the example defaults file, see
[poolsmart_defaults.example.json](poolsmart_defaults.example.json).

---

Every field in the setup wizard arrives with a value already in it, so nothing is
ever a blank box. The built-in numbers describe a generic mid-sized pool with a
typical cartridge pump and a small heat pump.

Those numbers are deliberately not anyone's actual pool. Baking one particular
installation into the integration would make it wrong for everybody else, and
being usable by other people was the point of building it this way.

If you reinstall often, or you simply do not want to retype your own figures,
drop a file called `poolsmart_defaults.json` in your Home Assistant configuration
directory — the same folder as `configuration.yaml`. Any keys it contains
override the built-in defaults when the wizard opens.

## Example

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
  "hp_air_temp_min": 11.0,
  "hp_air_temp_max": 43.0,
  "hp_flow_min_m3h": 2.0
}
```

A ready-made copy of this is in
[poolsmart_defaults.example.json](poolsmart_defaults.example.json).

## Every Key You Can Set

| Key | Meaning | Built-in default |
|---|---|---|
| `volume_l` | Water volume in litres | 10000 |
| `depth_m` | Water depth in metres | 1.2 |
| `target_temp` | Desired temperature | 28.0 |
| `max_temp` | Highest you would ever set | 32.0 |
| `pump_flow_m3h` | Circulation pump flow | 3.0 |
| `pump_flow_measured` | `true` if measured, `false` if from the datasheet | false |
| `pump_power_kw` | Pump electrical power | 0.1 |
| `hp_input_kw` | Heat pump electrical input | 1.0 |
| `hp_thermal_kw` | Heat pump thermal output | 4.0 |
| `hp_cop_ref_temp` | Air temperature that output was measured at | 26.0 |
| `hp_cop_low_temp` | Air temperature for the second COP point | 15.0 |
| `hp_air_temp_min` | Below this the heat pump may not run | 11.0 |
| `hp_air_temp_max` | Above this the heat pump may not run | 43.0 |
| `hp_flow_min_m3h` | Minimum flow the heat pump needs | 2.0 |

Unknown keys are ignored and logged at debug level. A malformed file is ignored
with a warning and the built-in defaults are used, so a typo here can never stop
the integration from being set up.

Note that this only affects what the wizard *starts with*. Changing the file
afterwards does not alter an existing installation — for that, use
Settings → Devices & services → PoolSmart → Configure → Pool and equipment.

## Notes

- Water surface may be left out entirely; it is calculated from volume and depth.
- Entity choices are not covered here. They differ per system and are picked from
  a dropdown anyway, and they can be corrected afterwards under Configure.

---

## See Also

- [README](../README.md) — Full installation walkthrough and configuration guide.
- [poolsmart_defaults.example.json](poolsmart_defaults.example.json) — Ready-made
  example file you can copy and edit.
- [sensors.md](sensors.md) — How to map your sensors after setup.
- [configuration.md](configuration.md) — How to change settings after initial setup.
- [heating.md](heating.md) — Heating sources and their configuration options.
