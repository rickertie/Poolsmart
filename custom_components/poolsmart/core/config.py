"""Configuration model for ha_poolsmart.

Pure Python: no Home Assistant imports. Every installation-specific value lives
here and is filled by the config flow. Nothing in this module is hardcoded to a
particular pool -- the defaults are merely sensible starting points.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from datetime import time

# --------------------------------------------------------------------------
# Physical constants (these are physics, not configuration)
# --------------------------------------------------------------------------

#: Specific heat capacity of water in kJ/(kg*K).
WATER_HEAT_CAPACITY_KJ_KG_K = 4.186

#: Conversion from kJ to kWh.
KJ_PER_KWH = 3600.0


#: Rough share of the rated pump flow that survives each filter medium. These
#: are starting points for people without a flow meter; anyone with one should
#: tick "measured" and use the real figure instead.
#:
#: Filter balls are the odd one out: they flow more freely than sand when fresh,
#: but they compress and mat over time, and a compressed bed chokes the flow far
#: more than sand ever does. A sudden drop is the signal to pull them out, wash
#: them and fluff them up.
FILTER_MEDIA_DERATE = {
    "sand": 0.70,
    "glass": 0.72,
    "balls": 0.80,
    "cartridge": 0.60,
    "none": 0.95,
}


class HeatingSource(str, Enum):
    """What warms the water, which changes far more than a label.

    A heat pump has a COP that varies with air temperature, a minimum air
    temperature below which it may not start, and a compressor that must not be
    short cycled. An immersion element has none of those: it is always exactly
    as efficient, works at any temperature, and can be switched freely. A solar
    collector is usually plumbed through a manual three-way valve, which the
    integration cannot operate at all -- so there it advises rather than
    controls.

    Asking the same questions for all of them, as earlier versions did, means
    asking most people about things that do not exist on their installation.
    """

    HEAT_PUMP = "heat_pump"
    ELECTRIC = "electric"
    SOLAR = "solar"
    GAS = "gas"
    NONE = "none"


#: Which capabilities each heating source actually has. Everything the ladder
#: and the settings screens do with a source is derived from this rather than
#: from scattered comparisons, so adding a source later is one entry here.
SOURCE_TRAITS = {
    HeatingSource.HEAT_PUMP: {
        "efficiency_varies": True,   # COP curve worth learning
        "air_temp_limits": True,     # may not run below a minimum
        "compressor": True,          # needs protection from short cycling
        "controllable": True,        # the integration can switch it
        "free": False,               # costs money to run
        "label_key": "heat_pump",
    },
    HeatingSource.ELECTRIC: {
        "efficiency_varies": False,  # always 1.0, nothing to learn
        "air_temp_limits": False,
        "compressor": False,
        "controllable": True,
        "free": False,
        "label_key": "electric",
    },
    HeatingSource.SOLAR: {
        "efficiency_varies": False,
        "air_temp_limits": False,
        "compressor": False,
        # Usually a manual three-way valve. The integration can see the water
        # getting warmer and say when the valve is worth opening; it cannot turn
        # anything on, and pretending otherwise would produce a decision log full
        # of instructions nobody carried out.
        "controllable": False,
        "free": True,
        "label_key": "solar",
    },
    HeatingSource.GAS: {
        "efficiency_varies": False,
        "air_temp_limits": False,
        "compressor": False,
        "controllable": True,
        "free": False,
        "label_key": "gas",
    },
    HeatingSource.NONE: {
        "efficiency_varies": False,
        "air_temp_limits": False,
        "compressor": False,
        "controllable": False,
        "free": False,
        "label_key": "none",
    },
}


class PoolKind(str, Enum):
    """Construction, which sets a sensible starting heat loss.

    An uninsulated inflatable standing in the wind loses heat several times
    faster than a built-in pool, and starting everyone at the same figure means
    starting most people at the wrong one. It is only a starting point -- the
    real figure is measured within days -- but the first days are exactly when
    someone is deciding whether the thing works.
    """

    INFLATABLE = "inflatable"
    FRAME = "frame"
    ABOVE_GROUND = "above_ground"
    IN_GROUND = "in_ground"


#: Starting heat loss in °C/h, before anything has been measured.
INITIAL_HEAT_LOSS = {
    PoolKind.INFLATABLE: 0.30,
    PoolKind.FRAME: 0.22,
    PoolKind.ABOVE_GROUND: 0.15,
    PoolKind.IN_GROUND: 0.08,
}


class UnitSystem(str, Enum):
    """Which units the user thinks in.

    Home Assistant converts temperatures on its own through device_class, so
    that part is free. Pool volume and chemical doses are not: a dose given in
    millilitres for a pool entered in litres is unusable to someone whose pool
    is 12,000 gallons and whose bottle is marked in fluid ounces.
    """

    METRIC = "metric"
    IMPERIAL = "imperial"


#: Conversions, kept in one place so a rounding choice made here is made once.
LITRES_PER_US_GALLON = 3.785411784
ML_PER_US_FL_OZ = 29.5735295625
GRAMS_PER_OZ = 28.349523125


def to_gallons(litres: float) -> float:
    return litres / LITRES_PER_US_GALLON


def from_gallons(gallons: float) -> float:
    return gallons * LITRES_PER_US_GALLON


def display_amount(amount: float, unit: str, system: str) -> tuple[float, str]:
    """Present a dose in the units the user actually measures with.

    Calculations stay metric throughout; only the presentation changes. Doing it
    the other way round would mean two sets of formulas and two sets of rounding
    errors to keep in step.
    """
    if system != UnitSystem.IMPERIAL:
        return round(amount, 1), unit
    if unit == "ml":
        return round(amount / ML_PER_US_FL_OZ, 2), "fl oz"
    if unit == "g":
        return round(amount / GRAMS_PER_OZ, 2), "oz"
    return round(amount, 1), unit


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
    #: See FILTER_MEDIA_DERATE for typical figures per medium.
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

    #: Minimum water flow the datasheet asks for.
    flow_min_m3h: float = 2.0
    #: Whether the datasheet minimum has been checked against this installation.
    #:
    #: Set once the owner has confirmed the system moves heat properly below the
    #: quoted figure -- a normal delta-T is the evidence. It silences the flow
    #: warning, which otherwise repeats a number the plumbing cannot reach.
    flow_min_site_verified: bool = False
    #: Whether falling below that figure stops heating or merely warns.
    #:
    #: Datasheet minima are conservative, and a pool heat pump has its own
    #: internal flow switch as a hardware backstop. Owners often run below the
    #: quoted figure without trouble, so the default is to warn and let the
    #: appliance protect itself rather than to override the owner's judgement.
    flow_min_blocking: bool = False

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

    Two things decide the daily runtime, and taking only the first is a mistake
    that shows up badly on pools with an oversized pump.

    **Turnover** is volume-based. Because filtered water mixes back in with
    unfiltered water, one turnover does not filter the pool once: it filters
    about 63% of it. Two turnovers reach 86%, three reach 95%, four reach 98%.
    Three is the point where the gains flatten out, so that is the default.

    **A daily minimum** is time-based, and turnover cannot substitute for it.
    A skimmer only catches the leaves, pollen and insects that land on the
    surface while it is actually running, sanitiser needs contact time, and water
    that sits still for twenty hours grows algae no matter how thoroughly it was
    filtered in the other four. The industry rule of thumb -- roughly an hour of
    running per 10 F of temperature -- is really this minimum in disguise, which
    is why it does not scale down for a fast pump.

    The requirement is the larger of the two.
    """

    #: How many times the full pool volume should pass the filter per day.
    turnover_factor: float = 3.0
    #: Time-based floor in hours, by water temperature. Warmer water means faster
    #: algae growth and more chlorine loss, so the floor rises with it.
    min_hours_by_temp: tuple[tuple[float, float], ...] = (
        (15.0, 2.0),
        (20.0, 3.0),
        (25.0, 4.0),
        (30.0, 5.0),
        (99.0, 6.0),
    )
    #: Applied when the water temperature is unknown.
    min_hours_fallback: float = 4.0
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

    def min_hours_at(self, water_temp: float | None) -> float:
        """The time-based floor at a given water temperature."""
        if water_temp is None:
            return self.min_hours_fallback
        for ceiling, hours in self.min_hours_by_temp:
            if water_temp < ceiling:
                return hours
        return self.min_hours_by_temp[-1][1]


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

    #: Compressor protection, enforced separately from the hold above.
    #:
    #: A hold protects a decision and can be overridden when waiting would be
    #: worse than switching. These cannot: a compressor needs its refrigerant
    #: pressures to equalise before restarting, and short cycling is the classic
    #: way to wear one out early. Manufacturers typically ask for five to ten
    #: minutes off and a similar minimum run.
    compressor_min_off_minutes: int = 10
    compressor_min_on_minutes: int = 10

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
    #: House-power cap in watts above which heating pauses, regardless of
    #: price or solar surplus. None when no grid power sensor is mapped or
    #: no cap was set -- the limiter is then simply absent. See issue #13.
    power_limit_w: float | None = None


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

    #: How long a sensor may be *unavailable* before its last known value is
    #: discarded.
    #:
    #: An ESP reboot takes ten seconds and makes every sensor on it unavailable.
    #: Treating that as a dead probe stops a heating session over a gap shorter
    #: than the time it takes to notice. Within this window the last reading is
    #: carried forward, which is far closer to the truth than having no reading
    #: at all -- pool water does not change temperature in twenty seconds.
    bridge_outage_seconds: int = 180
    #: Plausible water temperature range.
    water_temp_min: float = -5.0
    water_temp_max: float = 45.0
    #: Expected delta-T range across the heat pump while it is running.
    delta_t_min: float = 0.2
    delta_t_max: float = 8.0

    #: Roles that legitimately sit still for a long time.
    #:
    #: Outdoor air overnight can hold the same value to two decimals for half an
    #: hour, and a probe measuring water in a heated pool barely moves either.
    #: Warning about those on the same clock as a probe that should be changing
    #: constantly produces alerts nobody can act on, which is how people learn to
    #: ignore the ones that matter.
    #: A stable heating session holds delta-T almost constant, so the probes
    #: either side of the heat pump stop publishing -- and the better the
    #: heating runs, the more certainly the session used to be discarded as
    #: stale. Exactly backwards.
    slow_roles: frozenset[str] = frozenset(
        {"air", "water", "hp_inlet", "hp_outlet", "pump_inlet", "pump_outlet"}
    )
    #: Multiplier applied to the staleness thresholds for those roles.
    slow_role_factor: float = 4.0

    #: Roles whose silence only matters while the heat pump is running.
    #:
    #: A probe on the heat pump outlet reports nothing while the appliance is
    #: off because nothing is changing, and that is correct behaviour rather than
    #: a fault. Warning about it trains people to ignore warnings.
    conditional_roles: frozenset[str] = frozenset({"hp_inlet", "hp_outlet"})

    #: Delta-T bands used to judge whether flow is adequate.
    #:
    #: This replaces judging flow against a datasheet minimum, which is a proxy
    #: for the same thing and a poor one: it is written for a generic
    #: installation and takes no account of pipe length, elbows or a diverter
    #: valve. Delta-T measures directly what the flow figure stands for.
    delta_t_healthy_max: float = 3.0
    delta_t_starved: float = 5.0
    #: Grace period before a running heat pump is expected to produce delta-T.
    hp_output_grace_minutes: int = 10
    #: How long after the pump starts before flow is judged at all.
    #:
    #: The pump has to prime, push the air out of the lines and get the impeller
    #: up to speed. Judging flow during that window reports a fault about the
    #: first few seconds of a perfectly normal start, which is exactly when
    #: someone switching from Off to Boost is watching.
    pump_startup_grace_seconds: int = 120
    #: Flow decline relative to the commissioned value that triggers a service
    #: notification rather than a fault.
    filter_service_flow_ratio: float = 0.75
    #: How long the pump must have run before two probes are worth comparing.
    #: Standing water stratifies, and a stratified pool is not a miscalibrated
    #: probe.
    mixing_minutes: int = 20
    #: How far two probes measuring the same water may disagree before it is
    #: worth mentioning. DS18B20s are accurate to about +/- 0.5 C, so anything
    #: under that is the sensors rather than the pool.
    calibration_tolerance: float = 0.6


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

    #: Which units to present figures in. Calculation stays metric regardless.
    unit_system: str = UnitSystem.METRIC

    #: What warms the water, and how the pool is built.
    heating_source: str = HeatingSource.HEAT_PUMP
    pool_kind: str = PoolKind.FRAME
    #: A second, free source alongside the main one -- a solar collector next to
    #: a heat pump. Free heat should always be preferred over paid heat.
    has_solar_collector: bool = False

    #: How much warmer the collector must be than the pool before sending water
    #: through it is worth doing. Too small a margin and the pump circulates
    #: water through a collector that is barely helping; too large and free heat
    #: goes unused on a mild day.
    collector_margin: float = 3.0

    #: How much operational data is shared with the external AI advisor.
    #: "minimal" sends only aggregated statistics, "standard" sends session
    #: summaries without precise timestamps or cost figures, "full" sends
    #: everything the integration knows.
    privacy_level: str = "standard"

    def source_has(self, trait: str) -> bool:
        """Whether the configured heating source has a given capability."""
        return bool(SOURCE_TRAITS[HeatingSource(self.heating_source)].get(trait))

    #: Logical sensor roles that resolve to the same physical entity. Aliased
    #: roles are excluded from cross-comparison, otherwise the plausibility
    #: check compares a sensor with itself, always sees zero difference and
    #: reports a fault that does not exist.
    sensor_aliases: frozenset[frozenset[str]] = frozenset()

    # -- Derived filtration figures ---------------------------------------

    def effective_flow(self, measured_m3h: float | None = None) -> float:
        """The flow figure to calculate with.

        A measured value beats a configured one every time. Filtration duration
        is entirely determined by this number, so using a datasheet figure the
        installation never reaches means filtering for a fraction of the time the
        pool actually needs.
        """
        if measured_m3h and measured_m3h > 0:
            return measured_m3h
        return self.pump.effective_flow_m3h

    def turnover_hours(self, measured_m3h: float | None = None) -> float:
        """Runtime needed to meet the turnover target."""
        litres = self.pool.volume_l * self.filtration.turnover_factor
        litres_per_hour = self.effective_flow(measured_m3h) * 1000.0
        if litres_per_hour <= 0:
            return 0.0
        return litres / litres_per_hour

    def daily_filtration_hours(
        self, water_temp: float | None = None, measured_m3h: float | None = None
    ) -> float:
        """Total pump runtime needed per day.

        The larger of the volume-based turnover requirement and the time-based
        minimum. On a pool with a generously sized pump the minimum usually wins,
        which is correct: a pump that can turn the water over in an hour still
        cannot skim the surface in an hour.
        """
        return max(
            self.turnover_hours(measured_m3h),
            self.filtration.min_hours_at(water_temp),
        )

    def filtration_driver(
        self, water_temp: float | None = None, measured_m3h: float | None = None
    ) -> str:
        """Which of the two rules is setting the requirement, for explanation."""
        return (
            "turnover"
            if self.turnover_hours(measured_m3h) >= self.filtration.min_hours_at(water_temp)
            else "daily minimum"
        )

    def block_hours(
        self, water_temp: float | None = None, measured_m3h: float | None = None
    ) -> float:
        """Runtime per filtration block."""
        count = self.filtration.block_count
        if count <= 0:
            return 0.0
        return self.daily_filtration_hours(water_temp, measured_m3h) / count

    def is_aliased(self, role_a: str, role_b: str) -> bool:
        """Whether two logical sensor roles are the same physical sensor."""
        for group in self.sensor_aliases:
            if role_a in group and role_b in group:
                return True
        return False
