"""Core data models for ha_poolsmart.

Pure Python: no Home Assistant imports, so the decision engine can be unit
tested without a running Home Assistant instance.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import Enum, IntEnum


class Mode(str, Enum):
    """Operating mode selected by the user.

    A mode does not carry its own logic. It enables or disables branches of the
    single decision ladder, which is what keeps the decision logic in one place.
    """

    AUTO = "auto"
    BOOST = "boost"
    ECO = "eco"
    PUMP = "pump"
    STANDBY = "standby"
    OFF = "off"


class Branch(IntEnum):
    """Branches of the decision ladder, in priority order.

    The ladder is walked from the top. The first branch that matches produces
    the decision and lower branches are not evaluated.
    """

    EMERGENCY_STOP = 0
    FROST_PROTECTION = 1
    MANUAL = 2
    CHEMISTRY = 3
    FREE_POWER = 4
    HEATING = 5
    FILTRATION_DEADLINE = 6
    FILTRATION_BLOCK = 7
    PUMP_RUNDOWN = 8
    IDLE = 9


#: Branches that represent safety or a non-negotiable obligation. These ignore
#: the night window and may always override an active hold.
PRIORITY_BRANCHES = frozenset(
    {
        Branch.EMERGENCY_STOP,
        Branch.FROST_PROTECTION,
        Branch.MANUAL,
        Branch.CHEMISTRY,
        Branch.FILTRATION_DEADLINE,
    }
)

#: Branches allowed per mode.
MODE_BRANCHES: dict[Mode, frozenset[Branch]] = {
    Mode.AUTO: frozenset(Branch),
    Mode.BOOST: frozenset(Branch),
    Mode.ECO: frozenset(Branch),
    Mode.PUMP: frozenset(
        {
            Branch.EMERGENCY_STOP,
            Branch.FROST_PROTECTION,
            Branch.MANUAL,
            Branch.CHEMISTRY,
            Branch.FILTRATION_DEADLINE,
            Branch.FREE_POWER,
            Branch.IDLE,
        }
    ),
    Mode.STANDBY: frozenset(
        {
            Branch.EMERGENCY_STOP,
            Branch.FROST_PROTECTION,
            Branch.MANUAL,
            Branch.CHEMISTRY,
            Branch.FILTRATION_DEADLINE,
            Branch.FREE_POWER,
            Branch.FILTRATION_BLOCK,
            Branch.PUMP_RUNDOWN,
            Branch.IDLE,
        }
    ),
    # Off means off. Nothing runs, including frost protection.
    #
    # The earlier design kept frost protection alive here, reasoning that a
    # freezing pool is damage and an off switch should not cause damage. That
    # reasoning has a hole in it: the pool may not be there any more. Someone who
    # has drained and dismantled it for the winter, or disconnected the pump, has
    # every right to expect an off switch to be off, and a system that starts a
    # pump against their explicit instruction is worse than one that lets an
    # unattended pool freeze.
    #
    # Frost protection therefore lives in Stand-by, which is the mode that means
    # "I am not swimming but the pool is still there". The distinction is now
    # something the user chooses rather than something the software assumes.
    Mode.OFF: frozenset({Branch.IDLE}),
}


class Severity(str, Enum):
    """How bad a fault is."""

    #: Everything off. Overrides any hold.
    CRITICAL = "critical"
    #: Heat pump may not run; circulation is still allowed.
    HEATING_BLOCKED = "heating_blocked"
    #: Informational; needs attention but does not change control.
    WARNING = "warning"


@dataclass(frozen=True)
class Fault:
    """A detected problem."""

    code: str
    severity: Severity
    message: str
    detail: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SensorReading:
    """A single sensor value with the age of the reading.

    ``value`` is ``None`` when the sensor is not configured or unavailable. The
    engine must treat "not configured" as "feature disabled", never as an
    assumed value.
    """

    value: float | None
    age_seconds: float | None = None
    #: Logical role, used for alias-aware plausibility checks.
    role: str = ""
    #: Set when the value is the last known reading carried through a brief
    #: outage rather than a fresh measurement.
    bridged: bool = False

    @property
    def available(self) -> bool:
        return self.value is not None


@dataclass(frozen=True)
class PoolState:
    """Immutable snapshot of everything known at one tick."""

    now: datetime
    mode: Mode

    # -- Measurements ------------------------------------------------------
    water_temp: SensorReading
    air_temp: SensorReading
    pump_inlet: SensorReading
    #: Water leaving the circulation pump, as distinct from the heat pump inlet.
    #:
    #: Kept separate rather than folded into hp_inlet, because that folding
    #: assumed one particular plumbing layout (pool -> pump -> heat pump -> pool,
    #: where the two are physically one point). Someone with a filter, a longer
    #: run, or a different loop between the pump and the heat pump has two real
    #: points to measure. Installations where they genuinely are the same point
    #: simply configure the same entity for both fields; alias detection then
    #: treats them as one measurement rather than two.
    pump_outlet: SensorReading
    hp_inlet: SensorReading
    hp_outlet: SensorReading
    flow_m3h: SensorReading
    pump_power_w: SensorReading
    hp_power_w: SensorReading

    # -- Actual switch states, read back from the plugs --------------------
    pump_on: bool
    heat_pump_on: bool

    # -- External data -----------------------------------------------------
    #: All-in price per kWh, including taxes and levies.
    price_total: float | None = None
    #: Raw spot price per kWh, excluding taxes and levies.
    price_energy: float | None = None
    #: Cheapest upcoming intervals, as (start, end, all-in price) tuples.
    price_forecast: tuple[tuple[datetime, datetime, float], ...] = ()
    solar_power_w: float | None = None
    #: Sunlight per square metre, W/m2, from a sensor that already reads in
    #: that unit. ``None`` when no such sensor is configured, in which case
    #: the solar power sensor above (scaled by its peak) stands in instead.
    irradiance_w_m2: float | None = None
    #: Total household power draw from a smart-meter/energy sensor, watts.
    #: ``None`` when no grid power sensor is configured. See issue #13.
    grid_power_w: float | None = None
    #: Whether the cover is on. ``None`` when no cover entity is configured.
    covered: bool | None = None

    #: Temperature at the solar collector, where one is fitted.
    collector_temp: SensorReading | None = None

    #: An external "this is a good moment to use power" signal, if configured.
    #:
    #: Integrations that publish dynamic tariffs often expose one, and it knows
    #: things the raw price does not: where today's cheap window sits relative to
    #: the rest of the day, rather than only how the current price compares to a
    #: fixed ceiling.
    cheap_price_now: bool | None = None
    #: Minutes left in the *current* cheap period, from the same kind of
    #: integration, if it publishes one. ``None`` when not configured or
    #: unavailable; ``0`` whenever no cheap period is active right now --
    #: including while heating is being refused on price, so this cannot
    #: stand in for a price forecast. Informational: it does not change
    #: whether ``cheap_price_now`` is honoured, only how that is reported.
    cheap_price_remaining_minutes: int | None = None
    solar_forecast_w: tuple[tuple[datetime, float], ...] = ()

    # -- Targets and plan --------------------------------------------------
    target_temp: float = 28.0
    #: Next moment the pool must be at target, if any.
    swim_time: datetime | None = None
    #: Set by the heating planner in WP3. Until then heating is reactive.
    heating_session_active: bool = False
    heating_session_planned_start: datetime | None = None
    #: Whether the plan behind this session actually compared prices.
    plan_price_informed: bool = False

    # -- Runtime bookkeeping ----------------------------------------------
    #: Pump runtime credited to today's filtration quota, in hours. Heating
    #: runs the pump too, so those hours count and are included here.
    filtration_done_h: float = 0.0
    #: Currently running filtration block, if any: (index, start, end).
    active_block: tuple[int, datetime, datetime] | None = None
    #: Continuous seconds the heat pump has been running, for output checks.
    heat_pump_runtime_seconds: float = 0.0
    #: Continuous seconds the circulation pump has been running. Flow is not
    #: judged until it has had time to prime.
    pump_runtime_seconds: float = 0.0
    #: Moment the heat pump last switched off, for the rundown branch and the
    #: compressor's minimum off time.
    heat_pump_stopped_at: datetime | None = None
    #: Moment the heat pump last switched on, for the compressor's minimum run.
    heat_pump_started_at: datetime | None = None
    #: A chemistry cycle requested by the user, with its end time.
    chemistry_until: datetime | None = None
    #: Manual override requested through the switch entity.
    manual_pump_request: bool = False

    # -- Learned values ----------------------------------------------------
    heat_loss_c_per_h: float = 0.08

    # -- Live session, for the dashboard -----------------------------------
    session_started_at: datetime | None = None
    session_start_temp: float | None = None
    session_energy_kwh: float = 0.0
    session_cost: float = 0.0
    measured_flow_m3h: float | None = None

    # -- Derived -----------------------------------------------------------

    @property
    def delta_t(self) -> float | None:
        """Temperature rise across the heat pump."""
        if not (self.hp_inlet.available and self.hp_outlet.available):
            return None
        return self.hp_outlet.value - self.hp_inlet.value

    @property
    def effective_flow_m3h(self) -> float | None:
        """Best available figure for the real flow."""
        if self.flow_m3h.available:
            return self.flow_m3h.value
        return self.measured_flow_m3h

    def replace(self, **changes) -> PoolState:
        """Return a copy with the given fields changed."""
        return replace(self, **changes)


@dataclass(frozen=True)
class Decision:
    """The single output of the decision engine.

    Everything the user sees is a rendering of this object. Nothing else in the
    integration may switch a relay.
    """

    pump: bool
    heat_pump: bool
    branch: Branch
    reason: str
    detail: dict = field(default_factory=dict)
    #: The decision is not revisited before this moment, except by a branch in
    #: PRIORITY_BRANCHES or by a stop condition. This is where hysteresis lives:
    #: a decision that switches something records how long it stays valid, so no
    #: code path can flip a relay inside the hold window.
    hold_until: datetime | None = None
    taken_at: datetime | None = None

    def with_hold(self, now: datetime, minutes: int) -> Decision:
        """Return a copy holding for the given number of minutes from ``now``."""
        return replace(self, hold_until=now + timedelta(minutes=minutes), taken_at=now)

    def same_outputs(self, other: Decision | None) -> bool:
        """Whether the physical outputs are identical."""
        if other is None:
            return False
        return self.pump == other.pump and self.heat_pump == other.heat_pump
