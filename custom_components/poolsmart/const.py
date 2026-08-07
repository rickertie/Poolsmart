"""Constants and configuration keys for PoolSmart."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "poolsmart"
DEFAULT_NAME = "Pool"

#: Sidebar panel URL path.
PANEL_URL = "poolsmart"

#: Set on the config entry once entity ids have been migrated to the fixed,
#: language-independent form. Stored on the entry rather than in the store so it
#: survives a reset of the learned values.
MIGRATION_FLAG = "entity_ids_migrated"

#: How often the decision engine runs.
UPDATE_INTERVAL = timedelta(seconds=30)

#: Storage key and version for persisted state.
STORAGE_KEY = f"{DOMAIN}.state"
STORAGE_VERSION = 1

#: Number of decisions kept in the log.
DECISION_LOG_SIZE = 100

#: Number of finished heating sessions kept in the log.
SESSION_LOG_SIZE = 60

# -- Events, which is how decisions reach the Home Assistant logbook -------
EVENT_DECISION = f"{DOMAIN}_decision"
EVENT_OBSTACLE = f"{DOMAIN}_obstacle"
EVENT_FAULT = f"{DOMAIN}_fault"

ATTR_BRANCH = "branch"
ATTR_REASON = "reason"
ATTR_PUMP = "pump"
ATTR_HEAT_PUMP = "heat_pump"
ATTR_DURATION = "duration_seconds"
ATTR_BLOCKERS = "blockers"
ATTR_MESSAGE = "message"
ATTR_TRACE = "trace"

#: An obstacle is only worth logging again after this long. Without it, a pool
#: waiting all evening for a cheaper price would fill the logbook with the same
#: sentence every thirty seconds.
OBSTACLE_REPEAT_MINUTES = 30

#: Prefix on notification action ids, so taps meant for this integration can be
#: told apart from every other app's buttons.
ACTION_PREFIX = "POOLSMART_"

# -- Step 1: pool ----------------------------------------------------------
CONF_VOLUME_L = "volume_l"
CONF_SURFACE_M2 = "surface_m2"
CONF_DEPTH_M = "depth_m"
CONF_TARGET_TEMP = "target_temp"
CONF_MAX_TEMP = "max_temp"

# -- Step 2: circulation pump ---------------------------------------------
CONF_PUMP_FLOW_M3H = "pump_flow_m3h"
CONF_PUMP_FLOW_MEASURED = "pump_flow_measured"
CONF_PUMP_POWER_KW = "pump_power_kw"
CONF_PUMP_DERATE = "pump_datasheet_derate"
CONF_FILTER_MEDIA = "filter_media"

# -- Step 3: heat pump -----------------------------------------------------
CONF_HP_INPUT_KW = "hp_input_kw"
CONF_HP_THERMAL_KW = "hp_thermal_kw"
CONF_HP_COP_REF = "hp_cop_ref"
CONF_HP_COP_REF_TEMP = "hp_cop_ref_temp"
CONF_HP_COP_LOW = "hp_cop_low"
CONF_HP_COP_LOW_TEMP = "hp_cop_low_temp"
CONF_HP_COP_CLAMP_MIN = "hp_cop_clamp_min"
CONF_HP_COP_CLAMP_MAX = "hp_cop_clamp_max"
CONF_HP_AIR_TEMP_MIN = "hp_air_temp_min"
CONF_HP_AIR_TEMP_MAX = "hp_air_temp_max"
CONF_HP_FLOW_MIN_M3H = "hp_flow_min_m3h"
CONF_HP_FLOW_MIN_BLOCKING = "hp_flow_min_blocking"
CONF_HP_FLOW_MIN_VERIFIED = "hp_flow_min_site_verified"

# -- Step 4: required entities --------------------------------------------
CONF_PUMP_SWITCH = "pump_switch"
CONF_HP_SWITCH = "heat_pump_switch"
CONF_WATER_TEMP_SENSOR = "water_temp_sensor"

# -- Step 5: optional entities --------------------------------------------
CONF_AIR_TEMP_SENSOR = "air_temp_sensor"
CONF_PUMP_INLET_SENSOR = "pump_inlet_sensor"
CONF_PUMP_OUTLET_SENSOR = "pump_outlet_sensor"
CONF_HP_INLET_SENSOR = "hp_inlet_sensor"
CONF_HP_OUTLET_SENSOR = "hp_outlet_sensor"
CONF_FLOW_SENSOR = "flow_sensor"
CONF_FLOW_UNIT = "flow_unit"
CONF_PUMP_POWER_SENSOR = "pump_power_sensor"
CONF_HP_POWER_SENSOR = "hp_power_sensor"
CONF_PRICE_SENSOR = "price_sensor"
CONF_CHEAP_PRICE_SENSOR = "cheap_price_sensor"
CONF_SOLAR_POWER_SENSOR = "solar_power_sensor"
CONF_SOLAR_FORECAST_SENSOR = "solar_forecast_sensor"
CONF_WEATHER_ENTITY = "weather_entity"
CONF_COVER_ENTITY = "cover_entity"

# -- Water chemistry readings ---------------------------------------------
#
# Defined here rather than further down with the other chemistry settings,
# because OPTIONAL_ENTITY_KEYS below refers to them: a name has to exist before
# the tuple that lists it is built, and Python will not wait.
CONF_PH_SENSOR = "ph_sensor"
CONF_CHLORINE_SENSOR = "chlorine_sensor"
CONF_TOTAL_CHLORINE_SENSOR = "total_chlorine_sensor"
CONF_BROMINE_SENSOR = "bromine_sensor"
CONF_ALKALINITY_SENSOR = "alkalinity_sensor"
CONF_CYANURIC_SENSOR = "cyanuric_sensor"
CONF_HARDNESS_SENSOR = "hardness_sensor"
CONF_SALT_SENSOR = "salt_sensor"
CONF_SANITISER = "sanitiser"
CONF_UNIT_SYSTEM = "unit_system"

#: Which config key holds which chemistry reading, so the whole set can be read
#: in one pass rather than named individually everywhere.
CHEMISTRY_SENSORS = {
    "ph": CONF_PH_SENSOR,
    "free_chlorine": CONF_CHLORINE_SENSOR,
    "total_chlorine": CONF_TOTAL_CHLORINE_SENSOR,
    "bromine": CONF_BROMINE_SENSOR,
    "alkalinity": CONF_ALKALINITY_SENSOR,
    "cyanuric": CONF_CYANURIC_SENSOR,
    "hardness": CONF_HARDNESS_SENSOR,
    "salt": CONF_SALT_SENSOR,
}

OPTIONAL_ENTITY_KEYS = (
    CONF_AIR_TEMP_SENSOR,
    CONF_PUMP_INLET_SENSOR,
    CONF_PUMP_OUTLET_SENSOR,
    CONF_HP_INLET_SENSOR,
    CONF_HP_OUTLET_SENSOR,
    CONF_FLOW_SENSOR,
    CONF_PUMP_POWER_SENSOR,
    CONF_HP_POWER_SENSOR,
    CONF_PRICE_SENSOR,
    CONF_CHEAP_PRICE_SENSOR,
    CONF_TOTAL_CHLORINE_SENSOR,
    CONF_BROMINE_SENSOR,
    CONF_ALKALINITY_SENSOR,
    CONF_CYANURIC_SENSOR,
    CONF_HARDNESS_SENSOR,
    CONF_SALT_SENSOR,
    CONF_SOLAR_POWER_SENSOR,
    CONF_SOLAR_FORECAST_SENSOR,
    CONF_WEATHER_ENTITY,
    CONF_COVER_ENTITY,
)

#: Which capability each optional entity unlocks. Used to tell the user exactly
#: what is switched off when a field is left blank, instead of failing.
CAPABILITY_BY_ENTITY = {
    CONF_AIR_TEMP_SENSOR: "operating_envelope",
    CONF_PUMP_INLET_SENSOR: "calibration_check",
    CONF_PUMP_OUTLET_SENSOR: "delta_t_and_cop",
    CONF_HP_INLET_SENSOR: "delta_t_and_cop",
    CONF_HP_OUTLET_SENSOR: "delta_t_and_cop",
    CONF_FLOW_SENSOR: "flow_protection",
    CONF_PUMP_POWER_SENSOR: "energy_and_cost",
    CONF_HP_POWER_SENSOR: "energy_and_cost",
    CONF_PRICE_SENSOR: "price_optimisation",
    CONF_CHEAP_PRICE_SENSOR: "cheap_period_signal",
    CONF_SOLAR_POWER_SENSOR: "solar_optimisation",
    CONF_SOLAR_FORECAST_SENSOR: "solar_forecast",
}

# -- Options ---------------------------------------------------------------
CONF_TURNOVER_FACTOR = "turnover_factor"
CONF_MIN_DAILY_HOURS = "min_daily_hours"
CONF_PUMP_STARTUP_GRACE = "pump_startup_grace_seconds"
CONF_BLOCK_WINDOWS = "block_windows"
CONF_MIN_BLOCK_MINUTES = "min_block_minutes"
CONF_NIGHT_START = "night_start"
CONF_NIGHT_END = "night_end"
CONF_MIN_ON_MINUTES = "min_on_minutes"
CONF_MIN_OFF_MINUTES = "min_off_minutes"
CONF_PUMP_RUNDOWN_MINUTES = "pump_rundown_minutes"
CONF_COMPRESSOR_MIN_OFF = "compressor_min_off_minutes"
CONF_COMPRESSOR_MIN_ON = "compressor_min_on_minutes"
CONF_TEMP_HYSTERESIS = "temp_hysteresis"
CONF_MIN_WATER_TEMP = "min_water_temp"
CONF_FROST_AIR_TEMP = "frost_air_temp"
CONF_MAX_PRICE = "max_price"
CONF_NEGATIVE_PRICE_BASIS = "negative_price_basis"
CONF_SOLAR_THRESHOLD_W = "solar_threshold_w"
CONF_SOLAR_MARGIN_W = "solar_margin_w"
CONF_SOLAR_HYSTERESIS_W = "solar_hysteresis_w"
CONF_ECO_PRICE_FACTOR = "eco_price_factor"
CONF_CALIBRATION_TOLERANCE = "calibration_tolerance"
CONF_STALE_WARNING_SECONDS = "stale_warning_seconds"
CONF_STALE_BLOCKING_SECONDS = "stale_blocking_seconds"
CONF_LEARNING_ENABLED = "learning_enabled"
CONF_SWIM_TIME = "swim_time"
CONF_SWIM_TIME_2 = "swim_time_2"
CONF_SWIM_DAYS = "swim_days"
CONF_NOTIFY_TARGETS = "notify_targets"
CONF_CHEMISTRY_MINUTES = "chemistry_cycle_minutes"
CONF_ACID_PRODUCT = "acid_product"
CONF_CHLORINE_PRODUCT = "chlorine_product"
CONF_TABLET_GRAMS = "tablet_grams"

#: Dose records kept, which is plenty to learn a correction factor from.
DOSE_LOG_SIZE = 40

DEFAULT_CHEMISTRY_MINUTES = 30

#: Starting price ceiling for heating, in the local currency per kWh.
DEFAULT_MAX_PRICE = 0.22

#: Starting values for the setup wizard, so no field is ever blank.
#:
#: These describe a mid-sized above-ground pool with a typical cartridge pump and
#: a small heat pump. They are deliberately generic: baking one particular pool
#: into the integration would make it useless to anyone else. Anybody whose setup
#: differs overwrites them while working through the wizard, and the numbers that
#: matter most are explained in the help text underneath each field.
#:
#: To pre-fill your own values instead, drop a `poolsmart_defaults.json` file in
#: the Home Assistant configuration directory containing any of these keys. See
#: docs/DEFAULTS.md.
SETUP_DEFAULTS: dict[str, object] = {
    CONF_VOLUME_L: 10000,
    CONF_DEPTH_M: 1.2,
    CONF_TARGET_TEMP: 28.0,
    CONF_MAX_TEMP: 32.0,
    CONF_PUMP_FLOW_M3H: 3.0,
    CONF_PUMP_FLOW_MEASURED: False,
    CONF_FILTER_MEDIA: "sand",
    CONF_PUMP_POWER_KW: 0.1,
    CONF_HP_INPUT_KW: 1.0,
    CONF_HP_THERMAL_KW: 4.0,
    CONF_HP_COP_REF_TEMP: 26.0,
    CONF_HP_COP_LOW_TEMP: 15.0,
    CONF_HP_AIR_TEMP_MIN: 11.0,
    CONF_HP_AIR_TEMP_MAX: 43.0,
    CONF_HP_FLOW_MIN_M3H: 2.0,
    CONF_HP_FLOW_MIN_BLOCKING: False,
    CONF_HP_FLOW_MIN_VERIFIED: False,
    CONF_FLOW_UNIT: "l_min",
    CONF_UNIT_SYSTEM: "metric",
    CONF_SANITISER: "chlorine",
}

#: Optional file in the configuration directory that overrides SETUP_DEFAULTS.
DEFAULTS_FILE = "poolsmart_defaults.json"

#: Attribute names published by the tibber_prices integration. The all-in price
#: is the sensor state; the raw spot price and the tax component are attributes.
ATTR_ENERGY_PRICE = "energy_price"
ATTR_TAX = "tax"

#: Notification event types the user can route independently.
NOTIFY_EVENTS = (
    "heating_started",
    "target_reached",
    "flow_fault",
    "sensor_fault",
    "chemistry_alarm",
    "high_energy_cost",
    "heating_postponed",
    "ai_recommendation",
    "filter_service",
)
