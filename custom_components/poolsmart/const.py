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

#: Internal data schema version, independent of HA's STORAGE_VERSION.
#: Bumped when the serialized dict structure changes and old data needs
#: migration to be parseable by the current code.
DATA_VERSION = 1

#: How much quieter the debounced store save is allowed to get.
#:
#: Quiet saves -- a dose logged, a learned value reset -- do not need their own
#: write, because the next tick writes the same file anyway. The write only
#: matters when it is the last chance to save data, and those callers pass
#: ``force=True``. The tick itself runs far less often than this, so it is never
#: skipped.
STORAGE_SAVE_DEBOUNCE_SECONDS = 10

#: Number of decisions kept in the log.
DECISION_LOG_SIZE = 100

#: Number of finished heating sessions kept in the log.
SESSION_LOG_SIZE = 60

#: Number of days of runtime summaries kept before the oldest is dropped.
DAILY_SUMMARY_MAX_DAYS = 90

#: Number of monthly trend rows kept before the oldest is dropped. Unlike the
#: session and daily caps this is purely defensive -- ten years is 120 tiny
#: rows -- because the whole point of the monthly aggregate is to survive
#: those caps indefinitely. See core.aggregates.
MONTHLY_AGGREGATE_MAX_MONTHS = 120

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
#: Total household power draw -- a smart-meter/energy-dashboard sensor,
#: independent of the pool's own equipment. See issue #13.
CONF_GRID_POWER_SENSOR = "grid_power_sensor"
#: A sensor already reading in W/m2 -- a weather station's pyranometer, a
#: KNMI-style solar-radiation entity, and so on. Preferred over the solar
#: power sensor below wherever both are mapped, because it needs no peak
#: figure to scale against: it already reads in the unit this whole module
#: works in, for a pool with or without solar panels of its own.
CONF_IRRADIANCE_SENSOR = "irradiance_sensor"
CONF_WEATHER_ENTITY = "weather_entity"
CONF_COVER_ENTITY = "cover_entity"
#: An input_datetime helper the dashboard can set directly, checked before
#: the static swim_time/swim_time_2 fields defined below. See issue #17.
CONF_SWIM_TIME_ENTITY = "swim_time_entity"
#: An input_boolean helper for "not swimming today", checked the same way.
CONF_SWIM_SKIP_ENTITY = "swim_skip_entity"

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
CONF_HEATING_SOURCE = "heating_source"
CONF_POOL_KIND = "pool_kind"
CONF_HAS_SOLAR_COLLECTOR = "has_solar_collector"
CONF_COLLECTOR_SENSOR = "collector_sensor"
CONF_COLLECTOR_MARGIN = "collector_margin"
CONF_ADOPT_FROM = "adopt_from"

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
    CONF_PH_SENSOR,
    CONF_CHLORINE_SENSOR,
    CONF_TOTAL_CHLORINE_SENSOR,
    CONF_BROMINE_SENSOR,
    CONF_ALKALINITY_SENSOR,
    CONF_CYANURIC_SENSOR,
    CONF_HARDNESS_SENSOR,
    CONF_SALT_SENSOR,
    CONF_SOLAR_POWER_SENSOR,
    CONF_SOLAR_FORECAST_SENSOR,
    CONF_IRRADIANCE_SENSOR,
    CONF_WEATHER_ENTITY,
    CONF_COVER_ENTITY,
    CONF_COLLECTOR_SENSOR,
    CONF_SWIM_TIME_ENTITY,
    CONF_SWIM_SKIP_ENTITY,
    CONF_GRID_POWER_SENSOR,
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
    CONF_WEATHER_ENTITY: "weather_forecast_planning",
    CONF_GRID_POWER_SENSOR: "demand_limiting",
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
#: How a cheap_price_sensor signal relates to max_price. See
#: core.config.CheapPriceMode. See issue #22.
CONF_CHEAP_PRICE_MODE = "cheap_price_mode"
#: Absolute ceiling the cheap-period signal may not cross, only used in
#: CheapPriceMode.CHEAP_WINS_CAPPED. See issue #22.
CONF_CHEAP_PRICE_CEILING = "cheap_price_ceiling"
CONF_NEGATIVE_PRICE_BASIS = "negative_price_basis"
CONF_SOLAR_THRESHOLD_W = "solar_threshold_w"
#: House-power cap above which heating pauses. See issue #13.
CONF_POWER_LIMIT_W = "power_limit_w"
CONF_SOLAR_PEAK_W = "solar_peak_w"
CONF_SOLAR_MARGIN_W = "solar_margin_w"
CONF_SOLAR_HYSTERESIS_W = "solar_hysteresis_w"
CONF_ECO_PRICE_FACTOR = "eco_price_factor"
CONF_CALIBRATION_TOLERANCE = "calibration_tolerance"
CONF_STALE_WARNING_SECONDS = "stale_warning_seconds"
CONF_STALE_BLOCKING_SECONDS = "stale_blocking_seconds"
CONF_LEARNING_ENABLED = "learning_enabled"
CONF_MAX_STEP_RATIO = "max_step_ratio"
CONF_TREND_MIN_MONTHS = "trend_min_months"
CONF_SWIM_TIME = "swim_time"
CONF_SWIM_TIME_2 = "swim_time_2"
CONF_SWIM_DAYS = "swim_days"
CONF_NOTIFY_TARGETS = "notify_targets"
CONF_PRIVACY_LEVEL = "privacy_level"
CONF_CHEMISTRY_MINUTES = "chemistry_cycle_minutes"
CONF_ACID_PRODUCT = "acid_product"
CONF_CHLORINE_PRODUCT = "chlorine_product"
CONF_TABLET_GRAMS = "tablet_grams"

#: Dose records kept, which is plenty to learn a correction factor from.
DOSE_LOG_SIZE = 40

#: Accepted AI suggestions kept, with their outcome once judged. See #10.
ACCEPTED_SUGGESTIONS_LOG_SIZE = 40

DEFAULT_CHEMISTRY_MINUTES = 30

#: Starting price ceiling for heating, in the local currency per kWh.
DEFAULT_MAX_PRICE = 0.22

#: The one allowed range for max_price, in the local currency per kWh.
#: Shared by the options flow, the live number entity, the AI advisor's
#: adjustable-settings whitelist, and the poolsmart.set_setting service, so
#: the four cannot drift into disagreeing about what a valid price is. 2.0
#: comfortably covers even the worst dynamic-tariff price spikes seen so far.
MAX_PRICE_BOUNDS = (0.0, 2.0)

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
    CONF_HEATING_SOURCE: "heat_pump",
    CONF_POOL_KIND: "frame",
    CONF_HAS_SOLAR_COLLECTOR: False,
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

# -- Measurement thresholds -------------------------------------------------

#: Below this flow (m³/h) a reading is treated as "no flow", not as a working
#: pump with a slow stream. Any meter idle or priming reads this low or lower.
MIN_FLOW_M3H = 0.05

#: How quickly the learned flow follows the sensor. Slow enough that a fouling
#: filter registers as a decline rather than being absorbed into the average.
FLOW_LEARN_ALPHA = 0.002

#: A heat pump drawing fewer watts than this is idling on standby, not working;
#: a COP measured in that state means nothing.
HP_STANDBY_WATTS = 50

#: Below this fraction of the day a progress figure is too early to judge.
PROGRESS_EPSILON = 0.25
