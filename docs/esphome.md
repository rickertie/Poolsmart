[← Back to README](../README.md) • [Architecture](architecture.md) • [Planning](planning.md) • [Learning](learning.md) • [Hardware](hardware.md) • **ESPHome** • [Defaults](defaults.md)
***

# ⚡ ESPHome Setup & Calibration

PoolSmart follows a simple principle: **"ESPHome measures, Home Assistant decides."** 
You don't *need* ESPHome to use PoolSmart — any Home Assistant temperature sensor, flow meter, or switch integration works fine[cite: 4]. However, this page provides a complete, battle-tested ESPHome configuration for users building a custom ESP32 board[cite: 7].

---

## 🧠 Why Calculate Metrics on the ESP32?

While PoolSmart makes high-level decisions, having the ESP32 compute low-level physical metrics locally offers major advantages[cite: 7]:

* **Real-time Clamping:** Measured COP is clamped to the heat pump's physical limits before sending data to Home Assistant, preventing noisy readings from corrupting the self-learning model[cite: 7].
* **Predictive COP Curve:** Linear interpolation calculates expected COP based on outdoor temperature alone, allowing PoolSmart to plan heating *before* the heat pump has even run[cite: 7].
* **Safe $\Delta T$ Alarming:** The $\Delta T$ alarm only arms when the heat pump is actively running, eliminating false alarms during startup or simple circulation[cite: 7].

---

## 🧪 Calibration Procedures

### 1. Temperature Sensor Calibration (The Water Glass Test)
DS18B20 sensors are accurate to $\pm 0.5\text{°C}$[cite: 4]. While fine for room temperatures, a $0.4\text{°C}$ error on a heat pump raising water by only $2.5\text{°C}$ will skew COP calculations by over $30\%$[cite: 4]!

1. Submerge all 5 Dallas temperature probes into a single glass of room-temperature water[cite: 4].
2. Stir thoroughly and let sit for 5 minutes[cite: 4].
3. Read the values in Home Assistant — pick the **Pool Probe** as your reference standard[cite: 4].
4. Adjust the offset number entities in Home Assistant (`number.offset_*`) until all 4 remaining probes match the reference probe[cite: 4].

> 💡 **Tip:** Calibration offsets survive Home Assistant restarts and can be adjusted without reflashing ESPHome[cite: 4]!

---

### 2. Flow Meter Calibration (The Bucket Test)
The datasheet pulse ratio ($30 \times Q$) is a starting point, but pipe geometry and mounting angles affect real flow[cite: 4].

1. Note the current `flow_pulsen_raw` value in ESPHome logs or Home Assistant[cite: 4, 7].
2. Run the circulation pump and catch **exactly 10 Liters** of water from the pool return line into a container[cite: 4].
3. Calculate your custom divisor[cite: 4]:
   $$\text{flow\_deler} = \frac{\text{Total Pulses Counted}}{10}$$
4. Update `flow_deler` in your ESPHome `substitutions:` block and reflash[cite: 4, 7].

---