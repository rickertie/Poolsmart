# Hardware & ESPHome example

PoolSmart's works with "ESPHome measures, Home Assistant decides" this
page shows what that actually looks like in a deployment, so you have
something concrete to start from instead of a blank YAML file.

## Example setup

This is my own pool, shown as a worked example not a
requirement. Your sensors, pins and pool dimensions will differ.

| | |
|---|---|
| Pool | Intex Metal Frame 300x200x75cm — 3,834 L measured at 66 cm water level |
| Filter pump | Bestway Flowclear, ~3.6 m³/h measured, 100 W electric |
| Heat pump | W'eau Mini, ~0.58 kW electric input, ~3.0 kW thermal at 26 °C air |
| Controller | Seeed XIAO ESP32C6 running ESPHome |
| Temperature sensors | 5x Dallas (pool water, pump in, pump out, heat pump in/out, outdoor) |
| Flow meter | Cheap Aliexpress Yanmis DN50 pulse flow sensor | 

The ESP32 itself only measures and does light local math (delta-T, COP,
heating rate). PoolSmart in Home Assistant is what actually decides
exactly the split the tagline describes.

### What the ESPHome device calculates locally

A few things are worth doing on the device itself rather than in Home
Assistant, because they need to react to every new sample:

- **Delta-T** across the filter loop and across the heat pump itself
- **Measured heat output** (from delta-T and flow) and from that, a
  **measured COP**, clamped to the heat pump's real-world spec sheet
  so a noisy reading can't report a nonsense value
- A **predicted COP** from outdoor temperature (linear interpolation
  between two reference points), so PoolSmart can estimate performance
  *before* the heat pump has even run
- **Heating rate** (°C/h) from a rolling comparison of pool temperature
  over time
- A **delta-T alarm** that only ever fires while the heat pump is
  actually active, to catch a stuck valve or a flow problem early

Everything hardware-specific — pump flow, heat pump electrical input, COP
clamps, pool volume, GPIO pins, sensor addresses lives in one
`substitutions:` block at the top of the file. Change your pump, your heat
pump, or your pool, and that's the only section you touch; every
calculation below it follows automatically.

### Full example configuration

```yaml
substitutions:
  device_name: zwembad-controller
  friendly_name: "Zwembad Controller"

  # ── Pump ──────────────────────────────────────────────────
  pomp_flow_m3h: "3.596"        # Bestway Flowclear, measured
  pomp_vermogen_kw: "0.10"      # 100W electric
  pomp_aansluiting_mm: "32"

  # ── Heat pump — electrical/COP ────────────────────────────
  wp_input_kw: "0.58"           # W'eau Mini Power, nominal electric
  wp_cop_max: "6.0"             # Clamp: sanity upper bound for measured COP
  wp_cop_min: "3.0"             # Clamp: sanity lower bound for measured COP
  wp_vermogen_kw: "3.0"         # Thermal output at 26°C air (nominal)

  # ── Heat pump — predictive COP curve (for planning) ───────
  # Linear interpolation between these two reference points
  wp_cop_referentie: "5.17"     # COP at 26°C air
  wp_cop_laag: "4.18"           # COP at 15°C air
  wp_cop_t_hoog: "26.0"         # °C matching wp_cop_referentie
  wp_cop_t_laag: "15.0"         # °C matching wp_cop_laag

  # ── Heat pump — operating limits ──────────────────────────
  wp_min_lucht_temp: "11.0"     # Below this outdoor temp: heat pump may not run
  wp_max_lucht_temp: "43.0"     # Above this outdoor temp: heat pump may not run
  wp_min_flow_m3h: "2.0"        # Minimum flow required for the heat pump
  wp_geluid_db: "53"            # Informational only, not used in any lambda
  wp_setpoint_min: "15.0"       # Physical heat pump thermostat range
  wp_setpoint_max: "40.0"

  # ── Pool specification ────────────────────────────────────
  volume_l: "3834"              # Intex Metal Frame 300x200x75cm, 66cm water level
  oppervlak_m2: "6.0"           # Water surface (evaporation/heat loss)
  waterdiepte_m: "0.66"

  onewire_pin: "GPIO22"
  status_led_pin: "GPIO23"

  # ── Flow meter ─────────────────────────────────────────────
  flow_pin: "GPIO19"
  # Datasheet formula: Hz = 0.5 x Q (L/min)
  # pulse_counter gives pulses/min -> Q = pulses/min / 30
  # Adjust if your own calibration differs
  flow_deler: "12.0"

  addr_pool:    "0x1400000047ec8c28"  # Pool water
  addr_pmp_in:  "0x5100000048d31b28"  # Pump supply (IN to heat pump)
  addr_pmp_uit: "0x1f0000004840be28"  # Pump return (OUT of heat pump)
  addr_wp_in:   "0x5100000048d31b28"  # Heat pump inlet — reserved, sensor not yet placed
  addr_wp_uit:  "0x7d00000048da8928"  # Heat pump outlet
  addr_buiten:  "0xd8000000490c1a28"  # Outdoor temperature probe

  opwarm_interval: "300"
  delta_t_min_alarm: "1.0"
  delta_t_max_alarm: "4.0"
  delta_t_alarm_delay: "300s"

esphome:
  name: ${device_name}
  friendly_name: ${friendly_name}
  on_boot:
    priority: -100
    then:
      - script.execute: bereken_cop

esp32:
  board: seeed_xiao_esp32c6
  variant: esp32c6
  framework:
    type: esp-idf

logger:
  level: INFO

api:
  encryption:
    key: !secret api_key

ota:
  - platform: esphome
    password: !secret ota_password

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
  fast_connect: true
  ap:
    ssid: "${friendly_name} Fallback"
    password: !secret wifi_password

captive_portal:
web_server:
  port: 80
  version: "3"
bluetooth_proxy:
  active: true

one_wire:
  - platform: gpio
    pin: ${onewire_pin}

sensor:
  - platform: dallas_temp
    address: ${addr_pool}
    name: "Temperatuur"
    id: temp_pool
    unit_of_measurement: "°C"
    accuracy_decimals: 2
    update_interval: 30s
    filters:
      - filter_out: nan
      - median:
          window_size: 5
          send_every: 1
          send_first_at: 1
      - lambda: "return x + id(offset_pool).state;"
    on_value:
      then:
        - script.execute: bereken_cop
        - script.execute: bereken_opwarm_snelheid
    icon: "mdi:temperature-celsius"

  - platform: dallas_temp
    address: ${addr_pmp_in}
    name: "Aanvoer"
    id: temp_in
    unit_of_measurement: "°C"
    accuracy_decimals: 2
    update_interval: 30s
    filters:
      - filter_out: nan
      - median:
          window_size: 5
          send_every: 1
          send_first_at: 1
      - lambda: "return x + id(offset_pmp_in).state;"
    on_value:
      then:
        - script.execute: bereken_delta_t
    icon: "mdi:temperature-celsius"

  - platform: dallas_temp
    address: ${addr_pmp_uit}
    name: "Retour"
    id: temp_uit
    unit_of_measurement: "°C"
    accuracy_decimals: 2
    update_interval: 30s
    filters:
      - filter_out: nan
      - median:
          window_size: 5
          send_every: 1
          send_first_at: 1
      - lambda: "return x + id(offset_pmp_uit).state;"
    on_value:
      then:
        - script.execute: bereken_delta_t
    icon: "mdi:temperature-celsius"

  - platform: dallas_temp
    address: ${addr_wp_in}
    name: "WP In"
    id: temp_wp_in
    unit_of_measurement: "°C"
    accuracy_decimals: 2
    update_interval: 30s
    filters:
      - filter_out: nan
      - median:
          window_size: 5
          send_every: 1
          send_first_at: 1
      - lambda: "return x + id(offset_wp_in).state;"
    on_value:
      then:
        - script.execute: bereken_wp_delta_t
    icon: "mdi:temperature-celsius"

  - platform: dallas_temp
    address: ${addr_wp_uit}
    name: "WP Uit"
    id: temp_wp_uit
    unit_of_measurement: "°C"
    accuracy_decimals: 2
    update_interval: 30s
    filters:
      - filter_out: nan
      - median:
          window_size: 5
          send_every: 1
          send_first_at: 1
      - lambda: "return x + id(offset_wp_uit).state;"
    on_value:
      then:
        - script.execute: bereken_wp_delta_t
    icon: "mdi:temperature-celsius"

  # Temporary outdoor sensor. Feeds the predictive COP curve and the heat
  # pump temperature-range interlock. Can later be replaced by addr_wp_in
  # once that sensor is physically installed.
  - platform: dallas_temp
    address: ${addr_buiten}
    name: "Buiten"
    id: temp_buiten
    unit_of_measurement: "°C"
    accuracy_decimals: 2
    update_interval: 30s
    filters:
      - filter_out: nan
      - median:
          window_size: 5
          send_every: 1
          send_first_at: 1
    on_value:
      then:
        - script.execute: bereken_verwachte_cop
    icon: "mdi:temperature-celsius"

  - platform: template
    name: "WP Delta-T"
    id: wp_delta_t
    unit_of_measurement: "°C"
    accuracy_decimals: 2
    icon: mdi:heat-pump
    lambda: |-
      if (id(temp_wp_uit).has_state() && id(temp_wp_in).has_state()) {
        return id(temp_wp_uit).state - id(temp_wp_in).state;
      }
      return {};
    update_interval: 30s

  - platform: template
    name: "Delta-T"
    id: delta_t
    unit_of_measurement: "°C"
    accuracy_decimals: 2
    icon: mdi:thermometer-lines
    lambda: |-
      if (id(temp_uit).has_state() && id(temp_in).has_state()) {
        return id(temp_uit).state - id(temp_in).state;
      }
      return {};
    update_interval: 30s

  # Measured heat output, from measured delta-T and flow
  - platform: template
    name: "Warmtevermogen"
    id: warmte_vermogen
    unit_of_measurement: "kW"
    accuracy_decimals: 3
    icon: mdi:fire
    lambda: |-
      if (!id(temp_uit).has_state() || !id(temp_in).has_state()) return {};
      float dt = id(temp_uit).state - id(temp_in).state;
      float flow_val = ${pomp_flow_m3h}f;
      if (id(flow_m3h).has_state() && id(flow_m3h).state > 0.1f) {
        flow_val = id(flow_m3h).state;
      }
      float flow_kgs = flow_val / 3.6f;
      float kw = flow_kgs * 4.186f * dt;
      return kw < 0.0f ? 0.0f : kw;
    update_interval: 30s

  # Measured COP, from measured heat output / electrical input
  - platform: template
    name: "COP"
    id: actuele_cop
    unit_of_measurement: ""
    accuracy_decimals: 2
    icon: mdi:lightning-bolt-circle
    lambda: |-
      if (!id(warmte_vermogen).has_state() || id(warmte_vermogen).state < 0.1f) return {};
      float cop = id(warmte_vermogen).state / ${wp_input_kw}f;
      if (cop > ${wp_cop_max}f) cop = ${wp_cop_max}f;
      if (cop < ${wp_cop_min}f) cop = ${wp_cop_min}f;
      return cop;
    update_interval: 30s

  # Predicted COP from outdoor temperature — usable before the heat pump
  # has even run, e.g. for planning
  - platform: template
    name: "Verwachte COP"
    id: verwachte_cop
    unit_of_measurement: ""
    accuracy_decimals: 2
    icon: mdi:chart-line
    lambda: |-
      if (!id(temp_buiten).has_state()) return {};
      float t = id(temp_buiten).state;
      float cop_hoog = ${wp_cop_referentie}f;
      float cop_laag = ${wp_cop_laag}f;
      float t_hoog = ${wp_cop_t_hoog}f;
      float t_laag = ${wp_cop_t_laag}f;
      if (t >= t_hoog) return cop_hoog;
      if (t <= t_laag) return cop_laag;
      float interp = cop_laag + (cop_hoog - cop_laag) * (t - t_laag) / (t_hoog - t_laag);
      return interp;
    update_interval: 30s

  - platform: template
    name: "Opwarm Snelheid"
    id: opwarm_snelheid
    unit_of_measurement: "°C/h"
    accuracy_decimals: 2
    icon: mdi:trending-up
    lambda: |-
      static float last_temp = -999.0f;
      static unsigned long last_time_ms = 0;
      if (!id(temp_pool).has_state()) return {};
      unsigned long now_ms = millis();
      float current = id(temp_pool).state;
      if (last_temp < -990.0f) {
        last_temp = current;
        last_time_ms = now_ms;
        return {};
      }
      float elapsed_h = (now_ms - last_time_ms) / 3600000.0f;
      if (elapsed_h < 0.05f) return {};
      float rate = (current - last_temp) / elapsed_h;
      last_temp = current;
      last_time_ms = now_ms;
      if (rate > 5.0f || rate < -5.0f) return {};
      return rate;
    update_interval: ${opwarm_interval}s

  # ── Flow meter (Yanmis DN50 pulse) ─────────────────────────
  #
  # CALIBRATION — do this once after installing:
  # 1. Connect a bucket of known volume to the outlet (e.g. 10L)
  # 2. Turn the pump on, collect exactly 10L
  # 3. Read sensor.zwembad_controller_flow_pulsen_totaal
  # 4. Calculate: pulses_per_liter = total_pulses / 10
  # 5. Enter that number as flow_deler above
  #
  # Output is DC 5V pulses -> use a voltage divider down to 3.3V,
  # or a 5V-tolerant GPIO pin.

  - platform: pulse_counter
    pin:
      number: ${flow_pin}
      mode:
        input: true
        pullup: false
    name: "Flow Pulsen Min"
    id: flow_pulsen_raw
    unit_of_measurement: "pulsen/min"
    accuracy_decimals: 0
    icon: mdi:counter
    update_interval: 10s
    internal: true

  - platform: template
    name: "Flow Lmin"
    id: flow_lmin
    unit_of_measurement: L/min
    accuracy_decimals: 2
    icon: mdi:water-pump
    lambda: |-
      if (!id(flow_pulsen_raw).has_state()) return {};
      float lmin = id(flow_pulsen_raw).state / ${flow_deler}f;
      return lmin < 0.0f ? 0.0f : lmin;
    update_interval: 10s
    on_value:
      then:
        - script.execute: bereken_delta_t
    device_class: volume_flow_rate

  - platform: template
    name: "Flow m3h"
    id: flow_m3h
    unit_of_measurement: "m³/h"
    accuracy_decimals: 3
    icon: mdi:waves-arrow-right
    lambda: |-
      if (!id(flow_lmin).has_state()) return {};
      return id(flow_lmin).state * 0.06f;
    update_interval: 10s
    device_class: volume_flow_rate

  - platform: dallas_temp
    name: "Dallas Scan Sensor"
    id: dallas_scan
    update_interval: 10s
    filters:
      - filter_out: nan

  - platform: uptime
    name: "Uptime"
    update_interval: 60s

  - platform: wifi_signal
    name: "WiFi RSSI"
    update_interval: 60s
    icon: "mdi:wifi"

binary_sensor:
  # Only alarms while the heat pump is actually running
  - platform: template
    name: "Delta-T Alarm"
    id: delta_t_alarm
    device_class: problem
    icon: mdi:alert-circle
    lambda: |-
      if (!id(wp_actief).state) return false;
      if (!id(delta_t).has_state()) return false;
      float dt = id(delta_t).state;
      return (dt < ${delta_t_min_alarm}f || dt > ${delta_t_max_alarm}f);
    filters:
      - delayed_on: ${delta_t_alarm_delay}
      - delayed_off: 30s

  - platform: template
    name: "WP Actief"
    id: wp_actief
    icon: mdi:heat-pump
    lambda: |-
      if (!id(delta_t).has_state()) return false;
      return id(delta_t).state > 1.0f;
    device_class: running

  # Is the outdoor temperature within the heat pump's operating range?
  - platform: template
    name: "WP Temp Bereik OK"
    id: wp_temp_bereik_ok
    icon: mdi:thermometer-check
    lambda: |-
      if (!id(temp_buiten).has_state()) return false;
      float t = id(temp_buiten).state;
      return (t >= ${wp_min_lucht_temp}f && t <= ${wp_max_lucht_temp}f);

  # Checks the 3-way valve is set correctly (17-20 L/min through the heat pump)
  - platform: template
    name: "Pomp Flow OK voor WP"
    id: pomp_flow_ok_voor_wp
    icon: mdi:water-check
    lambda: |-
      if (!id(flow_lmin).has_state()) return false;
      float lmin = id(flow_lmin).state;
      return (lmin >= 17.0f && lmin <= 20.0f);
    filters:
      - delayed_on: 5s
      - delayed_off: 5s

script:
  - id: bereken_delta_t
    then:
      - component.update: delta_t
      - component.update: warmte_vermogen
      - component.update: actuele_cop

  - id: bereken_wp_delta_t
    then:
      - component.update: wp_delta_t

  - id: bereken_cop
    then:
      - component.update: actuele_cop

  - id: bereken_verwachte_cop
    then:
      - component.update: verwachte_cop

  - id: bereken_opwarm_snelheid
    then:
      - component.update: opwarm_snelheid

light:
  - platform: status_led
    name: "Status LED"
    pin:
      number: ${status_led_pin}
      inverted: true

text_sensor:
  - platform: wifi_info
    ip_address:
      name: "IP Adres"
    ssid:
      name: "WiFi SSID"
    mac_address:
      name: "MAC Adres"
  - platform: version
    name: "ESPHome Versie"

number:
  # Sensor calibration offsets, adjustable from Home Assistant.
  # Positive = sensor reads too low (add), negative = too high (subtract)
  - platform: template
    name: "Offset Pool"
    id: offset_pool
    unit_of_measurement: "°C"
    icon: mdi:thermometer-lines
    min_value: -2.0
    max_value: 2.0
    step: 0.01
    initial_value: 0.04
    restore_value: true
    optimistic: true
    mode: BOX

  - platform: template
    name: "Offset Pomp In"
    id: offset_pmp_in
    unit_of_measurement: "°C"
    icon: mdi:thermometer-lines
    min_value: -2.0
    max_value: 2.0
    step: 0.01
    initial_value: 0.10
    restore_value: true
    optimistic: true
    mode: BOX

  - platform: template
    name: "Offset Pomp Uit"
    id: offset_pmp_uit
    unit_of_measurement: "°C"
    icon: mdi:thermometer-lines
    min_value: -2.0
    max_value: 2.0
    step: 0.01
    initial_value: 0.41
    restore_value: true
    optimistic: true
    mode: BOX

  - platform: template
    name: "Offset WP In"
    id: offset_wp_in
    unit_of_measurement: "°C"
    icon: mdi:thermometer-lines
    min_value: -2.0
    max_value: 2.0
    step: 0.01
    initial_value: 0.35
    restore_value: true
    optimistic: true
    mode: BOX

  - platform: template
    name: "Offset WP Uit"
    id: offset_wp_uit
    unit_of_measurement: "°C"
    icon: mdi:thermometer-lines
    min_value: -2.0
    max_value: 2.0
    step: 0.01
    initial_value: 0.22
    restore_value: true
    optimistic: true
    mode: BOX

button:
  - platform: restart
    name: "Herstart"
    id: restart_button

  - platform: template
    name: "Dallas Scan"
    icon: mdi:thermometer-probe
    on_press:
      then:
        - logger.log:
            level: INFO
            format: "=== Dallas scan — open ESPHome logs after restart ==="
        - delay: 1s
        - button.press: restart_button
```

### Why the ESPHome-side calculations matter

A couple of design choices worth calling out, because they're easy to
overlook:

- **Clamping the measured COP** to the heat pump's own realistic range
  means a single noisy reading can't feed a wildly wrong value into
  PoolSmart's learning model in Home Assistant.
- **The delta-T alarm only arms while the heat pump is confirmed active**
  (via its own delta-T threshold), so it doesn't false-alarm during
  startup or while the pump is simply circulating without heating.
- **The predictive COP curve** means PoolSmart can reason about
  "is heating worth it right now" using outdoor temperature alone,
  before it has any live heat pump data for the day.

None of this is required to use PoolSmart a much simpler ESPHome config
with just a pool temperature sensor works fine, with fewer features
available. This example shows what's possible once you add flow and
heat-pump-loop sensors.
