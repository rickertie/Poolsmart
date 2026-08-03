[← Back to README](../README.md) • [Architecture](architecture.md) • [Planning](planning.md) • [Learning](learning.md) • [Hardware](hardware.md) • [ESPHome](esphome.md) • [Defaults](defaults.md)
***

# Sensors and ESPHome

PoolSmart does not require ESPHome. It reads whatever temperature, flow and
power sensors you point it at Shelly, Zigbee, Tasmota, a template sensor
fed from somewhere else. `pool_sensors.yaml` is a worked example for people
building their own board, not a dependency.

## What goes where

| | Board | Integration |
|---|---|---|
| Reading probes | ✅ | |
| Calibration offsets | ✅ | |
| Converting pulses to flow | ✅ | |
| Delta-T | | ✅ |
| Thermal power | | ✅ |
| COP | | ✅ |
| Deciding what should run | | ✅ |

This split moved in version 0.12.2. Earlier the board calculated delta-T and
thermal power, which had two problems: those figures only existed for people
running ESPHome, and once a calibration offset changed on one side the two
numbers drifted apart with no way to tell which was right.

Everything derived now lives in one place. Fit two probes, tell the integration
which is the heat pump inlet and which is the outlet, and delta-T, thermal power
and COP appear regardless of what hardware produced the readings.

## Calibrating the temperature probes

DS18B20s are accurate to roughly ±0.5 °C. Fine for a room. Not fine here.

A heat pump moving 3 kW through 1 m³/h of water produces about 2.5 °C of rise.
Two probes off by 0.4 °C in opposite directions turn that into 1.7 °C, and the
COP calculated from it is out by a third  which then feeds the learning model
and stays wrong.

1. Put all five probes in one glass of water. Stir it. Wait five minutes.
2. Read all five. They should agree; they will not.
3. Pick the pool probe as the reference.
4. Adjust the other offsets until they match. A probe reading low needs a
   positive offset.

The offsets are number entities, so no reflashing, and they survive restarts.
Worth redoing once a season.

## Calibrating the flow meter

This is the measurement everything else leans on. Filtration duration is
calculated directly from flow, so an error here becomes an error in how long the
pump runs every single day.

**The datasheet is a starting point, not an answer.** Yanmis DN50 quotes
Hz = 0.5 × Q(L/min), giving pulses/min = 30 × Q, so the divisor is 30. Installed
meters routinely differ: pipe diameter, nearby elbows and mounting orientation
all shift the figure.

**The bucket test settles it.** Five minutes, once:

1. Note `Flow pulses total` in Home Assistant.
2. Run the pump and catch exactly 10 litres from the return.
3. Note the total again. The difference is pulses per 10 litres.
4. `flow_divisor` = difference ÷ 10.
5. Put that number in the substitutions and reflash.

**Sanity check before you trust a reading.** At a divisor of 30, a flow of
17 L/min means the raw pulse count sits at 510 per minute. If your raw count is
nowhere near that, the divisor is wrong.

This is worth being fussy about. A divisor of 12 against a true 30 reports
17 L/min where the reality is under 7  and the daily filtration requirement
that follows from it would be more than twice too short, while looking entirely
plausible on the dashboard.

## Wiring the flow meter

Hall effect meters output 5 V pulses. ESP32 pins are not 5 V tolerant.

```
meter signal ──[ 10 kΩ ]──┬── GPIO
                          │
                       [ 20 kΩ ]
                          │
                         GND
```

That lands at 3.3 V. Connecting 5 V directly works for a while, then destroys
the pin. have done that :-)

## Pointing the integration at the sensors

Settings → Devices & services → PoolSmart → Configure → Entities.

| Field | Sensor |
|---|---|
| Pool water temperature | `sensor.<device>_pool_water_temperature` |
| Outdoor temperature | `sensor.<device>_outdoor_temperature` |
| Heat pump inlet | `sensor.<device>_pump_outlet_temperature` |
| Heat pump outlet | `sensor.<device>_heat_pump_outlet_temperature` |
| Flow meter | `sensor.<device>_flow` |

The inlet mapping surprises people. If the plumbing runs pool → pump → heat pump
→ pool, then the pump *outlet* is physically the heat pump *inlet*. Using it
means delta-T works without fitting a fifth probe.

Do not point inlet and outlet at the same entity. The integration detects that
and refuses to report a permanent zero difference as a real measurement, but it
also cannot give you delta-T or COP until they are two distinct probes.

## Without ESPHome

Point the integration at whatever you have. Only three entities are required 
the two switches and a water temperature. Everything else is optional and
switches off cleanly when left blank, with the reason visible in the panel.
