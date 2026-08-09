"""Fault detection.

Severity drives what the ladder does with a fault:

* ``CRITICAL`` -- everything off, and it overrides any active hold.
* ``HEATING_BLOCKED`` -- the heat pump may not run; circulation continues.
* ``WARNING`` -- notify only.

A missing optional sensor is never a fault. It disables the check that depends
on it and is reported as such, because inventing a value would be worse than
not having one.
"""

from __future__ import annotations

from .config import PoolConfig
from .models import Fault, PoolState, Severity


def _reading_faults(state: PoolState, config: PoolConfig) -> list[Fault]:
    """Judge the temperature readings.

    None of these produce an emergency stop. A failed temperature sensor means
    heating cannot be controlled safely, so heating is blocked -- but circulation
    is never the unsafe option, and the pool still has to be filtered. Cutting
    everything because a thermometer went quiet would trade a small problem for
    a bigger one.
    """
    faults: list[Fault] = []
    warn_after = config.safety.stale_warning_seconds
    block_after = config.safety.stale_blocking_seconds

    if not state.water_temp.available:
        faults.append(
            Fault(
                "water_temp_unavailable",
                Severity.HEATING_BLOCKED,
                "The pool water temperature is unavailable, so heating is paused. "
                "Circulation and filtration continue as normal.",
            )
        )
    else:
        value = state.water_temp.value
        if not config.safety.water_temp_min <= value <= config.safety.water_temp_max:
            faults.append(
                Fault(
                    "water_temp_implausible",
                    Severity.HEATING_BLOCKED,
                    f"The pool water temperature of {value:.1f} C is outside the "
                    "plausible range, so heating is paused.",
                    {"value": value},
                )
            )

    for reading, label in (
        (state.water_temp, "pool water temperature"),
        (state.air_temp, "outdoor temperature"),
        (state.hp_inlet, "heat pump inlet"),
        (state.hp_outlet, "heat pump outlet"),
    ):
        if not reading.available or reading.age_seconds is None:
            continue
        age = reading.age_seconds
        limit = warn_after
        block_limit = block_after
        if reading.role in config.safety.slow_roles:
            limit *= config.safety.slow_role_factor
            block_limit *= config.safety.slow_role_factor
        if age <= limit:
            continue
        # A probe that only matters while the heat pump runs is allowed to go
        # quiet while it is off: nothing is changing, so nothing is reported.
        # Warning about that trains people to ignore warnings.
        if reading.role in config.safety.conditional_roles and not state.heat_pump_on:
            continue

        code = f"stale_{reading.role or label.replace(' ', '_')}"
        minutes = age / 60
        if age > block_limit:
            faults.append(
                Fault(
                    code,
                    Severity.HEATING_BLOCKED,
                    f"The {label} has not been reported for {minutes:.0f} minutes. "
                    "Heating is paused until it returns.",
                    {"age_seconds": age},
                )
            )
        else:
            faults.append(
                Fault(
                    code,
                    Severity.WARNING,
                    f"The {label} has not been reported for {minutes:.0f} minutes. "
                    "Some sensors only report when the value changes, so this is "
                    "often harmless.",
                    {"age_seconds": age},
                )
            )
    return faults


def _flow_faults(state: PoolState, config: PoolConfig) -> list[Fault]:
    faults: list[Fault] = []
    flow = state.effective_flow_m3h
    if flow is None:
        return faults

    # Let the pump prime before judging it. Coming out of Off, the first reading
    # is always low, and reporting that as a fault turns a normal start into an
    # alarm at the precise moment someone is watching to see whether it works.
    if state.pump_on and state.pump_runtime_seconds < config.safety.pump_startup_grace_seconds:
        return faults

    threshold = config.heat_pump.flow_min_m3h
    if (
        state.heat_pump_on
        and flow < threshold
        and not config.heat_pump.flow_min_site_verified
    ):
        blocking = config.heat_pump.flow_min_blocking
        faults.append(
            Fault(
                "flow_below_heat_pump_minimum",
                Severity.HEATING_BLOCKED if blocking else Severity.WARNING,
                (
                    f"Flow of {flow:.2f} m3/h ({flow / 0.06:.0f} L/min) is below the "
                    f"datasheet minimum of {threshold:.2f} m3/h "
                    f"({threshold / 0.06:.0f} L/min)."
                    + (
                        " Heating is paused."
                        if blocking
                        else " Heating continues; the heat pump's own flow switch"
                        " remains the hardware backstop. Check the temperature rise"
                        " across the heat pump: if it is normal, the water is"
                        " carrying the heat away and the datasheet figure simply"
                        " does not apply to this plumbing. Tick 'verified for this"
                        " installation' to stop this warning."
                    )
                ),
                {"flow_m3h": flow, "blocking": blocking},
            )
        )
    elif state.pump_on and flow <= 0.05:
        faults.append(
            Fault(
                "no_flow_while_pump_running",
                Severity.CRITICAL,
                "The pump is switched on but no flow is measured.",
                {"flow_m3h": flow},
            )
        )

    if not state.pump_on:
        return faults

    # A fouling filter shows up as a decline from what this installation normally
    # achieves. Comparing against the configured figure instead would fire
    # permanently on any system whose real flow sits below its datasheet number,
    # which is most of them: that reports a fact about the paperwork, not about
    # the filter.
    baseline = state.measured_flow_m3h
    if baseline and baseline > 0:
        ratio = flow / baseline
        if ratio < config.safety.filter_service_flow_ratio:
            faults.append(
                Fault(
                    "filter_service_needed",
                    Severity.WARNING,
                    (
                        f"Flow has fallen to {ratio * 100:.0f}% of the usual "
                        f"{baseline:.2f} m3/h for this system. The filter probably "
                        "needs cleaning."
                    ),
                    {"ratio": ratio, "flow_m3h": flow, "baseline_m3h": baseline},
                )
            )
        return faults

    # No baseline yet. Point out a configured figure that measurement clearly
    # contradicts, because every derived number depends on it.
    configured = config.pump.effective_flow_m3h
    if configured > 0 and flow < configured * 0.6:
        faults.append(
            Fault(
                "configured_flow_too_high",
                Severity.WARNING,
                (
                    f"The configured pump flow of {configured:.2f} m3/h does not match "
                    f"the measured {flow:.2f} m3/h ({flow / 0.06:.0f} L/min). Nothing "
                    "is wrong with the pump or the filter; the setting is simply out "
                    "of date, and filtration times are calculated from it. Correct it "
                    "under Configure, Pool and equipment, and tick 'measured'."
                ),
                {"measured_m3h": flow, "configured_m3h": configured},
            )
        )
    return faults


def _delta_t_faults(state: PoolState, config: PoolConfig) -> list[Fault]:
    """Check the temperature rise across the heat pump.

    Skipped entirely when the inlet and outlet roles resolve to the same
    physical sensor. Comparing a sensor with itself always yields zero
    difference and would report a fault that does not exist.
    """
    if config.is_aliased("hp_inlet", "hp_outlet"):
        return []

    delta = state.delta_t
    if delta is None or not state.heat_pump_on:
        return []

    grace = config.safety.hp_output_grace_minutes * 60
    if state.heat_pump_runtime_seconds < grace:
        return []

    if delta < config.safety.delta_t_min:
        return [
            Fault(
                "heat_pump_not_producing",
                Severity.HEATING_BLOCKED,
                (
                    f"The heat pump has run for {state.heat_pump_runtime_seconds / 60:.0f} "
                    f"minutes without producing a temperature rise (delta-T {delta:.2f} C)."
                ),
                {"delta_t": delta},
            )
        ]
    if delta > config.safety.delta_t_max:
        return [
            Fault(
                "delta_t_too_high",
                Severity.HEATING_BLOCKED,
                f"Temperature rise across the heat pump is {delta:.1f} C, which is too high.",
                {"delta_t": delta},
            )
        ]
    return []


def _calibration_faults(state: PoolState, config: PoolConfig) -> list[Fault]:
    """Cross-check two probes that should agree.

    The pool probe and the pump inlet measure the same water a metre apart, so
    they should read the same. When they do not, one of three things is true and
    all of them are worth knowing:

    * a probe needs calibrating, which quietly corrupts delta-T and every COP
      figure derived from it;
    * the pool is stratified, warm at the surface and cold at the inlet, which
      means the pump has not been circulating enough;
    * a probe is not actually in the water.

    This is the only use for a fifth probe that would otherwise be redundant, and
    it is a good one: it is the only check in the system capable of noticing that
    a temperature reading is simply wrong rather than merely surprising.
    """
    if config.is_aliased("water", "pump_inlet"):
        return []
    if not (state.water_temp.available and state.pump_inlet.available):
        return []
    if state.heat_pump_on:
        # The heat pump is adding heat; the two probes are legitimately apart.
        return []

    # Standing water stratifies: warm at the surface where the pool probe sits,
    # cooler at the intake. That is physics, not a fault, and comparing the two
    # before the pump has mixed the water measures the stratification rather
    # than the calibration. The check only means anything after a decent run.
    if not state.pump_on:
        return []
    if state.pump_runtime_seconds < config.safety.mixing_minutes * 60:
        return []

    difference = abs(state.water_temp.value - state.pump_inlet.value)
    if difference <= config.safety.calibration_tolerance:
        return []

    return [
        Fault(
            "probe_disagreement",
            Severity.WARNING,
            (
                f"The pool probe reads {state.water_temp.value:.2f} C and the pump "
                f"inlet {state.pump_inlet.value:.2f} C, a difference of "
                f"{difference:.2f} C. They measure the same water, so either a probe "
                "needs calibrating, the pool is stratified from too little "
                "circulation, or a probe is not in the water."
            ),
            {
                "pool": state.water_temp.value,
                "pump_inlet": state.pump_inlet.value,
                "difference": round(difference, 3),
            },
        )
    ]


def flow_adequacy(state: PoolState, config: PoolConfig) -> tuple[str, str, dict]:
    """Judge whether the water is carrying the heat away, using delta-T.

    Flow in m³/h is a proxy. Delta-T is the thing the proxy stands for, and it can
    be measured directly.

    The reasoning: a heat pump rejecting a fixed amount of heat into a stream of
    water raises that water by ``kW / (flow × 1.163)`` degrees. Halve the flow and
    the rise doubles. Starve it further and the condensing temperature climbs
    until the appliance derates or trips on high pressure. So the danger has a
    signature, and the signature is a *high* delta-T, not a low flow number.

    This matters because datasheet minima are written for a generic installation.
    A long pipe run, a filter, elbows and a diverter valve all cost head, and
    plenty of systems settle below the quoted figure while moving heat perfectly
    well. Judging them on the quoted figure tells the owner to chase a number
    their plumbing cannot produce, while the actual measurements say everything
    is fine.

    Returns a verdict, an explanation, and the numbers behind it.
    """
    delta = state.delta_t
    flow = state.effective_flow_m3h

    if not state.heat_pump_on:
        return "idle", "The heat pump is not running.", {}
    if delta is None:
        return (
            "unknown",
            "No inlet and outlet probes, so heat transfer cannot be judged. Flow "
            "alone cannot tell an adequate installation from a starved one.",
            {},
        )
    if state.heat_pump_runtime_seconds < config.safety.hp_output_grace_minutes * 60:
        return "starting", "The heat pump has not been running long enough to judge.", {}

    numbers = {
        "delta_t": round(delta, 2),
        "flow_m3h": round(flow, 3) if flow else None,
        "healthy_below": config.safety.delta_t_healthy_max,
        "starved_above": config.safety.delta_t_starved,
    }

    if delta >= config.safety.delta_t_starved:
        return (
            "starved",
            (
                f"A temperature rise of {delta:.1f} C means the water is not carrying "
                "the heat away fast enough. This is what a genuine flow problem looks "
                "like: check the filter, the valve positions and for air in the lines."
            ),
            numbers,
        )
    if delta >= config.safety.delta_t_healthy_max:
        return (
            "marginal",
            (
                f"A temperature rise of {delta:.1f} C is on the high side. Not a "
                "problem yet, but worth watching if it climbs."
            ),
            numbers,
        )
    return (
        "healthy",
        (
            f"A temperature rise of {delta:.1f} C means the water is carrying the heat "
            "away comfortably, whatever the flow figure says against the datasheet."
        ),
        numbers,
    )


def evaluate(state: PoolState, config: PoolConfig) -> list[Fault]:
    """Return every fault currently detected, most severe first."""
    faults = _reading_faults(state, config)
    faults += _flow_faults(state, config)
    faults += _delta_t_faults(state, config)
    faults += _calibration_faults(state, config)

    order = {Severity.CRITICAL: 0, Severity.HEATING_BLOCKED: 1, Severity.WARNING: 2}
    return sorted(faults, key=lambda f: order[f.severity])


def heat_pump_available(
    state: PoolState, config: PoolConfig, faults: list[Fault]
) -> tuple[bool, str]:
    """The operating envelope gate that sits in front of every heating branch.

    This is a gate rather than a condition inside the branches because it is a
    property of the appliance, not of the decision. The consequence matters:
    below the minimum air temperature nothing can heat the pool, not even a
    negative electricity price and not even the minimum-temperature protection.
    That protection can only circulate.
    """
    if any(f.severity in (Severity.CRITICAL, Severity.HEATING_BLOCKED) for f in faults):
        blocking = next(
            f
            for f in faults
            if f.severity in (Severity.CRITICAL, Severity.HEATING_BLOCKED)
        )
        return False, blocking.message

    # A source with no air temperature limits has no envelope to check. An
    # immersion element works at any outdoor temperature, so refusing to heat
    # because the outdoor probe is missing would be inventing a restriction the
    # hardware does not have.
    if not config.source_has("air_temp_limits"):
        if not config.source_has("controllable"):
            return False, (
                "This heating source is operated by hand, so the integration "
                "advises rather than switching it."
            )
        return True, "No operating envelope applies to this heating source."

    if not state.air_temp.available:
        return False, "Outdoor temperature is unknown, so the operating envelope cannot be checked."

    air = state.air_temp.value
    if air < config.heat_pump.air_temp_min:
        return False, (
            f"Outdoor temperature of {air:.1f} C is below the heat pump minimum of "
            f"{config.heat_pump.air_temp_min:.1f} C."
        )
    if air > config.heat_pump.air_temp_max:
        return False, (
            f"Outdoor temperature of {air:.1f} C is above the heat pump maximum of "
            f"{config.heat_pump.air_temp_max:.1f} C."
        )

    flow = state.effective_flow_m3h
    if (
        config.heat_pump.flow_min_blocking
        and flow is not None
        and flow < config.heat_pump.flow_min_m3h
        and state.pump_on
        and state.pump_runtime_seconds >= config.safety.pump_startup_grace_seconds
    ):
        return False, (
            f"Flow of {flow:.2f} m3/h is below the heat pump minimum of "
            f"{config.heat_pump.flow_min_m3h:.2f} m3/h."
        )

    return True, "Within the operating envelope."


def solar_collector_advice(
    state: PoolState, config: PoolConfig
) -> tuple[bool, str, dict]:
    """Whether water should be going through the solar collector.

    Almost every solar collector is plumbed through a manual three-way valve, so
    there is nothing here to switch. What the integration can do is watch the
    collector against the pool and say when turning the valve is worth the walk
    outside -- and, just as usefully, when it is not, because water pushed
    through a cold collector loses heat rather than gaining it.
    """
    if not (config.has_solar_collector or config.heating_source == "solar"):
        return False, "", {}

    collector = state.collector_temp
    if collector is None or not collector.available:
        return (
            False,
            "No collector temperature sensor, so there is nothing to compare.",
            {},
        )
    if not state.water_temp.available:
        return False, "The pool temperature is unknown.", {}

    difference = collector.value - state.water_temp.value
    numbers = {
        "collector": round(collector.value, 1),
        "pool": round(state.water_temp.value, 1),
        "difference": round(difference, 1),
        "margin": config.collector_margin,
    }

    if difference >= config.collector_margin:
        return (
            True,
            (
                f"The collector is at {collector.value:.1f} C against "
                f"{state.water_temp.value:.1f} C in the pool. Opening the valve "
                "is free heat."
            ),
            numbers,
        )
    if difference <= 0:
        return (
            False,
            (
                f"The collector is at {collector.value:.1f} C, colder than the "
                "pool. Water sent through it now would lose heat rather than "
                "gain it, so keep the valve closed."
            ),
            numbers,
        )
    return (
        False,
        (
            f"The collector is only {difference:.1f} C above the pool, under the "
            f"{config.collector_margin:.1f} C worth bothering with."
        ),
        numbers,
    )
