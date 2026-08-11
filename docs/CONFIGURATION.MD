> [? Back to README](../README.md) | [Getting Started](GETTING_STARTED.MD) | [Architecture](architecture.md) | [Configuration](configuration.md) | [Troubleshooting](troubleshooting.md)

---

# Configuration

This document covers how to change settings after initial setup, the options
flow menu, entity reassignment, and the heat pump thermostat recommendation.
For the initial setup wizard, see the [README](../README.md). For pre-filling
the wizard with your own figures, see [defaults.md](defaults.md).

---

## Changing Things Afterwards

Nothing is locked in. Settings → Devices & Services → PoolSmart → **Configure**
opens a menu of subjects:

| Section | Contains |
|---|---|
| Sensors and switches | Every switch and sensor, including the required ones. The heat pump's own sensors and the collector sensor only appear when the heating source has them |
| Pool and pump | Volume, depth, pump flow, pump power, units, sanitiser, filter medium |
| Heating appliance | The heating source and everything that follows from it: heat pump figures, the efficiency curve, the operating envelope, the solar collector. A source without a heat pump is not asked about one |
| When to heat | Target temperature, price ceiling, solar surplus, swimming time |
| Filtration | Turnover, quiet hours, pump rundown |
| Water treatment | Sanitiser, chemistry products, doses |
| Notifications | Which message goes to which device |
| Advanced | Timings and tolerances for when a measurement misbehaves |

Picking the wrong temperature sensor during setup is easy to do, so the entity could be easly replaced in the menu.

---

## Optional Entities

Every optional entity may be left blank. The matching capability is switched off
and listed in diagnostics rather than failing.

| Left blank | What stops working |
|---|---|
| Outdoor temperature | Operating envelope check; falls back to the weather entity |
| Heat pump inlet or outlet | Delta-T and COP learning |
| Flow meter | Flow protection and self-correcting block duration |
| Power sensors | Energy, cost and measured COP |
| Price sensor | Price optimisation, including the free-electricity branch |
| Solar sensors | Solar optimisation |

---

## Heat Pump Thermostat Recommendation

Set the heat pump's own thermostat to the highest temperature you would ever want
plus about two degrees. If your maximum is 32 °C, set it to 34 °C. Below that you
keep full software control over any target, and above it the hardware intervenes
if the software ever fails to switch off. The setup wizard shows this suggestion
with your own numbers filled in.

---

## See Also

- [sensors.md](sensors.md) — Mapping your sensors to the right fields
- [architecture.md](architecture.md) — Entity fallback table and operating envelope
- [filtration.md](filtration.md) — Turnover, quiet hours, and pump rundown settings
- [heating.md](heating.md) — Heating appliance configuration
