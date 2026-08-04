"""The tick.

Every 30 seconds: gather, assess, decide, execute, log, persist. The decision
itself comes from :mod:`core.ladder` and nowhere else. This module is plumbing --
it must never contain a rule about when something should run.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, time, timedelta

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
from .core.trace import Trace
from .core.config import (
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
        self._session_cost: float = 0.0
        self._price_slots: tuple = ()
        self._last_obstacle: tuple | None = None
        self._last_obstacle_at: datetime | None = None
        self._active_faults: dict[str, datetime] = {}
        self._device_id_cache: str | None = None
        self._last_good: dict[str, tuple[float, datetime]] = {}
        #: Roles currently running on a carried-forward reading.
        self.bridged_roles: set[str] = set()

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
        """Build the pure-Python config from the config entry."""
        windows_raw = self._conf(
            c.CONF_BLOCK_WINDOWS, [["07:00", "11:00"], ["12:00", "17:00"], ["17:00", "21:00"]]
        )
        windows = tuple(
            (_parse_time(start, time(7, 0)), _parse_time(end, time(11, 0)))
            for start, end in windows_raw
        )

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
                enabled=bool(self._conf(c.CONF_LEARNING_ENABLED, True))
            ),
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

        # last_updated only moves when the value or an attribute changes, so a
        # steady temperature looks frozen even though the sensor is reporting
        # normally. last_reported moves on every report and is the honest
        # measure of liveness; it falls back for older Home Assistant versions.
        reported = getattr(state, "last_reported", None) or state.last_updated
        age = (dt_util.utcnow() - reported).total_seconds()
        return SensorReading(value, age, role)

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

        return PoolState(
            now=now,
            mode=self._mode,
            water_temp=self._read(c.CONF_WATER_TEMP_SENSOR, "water"),
            air_temp=self._read(c.CONF_AIR_TEMP_SENSOR, "air"),
            pump_inlet=self._read(c.CONF_PUMP_INLET_SENSOR, "pump_inlet"),
            pump_outlet=self._read(c.CONF_PUMP_OUTLET_SENSOR, "pump_outlet"),
            hp_inlet=self._read(c.CONF_HP_INLET_SENSOR, "hp_inlet"),
            hp_outlet=self._read(c.CONF_HP_OUTLET_SENSOR, "hp_outlet"),
            flow_m3h=self._read_flow(),
            pump_power_w=self._read(c.CONF_PUMP_POWER_SENSOR, "pump_power"),
            hp_power_w=self._read(c.CONF_HP_POWER_SENSOR, "hp_power"),
            pump_on=pump_on,
            heat_pump_on=heat_pump_on,
            price_total=price_total,
            price_energy=price_energy,
            solar_power_w=solar.value,
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
            heat_loss_c_per_h=self._heat_loss_for(covered),
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
        config = self.pool_config

        if self.store.roll_day(now):
            _LOGGER.debug("Filtration quota reset for a new day")

        state = self._build_state(now, config)

        # Record actual pump runtime before deciding, so the quota reflects what
        # really happened rather than what was intended.
        self.store.record_pump(now, state.pump_on)
        state = state.replace(filtration_done_h=self.store.runtime_hours(now))

        self.faults = safety.evaluate(state, config)
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

    def _heat_loss_for(self, covered: bool | None) -> float:
        """The heat loss figure matching the current cover state.

        Kept separate rather than averaged. A cover typically halves the loss or
        better, and on a pool losing two thirds of its input to the air that is
        the difference between a two degree rise taking fourteen hours and taking
        five. One averaged number would be wrong in both states.

        Until the covered figure has been measured, the open-air one is used:
        over-estimating the loss makes the system start early, which is the safe
        direction to be wrong in.
        """
        learned = self.store.learned
        if covered and learned.heat_loss_covered_c_per_h is not None:
            return learned.heat_loss_covered_c_per_h
        if learned.heat_loss_c_per_h is not None:
            return learned.heat_loss_c_per_h
        return self.pool_config.learning.initial_heat_loss_c_per_h

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
        if reading <= 0.05:
            return

        current = self.store.learned.measured_flow_m3h
        if current is None:
            self.store.learned.measured_flow_m3h = round(reading, 3)
            return

        # Slow enough that a fouling filter registers as a decline rather than
        # being quietly absorbed into the average.
        alpha = 0.002
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
        verdict = learning.assess(record, config)
        payload = record.as_dict()
        payload["usable"] = verdict.usable
        payload["verdict"] = verdict.reason
        self.store.log_session(payload)

        if not verdict.usable or not config.learning.enabled:
            _LOGGER.debug("Session not used for learning: %s", verdict.reason)
            return

        ratio = config.learning.max_step_ratio
        if record.heating_rate is not None:
            self.store.learned.heating_rate_c_per_h = round(
                learning.capped_update(
                    self.store.learned.heating_rate_c_per_h, record.heating_rate, ratio
                ),
                4,
            )
        before = dict(self.store.learned.cop_by_air_bucket)
        self.store.learned.cop_by_air_bucket = learning.update_cop_curve(
            before, record, config
        )
        if record.air_avg is not None and record.measured_cop is not None:
            key = learning.bucket_key(record.air_avg)
            counts = dict(self.store.learned.cop_sessions_by_bucket)
            counts[key] = counts.get(key, 0) + 1
            self.store.learned.cop_sessions_by_bucket = counts
        if record.heating_rate is not None:
            self.store.learned.heating_rate_sessions += 1
        self.store.learned.session_count += 1

    # -- Idle observation, for heat loss -----------------------------------

    def _track_idle(self, now: datetime, state: PoolState, config: PoolConfig) -> None:
        """Measure heat loss while nothing is running."""
        idle = not state.heat_pump_on
        if not idle or not state.water_temp.available:
            self._idle_since = None
            self._idle_water_temp = None
            return

        if self._idle_since is None:
            self._idle_since = now
            self._idle_water_temp = state.water_temp.value
            return

        hours = (now - self._idle_since).total_seconds() / 3600.0
        if hours < 6:
            return

        covered = state.covered
        rate = learning.heat_loss_from_idle(
            self._idle_water_temp,
            state.water_temp.value,
            hours,
            covered=bool(covered),
        )
        started_covered = self._idle_covered
        self._idle_since = now
        self._idle_water_temp = state.water_temp.value
        self._idle_covered = covered

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
                    learned.heat_loss_covered_c_per_h, rate, config.learning.max_step_ratio
                ),
                4,
            )
            learned.heat_loss_covered_samples += 1
        else:
            learned.heat_loss_c_per_h = round(
                learning.capped_update(
                    learned.heat_loss_c_per_h, rate, config.learning.max_step_ratio
                ),
                4,
            )
            learned.heat_loss_samples += 1

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
        self.store.target_temp = value
        await self.async_request_refresh()

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

    @property
    def water_chemistry(self) -> dict:
        """Current readings, the dose they call for, and when to test next."""
        config = self.pool_config
        ph = self._reading(c.CONF_PH_SENSOR)
        chlorine = self._reading(c.CONF_CHLORINE_SENSOR)

        state = self.data.get("state") if self.data else None
        water_temp = (
            state.water_temp.value if state and state.water_temp.available else None
        )

        records = [chem.DoseRecord.from_dict(r) for r in self.store.dose_log]
        acid_product = chem.Product(self._conf(c.CONF_ACID_PRODUCT, "acid_15"))
        chlorine_product = chem.Product(
            self._conf(c.CONF_CHLORINE_PRODUCT, "chlorine_granules_70")
        )

        ph_dose = (
            chem.dose_for_ph(
                ph,
                config.pool.volume_l,
                acid_product,
                chem.learn_correction(records, acid_product.value),
            )
            if ph is not None
            else None
        )
        chlorine_dose = (
            chem.dose_for_chlorine(
                chlorine,
                config.pool.volume_l,
                chlorine_product,
                chem.learn_correction(records, chlorine_product.value),
            )
            if chlorine is not None
            else None
        )

        due_at, overdue, why = chem.next_test_due(
            self.store.last_water_test, water_temp, dt_util.now()
        )
        interval, _ = chem.test_interval_days(water_temp)

        return {
            "ph": ph,
            "chlorine": chlorine,
            "ph_dose": ph_dose.as_dict() if ph_dose else None,
            "chlorine_dose": chlorine_dose.as_dict() if chlorine_dose else None,
            "test_interval_days": interval,
            "test_interval_reason": why,
            "test_due_at": due_at.isoformat() if due_at else None,
            "test_overdue": overdue,
            "dose_log": list(reversed(self.store.dose_log)),
            "corrections": {
                acid_product.value: chem.learn_correction(records, acid_product.value),
                chlorine_product.value: chem.learn_correction(
                    records, chlorine_product.value
                ),
            },
        }

    async def async_record_dose(
        self, product: str, amount: float, unit: str, measured_before: float
    ) -> None:
        """Log a dose and circulate so it disperses."""
        record = chem.DoseRecord(
            at=dt_util.now(),
            product=product,
            amount=amount,
            unit=unit,
            measured_before=measured_before,
        )
        self.store.log_dose(record.as_dict())
        await self.async_start_chemistry()

    async def async_record_test(self) -> None:
        """Mark the water as tested just now, and close off any open dose."""
        now = dt_util.now()
        self.store.last_water_test = now

        chemistry = self.water_chemistry
        if self.store.dose_log:
            latest = self.store.dose_log[-1]
            if latest.get("measured_after") is None:
                reading = (
                    chemistry["ph"]
                    if "acid" in latest["product"] or "ph" in latest["product"]
                    else chemistry["chlorine"]
                )
                if reading is not None:
                    latest["measured_after"] = reading
        await self.store.async_save()
        self.async_update_listeners()

    async def async_start_chemistry(self, minutes: int | None = None) -> None:
        duration = minutes or int(self._conf(c.CONF_CHEMISTRY_MINUTES, 30))
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
        self.store.intervals = []
        self.store.active_block = None
        await self.async_request_refresh()

    async def async_reset_learning(self) -> None:
        from .store import LearnedValues

        self.store.learned = LearnedValues()
        await self.store.async_save()
        await self.async_request_refresh()

    async def async_restore(self) -> None:
        await self.store.async_load()
        if self.store.mode:
            try:
                self._mode = Mode(self.store.mode)
            except ValueError:
                self._mode = Mode.AUTO
        if self.store.target_temp is not None:
            self._target_temp = self.store.target_temp

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
