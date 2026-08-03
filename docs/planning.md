[← Back to README](../README.md) • [Architecture](architecture.md) • **Planning** • [Learning](learning.md) • [Hardware](hardware.md) • [ESPHome](esphome.md) • [Defaults](defaults.md)
***

# 📅 Heating Planning & Price Optimization

PoolSmart handles pool heating dynamically rather than relying on fixed daily schedules[cite: 3]. The planner continuously balances price forecasts, heat loss estimates, and user-defined swim schedules to determine when and how long to heat[cite: 3].

---

## 🏎️ Maintenance vs. Seasonal Mode

Depending on the difference between the target temperature and current water temperature, the optimizer operates in one of two distinct modes[cite: 3]:

| Mode | Trigger / Condition | How It Works | Expected Result |
| :--- | :--- | :--- | :--- |
| **Maintenance** | Compensating daily heat loss ($\Delta T \le \sim 2\text{°C}$)[cite: 3]. | Selects the single cheapest interval or solar window before your next planned swim time[cite: 3]. | Reports a **Target Time** (e.g., *"Ready today at 14:30"*)[cite: 3]. |
| **Seasonal** | Warming up a cold pool after winter/fill-up ($\Delta T > 2\text{°C}$)[cite: 3]. | Requires long continuous runs (10–15+ hours)[cite: 3]. Projects budget across multiple days[cite: 3]. | Reports a **Target Date** (e.g., *"Ready on Saturday 16:00"*)[cite: 3]. |

> ⚠️ **Thermal Equilibrium Warning:** If heat loss equals or exceeds the maximum thermal output of your heat pump (e.g., during cold nights without a cover), Seasonal mode will explicitly notify you that the temperature cannot be reached instead of outputting an impossible target date[cite: 3].

---

## ⚡ Dynamic Electricity Price Integrations

PoolSmart parses hourly price attributes automatically from popular Home Assistant integrations (such as Nordpool, EnergyZero, Frank Energie, ENTSO-E, or custom template sensors)[cite: 3].

### Price Optimization Logic:
1. **Window Selection:** The optimizer maps the required heat-up duration against upcoming price slots before the scheduled swim time[cite: 3].
2. **COP Weighted Cost:** It adjusts the effective cost per thermal kWh using the self-learning COP curve[cite: 3]. *(A slightly higher electricity price at $22\text{°C}$ air temperature might actually be cheaper per thermal kWh than a lower price at $12\text{°C}$ air due to higher heat pump COP!)*[cite: 3]
3. **Fallback Mode:** If no valid price entity or forecast attribute is found, PoolSmart falls back to **heating on demand** whenever temperature drops below hysteresis[cite: 3].

---

## 🔗 Related Documentation

* [`architecture.md`](architecture.md) — Details on how the heat pump's operating envelope gates heating sessions[cite: 3].
* [`learning.md`](learning.md) — How COP per temperature band and thermal loss rates are learned over time[cite: 3].