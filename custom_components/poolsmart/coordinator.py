"""The tick.

Every 30 seconds: gather, assess, decide, execute, log, persist. The decision
itself comes from :mod:`core.ladder` and nowhere else. This module is plumbing --
it must never contain a rule about when something should run.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, time, timedelta
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_DEVICE_ID, ATTR_NAME
from homeassistant.helpers import device_registry as dr
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import const as c
from .core import chemistry as chem
from .core import filtration as filt
from .core import heating, ladder, learning, optimizer, safety
from .core.trace import NearMissLog, Trace
from .core.config import (
    INITIAL_HEAT_LOSS,
    PoolKind,
    display_amount,
    FILTER_MEDIA_DERATE,
    ComfortSettings,
    EnergySettings,
    FiltrationSettings,
    HeatPumpSpec,
    LearningSettings,
    PoolConfig,
    PoolSpec,
    PumpSpec,
    SafetySettings,
)
from .core.models import Branch, Decision, Fault, Mode, PoolState, SensorReading, Severity
from .ai.advisor import Advisor
from .engine.chemistry import ChemistryModule
from .engine.cover import CoverModule
from .notify import ActionHandler, NotificationManager
from .price import average_price, extract_forecast
from .store import PoolStore

_LOGGER = logging.getLogger(__name__)

UNAVAILABLE = ("unknown", "unavailable", "none", "")

#: How often the weather forecast is refetched. A forecast does not move fast
#: enough to justify a service call on every tick, and a figure up to this old
#: is still far closer to tomorrow's weather than none at all.
_WEATHER_FORECAST_REFRESH = timedelta(minutes=30)

#: How long after rain was last observed chemistry advice and the test
#: interval keep treating the water as recently rained-on.
_RECENT_RAIN_WINDOW = timedelta(hours=12)

#: How far ahead the forecast is averaged into one figure: about a day of
#: hourly entries, or a couple of days when only a daily forecast is on offer.
_WEATHER_FORECAST_HOURLY_HORIZON = 24
_WEATHER_FORECAST_DAILY_HORIZON = 2

#: Physically plausible ranges per sensor role, as (min, max). Readings outside
#: these are rejected at ingestion rather than stored in ``_last_good``, so an
#: impossible value can never be used as the fallback when bridging or leak into
#: a calculation before fault detection catches it on the next tick.
_PLAUSIBLE_RANGES: dict[str, tuple[float, float]] = {
    "water": (-5.0, 55.0),
    "air": (-5.0, 55.0),
    "pump_inlet": (-5.0, 55.0),
    "pump_outlet": (-5.0, 55.0),
    "hp_inlet": (-5.0, 55.0),
    "hp_outlet": (-5.0, 55.0),
    "collector": (-5.0, 55.0),
    "pump_power": (0.0, 10000.0),
    "hp_power": (0.0, 10000.0),
    "solar": (0.0, 1500.0),
    "irradiance": (0.0, 1500.0),
}

#: Conversion to cubic metres per hour.
#:
#: Two kinds of key live here on purpose. The unit a sensor publishes in its
#: ``unit_of_measurement`` is a real unit string like "L/min", and that is
#: checked first. The setting chosen in the config flow is a slug like "l_min",
#: because Home Assistant translation keys cannot contain a slash or a
#: superscript — so the stored value and the displayed unit are different
#: strings for the same thing, and both have to resolve.
FLOW_UNIT_FACTORS = {
    # As published by a sensor
    "m³/h": 1.0,
    "m3/h": 1.0,
    "m³/u": 1.0,
    "m3/u": 1.0,
    "l/min": 0.06,
    "lpm": 0.06,
    "l/m": 0.06,
    "l/h": 0.001,
    "l/u": 0.001,
    "lph": 0.001,
    "l/s": 3.6,
    "gpm": 0.2271,  # both the published unit and the stored slug
    # As stored by the config flow
    "m3_h": 1.0,
    "l_min": 0.06,
    "l_h": 0.001,
    "l_s": 3.6,
}


#: HA weather-entity `state.state` values that mean active precipitation.
#: See https://www.home-assistant.io/integrations/weather/ for the full set
#: of standard condition strings.
_RAINY_CONDITIONS = {"rainy", "pouring", "lightning-rainy", "snowy", "snowy-rainy", "hail"}


def _condition_is_rainy(condition: str | None) -> bool:
    return condition in _RAINY_CONDITIONS


def _positive_number(value) -> bool:
    return isinstance(value, (int, float)) and value > 0


def _parse_time(raw: str | None, fallback: time) -> time:
    if not raw:
        return fallback
    try:
        hour, minute = str(raw).split(":")[:2]
        return time(int(hour), int(minute))
    except (ValueError, TypeError):
        return fallback


class PoolSmartCoordinator(DataUpdateCoordinator):
    """Runs the decision engine and drives the two switches."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=c.DOMAIN,
            update_interval=c.UPDATE_INTERVAL,
        )
        self.entry = entry
        self.store = PoolStore(hass, entry.entry_id)

        self.decision: Decision | None = None
        self.faults: list[Fault] = []
        self.filtration: filt.FiltrationStatus | None = None
        self.estimate: heating.HeatingEstimate | None = None
        self.plan: optimizer.HeatingPlan | None = None
        #: What the ladder considered on the last tick.
        self.trace: Trace | None = None
        self.near_misses = NearMissLog()
        self.notifier = NotificationManager(hass, self)
        self.actions = ActionHandler(hass, self)
        self.advisor = Advisor(hass, self)
        self.chemistry = ChemistryModule(self)
        self.cover = CoverModule(self, self._conf(c.CONF_COVER_ENTITY))
        self.heat_pump_available: bool = False
        self.heat_pump_gate_reason: str = ""
        self.disabled_capabilities: set[str] = set()
        #: Last tick-level failure, surfaced in diagnostics and the status sensor.
        self.last_error: str | None = None
        #: Optional subsystems that failed, and when. Control continues without them.
        self.subsystem_errors: dict[str, str] = {}
        #: Set just before an options update that already took effect live (see
        #: :meth:`async_set_max_price`), so the config entry's update listener
        #: knows to skip the reload it would otherwise trigger. Consumed by
        #: :meth:`consume_suppressed_reload`.
        self._suppress_next_reload: bool = False

        self._mode: Mode = Mode.AUTO
        self._target_temp: float = self._conf(c.CONF_TARGET_TEMP, 28.0)
        self._manual_pump_request = False
        self._hp_running_since: datetime | None = None
        self._pump_running_since: datetime | None = None
        self._last_tick: datetime | None = None
        self._session: learning.SessionRecord | None = None
        self._idle_since: datetime | None = None
        self._idle_water_temp: float | None = None
        self._idle_covered: bool | None = None
        self._idle_irradiance_samples: list[float] = []
        self._idle_daylight: bool = False
        #: Whether rain was observed at any point during the current idle
        #: period, so the resulting heat-loss sample can be excluded rather
        #: than attributing weather-driven loss to the pool itself. See #7.
        self._idle_rain_seen: bool = False
        self._session_cost: float = 0.0
        self._price_slots: tuple = ()
        #: Air temperature the weather forecast expects over the coming day,
        #: averaged into one figure. ``None`` when no weather entity is
        #: mapped, or the last fetch failed.
        self._forecast_air_temp: float | None = None
        #: Highest precipitation probability (0-100) seen across the same
        #: forecast window, or None when the weather integration does not
        #: report one. See issue #7.
        self._forecast_rain_probability: float | None = None
        #: Whether the mapped weather entity currently reports a rainy
        #: condition or active precipitation. None when no entity is mapped.
        self._is_raining_now: bool | None = None
        #: Last time rain was actually observed, for the "recent rain" window
        #: chemistry advice and the test interval use. See #7.
        self._last_rain_seen_at: datetime | None = None
        self._forecast_fetched_at: datetime | None = None
        self._last_obstacle: tuple | None = None
        self._last_obstacle_at: datetime | None = None
        self._active_faults: dict[str, datetime] = {}
        self._device_id_cache: str | None = None
        self._last_good: dict[str, tuple[float, datetime]] = {}
        #: Desired switch states, set when a command is sent and verified against
        #: the actual state on subsequent ticks.
        self._desired_pump_state: bool | None = None
        self._desired_heat_pump_state: bool | None = None
        self._desired_pump_since: datetime | None = None
        self._desired_heat_pump_since: datetime | None = None
        self._pump_mismatch_ticks: int = 0
        self._heat_pump_mismatch_ticks: int = 0
        #: Roles currently running on a carried-forward reading.
        self.bridged_roles: set[str] = set()
        #: Built once and reused, because the wizard's answers (and nothing
        #: else on a live copy) feed every part of every tick. Invalidated when
        #: the target temperature moves, since that is the one field the
        #: entities change at runtime.
        self._config_cache: PoolConfig | None = None
        #: Cached chemistry picture, rebuilt once per tick. Invalidated at the
        #: start of each tick and when a dose or water test is recorded, since
        #: both change the corrections and dose log the picture is built from.
        self._chemistry_cache: dict | None = None
        self._chemistry_cache_tick: datetime | None = None

    # -- Configuration -----------------------------------------------------

    def _conf(self, key: str, default=None):
        """Options override data, so the options flow can change anything."""
        if key in self.entry.options:
            return self.entry.options[key]
        return self.entry.data.get(key, default)

    def _default_solar_threshold(self) -> float:
        """Solar surplus at which heating counts as free.

        A fixed default is wrong for everyone: the figure has to be at least what
        the equipment draws, and that is a property of the installation. A 3 kW
        heat pump drawing 580 W with a 100 W pump needs 680 W plus a margin, so a
        blanket 1500 W meant missing every moderately sunny afternoon.
        """
        draw_w = (
            float(self._conf(c.CONF_HP_INPUT_KW, 1.0))
            + float(self._conf(c.CONF_PUMP_POWER_KW, 0.1))
        ) * 1000.0
        return round(draw_w + float(self._conf(c.CONF_SOLAR_MARGIN_W, 200)), 0)

    def _min_hours_curve(self) -> tuple[tuple[float, float], ...]:
        """The time-based daily minimum, scaled by water temperature.

        The user sets one number -- the minimum at a normal swimming temperature
        -- and the curve is derived from it, so there is one dial rather than
        five to keep consistent.
        """
        base = float(self._conf(c.CONF_MIN_DAILY_HOURS, 4.0))
        return (
            (15.0, round(base * 0.5, 2)),
            (20.0, round(base * 0.75, 2)),
            (25.0, base),
            (30.0, round(base * 1.25, 2)),
            (99.0, round(base * 1.5, 2)),
        )

    @property
    def pool_config(self) -> PoolConfig:
        """The pure-Python config, built once from the config entry.

        Building it parses the block windows, resolves every optional sensor
        alias into a frozenset of roles and constructs a dozen nested dataclasses.
        On a thirty-second tick none of that changes, so it is computed once and
        reused until something changes it. The one runtime value it carries is the
        target temperature, which is why :meth:`async_set_target` throws the cache
        away.
        """
        if self._config_cache is None:
            self._config_cache = self._build_pool_config()
        return self._config_cache

    def _build_pool_config(self) -> PoolConfig:
        """Build the pure-Python config from the config entry."""
        windows_raw = self._conf(
            c.CONF_BLOCK_WINDOWS, [["07:00", "11:00"], ["12:00", "17:00"], ["17:00", "21:00"]]
        )
        windows = []
        for pair in windows_raw:
            if len(pair) < 2:
                _LOGGER.warning(
                    "Block window %r is missing an end time and will be ignored", pair
                )
                continue
            start, end = pair[0], pair[1]
            windows.append((_parse_time(start, time(7, 0)), _parse_time(end, time(11, 0))))
        windows = tuple(windows)

        # Two logical roles pointing at one physical sensor would otherwise be
        # compared against each other, yielding a permanent zero difference and a
        # fault that does not exist.
        aliases: set[frozenset[str]] = set()
        inlet = self._conf(c.CONF_HP_INLET_SENSOR)
        outlet = self._conf(c.CONF_HP_OUTLET_SENSOR)
        water = self._conf(c.CONF_WATER_TEMP_SENSOR)
        pump_inlet = self._conf(c.CONF_PUMP_INLET_SENSOR)
        pump_outlet = self._conf(c.CONF_PUMP_OUTLET_SENSOR)
        # Every configured temperature role is compared against every other.
        # This is what lets someone whose pump outlet and heat pump inlet really
        # are the same physical probe just point both fields at it: the two
        # roles are recognised as one measurement rather than compared as if
        # they were independent, which would otherwise report a permanent
        # zero-difference "fault" that is not one.
        roles = (
            ("hp_inlet", inlet),
            ("hp_outlet", outlet),
            ("water", water),
            ("pump_inlet", pump_inlet),
            ("pump_outlet", pump_outlet),
        )
        for role_a, entity_a in roles:
            for role_b, entity_b in roles:
                if role_a != role_b and entity_a and entity_a == entity_b:
                    aliases.add(frozenset({role_a, role_b}))

        return PoolConfig(
            pool=PoolSpec(
                volume_l=float(self._conf(c.CONF_VOLUME_L, 10000)),
                surface_m2=float(self._conf(c.CONF_SURFACE_M2, 10.0)),
                depth_m=float(self._conf(c.CONF_DEPTH_M, 1.0)),
            ),
            pump=PumpSpec(
                flow_m3h=float(self._conf(c.CONF_PUMP_FLOW_M3H, 3.0)),
                flow_is_measured=bool(self._conf(c.CONF_PUMP_FLOW_MEASURED, False)),
                power_kw=float(self._conf(c.CONF_PUMP_POWER_KW, 0.1)),
                datasheet_derate=float(
                    self._conf(
                        c.CONF_PUMP_DERATE,
                        FILTER_MEDIA_DERATE.get(
                            self._conf(c.CONF_FILTER_MEDIA, "sand"), 0.7
                        ),
                    )
                ),
            ),
            heat_pump=HeatPumpSpec(
                input_kw=float(self._conf(c.CONF_HP_INPUT_KW, 1.0)),
                thermal_kw=float(self._conf(c.CONF_HP_THERMAL_KW, 4.0)),
                cop_ref=float(self._conf(c.CONF_HP_COP_REF, 5.0)),
                cop_ref_temp=float(self._conf(c.CONF_HP_COP_REF_TEMP, 26.0)),
                cop_low=float(self._conf(c.CONF_HP_COP_LOW, 4.0)),
                cop_low_temp=float(self._conf(c.CONF_HP_COP_LOW_TEMP, 15.0)),
                cop_clamp_min=float(self._conf(c.CONF_HP_COP_CLAMP_MIN, 3.0)),
                cop_clamp_max=float(self._conf(c.CONF_HP_COP_CLAMP_MAX, 6.0)),
                air_temp_min=float(self._conf(c.CONF_HP_AIR_TEMP_MIN, 11.0)),
                air_temp_max=float(self._conf(c.CONF_HP_AIR_TEMP_MAX, 43.0)),
                flow_min_m3h=float(self._conf(c.CONF_HP_FLOW_MIN_M3H, 2.0)),
                flow_min_blocking=bool(
                    self._conf(c.CONF_HP_FLOW_MIN_BLOCKING, False)
                ),
                flow_min_site_verified=bool(
                    self._conf(c.CONF_HP_FLOW_MIN_VERIFIED, False)
                ),
            ),
            filtration=FiltrationSettings(
                turnover_factor=float(self._conf(c.CONF_TURNOVER_FACTOR, 3.0)),
                windows=windows,
                min_block_minutes=int(self._conf(c.CONF_MIN_BLOCK_MINUTES, 20)),
                min_hours_fallback=float(self._conf(c.CONF_MIN_DAILY_HOURS, 4.0)),
                min_hours_by_temp=self._min_hours_curve(),
            ),
            comfort=ComfortSettings(
                compressor_min_off_minutes=int(
                    self._conf(c.CONF_COMPRESSOR_MIN_OFF, 10)
                ),
                compressor_min_on_minutes=int(
                    self._conf(c.CONF_COMPRESSOR_MIN_ON, 10)
                ),
                target_temp=self._target_temp,
                max_temp=float(self._conf(c.CONF_MAX_TEMP, 32.0)),
                min_water_temp=float(self._conf(c.CONF_MIN_WATER_TEMP, 10.0)),
                frost_air_temp=float(self._conf(c.CONF_FROST_AIR_TEMP, 3.0)),
                night_start=_parse_time(self._conf(c.CONF_NIGHT_START), time(22, 0)),
                night_end=_parse_time(self._conf(c.CONF_NIGHT_END), time(7, 0)),
                min_on_minutes=int(self._conf(c.CONF_MIN_ON_MINUTES, 15)),
                min_off_minutes=int(self._conf(c.CONF_MIN_OFF_MINUTES, 10)),
                pump_rundown_minutes=int(self._conf(c.CONF_PUMP_RUNDOWN_MINUTES, 5)),
                temp_hysteresis=float(self._conf(c.CONF_TEMP_HYSTERESIS, 0.3)),
            ),
            energy=EnergySettings(
                max_price=float(self._conf(c.CONF_MAX_PRICE, c.DEFAULT_MAX_PRICE)),
                negative_price_basis=self._conf(c.CONF_NEGATIVE_PRICE_BASIS, "total"),
                solar_threshold_w=float(
                    self._conf(c.CONF_SOLAR_THRESHOLD_W)
                    or self._default_solar_threshold()
                ),
                solar_hysteresis_w=float(self._conf(c.CONF_SOLAR_HYSTERESIS_W, 300.0)),
                eco_price_factor=float(self._conf(c.CONF_ECO_PRICE_FACTOR, 0.7)),
            ),
            safety=SafetySettings(
                calibration_tolerance=float(
                    self._conf(c.CONF_CALIBRATION_TOLERANCE, 0.6)
                ),
                pump_startup_grace_seconds=int(
                    self._conf(c.CONF_PUMP_STARTUP_GRACE, 120)
                ),
                stale_warning_seconds=int(
                    self._conf(c.CONF_STALE_WARNING_SECONDS, 900)
                ),
                stale_blocking_seconds=int(
                    self._conf(c.CONF_STALE_BLOCKING_SECONDS, 3600)
                ),
            ),
            learning=LearningSettings(
                initial_heat_loss_c_per_h=INITIAL_HEAT_LOSS.get(
                    PoolKind(self._conf(c.CONF_POOL_KIND, "frame")), 0.22
                ),
                max_step_ratio=float(self._conf(c.CONF_MAX_STEP_RATIO, 0.15)),
                enabled=bool(self._conf(c.CONF_LEARNING_ENABLED, True))
            ),
            heating_source=self._conf(c.CONF_HEATING_SOURCE, "heat_pump"),
            pool_kind=self._conf(c.CONF_POOL_KIND, "frame"),
            has_solar_collector=bool(self._conf(c.CONF_HAS_SOLAR_COLLECTOR, False)),
            collector_margin=float(self._conf(c.CONF_COLLECTOR_MARGIN, 3.0)),
            unit_system=self._conf(c.CONF_UNIT_SYSTEM, "metric"),
            sensor_aliases=frozenset(aliases),
        )

    # -- Reading entities --------------------------------------------------

    def _read(self, key: str, role: str) -> SensorReading:
        entity_id = self._conf(key)
        if not entity_id:
            self.disabled_capabilities.add(c.CAPABILITY_BY_ENTITY.get(key, key))
            return SensorReading(None, None, role)

        state: State | None = self.hass.states.get(entity_id)
        if state is None or state.state in UNAVAILABLE:
            return self._bridge(role)
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return SensorReading(None, None, role)

        plausible = _PLAUSIBLE_RANGES.get(role)
        if plausible is not None:
            lo, hi = plausible
            if not (lo <= value <= hi):
                _LOGGER.warning(
                    "Implausible %s reading %.1f outside [%.1f, %.1f] on %s",
                    role,
                    value,
                    lo,
                    hi,
                    entity_id,
                )
                return self._bridge(role)

        # last_updated only moves when the value or an attribute changes, so a
        # steady temperature looks frozen even though the sensor is reporting
        # normally. last_reported moves on every report and is the honest
        # measure of liveness; it falls back for older Home Assistant versions.
        reported = getattr(state, "last_reported", None) or state.last_updated
        age = (dt_util.utcnow() - reported).total_seconds()
        self._last_good[role] = (value, dt_util.utcnow())
        return SensorReading(value, age, role)

    def _bridge(self, role: str) -> SensorReading:
        """Carry the last reading through a brief outage.

        An ESP reboot takes ten seconds and makes every sensor on it
        unavailable. Treating that as a dead probe stops a heating session over
        a gap shorter than the time it takes to notice -- and pool water does
        not change temperature in twenty seconds, so the last reading is far
        closer to the truth than no reading at all.

        Past the bridge window the value is dropped and the normal fault
        handling takes over, because at that point something really is wrong.
        """
        remembered = self._last_good.get(role)
        if remembered is None:
            return SensorReading(None, None, role)

        value, seen_at = remembered
        gap = (dt_util.utcnow() - seen_at).total_seconds()
        if gap > self.pool_config.safety.bridge_outage_seconds:
            self._last_good.pop(role, None)
            return SensorReading(None, None, role)

        self.bridged_roles.add(role)
        return SensorReading(value, gap, role, bridged=True)

    def _read_binary(self, key: str) -> bool | None:
        """Read an optional on/off signal.

        Returns ``None`` when not configured or unavailable, which the engine
        treats as "no opinion" rather than as a negative. A missing signal must
        never read as "this is an expensive moment".
        """
        entity_id = self._conf(key)
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in UNAVAILABLE:
            return None
        return state.state == "on"

    def _switch_is_on(self, key: str) -> bool:
        entity_id = self._conf(key)
        if not entity_id:
            return False
        state = self.hass.states.get(entity_id)
        return state is not None and state.state == "on"

    def _read_price(self) -> tuple[float | None, float | None]:
        """Read the all-in price and the raw spot price.

        The tibber_prices integration exposes the all-in price as the sensor
        state and splits it into an energy component and a tax component as
        attributes, so both definitions of "below zero" are available.
        """
        entity_id = self._conf(c.CONF_PRICE_SENSOR)
        if not entity_id:
            self.disabled_capabilities.add("price_optimisation")
            return None, None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in UNAVAILABLE:
            return None, None
        try:
            total = float(state.state)
        except (TypeError, ValueError):
            return None, None
        energy = state.attributes.get(c.ATTR_ENERGY_PRICE)
        try:
            energy = float(energy) if energy is not None else None
        except (TypeError, ValueError):
            energy = None
        return total, energy

    def _read_price_forecast(self) -> tuple:
        entity_id = self._conf(c.CONF_PRICE_SENSOR)
        if not entity_id:
            return ()
        return extract_forecast(self.hass.states.get(entity_id))

    def _next_swim_deadline(self, now: datetime) -> datetime | None:
        """When the pool is next wanted at temperature.

        One window per weekday covers nearly every household; a second is
        supported for the exceptions and costs almost nothing because the planner
        works from a list either way.
        """
        candidates: list[datetime] = []
        days = self._conf(c.CONF_SWIM_DAYS, [0, 1, 2, 3, 4, 5, 6]) or []
        for key in (c.CONF_SWIM_TIME, c.CONF_SWIM_TIME_2):
            raw = self._conf(key)
            if not raw:
                continue
            wanted = _parse_time(raw, time(17, 0))
            for offset in range(0, 8):
                day = now.date() + timedelta(days=offset)
                if days and day.weekday() not in [int(d) for d in days]:
                    continue
                moment = datetime.combine(day, wanted).replace(tzinfo=now.tzinfo)
                if moment > now:
                    candidates.append(moment)
                    break
        return min(candidates) if candidates else None

    def _read_flow(self) -> SensorReading:
        """Read the flow sensor and convert it to cubic metres per hour.

        Flow meters report in whatever unit their firmware was written for --
        L/min is the most common on pool hardware, L/h and m3/h both occur. The
        value was previously taken at face value, so a sensor reporting 17 L/min
        was read as 17 m3/h: nonsense in both directions, and it made the heat
        pump's 2 m3/h threshold meaningless.

        The unit comes from the sensor's own ``unit_of_measurement`` where it has
        one, and falls back to the setting for meters that publish a bare number.
        """
        entity_id = self._conf(c.CONF_FLOW_SENSOR)
        if not entity_id:
            self.disabled_capabilities.add("flow_protection")
            return SensorReading(None, None, "flow")

        state = self.hass.states.get(entity_id)
        if state is None or state.state in UNAVAILABLE:
            return SensorReading(None, None, "flow")
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return SensorReading(None, None, "flow")

        unit = (state.attributes.get("unit_of_measurement") or "").strip()
        factor = FLOW_UNIT_FACTORS.get(unit.lower())
        if factor is None:
            configured = str(self._conf(c.CONF_FLOW_UNIT, "l_min")).lower()
            factor = FLOW_UNIT_FACTORS.get(configured)
            if factor is None:
                # Falling back to 1.0 here would silently treat 17 L/min as
                # 17 m3/h, and every figure derived from flow would be wrong by a
                # factor of seventeen without anything looking broken. Refusing
                # the reading is far safer than guessing at it.
                _LOGGER.warning(
                    "Flow unit %r is not recognised, and the sensor %s reports "
                    "%r. Set the flow meter unit under Configure, Entities.",
                    configured,
                    entity_id,
                    unit or "no unit",
                )
                return SensorReading(None, None, "flow")
            if unit:
                _LOGGER.debug(
                    "Unrecognised sensor unit %r on %s; using the configured unit",
                    unit,
                    entity_id,
                )

        reported = getattr(state, "last_reported", None) or state.last_updated
        age = (dt_util.utcnow() - reported).total_seconds()
        return SensorReading(value * factor, age, "flow")

    def _build_state(self, now: datetime, config: PoolConfig) -> PoolState:
        self.disabled_capabilities = set()
        self.bridged_roles = set()
        price_total, price_energy = self._read_price()

        solar = self._read(c.CONF_SOLAR_POWER_SENSOR, "solar")
        irradiance = self._read(c.CONF_IRRADIANCE_SENSOR, "irradiance")
        cheap_now = self._read_binary(c.CONF_CHEAP_PRICE_SENSOR)
        covered = self._read_binary(c.CONF_COVER_ENTITY)
        pump_on = self._switch_is_on(c.CONF_PUMP_SWITCH)
        heat_pump_on = self._switch_is_on(c.CONF_HP_SWITCH)

        if heat_pump_on and self._hp_running_since is None:
            self._hp_running_since = now
            self.store.heat_pump_started_at = now
        elif not heat_pump_on:
            self._hp_running_since = None

        if pump_on and self._pump_running_since is None:
            self._pump_running_since = now
        elif not pump_on:
            self._pump_running_since = None

        runtime = (
            (now - self._hp_running_since).total_seconds() if self._hp_running_since else 0.0
        )
        pump_runtime = (
            (now - self._pump_running_since).total_seconds()
            if self._pump_running_since
            else 0.0
        )

        block = None
        if self.store.active_block:
            try:
                block = filt.BlockPlan(
                    index=self.store.active_block["index"],
                    start=datetime.fromisoformat(self.store.active_block["start"]),
                    end=datetime.fromisoformat(self.store.active_block["end"]),
                    rationale=self.store.active_block.get("rationale", "restored"),
                )
            except (KeyError, ValueError):
                block = None
        self._restored_block = block

        water_temp = self._read(c.CONF_WATER_TEMP_SENSOR, "water")
        air_temp = self._read(c.CONF_AIR_TEMP_SENSOR, "air")

        return PoolState(
            now=now,
            mode=self._mode,
            water_temp=water_temp,
            air_temp=air_temp,
            pump_inlet=self._read(c.CONF_PUMP_INLET_SENSOR, "pump_inlet"),
            pump_outlet=self._read(c.CONF_PUMP_OUTLET_SENSOR, "pump_outlet"),
            hp_inlet=self._read(c.CONF_HP_INLET_SENSOR, "hp_inlet"),
            hp_outlet=self._read(c.CONF_HP_OUTLET_SENSOR, "hp_outlet"),
            collector_temp=self._read(c.CONF_COLLECTOR_SENSOR, "collector"),
            flow_m3h=self._read_flow(),
            pump_power_w=self._read(c.CONF_PUMP_POWER_SENSOR, "pump_power"),
            hp_power_w=self._read(c.CONF_HP_POWER_SENSOR, "hp_power"),
            pump_on=pump_on,
            heat_pump_on=heat_pump_on,
            price_total=price_total,
            price_energy=price_energy,
            solar_power_w=solar.value,
            irradiance_w_m2=irradiance.value,
            cheap_price_now=cheap_now,
            covered=covered,
            target_temp=self._target_temp,
            filtration_done_h=self.store.runtime_hours(now),
            heat_pump_runtime_seconds=runtime,
            pump_runtime_seconds=pump_runtime,
            heat_pump_stopped_at=self.store.heat_pump_stopped_at,
            heat_pump_started_at=self.store.heat_pump_started_at,
            chemistry_until=self.store.chemistry_until,
            manual_pump_request=self._manual_pump_request,
            heat_loss_c_per_h=self._heat_loss_for(covered, water_temp, air_temp),
            session_started_at=self._session.start if self._session else None,
            session_start_temp=(
                self._session.water_start if self._session else None
            ),
            session_energy_kwh=(
                self._session.energy_kwh if self._session else 0.0
            ),
            session_cost=self._session_cost,
            measured_flow_m3h=self.store.learned.measured_flow_m3h,
        )

    # -- The tick ----------------------------------------------------------

    async def _async_update_data(self) -> dict:
        """One tick.

        The control decision is the only part that may not fail. Everything
        else -- planning, learning, energy bookkeeping, notifications -- runs
        inside its own guard, because a hiccup in an optional subsystem must not
        take the whole integration off the dashboard. Without that separation a
        single exception anywhere marks every entity unavailable, which is how
        the entities ended up flapping between Problem and Unavailable.
        """
        now = dt_util.now()
        try:
            data = await self._async_tick(now)
        except Exception as err:  # noqa: BLE001 -- see docstring
            self.last_error = f"{type(err).__name__}: {err}"
            _LOGGER.exception("PoolSmart tick failed")
            if self.data is not None:
                # Keep the previous picture rather than blanking everything. The
                # switches keep the state the last good decision put them in.
                return self.data
            raise UpdateFailed(self.last_error) from err

        self.last_error = None
        return data

    async def _async_tick(self, now: datetime) -> dict:
        # Yesterday's optional-subsystem errors describe the state they were in
        # then. If a subsystem has been quiet since, its failure has recovered
        # and should not stay on the diagnostics forever.
        self.subsystem_errors = {}
        self._invalidate_chemistry_cache()
        config = self.pool_config

        if self.store.roll_day(now):
            _LOGGER.debug("Filtration quota reset for a new day")

        try:
            await self._refresh_weather_forecast(now)
        except Exception:  # noqa: BLE001 -- see _async_update_data
            _LOGGER.exception("PoolSmart weather forecast fetch failed")
            self.subsystem_errors["weather_forecast"] = dt_util.now().isoformat()

        state = self._build_state(now, config)

        # Record actual pump runtime before deciding, so the quota reflects what
        # really happened rather than what was intended.
        self.store.record_pump(now, state.pump_on)
        state = state.replace(filtration_done_h=self.store.runtime_hours(now))

        self.faults = safety.evaluate(state, config)
        self.faults += self._verify_switch_states(state)
        self.heat_pump_available, self.heat_pump_gate_reason = safety.heat_pump_available(
            state, config, self.faults
        )

        # Plan before deciding, so the ladder knows whether this moment is part
        # of the plan rather than judging price in isolation.
        state = self._guard("planning", self._plan, now, config, state) or state

        self.filtration = filt.evaluate(
            now,
            config,
            done_h=state.filtration_done_h,
            active_block=self._restored_block,
            price_forecast=self._price_slots,
            water_temp=state.water_temp.value if state.water_temp.available else None,
            measured_flow_m3h=self.store.learned.measured_flow_m3h,
        )

        self.trace = Trace()
        decision = ladder.decide(
            state,
            config,
            self.filtration,
            self.faults,
            self.heat_pump_available,
            self.heat_pump_gate_reason,
            previous=self.decision,
            trace=self.trace,
        )

        await self._async_execute(decision, state)
        self._persist_block(decision)
        self._log(decision, state)

        if decision.heat_pump is False and state.heat_pump_on:
            self.store.heat_pump_stopped_at = now

        self._guard("flow", self._track_flow, now, state, config)
        self._guard("energy", self._track_energy, now, state)
        self._guard("session", self._track_session, now, state, config)
        self._persist_session()
        self._guard("idle", self._track_idle, now, state, config)

        self.decision = decision
        self._last_tick = now

        try:
            await self.store.async_save()
        except Exception:  # noqa: BLE001 -- losing a save is better than losing control
            _LOGGER.exception("Could not persist PoolSmart state")

        try:
            await self.notifier.async_process(decision, self.faults, now)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Notification handling failed")

        return {"decision": decision, "state": state}

    def _guard(self, name: str, func, *args):
        """Run an optional subsystem without letting it break the tick."""
        try:
            return func(*args)
        except Exception:  # noqa: BLE001 -- see _async_update_data
            _LOGGER.exception("PoolSmart %s step failed; continuing without it", name)
            self.subsystem_errors[name] = dt_util.now().isoformat()
            return None

    # -- Planning ----------------------------------------------------------

    def _plan(self, now: datetime, config: PoolConfig, state: PoolState) -> PoolState:
        """Work out when to heat and fold the answer back into the state."""
        if not (state.water_temp.available and state.air_temp.available):
            self.estimate = None
            self.plan = None
            return state

        deadline = self._next_swim_deadline(now)
        hours_available = (
            (deadline - now).total_seconds() / 3600.0 if deadline else None
        )

        learned = self.store.learned
        self.estimate = heating.estimate(
            config,
            water_temp=state.water_temp.value,
            target_temp=self._target_temp,
            air_temp=state.air_temp.value,
            hours_available=hours_available,
            heat_loss_c_per_h=state.heat_loss_c_per_h,
            learned_cop=(
                learning.cop_for(
                    learned.cop_by_air_bucket,
                    learned.cop_sessions_by_bucket,
                    state.air_temp.value,
                )
                if config.learning.enabled
                else None
            ),
            learned_rate_c_per_h=(
                learned.heating_rate_c_per_h
                if config.learning.enabled
                and learned.heating_rate_sessions >= learning.COP_CONFIDENCE_SESSIONS
                else None
            ),
        )

        self._price_slots = self._read_price_forecast()
        self.plan = optimizer.plan(
            now,
            config,
            self.estimate,
            slots=self._price_slots,
            deadline=deadline,
            heat_loss_c_per_h=state.heat_loss_c_per_h,
            boost=self._mode is Mode.BOOST,
        )

        return state.replace(
            swim_time=deadline,
            heating_session_active=self.plan.is_active(now),
            heating_session_planned_start=self.plan.next_start,
            plan_price_informed=self.plan.price_informed,
        )

    @property
    def _device_id(self) -> str | None:
        """This integration's device, so logbook entries attach to it."""
        if self._device_id_cache is None:
            registry = dr.async_get(self.hass)
            device = registry.async_get_device(identifiers={(c.DOMAIN, self.entry.entry_id)})
            self._device_id_cache = device.id if device else None
        return self._device_id_cache

    async def _refresh_weather_forecast(self, now: datetime) -> None:
        """Keep a cached forecast air temperature for the coming day.

        Refetched at most every :data:`_WEATHER_FORECAST_REFRESH`: a forecast
        does not change fast enough to justify a service call on every tick.
        Hourly entries are tried first for the finer-grained next-day figure
        the issue asked for; a weather integration that only offers a daily
        forecast still gets a usable, coarser figure rather than nothing.
        """
        entity_id = self._conf(c.CONF_WEATHER_ENTITY)
        if not entity_id:
            self._forecast_air_temp = None
            self._forecast_rain_probability = None
            self._is_raining_now = None
            return

        current = self.hass.states.get(entity_id)
        self._is_raining_now = (
            _condition_is_rainy(current.state)
            or _positive_number(current.attributes.get("precipitation"))
            if current is not None
            else None
        )
        if self._is_raining_now:
            self._last_rain_seen_at = now

        if (
            self._forecast_fetched_at is not None
            and now - self._forecast_fetched_at < _WEATHER_FORECAST_REFRESH
        ):
            return
        self._forecast_fetched_at = now

        entries: list = []
        for forecast_type, horizon in (
            ("hourly", _WEATHER_FORECAST_HOURLY_HORIZON),
            ("daily", _WEATHER_FORECAST_DAILY_HORIZON),
        ):
            try:
                response = await self.hass.services.async_call(
                    "weather",
                    "get_forecasts",
                    {"entity_id": entity_id, "type": forecast_type},
                    blocking=True,
                    return_response=True,
                )
            except Exception:  # noqa: BLE001 -- a type this integration does not support
                continue
            entries = ((response or {}).get(entity_id) or {}).get("forecast") or []
            if entries:
                entries = entries[:horizon]
                break

        temps = []
        rain_probs = []
        for entry in entries:
            temp = entry.get("temperature")
            templow = entry.get("templow")
            if isinstance(temp, (int, float)) and isinstance(templow, (int, float)):
                temps.append((temp + templow) / 2)
            elif isinstance(temp, (int, float)):
                temps.append(float(temp))
            prob = entry.get("precipitation_probability")
            if isinstance(prob, (int, float)):
                rain_probs.append(float(prob))
            elif _positive_number(entry.get("precipitation")):
                # Some integrations report an amount instead of a
                # probability; treat any forecast rain as worth flagging.
                rain_probs.append(100.0)

        self._forecast_air_temp = sum(temps) / len(temps) if temps else None
        self._forecast_rain_probability = max(rain_probs) if rain_probs else None

    def _recent_rain(self, now: datetime) -> bool:
        """Whether rain was observed within the last :data:`_RECENT_RAIN_WINDOW`.

        A snapshot of "is it raining right this tick" would miss a shower
        that passed between ticks; remembering the last time rain was seen
        gives chemistry advice and the test interval a window to react in
        instead of only the exact minute it started.
        """
        return (
            self._last_rain_seen_at is not None
            and now - self._last_rain_seen_at < _RECENT_RAIN_WINDOW
        )

    def _irradiance(self, state: PoolState) -> float | None:
        """Sunlight per square metre, if anything can tell us.

        A direct irradiance sensor -- a weather station's pyranometer, a
        KNMI-style solar-radiation entity, anything already reporting W/m2 --
        is used as-is when mapped, and wins over the estimate below because it
        measures the sky rather than a proxy for it. It works for a pool with
        no solar panels of its own just as well as for one with them.

        Failing that, a solar power sensor measures a panel array rather than
        the pool, but the two rise and fall together, so scaling the array
        against its peak gives a serviceable estimate of how bright it is.
        Without either a direct sensor or a peak figure to scale against there
        is nothing to infer, and the caller falls back to a time-of-day
        assumption rather than a bad number.
        """
        if state.irradiance_w_m2 is not None:
            return state.irradiance_w_m2
        if state.solar_power_w is None:
            return None
        peak = float(self._conf(c.CONF_SOLAR_PEAK_W, 0) or 0)
        if peak <= 0:
            return None
        return max(0.0, min(1.0, state.solar_power_w / peak)) * 1000.0

    def _heat_loss_for(
        self,
        covered: bool | None,
        water_temp: SensorReading,
        air_temp: SensorReading,
    ) -> float:
        """The heat loss figure matching the current cover state and forecast.

        Kept separate by cover state rather than averaged. A cover typically
        halves the loss or better, and on a pool losing two thirds of its
        input to the air that is the difference between a two degree rise
        taking fourteen hours and taking five. One averaged number would be
        wrong in both states.

        Until the covered figure has been measured, the open-air one is used:
        over-estimating the loss makes the system start early, which is the
        safe direction to be wrong in. The same reasoning sets the bounds in
        :func:`learning.forecast_scaled_heat_loss_c_per_h`, which the learned
        figure is then run through when a weather forecast is mapped: a colder
        day ahead is trusted more than a warmer one claiming less loss than
        usual.
        """
        learned = self.store.learned
        if covered and learned.heat_loss_covered_c_per_h is not None:
            base = learned.heat_loss_covered_c_per_h
        elif learned.heat_loss_c_per_h is not None:
            base = learned.heat_loss_c_per_h
        else:
            base = self.pool_config.learning.initial_heat_loss_c_per_h

        if (
            self._forecast_air_temp is None
            or not water_temp.available
            or not air_temp.available
        ):
            return base

        return learning.forecast_scaled_heat_loss_c_per_h(
            base, water_temp.value, air_temp.value, self._forecast_air_temp
        )

    # -- Flow baseline -----------------------------------------------------

    def _track_flow(self, now: datetime, state: PoolState, config: PoolConfig) -> None:
        """Learn what flow this installation normally achieves.

        Everything derived from flow -- filtration duration, the filter service
        warning -- is only as good as this figure, and the datasheet number is
        not it. A slow rolling average settles on the truth within a few hours of
        running and then tracks gradual fouling.
        """
        if not state.pump_on or not state.flow_m3h.available:
            return
        reading = state.flow_m3h.value
        if reading <= c.MIN_FLOW_M3H:
            return

        current = self.store.learned.measured_flow_m3h
        if current is None:
            self.store.learned.measured_flow_m3h = round(reading, 3)
            return

        # Slow enough that a fouling filter registers as a decline rather than
        # being quietly absorbed into the average.
        alpha = c.FLOW_LEARN_ALPHA
        self.store.learned.measured_flow_m3h = round(
            current * (1 - alpha) + reading * alpha, 3
        )

    # -- Energy and cost ---------------------------------------------------

    def _track_energy(self, now: datetime, state: PoolState) -> None:
        """Accumulate consumption and cost, plus the baseline for savings.

        The baseline is what the same energy would have cost at the average price
        of the forecast. The difference is the value of having chosen the moment,
        which is the only savings figure that means anything here.
        """
        if self._last_tick is None:
            return
        hours = (now - self._last_tick).total_seconds() / 3600.0
        if hours <= 0 or hours > 0.5:
            return

        watts = 0.0
        if state.pump_power_w.available:
            watts += state.pump_power_w.value
        if state.hp_power_w.available:
            watts += state.hp_power_w.value
        if watts <= 0:
            return

        kwh = watts / 1000.0 * hours
        self.store.energy_today_kwh += kwh

        if state.price_total is not None:
            self.store.cost_today += kwh * state.price_total
            baseline = average_price(self._price_slots) or state.price_total
            self.store.cost_baseline_today += kwh * baseline

    # -- Session recording -------------------------------------------------

    def _track_session(self, now: datetime, state: PoolState, config: PoolConfig) -> None:
        """Record heating sessions and learn from the clean ones."""
        heating_now = state.heat_pump_on

        if heating_now and self._session is None:
            self._session_cost = 0.0
            self._session = learning.SessionRecord(
                start=now,
                water_start=state.water_temp.value if state.water_temp.available else None,
            )

        if heating_now and self._session is not None:
            self._session.sample_air(
                state.air_temp.value if state.air_temp.available else None
            )
            self._session.sample_irradiance(self._irradiance(state))
            # A session that touched daylight is allowed a sunnier ceiling, since
            # for those hours the sky was heating the pool alongside the
            # appliance. Judged by the clock rather than by sun angle, which
            # would be precision this does not need.
            if 7 <= state.now.hour < 20:
                self._session.spans_daylight = True
            if self._last_tick is not None:
                hours = (now - self._last_tick).total_seconds() / 3600.0
                if 0 < hours <= 0.5:
                    if state.hp_power_w.available:
                        used = state.hp_power_w.value / 1000.0 * hours
                        self._session.energy_kwh += used
                        if state.price_total is not None:
                            self._session_cost += used * state.price_total
                    thermal = self._thermal_kw(state, config)
                    if thermal is not None:
                        self._session.thermal_kwh += thermal * hours
            for fault in self.faults:
                if fault.code not in self._session.faults:
                    self._session.faults.append(fault.code)

        if not heating_now and self._session is not None:
            record = self._session
            record.end = now
            record.water_end = (
                state.water_temp.value if state.water_temp.available else None
            )
            self._session = None
            self._finish_session(record, config)

    def _thermal_kw(self, state: PoolState, config: PoolConfig) -> float | None:
        delta = state.delta_t
        flow = state.effective_flow_m3h
        if delta is None or flow is None:
            return None
        if config.is_aliased("hp_inlet", "hp_outlet"):
            return None
        return flow * delta * 1.163

    def _finish_session(self, record: learning.SessionRecord, config: PoolConfig) -> None:
        measurements = learning.assess_measurements(record, config)

        payload = record.as_dict()
        payload["usable"] = measurements.anything_usable
        payload["verdict"] = measurements.describe()
        payload["measurements"] = measurements.as_dict()
        #: Human curation, WashData-style: "auto" leaves the automatic verdict
        #: above in charge; "included"/"excluded" (set via async_set_session_review)
        #: override it and win when the learned values are next rebuilt.
        payload["needs_review"] = learning.needs_review(record, measurements)
        payload["review"] = "auto"
        self.store.log_session(payload)

        if not measurements.anything_usable or not config.learning.enabled:
            _LOGGER.debug("Session taught nothing: %s", measurements.describe())
        else:
            # Each measurement stands or falls on its own. The all-or-nothing
            # version discarded seven sessions out of seven on a real
            # installation, several of which held perfectly good evidence of
            # how fast the pool warms up -- ruined by a probe on the heat pump
            # going quiet, which spoils the efficiency figure and says
            # nothing whatever about the rise.
            ratio = config.learning.max_step_ratio

            if measurements.heating_rate and record.heating_rate is not None:
                self.store.learned.heating_rate_c_per_h = round(
                    learning.capped_update(
                        self.store.learned.heating_rate_c_per_h,
                        record.heating_rate,
                        ratio,
                        self.store.learned.heating_rate_updated_at,
                        record.end,
                    ),
                    4,
                )
                self.store.learned.heating_rate_updated_at = record.end
                self.store.learned.heating_rate_sessions += 1
                self.store.record_monthly_metric(
                    "heating_rate", record.heating_rate, record.end
                )

            if measurements.cop:
                before = dict(self.store.learned.cop_by_air_bucket)
                curve, cop_timestamps = learning.update_cop_curve(
                    before,
                    record.measured_cop,
                    record.air_avg,
                    config,
                    self.store.learned.cop_updated_at,
                    record.end,
                )
                self.store.learned.cop_by_air_bucket = curve
                self.store.learned.cop_updated_at = cop_timestamps
                if record.air_avg is not None and record.measured_cop is not None:
                    key = learning.bucket_key(record.air_avg)
                    counts = dict(self.store.learned.cop_sessions_by_bucket)
                    counts[key] = counts.get(key, 0) + 1
                    self.store.learned.cop_sessions_by_bucket = counts
                    self.store.record_monthly_cop(
                        record.air_avg, record.measured_cop, record.end
                    )

            self.store.learned.session_count += 1
            self.store.bump_monthly_session_count(record.end)

        # Last, and never allowed to take the learning update above down with
        # it: a failure writing this backup must never look like a failure to
        # learn. See _write_learning_snapshot's own guard as well -- this is
        # belt and suspenders on purpose, after a version of this ran ahead of
        # the learning update with nothing catching it, silently discarding
        # every session's learning behind whatever went wrong.
        try:
            self._write_learning_snapshot()
        except Exception:  # noqa: BLE001 -- see comment above
            _LOGGER.exception("Could not schedule the learning safety-net snapshot")

    def _write_learning_snapshot(self) -> None:
        """Write a rolling safety-net copy of the learned history to disk.

        A reload -- or any other way the ``.storage`` file could be lost --
        should not depend on the user having remembered to run
        ``poolsmart.export_learning`` beforehand (see #2, where a reload bug
        wiped an in-progress session with nothing to recover it from). Mirrors
        that service's payload, overwritten after every finished session,
        which is roughly how often the learned values actually change. Runs in
        the background rather than blocking the tick that triggered it.
        """
        from .recovery import export_payload

        payload = export_payload(self.store)
        path = Path(
            self.hass.config.path(f"poolsmart_learning_backup.{self.entry.entry_id}.json")
        )

        def _write() -> None:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            os.replace(tmp, path)

        async def _run() -> None:
            try:
                await self.hass.async_add_executor_job(_write)
            except OSError:
                _LOGGER.exception("Could not write the learning safety-net snapshot")

        self.hass.async_create_task(_run())

    # -- Idle observation, for heat loss -----------------------------------

    def _track_idle(self, now: datetime, state: PoolState, config: PoolConfig) -> None:
        """Measure heat loss while nothing is running."""
        idle = not state.heat_pump_on
        if not idle or not state.water_temp.available:
            self._idle_since = None
            self._idle_water_temp = None
            self._idle_irradiance_samples = []
            self._idle_daylight = False
            self._idle_rain_seen = False
            return

        if self._idle_since is None:
            self._idle_since = now
            self._idle_water_temp = state.water_temp.value
            self._idle_irradiance_samples = []
            self._idle_daylight = False
            self._idle_rain_seen = False
            return

        # Sampled on every idle tick, not only at the boundary, for the same
        # reason a session samples irradiance throughout rather than once: an
        # average across the whole period is what the solar-gain estimate
        # needs, not a snapshot from whichever moment it happened to close.
        irradiance = self._irradiance(state)
        if irradiance is not None:
            self._idle_irradiance_samples.append(irradiance)
        if 7 <= state.now.hour < 20:
            self._idle_daylight = True
        if self._is_raining_now:
            self._idle_rain_seen = True

        hours = (now - self._idle_since).total_seconds() / 3600.0
        if hours < 6:
            return

        covered = state.covered
        irradiance_avg = (
            sum(self._idle_irradiance_samples) / len(self._idle_irradiance_samples)
            if self._idle_irradiance_samples
            else None
        )
        rate = learning.heat_loss_from_idle(
            self._idle_water_temp,
            state.water_temp.value,
            hours,
            config,
            covered=bool(covered),
            irradiance_w_m2=irradiance_avg,
            daytime=self._idle_daylight,
            rain_flag=self._idle_rain_seen,
        )
        started_covered = self._idle_covered
        self._idle_since = now
        self._idle_water_temp = state.water_temp.value
        self._idle_covered = covered
        self._idle_irradiance_samples = []
        self._idle_daylight = False
        self._idle_rain_seen = False

        if rate is None or not config.learning.enabled:
            return
        # Only learn from a period where the cover did not change, or the figure
        # belongs to neither state.
        if started_covered is not None and started_covered != covered:
            _LOGGER.debug("Cover changed during the idle period; not learning from it")
            return

        learned = self.store.learned
        if covered:
            learned.heat_loss_covered_c_per_h = round(
                learning.capped_update(
                    learned.heat_loss_covered_c_per_h,
                    rate,
                    config.learning.max_step_ratio,
                    learned.heat_loss_covered_updated_at,
                    now,
                ),
                4,
            )
            learned.heat_loss_covered_updated_at = now
            learned.heat_loss_covered_samples += 1
            self.store.record_monthly_metric("heat_loss_covered", rate, now)
        else:
            learned.heat_loss_c_per_h = round(
                learning.capped_update(
                    learned.heat_loss_c_per_h,
                    rate,
                    config.learning.max_step_ratio,
                    learned.heat_loss_updated_at,
                    now,
                ),
                4,
            )
            learned.heat_loss_updated_at = now
            learned.heat_loss_samples += 1
            self.store.record_monthly_metric("heat_loss", rate, now)

    # -- Execution ---------------------------------------------------------

    async def _async_execute(self, decision: Decision, state: PoolState) -> None:
        """Drive the switches, and never assume a command succeeded.

        The plug state is read back on the next tick. A mismatch is reported
        rather than ignored, because on this kind of installation the software is
        the only thing that stops the heat pump at target.
        """
        await self._async_set(c.CONF_HP_SWITCH, decision.heat_pump, state.heat_pump_on)
        await self._async_set(c.CONF_PUMP_SWITCH, decision.pump, state.pump_on)

    async def _async_set(self, key: str, wanted: bool, actual: bool) -> None:
        entity_id = self._conf(key)
        if not entity_id or wanted == actual:
            return
        service = "turn_on" if wanted else "turn_off"
        await self.hass.services.async_call(
            "switch", service, {"entity_id": entity_id}, blocking=False
        )
        _LOGGER.debug("Requested switch.%s for %s", service, entity_id)
        if key == c.CONF_PUMP_SWITCH:
            self._desired_pump_state = wanted
            self._desired_pump_since = dt_util.now()
        elif key == c.CONF_HP_SWITCH:
            self._desired_heat_pump_state = wanted
            self._desired_heat_pump_since = dt_util.now()

    def _verify_switch_states(self, state: PoolState) -> list[Fault]:
        """Detect switches that do not respond to commands.

        A command is sent with ``blocking=False``, so the actual state is only
        known on the next tick. A mismatch between commanded and actual state is
        expected for one tick while the switch acts; if it persists the switch is
        not responding and the system is running on a lie.
        """
        faults: list[Fault] = []

        if self._desired_pump_state is not None:
            if state.pump_on == self._desired_pump_state:
                self._pump_mismatch_ticks = 0
            else:
                self._pump_mismatch_ticks += 1
                if self._pump_mismatch_ticks >= 3:
                    faults.append(
                        Fault(
                            "pump_switch_unresponsive",
                            Severity.WARNING,
                            "The circulation pump switch is not responding to "
                            "commands. The pump may be stuck.",
                            {
                                "desired": self._desired_pump_state,
                                "actual": state.pump_on,
                                "since": (
                                    self._desired_pump_since.isoformat()
                                    if self._desired_pump_since
                                    else None
                                ),
                            },
                        )
                    )

        if self._desired_heat_pump_state is not None:
            if state.heat_pump_on == self._desired_heat_pump_state:
                self._heat_pump_mismatch_ticks = 0
            else:
                self._heat_pump_mismatch_ticks += 1
                if self._heat_pump_mismatch_ticks >= 3:
                    faults.append(
                        Fault(
                            "heat_pump_switch_unresponsive",
                            Severity.WARNING,
                            "The heat pump switch is not responding to commands. "
                            "The heat pump may be stuck.",
                            {
                                "desired": self._desired_heat_pump_state,
                                "actual": state.heat_pump_on,
                                "since": (
                                    self._desired_heat_pump_since.isoformat()
                                    if self._desired_heat_pump_since
                                    else None
                                ),
                            },
                        )
                    )

        return faults

    def _persist_block(self, decision: Decision) -> None:
        if decision.branch is Branch.FILTRATION_BLOCK and self.filtration.active_block:
            block = self.filtration.active_block
            self.store.active_block = {
                "index": block.index,
                "start": block.start.isoformat(),
                "end": block.end.isoformat(),
                "rationale": block.rationale,
            }
        elif decision.branch is not Branch.FILTRATION_BLOCK:
            self.store.active_block = None

    def _persist_session(self) -> None:
        """Keep the store's copy of the in-progress session current.

        Without this a reload -- deliberate or a real restart -- loses whatever
        heating session was running, because :attr:`_session` otherwise lives
        only in memory. Written every tick alongside the block above so a save
        never captures one without the other.
        """
        self.store.active_session = self._session.snapshot() if self._session else None

    def _log(self, decision: Decision, state: PoolState) -> None:
        """Record the decision, in the store and in the Home Assistant logbook.

        Two things are logged that the old version missed. A branch change with
        identical outputs is still a change of reasoning, and it used to be
        invisible: the pump stayed on, so nothing was written, and the answer to
        "why is it not heating" was thrown away. And how long the previous state
        lasted is recorded here rather than left to be worked out by subtracting
        timestamps.
        """
        previous = self.decision
        changed_outputs = not decision.same_outputs(previous)
        changed_branch = previous is None or decision.branch is not previous.branch

        duration = None
        if previous is not None and previous.taken_at is not None:
            duration = (state.now - previous.taken_at).total_seconds()

        if changed_outputs or changed_branch:
            payload = {
                "at": state.now.isoformat(),
                "branch": decision.branch.name,
                "pump": decision.pump,
                "heat_pump": decision.heat_pump,
                "reason": decision.reason,
                "detail": decision.detail,
                "faults": [f.code for f in self.faults],
                "duration_seconds": round(duration) if duration else None,
                "trace": self.trace.as_list() if self.trace else [],
            }
            self.store.log_decision(payload)
            self._fire_decision(decision, duration)

        self._guard("near_misses", self._track_near_misses, state, duration)
        self._log_obstacles(state)
        self._log_faults(state, duration)

    def _fire_decision(self, decision: Decision, duration: float | None) -> None:
        self.hass.bus.async_fire(
            c.EVENT_DECISION,
            {
                ATTR_NAME: self.entry.title,
                ATTR_DEVICE_ID: self._device_id,
                c.ATTR_BRANCH: decision.branch.name,
                c.ATTR_REASON: decision.reason,
                c.ATTR_PUMP: decision.pump,
                c.ATTR_HEAT_PUMP: decision.heat_pump,
                c.ATTR_DURATION: round(duration) if duration else None,
            },
        )

    def _track_near_misses(self, state: PoolState, duration: float | None) -> None:
        """Tally what stopped each branch, across the whole day.

        One tick's trace answers "why not now". This answers "why not today",
        which is the more useful question: twenty refusals on price is a setting
        worth revisiting, one is a passing expensive hour.
        """
        if self.trace is None:
            return
        if self.near_misses.roll_day(state.now.date().isoformat()):
            _LOGGER.debug("Near-miss tallies reset for a new day")
        self.near_misses.record(self.trace, duration or 0.0)

    def _log_obstacles(self, state: PoolState) -> None:
        """Log what the ladder wanted to do but could not.

        Rate limited, because a pool waiting all evening for a cheaper price
        would otherwise write the same sentence every thirty seconds.
        """
        if self.trace is None:
            return
        blockers = self.trace.blockers
        if not blockers:
            self._last_obstacle = None
            self._last_obstacle_at = None
            return

        signature = tuple(sorted((b.branch.name, b.verdict.value) for b in blockers))
        recently = (
            self._last_obstacle_at is not None
            and (state.now - self._last_obstacle_at).total_seconds()
            < c.OBSTACLE_REPEAT_MINUTES * 60
        )
        if signature == self._last_obstacle and recently:
            return

        self._last_obstacle = signature
        self._last_obstacle_at = state.now
        self.hass.bus.async_fire(
            c.EVENT_OBSTACLE,
            {
                ATTR_NAME: self.entry.title,
                ATTR_DEVICE_ID: self._device_id,
                c.ATTR_BLOCKERS: [b.describe() for b in blockers],
            },
        )

    def _log_faults(self, state: PoolState, duration: float | None) -> None:
        """Fire an event when a fault appears and when it clears."""
        current = {f.code: f for f in self.faults}

        for code, fault in current.items():
            if code in self._active_faults:
                continue
            self._active_faults[code] = state.now
            self.hass.bus.async_fire(
                c.EVENT_FAULT,
                {
                    ATTR_NAME: self.entry.title,
                    ATTR_DEVICE_ID: self._device_id,
                    "code": code,
                    "severity": fault.severity.value,
                    c.ATTR_MESSAGE: fault.message,
                    "cleared": False,
                },
            )

        for code in list(self._active_faults):
            if code in current:
                continue
            started = self._active_faults.pop(code)
            self.hass.bus.async_fire(
                c.EVENT_FAULT,
                {
                    ATTR_NAME: self.entry.title,
                    ATTR_DEVICE_ID: self._device_id,
                    "code": code,
                    "cleared": True,
                    c.ATTR_DURATION: round((state.now - started).total_seconds()),
                },
            )

    # -- Commands from entities -------------------------------------------

    async def async_set_mode(self, mode: str) -> None:
        self._mode = Mode(mode)
        self.store.mode = mode
        await self.async_request_refresh()

    async def async_set_target(self, value: float) -> None:
        self._target_temp = value
        self._config_cache = None
        self.store.target_temp = value
        await self.async_request_refresh()

    async def _async_set_option_live(self, key: str, value: float) -> None:
        """Update one config-entry option without reloading the integration.

        Unlike a change made through the options flow, this is a plain value the
        user tunes from the dashboard -- the price ceiling, the solar threshold
        -- while a session may be running. A full reload used to follow, which
        restarted the coordinator, closed the currently-open filtration interval
        at its own start (crediting it nothing), and discarded whatever heating
        session was in progress. ``async_update_entry`` still runs, so the value
        is persisted and visible in the options flow; :meth:`consume_suppressed_reload`
        is what stops the reload that would otherwise follow.
        """
        options = dict(self.entry.options)
        options[key] = value
        self._suppress_next_reload = True
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        self._config_cache = None
        await self.async_request_refresh()

    async def async_set_max_price(self, value: float) -> None:
        await self._async_set_option_live(c.CONF_MAX_PRICE, value)

    async def async_set_solar_threshold(self, value: float) -> None:
        await self._async_set_option_live(c.CONF_SOLAR_THRESHOLD_W, value)

    async def async_set_session_review(self, session_start: str, review: str) -> bool:
        """Override whether one logged session counts toward learning.

        ``session_start`` identifies the session by its ``start`` field, as
        shown in the Sessions tab. Rebuilds the learned values from the whole
        log afterwards, so the change actually takes effect immediately rather
        than only influencing the next session.
        """
        found = self.store.set_session_review(session_start, review)
        if not found:
            return False
        self.store.rebuild_learned(self.pool_config)
        await self.store.async_save(force=True)
        await self.async_request_refresh()
        return True

    def consume_suppressed_reload(self) -> bool:
        """Whether the config entry's next options-triggered reload should be skipped.

        True at most once per call: set by :meth:`_async_set_option_live` for a
        value that already took effect live, then cleared here so it can't
        accidentally swallow a later, genuine options-flow change too.
        """
        suppress, self._suppress_next_reload = self._suppress_next_reload, False
        return suppress

    async def async_set_manual_pump(self, enabled: bool) -> None:
        self._manual_pump_request = enabled
        await self.async_request_refresh()

    # -- Water chemistry ---------------------------------------------------

    def _reading(self, key: str) -> float | None:
        entity_id = self._conf(key)
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in UNAVAILABLE:
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return None

    def _invalidate_chemistry_cache(self) -> None:
        self._chemistry_cache = None
        self._chemistry_cache_tick = None

    @property
    def water_chemistry(self) -> dict:
        """Every reading, judged, with the doses and advice that follow from it."""
        if (
            self._chemistry_cache is not None
            and self._chemistry_cache_tick == self._last_tick
        ):
            return self._chemistry_cache

        config = self.pool_config
        sanitiser = chem.Sanitiser(self._conf(c.CONF_SANITISER, "chlorine"))
        relevant = chem.RELEVANT_READINGS[sanitiser]

        readings = {
            key: self._reading(conf_key)
            for key, conf_key in c.CHEMISTRY_SENSORS.items()
            if key in relevant
        }

        state = self.data.get("state") if self.data else None
        water_temp = (
            state.water_temp.value if state and state.water_temp.available else None
        )

        bands = [
            band.as_dict()
            for band in (chem.judge(key, value) for key, value in readings.items())
            if band is not None
        ]

        acid_product = chem.Product(self._conf(c.CONF_ACID_PRODUCT, "acid_15"))
        chlorine_product = chem.Product(
            self._conf(c.CONF_CHLORINE_PRODUCT, "chlorine_granules_70")
        )
        units = self._conf(c.CONF_UNIT_SYSTEM, "metric")

        # The persisted, capped/decayed correction (learning.capped_update,
        # blended in by _learn_dose_correction) rather than a fresh recompute
        # from the raw log every call -- confidence-gated the same way
        # chem.learn_correction's own minimum works, until enough dose/test
        # pairs exist to trust it.
        learned = self.store.learned
        ph_correction = (
            learned.ph_correction if learned.ph_correction_sessions >= 2 else 1.0
        )
        chlorine_correction = (
            learned.chlorine_correction
            if learned.chlorine_correction_sessions >= 2
            else 1.0
        )

        def present(dose):
            """Convert a dose into the units the user measures with."""
            if dose is None:
                return None
            payload = dose.as_dict()
            amount, unit = display_amount(dose.amount, dose.unit, units)
            payload["amount"] = amount
            payload["unit"] = unit
            payload["circulation_minutes"], payload["circulation_reason"] = (
                chem.circulation_for(dose.product)
            )
            return payload

        ph_dose = (
            chem.dose_for_ph(
                readings["ph"],
                config.pool.volume_l,
                acid_product,
                ph_correction,
            )
            if readings.get("ph") is not None
            else None
        )
        chlorine_dose = (
            chem.dose_for_chlorine(
                readings["free_chlorine"],
                config.pool.volume_l,
                chlorine_product,
                chlorine_correction,
                float(self._conf(c.CONF_TABLET_GRAMS, 20)),
            )
            if readings.get("free_chlorine") is not None
            else None
        )

        recent_rain = self._recent_rain(dt_util.now())
        due_at, overdue, why = chem.next_test_due(
            self.store.last_water_test, water_temp, dt_util.now(), recent_rain
        )
        interval, _ = chem.test_interval_days(water_temp)
        interval = chem.rain_adjusted_test_interval(interval, recent_rain)

        result = {
            "sanitiser": sanitiser.value,
            "unit_system": units,
            "readings": readings,
            "bands": bands,
            "urgent": [b for b in bands if b["urgent"]],
            "combined_chlorine": chem.combined_chlorine(
                readings.get("free_chlorine"), readings.get("total_chlorine")
            ),
            "advice": chem.water_advice(readings) + chem.rain_advice(recent_rain),
            # Kept for the older cards that read these directly.
            "ph": readings.get("ph"),
            "chlorine": readings.get("free_chlorine"),
            "ph_dose": present(ph_dose),
            "chlorine_dose": present(chlorine_dose),
            "test_interval_days": interval,
            "test_interval_reason": why,
            "test_due_at": due_at.isoformat() if due_at else None,
            "test_overdue": overdue,
            "dose_log": list(reversed(self.store.dose_log)),
            "corrections": {
                acid_product.value: ph_correction,
                chlorine_product.value: chlorine_correction,
            },
            "correction_confidence": {
                "ph": learning.rate_confidence(learned.ph_correction_sessions),
                "chlorine": learning.rate_confidence(
                    learned.chlorine_correction_sessions
                ),
            },
        }

        self._chemistry_cache = result
        self._chemistry_cache_tick = self._last_tick
        return result

    async def async_record_dose(
        self, product: str, amount: float, unit: str, measured_before: float
    ) -> None:
        """Log a dose and circulate for as long as that product needs.

        The duration comes from the product rather than from one setting,
        because the products are not comparable: non-chlorine shock is done in
        half an hour and chlorine shock wants a full night. Stopping early
        leaves undissolved product sitting on the floor bleaching the liner.
        """
        expected_change = chem.expected_change_for_dose(
            measured_before,
            self.pool_config.pool.volume_l,
            chem.Product(product),
            amount,
            unit,
            float(self._conf(c.CONF_TABLET_GRAMS, 20)),
        )
        record = chem.DoseRecord(
            at=dt_util.now(),
            product=product,
            amount=amount,
            unit=unit,
            measured_before=measured_before,
            expected_change=expected_change,
        )
        self.store.log_dose(record.as_dict())
        self._invalidate_chemistry_cache()

        minutes, reason = chem.circulation_for(product)
        if minutes <= 0:
            # A tablet dissolves over days in a floater; there is nothing to
            # circulate now, and pretending otherwise would run the pump for no
            # reason.
            _LOGGER.info("Logged %s; no circulation needed: %s", product, reason)
            await self.store.async_save()
            self.async_update_listeners()
            return

        await self.async_start_chemistry(minutes)

    async def async_record_test(self) -> None:
        """Mark the water as tested just now, and close off any open dose."""
        now = dt_util.now()
        self.store.last_water_test = now
        self._invalidate_chemistry_cache()

        chemistry = self.water_chemistry
        if self.store.dose_log:
            latest = self.store.dose_log[-1]
            if latest.get("measured_after") is None:
                is_ph_product = latest["product"] in (
                    chem.Product.ACID_15.value,
                    chem.Product.ACID_37.value,
                    chem.Product.PH_PLUS.value,
                )
                reading = chemistry["ph"] if is_ph_product else chemistry["chlorine"]
                if reading is not None:
                    latest["measured_after"] = reading
                    self._learn_dose_correction(latest, is_ph_product, now)
        await self.store.async_save()
        self.async_update_listeners()

    def _learn_dose_correction(
        self, dose_dict: dict, is_ph_product: bool, now: datetime
    ) -> None:
        """Blend one dose's actual-vs-expected response into the persisted
        pH/chlorine correction factor -- the same capped, decayed update
        heating learning uses for heat loss and COP.
        """
        effectiveness = chem.DoseRecord.from_dict(dose_dict).effectiveness
        if effectiveness is None or not (0.2 < effectiveness < 5):
            return
        # A pool that moved half as far as predicted needs twice the dose.
        proposed = max(0.5, min(2.0, 1 / effectiveness))
        learned = self.store.learned
        max_step_ratio = self.pool_config.learning.max_step_ratio
        if is_ph_product:
            learned.ph_correction = round(
                learning.capped_update(
                    learned.ph_correction,
                    proposed,
                    max_step_ratio,
                    learned.ph_correction_updated_at,
                    now,
                ),
                3,
            )
            learned.ph_correction_sessions += 1
            learned.ph_correction_updated_at = now
        else:
            learned.chlorine_correction = round(
                learning.capped_update(
                    learned.chlorine_correction,
                    proposed,
                    max_step_ratio,
                    learned.chlorine_correction_updated_at,
                    now,
                ),
                3,
            )
            learned.chlorine_correction_sessions += 1
            learned.chlorine_correction_updated_at = now

    async def async_start_chemistry(self, minutes: int | None = None) -> None:
        """Circulate for a chemical treatment.

        Branch 3 sits above the filtration branches in the ladder, so a day
        whose filtration quota is already met does not stop this: dosing in the
        evening still gets the circulation it needs, which is the whole point of
        having a separate branch for it rather than borrowing the filtration one.
        """
        duration = minutes or int(self._conf(c.CONF_CHEMISTRY_MINUTES, 60))
        request = self.chemistry.manual_cycle(dt_util.now(), duration)
        self.store.chemistry_until = request.until
        await self.notifier.async_send_chemistry(request.reason)
        await self.async_request_refresh()

    async def async_run_advisor(self) -> None:
        """Ask the advisory layer for a review. Never blocks control."""
        result = await self.advisor.async_review()
        if result.summary and not result.error:
            await self.notifier.async_send_recommendation(result.summary)
        self.async_update_listeners()

    async def async_accept_suggestion(self, index: int = 0) -> None:
        await self.advisor.async_accept(index)
        self.async_update_listeners()

    async def async_force_filtration(self) -> None:
        """Clear today's credited runtime so a full cycle runs again."""
        self.store.clear_runtime()
        self.store.active_block = None
        await self.async_request_refresh()

    async def async_reset_learning(self) -> None:
        from .store import LearnedValues

        self.store.learned = LearnedValues()
        await self.store.async_save()
        await self.async_request_refresh()

    async def async_rebuild_learning(self) -> None:
        """Reprocess the session log: recompute rate/COP, recover COP counts.

        The maintenance-tab equivalent of re-running matching on stored
        history. Nothing here reads new data -- it re-derives the learned
        heating rate and COP curve from the session log exactly as
        :meth:`async_set_session_review` does after one review, useful after a
        batch of reviews or an import where doing it session-by-session would
        be tedious.
        """
        self.store.rebuild_learned(self.pool_config)
        self.store.backfill_cop_counts()
        await self.store.async_save(force=True)
        await self.async_request_refresh()

    async def async_clear_debug_log(self) -> None:
        """Empty the decision log and the near-miss tally.

        Diagnostic trails only -- nothing here is read by the decision engine
        or the learning model, so this is always safe and never loses
        anything that could be relearned.
        """
        self.store.decision_log.clear()
        self.store.near_miss_log = NearMissLog()
        self.near_misses = NearMissLog()
        await self.store.async_save(force=True)
        await self.async_request_refresh()

    async def async_clear_all_history(self) -> None:
        """Factory-reset everything sessions and doses have taught the model.

        Irreversible, and deliberately not reachable without an explicit
        confirmation -- see the ``confirm`` field on the
        ``poolsmart.clear_all_history`` service. Leaves today's live
        filtration progress and current mode/target alone: those are ongoing
        operational state, not history.
        """
        from .store import LearnedValues

        self.store.learned = LearnedValues()
        self.store.session_log.clear()
        self.store.dose_log.clear()
        self.store.decision_log.clear()
        self.store.near_miss_log = NearMissLog()
        self.near_misses = NearMissLog()
        self.store.daily_summaries = []
        self.store.last_water_test = None
        await self.store.async_save(force=True)
        await self.async_request_refresh()

    async def async_replace_history(self, payload: dict, sections: list[str] | None) -> str:
        """Overwrite learned history from a validated import payload.

        Thin wrapper so the service handler in ``__init__.py`` does not have
        to know about cache invalidation and refresh order.
        """
        replaced = self.store.replace(payload, sections)
        await self.store.async_save(force=True)
        await self.async_request_refresh()
        return replaced

    async def async_restore(self) -> None:
        await self.store.async_load()
        if self.store.mode:
            try:
                self._mode = Mode(self.store.mode)
            except ValueError:
                self._mode = Mode.AUTO
        if self.store.target_temp is not None:
            self._target_temp = self.store.target_temp
        if self.store.active_session is not None:
            try:
                self._session = learning.SessionRecord.from_snapshot(
                    self.store.active_session
                )
            except (KeyError, ValueError, TypeError):
                _LOGGER.warning("Stored in-progress session was unreadable and was dropped")
                self.store.active_session = None

    # -- Convenience for entities -----------------------------------------

    @property
    def mode(self) -> Mode:
        return self._mode

    @property
    def target_temp(self) -> float:
        return self._target_temp

    @property
    def critical_fault(self) -> Fault | None:
        return next((f for f in self.faults if f.severity is Severity.CRITICAL), None)

    def fault_codes(self) -> list[str]:
        return [f.code for f in self.faults]
