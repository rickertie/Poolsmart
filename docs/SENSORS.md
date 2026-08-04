[← Back to README](../README.md) • [Architecture](architecture.md) • [Planning](planning.md) • **Learning** • [Hardware](hardware.md) • [ESPHome](esphome.md) • [Defaults](defaults.md)
***

# Sensors and ESPHome

PoolSmart does not require ESPHome. It reads whatever temperature, flow and
power sensors you point it at — Shelly, Zigbee, Tasmota, a template sensor
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
COP calculated from it is out by a third — which then feeds the learning model
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
17 L/min where the reality is under 7 — and the daily filtration requirement
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
the pin.

## Pointing the integration at the sensors

Settings → Devices & services → PoolSmart → Configure → Entities.

| Field | Sensor | Purpose |
|---|---|---|
| Pool water temperature | `sensor.<device>_pool_water_temperature` | Required |
| Outdoor temperature | `sensor.<device>_outdoor_temperature` | Operating envelope, frost |
| Pump inlet | `sensor.<device>_pump_inlet_temperature` | Calibration check |
| Pump outlet | `sensor.<device>_pump_outlet_temperature` | Delta-T, COP |
| Heat pump inlet | *depends on your plumbing, see below* | Delta-T, COP |
| Heat pump outlet | `sensor.<device>_heat_pump_outlet_temperature` | Delta-T, COP |
| Flow meter | `sensor.<device>_flow` | Flow protection, filtration timing |
| Electricity price | your tariff integration | Price optimisation |
| Cheap price period | your tariff integration's binary sensor | Beats the price ceiling |

Pump inlet, pump outlet, heat pump inlet and heat pump outlet are four separate
fields on purpose, because plumbing differs between installations. A pool with a
filter housing, a longer run, or anything else between the circulation pump and
the heat pump has four real points to measure, and forcing two of them into one
field would be wrong for that installation even though it happened to be right
for the one this integration was first built on.

**If your plumbing runs pool → pump → heat pump → pool with nothing in
between**, and you only fitted one probe at that junction, the pump outlet and
the heat pump inlet are physically the same point. Point both fields at that one
entity rather than leaving either blank. The integration recognises two fields
sharing an entity as one measurement — it will not compare a probe against
itself and report a fault that is not one, and every calculation that needs a
heat pump inlet reading gets it either way. This is the case in the example
ESPHome configuration in `docs/esphome/`, which publishes one "Pump outlet
temperature" sensor and expects it mapped into both fields.

**If your heat pump sits further from the pump**, with its own dedicated inlet
probe, configure that probe under "Heat pump inlet" and leave "Pump outlet" as
the separate reading it is. Nothing about the calculations changes; they simply
read from four distinct sensors instead of three.

**The pump inlet probe is worth wiring up on its own merits.** It measures the
same water as the pool probe, a metre apart, so the two should agree. When they
do not, one of three things is true: a probe needs calibrating, the pool is
stratified from too little circulation, or a probe is not actually in the water.
It is the only check in the system able to notice that a temperature reading is
simply wrong
rather than merely surprising — and a miscalibrated probe quietly corrupts
delta-T and every COP figure that follows from it.

Leave it blank and nothing breaks; you just lose that check.

**Heat pump inlet and heat pump outlet must stay two distinct entities.**
Pointing them at the same one, unlike pump outlet and heat pump inlet above,
gets refused: the integration will not report a permanent zero difference as a
real measurement, but it also cannot give you delta-T or COP until they are two
separate probes either side of the appliance.

## Without ESPHome

Point the integration at whatever you have. Only three entities are required —
the two switches and a water temperature. Everything else is optional and
switches off cleanly when left blank, with the reason visible in the panel.