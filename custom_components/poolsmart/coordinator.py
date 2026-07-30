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
from .core import heating, ladder, safety
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
        self.heat_pump_available: bool = False
        self.heat_pump_gate_reason: str = ""
        self.disabled_capabilities: set[str] = set()

        self._mode: Mode = Mode.AUTO
        self._target_temp: float = self._conf(c.CONF_TARGET_TEMP, 28.0)
        self._manual_pump_request = False
        self._hp_running_since: datetime | None = None
        self._last_tick: datetime | None = None

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

        decision = ladder.decide(
            state,
            config,
            self.filtration,
            self.faults,
            self.heat_pump_available,
            self.heat_pump_gate_reason,
            previous=self.decision,
        )

        if state.water_temp.available and state.air_temp.available:
            hours_available = None
            self.estimate = heating.estimate(
                config,
                water_temp=state.water_temp.value,
                target_temp=self._target_temp,
                air_temp=state.air_temp.value,
                hours_available=hours_available,
                heat_loss_c_per_h=state.heat_loss_c_per_h,
            )

        await self._async_execute(decision, state)
        self._persist_block(decision)
        self._log(decision, state)

        if decision.heat_pump is False and state.heat_pump_on:
            self.store.heat_pump_stopped_at = now

        self.decision = decision
        self._last_tick = now
        await self.store.async_save()

        return {"decision": decision, "state": state}

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
        self.store.chemistry_until = dt_util.now() + timedelta(minutes=duration)
        await self.async_request_refresh()

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
