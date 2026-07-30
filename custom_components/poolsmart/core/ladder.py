"""The decision ladder.

This is the only place in the integration where it is decided whether the pump
and the heat pump run. Every tick produces exactly one :class:`Decision`, and
everything the user sees is a rendering of that object.

The ladder is walked from the top. The first branch that matches wins and lower
branches are not evaluated. Modes do not carry their own logic; they enable or
disable branches, which is what keeps the logic in one place.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from .config import NegativePriceBasis, PoolConfig
from .filtration import FiltrationStatus
from .models import (
    MODE_BRANCHES,
    PRIORITY_BRANCHES,
    Branch,
    Decision,
    Fault,
    Mode,
    PoolState,
    Severity,
)

#: Branches that must not run during the night window.
NIGHT_BLOCKED = frozenset({Branch.HEATING, Branch.FILTRATION_BLOCK, Branch.PUMP_RUNDOWN})


def _in_night_window(state: PoolState, config: PoolConfig) -> bool:
    start = config.comfort.night_start
    end = config.comfort.night_end
    current = state.now.time()
    if start <= end:
        return start <= current < end
    return current >= start or current < end


def _negative_price(state: PoolState, config: PoolConfig) -> tuple[bool, float | None]:
    """Whether electricity is currently priced below zero."""
    if config.energy.negative_price_basis == NegativePriceBasis.MARKET:
        price = state.price_energy
    else:
        price = state.price_total
    if price is None:
        return False, None
    return price < 0, price


def _price_acceptable(state: PoolState, config: PoolConfig) -> tuple[bool, str]:
    """Whether the current price and solar situation permit heating."""
    limit = config.energy.max_price
    if state.mode is Mode.ECO and limit is not None:
        limit *= config.energy.eco_price_factor

    solar = state.solar_power_w
    threshold = config.energy.solar_threshold_w
    if state.mode is Mode.ECO:
        threshold += config.energy.solar_hysteresis_w
    if solar is not None and solar >= threshold:
        return True, f"solar surplus of {solar:.0f} W covers the heat pump"

    if limit is None or state.price_total is None:
        return True, "no price limit configured"
    if state.price_total <= limit:
        return True, f"price {state.price_total:.3f}/kWh is within the limit of {limit:.3f}"
    return False, f"price {state.price_total:.3f}/kWh exceeds the limit of {limit:.3f}"


def _needs_heat(state: PoolState, config: PoolConfig) -> bool:
    """Whether the pool is below target, with hysteresis on the start side.

    Starting requires the water to be a little below target; stopping happens as
    soon as target is reached. The asymmetry is deliberate: overshooting wastes
    energy and, on this kind of installation, the software is the only thing that
    stops the heat pump at target.
    """
    if not state.water_temp.available:
        return False
    water = state.water_temp.value
    if state.heat_pump_on:
        return water < state.target_temp
    return water < state.target_temp - config.comfort.temp_hysteresis


def _protection_needed(state: PoolState, config: PoolConfig) -> tuple[bool, str]:
    """Frost and minimum-temperature protection.

    Note what this branch can and cannot do. Below the heat pump's minimum air
    temperature -- exactly the conditions in which this protection is needed --
    the appliance may not start, so protection can only circulate. Circulating
    water does not freeze, which is the point.
    """
    if state.air_temp.available and state.air_temp.value < config.comfort.frost_air_temp:
        return True, (
            f"outdoor temperature {state.air_temp.value:.1f} C is below the frost "
            f"threshold of {config.comfort.frost_air_temp:.1f} C"
        )
    if state.water_temp.available and state.water_temp.value < config.comfort.min_water_temp:
        return True, (
            f"water temperature {state.water_temp.value:.1f} C is below the minimum of "
            f"{config.comfort.min_water_temp:.1f} C"
        )
    return False, ""


def _walk(
    state: PoolState,
    config: PoolConfig,
    filtration: FiltrationStatus,
    faults: list[Fault],
    hp_available: bool,
    hp_gate_reason: str,
) -> Decision:
    """Walk the ladder and return the first matching branch."""
    allowed = MODE_BRANCHES[state.mode]
    night = _in_night_window(state, config)

    def permitted(branch: Branch) -> bool:
        if branch not in allowed:
            return False
        if night and branch in NIGHT_BLOCKED and state.mode is not Mode.BOOST:
            return False
        return True

    # -- 0. Emergency stop -------------------------------------------------
    critical = [f for f in faults if f.severity is Severity.CRITICAL]
    if critical:
        return Decision(
            pump=False,
            heat_pump=False,
            branch=Branch.EMERGENCY_STOP,
            reason=f"Emergency stop: {critical[0].message}",
            detail={"faults": [f.code for f in critical]},
        )

    # -- 1. Frost and minimum-temperature protection -----------------------
    if permitted(Branch.FROST_PROTECTION):
        needed, why = _protection_needed(state, config)
        if needed:
            can_heat = hp_available and _needs_heat(state, config)
            reason = f"Protecting the pool because {why}."
            if not can_heat and not hp_available:
                reason += f" Heating is not possible: {hp_gate_reason}"
            return Decision(
                pump=True,
                heat_pump=can_heat,
                branch=Branch.FROST_PROTECTION,
                reason=reason,
                detail={"heat_pump_available": hp_available},
            )

    # -- 2. Manual control -------------------------------------------------
    if permitted(Branch.MANUAL) and (state.mode is Mode.PUMP or state.manual_pump_request):
        return Decision(
            pump=True,
            heat_pump=False,
            branch=Branch.MANUAL,
            reason="The pump is running because it was switched on manually.",
        )

    # -- 3. Chemistry cycle ------------------------------------------------
    if (
        permitted(Branch.CHEMISTRY)
        and state.chemistry_until is not None
        and state.now < state.chemistry_until
    ):
        minutes = (state.chemistry_until - state.now).total_seconds() / 60
        return Decision(
            pump=True,
            heat_pump=False,
            branch=Branch.CHEMISTRY,
            reason=f"Circulating for a chemical treatment cycle, {minutes:.0f} minutes remaining.",
            detail={"until": state.chemistry_until.isoformat()},
        )

    # -- 4. Filtration deadline -------------------------------------------
    if permitted(Branch.FILTRATION_DEADLINE) and filtration.deadline_critical:
        return Decision(
            pump=True,
            heat_pump=False,
            branch=Branch.FILTRATION_DEADLINE,
            reason=(
                f"Circulating to meet today's filtration requirement: "
                f"{filtration.remaining_h:.2f} h still needed and only "
                f"{filtration.available_h:.2f} h of window left. Price is ignored."
            ),
            detail={
                "remaining_h": round(filtration.remaining_h, 3),
                "available_h": round(filtration.available_h, 3),
            },
        )

    # -- 5. Free electricity ----------------------------------------------
    if permitted(Branch.FREE_POWER) and hp_available and _needs_heat(state, config):
        negative, price = _negative_price(state, config)
        if negative:
            return Decision(
                pump=True,
                heat_pump=True,
                branch=Branch.FREE_POWER,
                reason=(
                    f"Heating because electricity is priced at {price:.3f}/kWh. "
                    "Running now earns money."
                ),
                detail={"price": price, "basis": config.energy.negative_price_basis},
            )

    # -- 6. Heating session ------------------------------------------------
    if permitted(Branch.HEATING) and _needs_heat(state, config):
        if not hp_available:
            # Fall through, but record why so the reason is not silently lost.
            pass
        else:
            if state.mode is Mode.BOOST:
                return Decision(
                    pump=True,
                    heat_pump=True,
                    branch=Branch.HEATING,
                    reason=(
                        f"Boost: heating to {state.target_temp:.1f} C regardless of price."
                    ),
                    detail={"mode": state.mode.value},
                )
            acceptable, why = _price_acceptable(state, config)
            planned = state.heating_session_active or (
                state.heating_session_planned_start is not None
                and state.heating_session_planned_start <= state.now
            )
            if acceptable or planned:
                return Decision(
                    pump=True,
                    heat_pump=True,
                    branch=Branch.HEATING,
                    reason=f"Heating to {state.target_temp:.1f} C because {why}.",
                    detail={"planned": planned, "price": state.price_total},
                )

    # -- 7. Scheduled filtration block ------------------------------------
    if permitted(Branch.FILTRATION_BLOCK) and filtration.active_block is not None:
        block = filtration.active_block
        return Decision(
            pump=True,
            heat_pump=False,
            branch=Branch.FILTRATION_BLOCK,
            reason=(
                f"Running filtration block {block.index + 1} until "
                f"{block.end.strftime('%H:%M')} ({block.rationale})."
            ),
            detail={
                "block_index": block.index,
                "block_end": block.end.isoformat(),
                "remaining_h": round(filtration.remaining_h, 3),
            },
        )

    # -- 8. Pump rundown after heating ------------------------------------
    if permitted(Branch.PUMP_RUNDOWN) and state.heat_pump_stopped_at is not None:
        rundown_end = state.heat_pump_stopped_at + timedelta(
            minutes=config.comfort.pump_rundown_minutes
        )
        if state.now < rundown_end:
            return Decision(
                pump=True,
                heat_pump=False,
                branch=Branch.PUMP_RUNDOWN,
                reason=(
                    "Circulating briefly after the heat pump stopped, until "
                    f"{rundown_end.strftime('%H:%M')}."
                ),
                detail={"until": rundown_end.isoformat()},
            )

    # -- 9. Idle -----------------------------------------------------------
    return Decision(
        pump=False,
        heat_pump=False,
        branch=Branch.IDLE,
        reason=_idle_reason(state, config, filtration, hp_available, hp_gate_reason, night),
        detail={
            "filtration_remaining_h": round(filtration.remaining_h, 3),
            "night": night,
            "heat_pump_available": hp_available,
        },
    )


def _idle_reason(
    state: PoolState,
    config: PoolConfig,
    filtration: FiltrationStatus,
    hp_available: bool,
    hp_gate_reason: str,
    night: bool,
) -> str:
    """Explain doing nothing.

    Idle is the branch users most often misread as a malfunction, so it gets the
    most specific explanation of all of them.
    """
    if state.mode is Mode.OFF:
        return "Everything is off. Frost protection stays active."
    if night:
        return "Night quiet hours. Nothing runs unless safety or a negative price requires it."
    if _needs_heat(state, config) and not hp_available:
        return f"Not heating: {hp_gate_reason}"
    if _needs_heat(state, config):
        acceptable, why = _price_acceptable(state, config)
        if not acceptable:
            return f"Waiting for cheaper electricity: {why}."
    if filtration.satisfied:
        return (
            f"Today's filtration is complete ({filtration.done_h:.2f} of "
            f"{filtration.required_h:.2f} h). Nothing to do."
        )
    if filtration.next_block is not None:
        block = filtration.next_block
        return (
            f"Waiting for the next filtration block at "
            f"{block.start.strftime('%H:%M')} ({block.rationale})."
        )
    if state.water_temp.available and state.water_temp.value >= state.target_temp:
        return f"The pool is at {state.water_temp.value:.1f} C, at or above target. Idle."
    return "Nothing to do right now."


def _hold_minutes(candidate: Decision, previous: Decision | None, config: PoolConfig) -> int:
    """How long a fresh decision stays valid."""
    turning_on = candidate.pump or candidate.heat_pump
    if previous is not None and candidate.same_outputs(previous):
        return 0
    return config.comfort.min_on_minutes if turning_on else config.comfort.min_off_minutes


def _may_override_hold(
    candidate: Decision, previous: Decision, state: PoolState, hp_available: bool
) -> bool:
    """Whether a fresh decision may break an active hold.

    Holds exist so that nothing can flip a relay inside the minimum on or off
    time. There are only three ways past one, and they are all cases where
    waiting would be worse than switching.
    """
    # Safety and non-negotiable obligations always win.
    if candidate.branch in PRIORITY_BRANCHES:
        return True
    # Switching the heat pump off is always allowed immediately. On this kind of
    # installation the software is the only thing that stops it at target, so a
    # stop must never be postponed by hysteresis.
    if previous.heat_pump and not candidate.heat_pump:
        return True
    # The appliance left its operating envelope.
    if previous.heat_pump and not hp_available:
        return True
    # The user changed mode.
    if previous.detail.get("mode_at_decision") != state.mode.value:
        return True
    return False


def decide(
    state: PoolState,
    config: PoolConfig,
    filtration: FiltrationStatus,
    faults: list[Fault],
    hp_available: bool,
    hp_gate_reason: str,
    previous: Decision | None = None,
) -> Decision:
    """Produce this tick's decision."""
    candidate = _walk(state, config, filtration, faults, hp_available, hp_gate_reason)

    detail = dict(candidate.detail)
    detail["mode_at_decision"] = state.mode.value
    candidate = replace(candidate, detail=detail, taken_at=state.now)

    if (
        previous is not None
        and previous.hold_until is not None
        and state.now < previous.hold_until
        and not candidate.same_outputs(previous)
        and not _may_override_hold(candidate, previous, state, hp_available)
    ):
        held_detail = dict(previous.detail)
        held_detail["held_until"] = previous.hold_until.isoformat()
        held_detail["suppressed_branch"] = candidate.branch.name
        return replace(previous, detail=held_detail)

    if candidate.same_outputs(previous) and previous is not None:
        # Nothing switches, so the existing hold simply carries on. Keeping the
        # original hold_until here is what makes a running filtration block
        # immune to reassessment on every tick.
        return replace(candidate, hold_until=previous.hold_until)

    minutes = _hold_minutes(candidate, previous, config)
    hold_until: datetime | None = (
        state.now + timedelta(minutes=minutes) if minutes else None
    )

    # A running filtration block holds until the block ends, not merely for the
    # minimum on time. The block is a state with an end, not a threshold.
    if candidate.branch is Branch.FILTRATION_BLOCK and filtration.active_block is not None:
        hold_until = max(hold_until or state.now, filtration.active_block.end)

    return replace(candidate, hold_until=hold_until)
