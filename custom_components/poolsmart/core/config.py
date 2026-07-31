"""Configuration model for ha_poolsmart.

Pure Python: no Home Assistant imports. Every installation-specific value lives
here and is filled by the config flow. Nothing in this module is hardcoded to a
particular pool -- the defaults are merely sensible starting points.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time

# --------------------------------------------------------------------------
# Physical constants (these are physics, not configuration)
# --------------------------------------------------------------------------

#: Specific heat capacity of water in kJ/(kg*K).
WATER_HEAT_CAPACITY_KJ_KG_K = 4.186

#: Conversion from kJ to kWh.
KJ_PER_KWH = 3600.0


class NegativePriceBasis:
    """Which price is checked against zero for the FREE_POWER branch.

    ``MARKET`` looks at the raw spot price, which goes negative fairly often in
    spring and summer. ``TOTAL`` looks at the all-in price including taxes and
    levies, which is rare but means the user genuinely earns money by consuming.
    """

    MARKET = "market"
    TOTAL = "total"


@dataclass(frozen=True)
class PoolSpec:
    """Physical properties of the pool itself."""

    volume_l: float
    surface_m2: float
    depth_m: float

    @property
    def kwh_thermal_per_degree(self) -> float:
        """Thermal energy needed to raise the whole pool by 1 degree C."""
        return self.volume_l * WATER_HEAT_CAPACITY_KJ_KG_K / KJ_PER_KWH


@dataclass(frozen=True)
class PumpSpec:
    """Circulation pump properties."""

    #: Flow in cubic metres per hour.
    flow_m3h: float
    #: Whether ``flow_m3h`` was measured in situ or taken from the datasheet.
    flow_is_measured: bool
    #: Electrical power draw in kW.
    power_kw: float
    #: Derating applied to datasheet values to account for filter resistance.
    datasheet_derate: float = 0.7

    @property
    def effective_flow_m3h(self) -> float:
        """Flow to use in calculations.

        Manufacturers specify pump flow without a filter installed. With a
        cartridge or sand filter in line roughly 60-75% remains, and it drops
        further as the filter fouls. Trusting the datasheet makes the system
        believe the water has been turned over when it has not.
        """
        if self.flow_is_measured:
            return self.flow_m3h
        return self.flow_m3h * self.datasheet_derate


@dataclass(frozen=True)
class HeatPumpSpec:
    """Heat pump properties and operating envelope.

    The COP curve is a straight line through two reference points, extrapolated
    outside that range and clamped to the sanity limits. Two points is all the
    accuracy the planning needs, and it is all a datasheet reliably provides.
    """

    input_kw: float
    thermal_kw: float

    cop_ref: float
    cop_ref_temp: float
    cop_low: float
    cop_low_temp: float

    cop_clamp_min: float = 3.0
    cop_clamp_max: float = 6.0

    #: Hard operating envelope. Outside this range the unit must not run.
    air_temp_min: float = 11.0
    air_temp_max: float = 43.0

    #: Minimum water flow required before the unit may start.
    flow_min_m3h: float = 2.0

    def cop_at(self, air_temp: float) -> float:
        """Expected COP at a given outdoor air temperature."""
        span = self.cop_ref_temp - self.cop_low_temp
        if abs(span) < 0.01:
            cop = self.cop_ref
        else:
            slope = (self.cop_ref - self.cop_low) / span
            cop = self.cop_low + (air_temp - self.cop_low_temp) * slope
        return max(self.cop_clamp_min, min(self.cop_clamp_max, cop))

    def thermal_kw_at(self, air_temp: float) -> float:
        """Expected thermal output at a given outdoor air temperature."""
        return self.input_kw * self.cop_at(air_temp)


@dataclass(frozen=True)
class FiltrationSettings:
    """Daily filtration requirement and how it is spread over the day.

    The daily requirement is derived from pool volume and pump flow rather than
    entered as a number of hours, so the integration works for a 1000 litre pool
    and a 10000 litre pool without the user doing arithmetic.
    """

    #: How many times the full pool volume should pass the filter per day.
    turnover_factor: float = 2.0
    #: Windows in which the blocks may be scheduled.
    windows: tuple[tuple[time, time], ...] = (
        (time(7, 0), time(11, 0)),
        (time(12, 0), time(17, 0)),
        (time(17, 0), time(21, 0)),
    )
    #: A block shorter than this is pointless for a filter.
    min_block_minutes: int = 20

    @property
    def block_count(self) -> int:
        return len(self.windows)


@dataclass(frozen=True)
class ComfortSettings:
    """Temperatures, timing and hysteresis."""

    target_temp: float = 28.0
    max_temp: float = 32.0

    #: Below this water temperature the pool is protected regardless of mode.
    min_water_temp: float = 10.0
    #: Below this outdoor temperature the pump circulates to prevent freezing.
    frost_air_temp: float = 3.0

    night_start: time = time(22, 0)
    night_end: time = time(7, 0)

    #: Minimum on and off times. A decision that switches something carries a
    #: hold until timestamp derived from these, which is what makes oscillation
    #: structurally impossible rather than merely unlikely.
    min_on_minutes: int = 15
    min_off_minutes: int = 10

    #: Pump keeps running after the heat pump stops, to clear residual heat.
    pump_rundown_minutes: int = 5

    #: Temperature hysteresis around the target.
    temp_hysteresis: float = 0.3


@dataclass(frozen=True)
class EnergySettings:
    """Price and solar optimisation settings."""

    #: Do not heat above this all-in price, except in BOOST.
    max_price: float | None = None
    #: Which price is compared against zero for the FREE_POWER branch.
    negative_price_basis: str = NegativePriceBasis.TOTAL
    #: Solar surplus in watts above which heating is considered free.
    solar_threshold_w: float = 1500.0
    #: Hysteresis on the solar threshold, in watts.
    solar_hysteresis_w: float = 300.0
    #: Stricter multiplier applied to price limits in ECO mode.
    eco_price_factor: float = 0.7


@dataclass(frozen=True)
class SafetySettings:
    """Fault detection thresholds."""

    #: A reading older than this is worth mentioning, but nothing more. Many
    #: integrations only push a state when the value changes, so a stable
    #: temperature legitimately looks old.
    stale_warning_seconds: int = 900
    #: A reading older than this is treated as a dead sensor and heating is
    #: blocked. Circulation continues: the pool still needs filtering, and
    #: moving water is never the unsafe option.
    stale_blocking_seconds: int = 3600
    #: Plausible water temperature range.
    water_temp_min: float = -5.0
    water_temp_max: float = 45.0
    #: Expected delta-T range across the heat pump while it is running.
    delta_t_min: float = 0.2
    delta_t_max: float = 8.0
    #: Grace period before a running heat pump is expected to produce delta-T.
    hp_output_grace_minutes: int = 10
    #: Flow decline relative to the commissioned value that triggers a service
    #: notification rather than a fault.
    filter_service_flow_ratio: float = 0.75


@dataclass(frozen=True)
class LearningSettings:
    """Self-learning behaviour."""

    enabled: bool = True
    #: Maximum relative change a single update may apply to a learned value.
    #: One strange session must not be able to wreck the model.
    max_step_ratio: float = 0.15
    #: Starting values used until something has been learned.
    initial_heat_loss_c_per_h: float = 0.08
    #: Rolling window for the measured flow average, in hours of runtime.
    flow_average_window_h: float = 6.0


@dataclass(frozen=True)
class PoolConfig:
    """Everything the decision engine needs to know about this installation."""

    pool: PoolSpec
    pump: PumpSpec
    heat_pump: HeatPumpSpec
    filtration: FiltrationSettings = field(default_factory=FiltrationSettings)
    comfort: ComfortSettings = field(default_factory=ComfortSettings)
    energy: EnergySettings = field(default_factory=EnergySettings)
    safety: SafetySettings = field(default_factory=SafetySettings)
    learning: LearningSettings = field(default_factory=LearningSettings)

    #: Logical sensor roles that resolve to the same physical entity. Aliased
    #: roles are excluded from cross-comparison, otherwise the plausibility
    #: check compares a sensor with itself, always sees zero difference and
    #: reports a fault that does not exist.
    sensor_aliases: frozenset[frozenset[str]] = frozenset()

    # -- Derived filtration figures ---------------------------------------

    @property
    def daily_filtration_hours(self) -> float:
        """Total pump runtime needed per day to meet the turnover target."""
        litres = self.pool.volume_l * self.filtration.turnover_factor
        litres_per_hour = self.pump.effective_flow_m3h * 1000.0
        if litres_per_hour <= 0:
            return 0.0
        return litres / litres_per_hour

    @property
    def block_hours(self) -> float:
        """Runtime per filtration block."""
        count = self.filtration.block_count
        if count <= 0:
            return 0.0
        return self.daily_filtration_hours / count

    def is_aliased(self, role_a: str, role_b: str) -> bool:
        """Whether two logical sensor roles are the same physical sensor."""
        for group in self.sensor_aliases:
            if role_a in group and role_b in group:
                return True
        return False
