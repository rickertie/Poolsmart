[← Back to README](../README.md) • [Architecture](architecture.md) • [Planning](planning.md) • **Learning** • [Hardware](hardware.md) • [ESPHome](esphome.md) • [Defaults](defaults.md)
***

# 🧠 Self-Learning Heating & Efficiency Model

PoolSmart automatically learns your pool's actual thermal behavior over time[cite: 2]. Instead of relying solely on factory datasheets, the system measures real-world performance after every heating session to continuously improve planning accuracy[cite: 2].

---

## 📊 What Is Learned?

After each heating session, PoolSmart updates three core parameters[cite: 2]:

1. **Heating Rate ($\text{°C/h}$):** How fast your pool water warms up per hour of active heating[cite: 2].
2. **Heat Loss Rate ($\text{°C/h}$):** How quickly your pool loses heat to ambient air and evaporation[cite: 2].
3. **COP Curve (per 5°C Air Band):** Thermal efficiency measured per 5°C outdoor temperature bracket (e.g., $10\text{--}15\text{°C}$, $15\text{--}20\text{°C}$, $20\text{--}25\text{°C}$)[cite: 2]. Because non-inverter heat pumps operate at fixed output, one COP value per temperature band is sufficient[cite: 2].

---

## 🛡️ The 3 Rules That Keep the Model Honest

To prevent corrupted sensors, hardware glitches, or open pool covers from ruining your baseline algorithms, PoolSmart enforces three strict validation rules[cite: 2]:

> 🧪 **Rule 1: Clean Sessions Only**  
> Interrupted sessions, safety trips, manual cut-offs, or sessions under the minimum measurement duration are logged and flagged, but **never used for learning**[cite: 2].

> 📉 **Rule 2: Weighted Moving Average (Exponential Smoothing)**  
> Every valid update is capped at a small fraction of the existing value[cite: 2]. A single unusual session (e.g., an exceptionally windy day) will only slightly nudge the model rather than overwrite it[cite: 2].

> 🚫 **Rule 3: Physical Outlier Rejection**  
> Data is rejected based on physical boundaries rather than purely statistical deviations[cite: 2]. For example:
> * A measured COP exceeding the heat pump's physical bounds[cite: 2].
> * Water failing to warm up while the pump was reported active[cite: 2].

---

## 🔍 Diagnostics & Session Logging

Rejected sessions are not deleted; they remain stored in the log history along with the explicit reason for rejection[cite: 2]. 

If the planning target dates stop updating or seem inaccurate, checking the **Learning** tab in the `/poolsmart` panel for rejected sessions is the first step in troubleshooting[cite: 2].

---

## 🔗 Related Documentation

* [`planning.md`](planning.md) — How the learned COP curve feeds directly into price optimization and heat scheduling[cite: 2, 3].
* [`architecture.md`](architecture.md) — Technical details on entity fallback when heat pump inlet/outlet sensors are missing[cite: 5].