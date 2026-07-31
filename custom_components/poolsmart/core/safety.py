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
        if age <= warn_after:
            continue

        code = f"stale_{reading.role or label.replace(' ', '_')}"
        minutes = age / 60
        if age > block_after:
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

    if state.heat_pump_on and flow < config.heat_pump.flow_min_m3h:
        faults.append(
            Fault(
                "flow_below_heat_pump_minimum",
                Severity.HEATING_BLOCKED,
                (
                    f"Flow of {flow:.2f} m3/h is below the heat pump minimum of "
                    f"{config.heat_pump.flow_min_m3h:.2f} m3/h."
                ),
                {"flow_m3h": flow},
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

    commissioned = config.pump.effective_flow_m3h
    if state.pump_on and commissioned > 0:
        ratio = flow / commissioned
        if ratio < config.safety.filter_service_flow_ratio:
            faults.append(
                Fault(
                    "filter_service_needed",
                    Severity.WARNING,
                    (
                        f"Flow has dropped to {ratio * 100:.0f}% of the commissioned value. "
                        "The filter probably needs cleaning."
                    ),
                    {"ratio": ratio, "flow_m3h": flow},
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


def evaluate(state: PoolState, config: PoolConfig) -> list[Fault]:
    """Return every fault currently detected, most severe first."""
    faults = _reading_faults(state, config)
    faults += _flow_faults(state, config)
    faults += _delta_t_faults(state, config)

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
    if flow is not None and flow < config.heat_pump.flow_min_m3h and state.pump_on:
        return False, (
            f"Flow of {flow:.2f} m3/h is below the heat pump minimum of "
            f"{config.heat_pump.flow_min_m3h:.2f} m3/h."
        )

    return True, "Within the operating envelope."
