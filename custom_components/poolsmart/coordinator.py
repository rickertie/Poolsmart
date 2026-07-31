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
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import const as c
from .core import filtration as filt
from .core import heating, ladder, learning, optimizer, safety
from .core.config import (
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
from .notify import NotificationManager
from .price import average_price, extract_forecast
from .store import PoolStore

_LOGGER = logging.getLogger(__name__)

UNAVAILABLE = ("unknown", "unavailable", "none", "")


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
        self.notifier = NotificationManager(hass, self)
        self.advisor = Advisor(hass, self)
        self.chemistry = ChemistryModule(self)
        self.cover = CoverModule(self, self._conf(c.CONF_COVER_ENTITY))
        self.heat_pump_available: bool = False
        self.heat_pump_gate_reason: str = ""
        self.disabled_capabilities: set[str] = set()

        self._mode: Mode = Mode.AUTO
        self._target_temp: float = self._conf(c.CONF_TARGET_TEMP, 28.0)
        self._manual_pump_request = False
        self._hp_running_since: datetime | None = None
        self._last_tick: datetime | None = None
        self._session: learning.SessionRecord | None = None
        self._idle_since: datetime | None = None
        self._idle_water_temp: float | None = None
        self._price_slots: tuple = ()

    # -- Configuration -----------------------------------------------------

    def _conf(self, key: str, default=None):
        """Options override data, so the options flow can change anything."""
        if key in self.entry.options:
            return self.entry.options[key]
        return self.entry.data.get(key, default)

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

        aliases: set[frozenset[str]] = set()
        inlet = self._conf(c.CONF_HP_INLET_SENSOR)
        outlet = self._conf(c.CONF_HP_OUTLET_SENSOR)
        water = self._conf(c.CONF_WATER_TEMP_SENSOR)
        for role_a, entity_a in (("hp_inlet", inlet), ("hp_outlet", outlet), ("water", water)):
            for role_b, entity_b in (
                ("hp_inlet", inlet),
                ("hp_outlet", outlet),
                ("water", water),
            ):
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
                datasheet_derate=float(self._conf(c.CONF_PUMP_DERATE, 0.7)),
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
            ),
            filtration=FiltrationSettings(
                turnover_factor=float(self._conf(c.CONF_TURNOVER_FACTOR, 2.0)),
                windows=windows,
                min_block_minutes=int(self._conf(c.CONF_MIN_BLOCK_MINUTES, 20)),
            ),
            comfort=ComfortSettings(
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
                max_price=self._conf(c.CONF_MAX_PRICE),
                negative_price_basis=self._conf(c.CONF_NEGATIVE_PRICE_BASIS, "total"),
                solar_threshold_w=float(self._conf(c.CONF_SOLAR_THRESHOLD_W, 1500.0)),
                solar_hysteresis_w=float(self._conf(c.CONF_SOLAR_HYSTERESIS_W, 300.0)),
                eco_price_factor=float(self._conf(c.CONF_ECO_PRICE_FACTOR, 0.7)),
            ),
            safety=SafetySettings(),
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
            return SensorReading(None, None, role)
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return SensorReading(None, None, role)

        age = (dt_util.utcnow() - state.last_updated).total_seconds()
        return SensorReading(value, age, role)

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

    def _build_state(self, now: datetime, config: PoolConfig) -> PoolState:
        self.disabled_capabilities = set()
        price_total, price_energy = self._read_price()

        solar = self._read(c.CONF_SOLAR_POWER_SENSOR, "solar")
        pump_on = self._switch_is_on(c.CONF_PUMP_SWITCH)
        heat_pump_on = self._switch_is_on(c.CONF_HP_SWITCH)

        if heat_pump_on and self._hp_running_since is None:
            self._hp_running_since = now
        elif not heat_pump_on:
            self._hp_running_since = None

        runtime = (
            (now - self._hp_running_since).total_seconds() if self._hp_running_since else 0.0
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
            hp_inlet=self._read(c.CONF_HP_INLET_SENSOR, "hp_inlet"),
            hp_outlet=self._read(c.CONF_HP_OUTLET_SENSOR, "hp_outlet"),
            flow_m3h=self._read(c.CONF_FLOW_SENSOR, "flow"),
            pump_power_w=self._read(c.CONF_PUMP_POWER_SENSOR, "pump_power"),
            hp_power_w=self._read(c.CONF_HP_POWER_SENSOR, "hp_power"),
            pump_on=pump_on,
            heat_pump_on=heat_pump_on,
            price_total=price_total,
            price_energy=price_energy,
            solar_power_w=solar.value,
            target_temp=self._target_temp,
            filtration_done_h=self.store.runtime_hours(now),
            heat_pump_runtime_seconds=runtime,
            heat_pump_stopped_at=self.store.heat_pump_stopped_at,
            chemistry_until=self.store.chemistry_until,
            manual_pump_request=self._manual_pump_request,
            heat_loss_c_per_h=(
                self.store.learned.heat_loss_c_per_h
                if self.store.learned.heat_loss_c_per_h is not None
                else 0.08
            ),
            measured_flow_m3h=self.store.learned.measured_flow_m3h,
        )

    # -- The tick ----------------------------------------------------------

    async def _async_update_data(self) -> dict:
        now = dt_util.now()
        config = self.pool_config

        if self.store.roll_day(now):
            _LOGGER.debug("Filtration quota reset for a new day")

        state = self._build_state(now, config)

        # Record actual pump runtime before deciding, so the quota reflects what
        # really happened rather than what was intended.
        self.store.record_pump(now, state.pump_on)
        state = state.replace(filtration_done_h=self.store.runtime_hours(now))

        self.faults = safety.evaluate(state, config)
        self.filtration = filt.evaluate(
            now,
            config,
            done_h=state.filtration_done_h,
            active_block=self._restored_block,
        )
        self.heat_pump_available, self.heat_pump_gate_reason = safety.heat_pump_available(
            state, config, self.faults
        )

        # Plan before deciding, so the ladder knows whether this moment is part
        # of the plan rather than judging price in isolation.
        state = self._plan(now, config, state)

        decision = ladder.decide(
            state,
            config,
            self.filtration,
            self.faults,
            self.heat_pump_available,
            self.heat_pump_gate_reason,
            previous=self.decision,
        )

        await self._async_execute(decision, state)
        self._persist_block(decision)
        self._log(decision, state)

        if decision.heat_pump is False and state.heat_pump_on:
            self.store.heat_pump_stopped_at = now

        self._track_energy(now, state)
        self._track_session(now, state, config)
        self._track_idle(now, state, config)

        self.decision = decision
        self._last_tick = now
        await self.store.async_save()
        await self.notifier.async_process(decision, self.faults, now)

        return {"decision": decision, "state": state}

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

        self.estimate = heating.estimate(
            config,
            water_temp=state.water_temp.value,
            target_temp=self._target_temp,
            air_temp=state.air_temp.value,
            hours_available=hours_available,
            heat_loss_c_per_h=state.heat_loss_c_per_h,
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
                        self._session.energy_kwh += state.hp_power_w.value / 1000.0 * hours
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
        self.store.learned.cop_by_air_bucket = learning.update_cop_curve(
            self.store.learned.cop_by_air_bucket, record, config
        )
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

        rate = learning.heat_loss_from_idle(
            self._idle_water_temp,
            state.water_temp.value,
            hours,
            covered=bool(self.cover.state().covered),
        )
        self._idle_since = now
        self._idle_water_temp = state.water_temp.value

        if rate is None or not config.learning.enabled:
            return
        self.store.learned.heat_loss_c_per_h = round(
            learning.capped_update(
                self.store.learned.heat_loss_c_per_h,
                rate,
                config.learning.max_step_ratio,
            ),
            4,
        )

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
        if self.decision is not None and decision.same_outputs(self.decision):
            if decision.branch is self.decision.branch:
                return
        self.store.log_decision(
            {
                "at": state.now.isoformat(),
                "branch": decision.branch.name,
                "pump": decision.pump,
                "heat_pump": decision.heat_pump,
                "reason": decision.reason,
                "detail": decision.detail,
                "faults": [f.code for f in self.faults],
            }
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
