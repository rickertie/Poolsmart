[← Back to README](../README.md) • [Architecture](architecture.md) • [Planning](planning.md) • [Learning](learning.md) • [Hardware](hardware.md) • **ESPHome** • [Sensors](SENSORS.md) • [Defaults](DEFAULTS.md)

---

# ESPHome Setup & Calibration

This document covers the ESPHome configuration for the sensor board: why
calculations live in the integration rather than on the board, and how to
calibrate the temperature probes and flow meter. For the physical wiring guide,
see [hardware.md](hardware.md). For mapping sensors to integration fields, see
[SENSORS.md](SENSORS.md).

---

## Why Calculate Metrics in the Integration?

PoolSmart follows a simple principle: **"ESPHome measures, Home Assistant
decides."**

You do not *need* ESPHome to use PoolSmart — any Home Assistant temperature
sensor, flow meter, or switch integration works fine. However, this page
provides a complete, battle-tested ESPHome configuration for users building a
custom ESP32 board.

The integration calculates delta-T, thermal power, and COP itself. Earlier
versions of the example configuration calculated these on the board, which had
two problems: those figures only existed for people running ESPHome, and once a
calibration offset changed on one side the two numbers drifted apart with no way
to tell which was right.

What belongs here: reading hardware, calibrating it, publishing honest numbers
with correct units. What belongs in the integration: everything derived from
those numbers, and every decision about what to do.

---

## Calibration Procedures

### 1. Temperature Sensor Calibration (The Water Glass Test)

DS18B20 sensors are accurate to ±0.5 °C. While fine for room temperatures, a
0.4 °C error on a heat pump raising water by only 2.5 °C will skew COP
calculations by over 30%.

1. Submerge all five Dallas temperature probes into a single glass of
   room-temperature water.
2. Stir thoroughly and let sit for 5 minutes.
3. Read the values in Home Assistant — pick the **pool probe** as your
   reference standard.
4. Adjust the offset number entities in Home Assistant (`number.offset_*`)
   until all four remaining probes match the reference probe.

> **Tip:** Calibration offsets survive Home Assistant restarts and can be
> adjusted without reflashing ESPHome.

---

### 2. Flow Meter Calibration (The Bucket Test)

The datasheet pulse ratio (30 × Q) is a starting point, but pipe geometry and
mounting angles affect real flow.

1. Note the current `flow_pulses_total` value in ESPHome logs or Home Assistant.
2. Run the circulation pump and catch **exactly 10 litres** of water from the
   pool return line into a container.
3. Calculate your custom divisor:

   ```
   flow_divisor = Total Pulses Counted / 10
   ```

4. Update `flow_divisor` in your ESPHome `substitutions:` block and reflash.

---

## See Also

- [hardware.md](hardware.md) — Physical wiring, pinouts, and component selection.
- [SENSORS.md](SENSORS.md) — Sensor mapping, probe calibration, and flow meter
  wiring.
- [esphome/pool_sensors.yaml](../esphome/pool_sensors.yaml) — Complete example
  ESPHome configuration with calibration offsets and heartbeat filters.
