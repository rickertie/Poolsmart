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
from .trace import Trace, Verdict
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


#: Branches that run the pump for their own reasons but have no objection to the
#: heat pump running at the same time. The pump is the expensive prerequisite;
#: once it is turning, heating alongside costs nothing extra in circulation.
CIRCULATION_ONLY = frozenset(
    {Branch.CHEMISTRY, Branch.FILTRATION_DEADLINE, Branch.FILTRATION_BLOCK}
)


def _augment_with_heating(
    decision: Decision,
    state: PoolState,
    config: PoolConfig,
    hp_available: bool,
) -> Decision:
    """Let a circulation branch heat as well when heating is wanted.

    Without this, a branch that only cares about circulation silently blocks
    heating for as long as it runs. On a pool needing many hours of filtration a
    day the deadline branch is active most of the time, so heating would almost
    never happen -- and asking for Boost would appear to do nothing at all, with
    the reason line talking about filtration.

    The pump is already running, so this changes nothing about circulation. It
    only adds heat that was wanted anyway.
    """
    if decision.branch not in CIRCULATION_ONLY or decision.heat_pump:
        return decision
    if not hp_available or not _needs_heat(state, config):
        return decision
    if Branch.HEATING not in MODE_BRANCHES[state.mode]:
        return decision
    # STANDBY deliberately circulates without heating; that is its whole purpose.
    if state.mode is Mode.STANDBY:
        return decision

    if state.mode is Mode.BOOST:
        why = "Boost is on, so price is ignored"
    else:
        acceptable, reason = _price_acceptable(state, config)
        planned = state.heating_session_active or (
            state.heating_session_planned_start is not None
            and state.heating_session_planned_start <= state.now
        )
        if not (acceptable or planned):
            return decision
        why = reason if acceptable else "this moment is part of the plan"

    detail = dict(decision.detail)
    detail["heating_added"] = True
    return replace(
        decision,
        heat_pump=True,
        reason=(
            f"{decision.reason} Heating at the same time to reach "
            f"{state.target_temp:.1f} C, because {why} and the pump is running anyway."
        ),
        detail=detail,
    )


def _walk(
    state: PoolState,
    config: PoolConfig,
    filtration: FiltrationStatus,
    faults: list[Fault],
    hp_available: bool,
    hp_gate_reason: str,
    trace: Trace | None = None,
) -> Decision:
    """Walk the ladder and return the first matching branch.

    Records why each branch it passes was passed over. That record is what turns
    "the pump is off" into "the pump is off because the mode excludes it", which
    is the difference between a log and an explanation.
    """
    allowed = MODE_BRANCHES[state.mode]
    night = _in_night_window(state, config)
    trace = trace if trace is not None else Trace()

    def permitted(branch: Branch) -> bool:
        if branch not in allowed:
            trace.record(
                branch,
                Verdict.MODE,
                f"the {state.mode.value} mode does not include this branch",
            )
            return False
        if night and branch in NIGHT_BLOCKED and state.mode is not Mode.BOOST:
            trace.record(branch, Verdict.NIGHT, "blocked by the night window")
            return False
        return True

    def skip(branch: Branch, why: str) -> None:
        trace.record(branch, Verdict.NOT_APPLICABLE, why)

    def win(decision: Decision) -> Decision:
        trace.record(decision.branch, Verdict.WON)
        trace.fill_unreached(decision.branch)
        return decision

    # -- 0. Emergency stop -------------------------------------------------
    critical = [f for f in faults if f.severity is Severity.CRITICAL]
    if critical:
        return win(
            Decision(
                pump=False,
                heat_pump=False,
                branch=Branch.EMERGENCY_STOP,
                reason=f"Emergency stop: {critical[0].message}",
                detail={"faults": [f.code for f in critical]},
            )
        )
    skip(Branch.EMERGENCY_STOP, "no critical fault")

    # -- 1. Frost and minimum-temperature protection -----------------------
    if permitted(Branch.FROST_PROTECTION):
        needed, why = _protection_needed(state, config)
        if needed:
            can_heat = hp_available and _needs_heat(state, config)
            reason = f"Protecting the pool because {why}."
            if not can_heat and not hp_available:
                reason += f" Heating is not possible: {hp_gate_reason}"
            return win(
                Decision(
                    pump=True,
                    heat_pump=can_heat,
                    branch=Branch.FROST_PROTECTION,
                    reason=reason,
                    detail={"heat_pump_available": hp_available},
                )
            )
        skip(Branch.FROST_PROTECTION, "no frost or low-temperature risk")

    # -- 2. Manual control -------------------------------------------------
    if permitted(Branch.MANUAL):
        if state.mode is Mode.PUMP or state.manual_pump_request:
            return win(
                Decision(
                    pump=True,
                    heat_pump=False,
                    branch=Branch.MANUAL,
                    reason="The pump is running because it was switched on manually.",
                )
            )
        skip(Branch.MANUAL, "no manual override is active")

    # -- 3. Chemistry cycle ------------------------------------------------
    if permitted(Branch.CHEMISTRY):
        if state.chemistry_until is not None and state.now < state.chemistry_until:
            minutes = (state.chemistry_until - state.now).total_seconds() / 60
            return win(
                Decision(
                    pump=True,
                    heat_pump=False,
                    branch=Branch.CHEMISTRY,
                    reason=(
                        "Circulating for a chemical treatment cycle, "
                        f"{minutes:.0f} minutes remaining."
                    ),
                    detail={"until": state.chemistry_until.isoformat()},
                )
            )
        skip(Branch.CHEMISTRY, "no chemistry cycle is running")

    # -- 4. Filtration deadline -------------------------------------------
    if permitted(Branch.FILTRATION_DEADLINE):
      if filtration.deadline_critical:
        return win(Decision(
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
        ))
      else:
        skip(
            Branch.FILTRATION_DEADLINE,
            f"{filtration.remaining_h:.2f} h still owed but {filtration.available_h:.2f} h "
            "of window left, so there is time",
        )

    # -- 5. Free electricity ----------------------------------------------
    if permitted(Branch.FREE_POWER):
        if not _needs_heat(state, config):
            skip(Branch.FREE_POWER, "the pool is already at target")
        elif not hp_available:
            trace.record(Branch.FREE_POWER, Verdict.ENVELOPE, hp_gate_reason)
        else:
            negative, price = _negative_price(state, config)
            if negative:
                return win(
                    Decision(
                        pump=True,
                        heat_pump=True,
                        branch=Branch.FREE_POWER,
                        reason=(
                            f"Heating because electricity is priced at {price:.3f}/kWh. "
                            "Running now earns money."
                        ),
                        detail={
                            "price": price,
                            "basis": config.energy.negative_price_basis,
                        },
                    )
                )
            skip(
                Branch.FREE_POWER,
                f"the price is {price:.3f}/kWh, not below zero"
                if price is not None
                else "no price data",
            )

    # -- 6. Heating session ------------------------------------------------
    if permitted(Branch.HEATING):
        if not _needs_heat(state, config):
            skip(
                Branch.HEATING,
                f"the pool is at {state.water_temp.value:.1f} C, at or above the "
                f"{state.target_temp:.1f} C target"
                if state.water_temp.available
                else "the water temperature is unknown",
            )
        elif not hp_available:
            trace.record(Branch.HEATING, Verdict.ENVELOPE, hp_gate_reason)
        elif state.mode is Mode.BOOST:
            return win(
                Decision(
                    pump=True,
                    heat_pump=True,
                    branch=Branch.HEATING,
                    reason=(
                        f"Boost: heating to {state.target_temp:.1f} C regardless of price."
                    ),
                    detail={"mode": state.mode.value},
                )
            )
        else:
            acceptable, why = _price_acceptable(state, config)
            planned = state.heating_session_active or (
                state.heating_session_planned_start is not None
                and state.heating_session_planned_start <= state.now
            )
            if acceptable or planned:
                return win(
                    Decision(
                        pump=True,
                        heat_pump=True,
                        branch=Branch.HEATING,
                        reason=f"Heating to {state.target_temp:.1f} C because {why}.",
                        detail={"planned": planned, "price": state.price_total},
                    )
                )
            trace.record(Branch.HEATING, Verdict.PRICE, why)

    # -- 7. Scheduled filtration block ------------------------------------
    if permitted(Branch.FILTRATION_BLOCK):
      if filtration.active_block is not None:
        block = filtration.active_block
        return win(Decision(
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
        ))
      else:
        skip(
            Branch.FILTRATION_BLOCK,
            "no filtration block is scheduled for right now"
            if not filtration.satisfied
            else "today's filtration is already complete",
        )

    # -- 8. Pump rundown after heating ------------------------------------
    if permitted(Branch.PUMP_RUNDOWN):
        rundown_end = (
            state.heat_pump_stopped_at
            + timedelta(minutes=config.comfort.pump_rundown_minutes)
            if state.heat_pump_stopped_at is not None
            else None
        )
        if rundown_end is not None and state.now < rundown_end:
            return win(
                Decision(
                    pump=True,
                    heat_pump=False,
                    branch=Branch.PUMP_RUNDOWN,
                    reason=(
                        "Circulating briefly after the heat pump stopped, until "
                        f"{rundown_end.strftime('%H:%M')}."
                    ),
                    detail={"until": rundown_end.isoformat()},
                )
            )
        skip(Branch.PUMP_RUNDOWN, "the heat pump did not just stop")

    # -- 9. Idle -----------------------------------------------------------
    return win(Decision(
        pump=False,
        heat_pump=False,
        branch=Branch.IDLE,
        reason=_idle_reason(state, config, filtration, hp_available, hp_gate_reason, night),
        detail={
            "filtration_remaining_h": round(filtration.remaining_h, 3),
            "night": night,
            "heat_pump_available": hp_available,
            "blocked_by": [e.describe() for e in trace.blockers],
        },
    ))


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
        return (
            "Everything is off, including frost protection. Use Stand-by if the "
            "pool is still filled and should be protected."
        )
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


def _compressor_guard(
    candidate: Decision,
    state: PoolState,
    config: PoolConfig,
) -> Decision:
    """Enforce the compressor's own minimum off and on times.

    This is separate from the ordinary hold, and deliberately so. A hold protects
    a decision; this protects hardware, and hardware does not care which branch
    won the argument. A scroll or rotary compressor needs its refrigerant
    pressures to equalise before restarting, and short cycling is the classic way
    to wear one out early.

    The bug this exists to prevent: priority branches are allowed to break a hold,
    which is right for the pump -- a filtration deadline should not wait ten
    minutes -- but once those branches learned to heat alongside, they started
    dragging the compressor through the exception with them. Off at 20:01 and on
    again at 20:04 is not something to do to a heat pump.

    Only an emergency stop overrides this, and that switches off, which is always
    safe.
    """
    if candidate.branch is Branch.EMERGENCY_STOP:
        return candidate

    # Starting: has it been off long enough?
    if candidate.heat_pump and not state.heat_pump_on:
        stopped = state.heat_pump_stopped_at
        if stopped is not None:
            elapsed = (state.now - stopped).total_seconds() / 60
            required = config.comfort.compressor_min_off_minutes
            if elapsed < required:
                wait = required - elapsed
                detail = dict(candidate.detail)
                detail["compressor_guard"] = "min_off"
                detail["minutes_remaining"] = round(wait, 1)
                return replace(
                    candidate,
                    heat_pump=False,
                    reason=(
                        f"{candidate.reason} Heating waits another {wait:.0f} min: the "
                        "compressor needs its pressures to equalise before restarting."
                    ),
                    detail=detail,
                )

    # Stopping: has it run long enough? Never delay a stop that is about
    # temperature or safety -- only one that is merely a change of plan.
    if not candidate.heat_pump and state.heat_pump_on:
        started = state.heat_pump_started_at
        target_reached = (
            state.water_temp.available and state.water_temp.value >= state.target_temp
        )
        if started is not None and not target_reached:
            elapsed = (state.now - started).total_seconds() / 60
            required = config.comfort.compressor_min_on_minutes
            if elapsed < required and candidate.branch is not Branch.EMERGENCY_STOP:
                detail = dict(candidate.detail)
                detail["compressor_guard"] = "min_on"
                return replace(
                    candidate,
                    heat_pump=True,
                    reason=(
                        f"{candidate.reason} The heat pump keeps running for now: "
                        f"stopping it after {elapsed:.0f} min would be short cycling."
                    ),
                    detail=detail,
                )

    return candidate


def _may_override_hold(
    candidate: Decision, previous: Decision, state: PoolState, hp_available: bool
) -> bool:
    """Whether a fresh decision may break an active hold.

    Holds exist so that nothing can flip a relay inside the minimum on or off
    time. There are only three ways past one, and they are all cases where
    waiting would be worse than switching.

    Note that breaking a hold does not give the compressor a free pass; that is
    handled separately by :func:`_compressor_guard`, because the reasons to
    override a hold are about circulation and the reasons to protect a compressor
    are about hardware.
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
    trace: Trace | None = None,
) -> Decision:
    """Produce this tick's decision.

    Pass a ``Trace`` to find out what was considered along the way; the decision
    itself is unaffected by whether anyone is listening.
    """
    trace = trace if trace is not None else Trace()
    candidate = _walk(
        state, config, filtration, faults, hp_available, hp_gate_reason, trace
    )
    candidate = _augment_with_heating(candidate, state, config, hp_available)
    # Hardware protection sits outside the branch argument entirely: it applies
    # to whatever the ladder decided, including the priority branches that are
    # allowed to break an ordinary hold.
    candidate = _compressor_guard(candidate, state, config)

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
