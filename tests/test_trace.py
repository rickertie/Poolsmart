"""Tests for the decision trace (T41 - T45).

A decision says what the pool is doing. The trace says why it is not doing the
other thing, which is the question that actually gets asked.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "poolsmart"))

from core import filtration as filt  # noqa: E402
from core import ladder, safety  # noqa: E402
from core.models import Branch, Mode, SensorReading  # noqa: E402
from core.trace import Trace, Verdict  # noqa: E402

from test_acceptance import TZ, make_config, make_state  # noqa: E402


def walk(state, config, done_h: float = 0.0, measured=1.02):
    """Run one tick and hand back both the decision and the trace."""
    faults = safety.evaluate(state, config)
    status = filt.evaluate(
        state.now,
        config,
        done_h,
        water_temp=state.water_temp.value if state.water_temp.available else None,
        measured_flow_m3h=measured,
    )
    available, reason = safety.heat_pump_available(state, config, faults)
    trace = Trace()
    decision = ladder.decide(
        state, config, status, faults, available, reason, trace=trace
    )
    return decision, trace


def verdict_for(trace: Trace, branch: Branch):
    return next((e for e in trace.entries if e.branch is branch), None)


# ---------------------------------------------------------------------------
# T41 - every branch is accounted for
# ---------------------------------------------------------------------------

def test_t41_every_branch_is_accounted_for():
    """A branch missing from the trace looks like an oversight.

    Saying "not reached" is a fact about how the ladder works; saying nothing
    leaves the reader to guess whether it was skipped or forgotten.
    """
    config = make_config()
    now = datetime(2026, 8, 1, 16, 0, tzinfo=TZ)
    state = make_state(now, water_temp=SensorReading(28.8, 10, "water"))

    _decision, trace = walk(state, config, done_h=1.0)

    covered = {entry.branch for entry in trace.entries}
    assert covered == set(Branch), sorted(b.name for b in set(Branch) - covered)
    # And they are in ladder order, so the trace reads top to bottom.
    assert [int(e.branch) for e in trace.entries] == sorted(
        int(e.branch) for e in trace.entries
    )


# ---------------------------------------------------------------------------
# T42 - the price obstacle is named
# ---------------------------------------------------------------------------

def test_t42_price_obstacle_is_named():
    config = make_config()  # limit 0.25
    now = datetime(2026, 8, 1, 12, 0, tzinfo=TZ)
    state = make_state(
        now,
        water_temp=SensorReading(24.0, 10, "water"),
        target_temp=30.0,
        price_total=0.55,
        solar_power_w=0.0,
    )
    decision, trace = walk(state, config, done_h=20.0)  # filtration satisfied

    heating = verdict_for(trace, Branch.HEATING)
    assert heating.verdict is Verdict.PRICE
    assert "0.550" in heating.detail

    # And the obstacle surfaces on the idle decision rather than being buried.
    assert decision.branch is Branch.IDLE
    assert trace.blockers
    assert "price" in trace.summary().lower()


# ---------------------------------------------------------------------------
# T43 - the operating envelope obstacle is named
# ---------------------------------------------------------------------------

def test_t43_envelope_obstacle_is_named():
    config = make_config()
    now = datetime(2026, 12, 1, 12, 0, tzinfo=TZ)
    state = make_state(
        now,
        mode=Mode.BOOST,
        water_temp=SensorReading(15.0, 10, "water"),
        air_temp=SensorReading(6.0, 10, "air"),
        target_temp=28.0,
    )
    _decision, trace = walk(state, config, done_h=20.0)

    heating = verdict_for(trace, Branch.HEATING)
    assert heating.verdict is Verdict.ENVELOPE
    assert "below the heat pump minimum" in heating.detail

    free = verdict_for(trace, Branch.FREE_POWER)
    assert free.verdict is Verdict.ENVELOPE


# ---------------------------------------------------------------------------
# T44 - the mode obstacle is named
# ---------------------------------------------------------------------------

def test_t44_mode_obstacle_is_named():
    """Someone who left the pool in Stand-by should be told that is why.

    Stand-by is the case that puzzles people: the pump runs, the water is cold,
    and nothing heats. The trace has to say the mode is the reason, not leave it
    looking like a fault.
    """
    config = make_config()
    now = datetime(2026, 8, 1, 12, 0, tzinfo=TZ)
    state = make_state(
        now,
        mode=Mode.STANDBY,
        water_temp=SensorReading(22.0, 10, "water"),
        target_temp=30.0,
        price_total=0.05,
    )
    _decision, trace = walk(state, config, done_h=20.0)

    heating = verdict_for(trace, Branch.HEATING)
    assert heating.verdict is Verdict.MODE
    assert "standby" in heating.detail

    # In Pump mode the manual branch wins outright, so heating is never even
    # reached -- a different answer, and the trace distinguishes them.
    pump_state = state.replace(mode=Mode.PUMP)
    decision, pump_trace = walk(pump_state, config, done_h=20.0)
    assert decision.branch is Branch.MANUAL
    assert verdict_for(pump_trace, Branch.HEATING).verdict is Verdict.NOT_REACHED


# ---------------------------------------------------------------------------
# T45 - the trace explains Rick's original complaint
# ---------------------------------------------------------------------------

def test_t45_explains_the_boost_puzzle():
    """Boost with a warm pool and a critical filtration deadline.

    Before the trace existed, the status line talked about filtration while the
    user waited for heat, and there was nothing anywhere saying why. Heating now
    sits above the filtration deadline in the ladder, so Boost heats directly
    and the winning branch and the outcome both say what happened.
    """
    config = make_config()
    now = datetime(2026, 8, 1, 16, 0, tzinfo=TZ)
    state = make_state(
        now,
        mode=Mode.BOOST,
        water_temp=SensorReading(28.8, 10, "water"),
        air_temp=SensorReading(26.5, 10, "air"),
        target_temp=32.0,
        price_total=0.45,
    )
    decision, trace = walk(state, config, done_h=1.0)

    assert decision.branch is Branch.HEATING
    assert decision.heat_pump is True
    assert verdict_for(trace, Branch.HEATING).verdict is Verdict.WON
    # The branch below was never evaluated, and the trace says so.
    assert verdict_for(trace, Branch.FILTRATION_DEADLINE).verdict is Verdict.NOT_REACHED
