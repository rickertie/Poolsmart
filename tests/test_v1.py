"""Tests for the 1.0 work: T54 - T62.

Covers the six points collected before the release: bridging a sensor outage,
per-role staleness, the mixing requirement on the calibration check, actually
using what was learned, and the chemistry module.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "poolsmart"))

from core import chemistry as chem  # noqa: E402
from core import heating, learning, safety  # noqa: E402
from core.models import SensorReading, Severity  # noqa: E402

from test_acceptance import TZ, make_config, make_state  # noqa: E402


# ---------------------------------------------------------------------------
# T54 - a probe that only matters while heating may go quiet
# ---------------------------------------------------------------------------

def test_t54_conditional_roles_stay_quiet_when_idle():
    """"The heat pump outlet has not been reported for 37 minutes."

    Perfectly true and completely uninteresting: the appliance was off, so
    nothing was changing, so nothing was published. Warning about it teaches
    people to ignore warnings.
    """
    config = make_config()
    now = datetime(2026, 8, 3, 14, 0, tzinfo=TZ)

    idle = make_state(
        now,
        hp_outlet=SensorReading(28.6, 37 * 60, "hp_outlet"),
        heat_pump_on=False,
    )
    assert not any(
        f.code.startswith("stale_hp") for f in safety.evaluate(idle, config)
    )

    # While it is running, the same silence is worth reporting.
    running = idle.replace(heat_pump_on=True, pump_on=True)
    assert any(f.code.startswith("stale_hp") for f in safety.evaluate(running, config))


# ---------------------------------------------------------------------------
# T55 - the water probe is not conditional
# ---------------------------------------------------------------------------

def test_t55_water_probe_silence_still_matters():
    """Whatever else is running, the pool temperature must keep arriving."""
    config = make_config()
    now = datetime(2026, 8, 3, 14, 0, tzinfo=TZ)
    state = make_state(
        now,
        water_temp=SensorReading(28.0, 40 * 60, "water"),
        heat_pump_on=False,
    )
    faults = safety.evaluate(state, config)
    assert any(f.code == "stale_water" for f in faults)


# ---------------------------------------------------------------------------
# T56 - stratified water is not a miscalibrated probe
# ---------------------------------------------------------------------------

def test_t56_calibration_check_needs_mixing():
    """Standing water is warm on top and cool at the intake. That is physics."""
    config = make_config()
    now = datetime(2026, 8, 3, 14, 0, tzinfo=TZ)

    # Pump off: the difference means nothing.
    settled = make_state(
        now,
        water_temp=SensorReading(28.06, 10, "water"),
        pump_inlet=SensorReading(26.94, 10, "pump_inlet"),
        pump_on=False,
    )
    assert not any(
        f.code == "probe_disagreement" for f in safety.evaluate(settled, config)
    )

    # Pump just started: still stratified, still not a verdict.
    starting = settled.replace(pump_on=True, pump_runtime_seconds=300)
    assert not any(
        f.code == "probe_disagreement" for f in safety.evaluate(starting, config)
    )

    # Well mixed and still disagreeing: now it is worth saying.
    mixed = settled.replace(pump_on=True, pump_runtime_seconds=45 * 60)
    assert any(
        f.code == "probe_disagreement" for f in safety.evaluate(mixed, config)
    )


# ---------------------------------------------------------------------------
# T57 - a measured COP is used instead of the datasheet
# ---------------------------------------------------------------------------

def test_t57_measured_cop_drives_the_estimate():
    """The datasheet said 1h29 per degree; the pool measured 2h17.

    Planning from the datasheet in that situation means starting too late and
    arriving cold, which is the failure people notice. The measurements to
    correct it were already being recorded and thrown away.
    """
    config = make_config()

    on_paper = heating.estimate(
        config, water_temp=26.0, target_temp=28.0, air_temp=26.0
    )
    measured = heating.estimate(
        config, water_temp=26.0, target_temp=28.0, air_temp=26.0, learned_cop=3.49
    )

    assert on_paper.source == "datasheet"
    assert measured.source == "measured COP"
    assert measured.hours_needed > on_paper.hours_needed * 1.4, (
        on_paper.hours_needed,
        measured.hours_needed,
    )
    # And the energy figure follows the measured efficiency, not the brochure.
    assert measured.kwh_electric > on_paper.kwh_electric


def test_t57b_measured_rate_beats_everything():
    """Degrees per hour is the most direct measurement there is."""
    config = make_config()
    est = heating.estimate(
        config,
        water_temp=26.0,
        target_temp=28.0,
        air_temp=26.0,
        learned_cop=3.49,
        learned_rate_c_per_h=0.44,
    )
    assert est.source == "measured heating rate"
    assert abs(est.hours_needed - 2 / 0.44) < 0.01


# ---------------------------------------------------------------------------
# T58 - one session is not a pattern
# ---------------------------------------------------------------------------

def test_t58_learned_cop_needs_confidence():
    """A wrong learned value is harder to spot than a wrong published one."""
    curve = {"25-30": 3.49}

    assert learning.cop_for(curve, {"25-30": 1}, 26.0) is None
    assert learning.cop_for(curve, {"25-30": 2}, 26.0) is None
    assert learning.cop_for(curve, {"25-30": 3}, 26.0) == 3.49

    # An adjacent band is a better guess than a datasheet for another pool.
    assert learning.cop_for(curve, {"25-30": 5}, 31.0) == 3.49
    # But not two bands away.
    assert learning.cop_for(curve, {"25-30": 5}, 12.0) is None


def test_t58b_confidence_is_reported_in_words():
    assert learning.rate_confidence(0) == "not learned yet"
    assert learning.rate_confidence(1) == "provisional"
    assert learning.rate_confidence(4) == "usable"
    assert learning.rate_confidence(12) == "reliable"


# ---------------------------------------------------------------------------
# T59 - dosing is computed from this pool's volume
# ---------------------------------------------------------------------------

def test_t59_ph_dose():
    volume = 3834

    assert chem.dose_for_ph(7.4, volume) is None, "in range needs nothing"

    dose = chem.dose_for_ph(7.82, volume)
    assert dose.unit == "ml"
    assert 10 < dose.amount < 40, dose.amount
    assert dose.partial is False
    assert dose.aiming_for == 7.55

    # A pool ten times the size needs ten times the acid.
    bigger = chem.dose_for_ph(7.82, volume * 10)
    assert abs(bigger.amount / dose.amount - 10) < 0.01


def test_t59b_large_corrections_are_truncated():
    """pH is buffered in a way this maths does not model.

    Attempting a whole point in one go overshoots and leaves you adding the
    opposite chemical. "Add some, wait, measure again" is the honest answer.
    """
    dose = chem.dose_for_ph(8.6, 3834)
    assert dose.partial is True
    assert dose.aiming_for == 8.2, "aims one step, not the whole way"


def test_t59c_chlorine_dose_aims_for_the_middle():
    """Landing on the lower limit means being under it by morning."""
    assert chem.dose_for_chlorine(2.0, 3834) is None

    dose = chem.dose_for_chlorine(0.6, 3834)
    assert dose.aiming_for == 2.0
    assert 3 < dose.amount < 20, dose.amount
    assert "evening" in dose.instructions


# ---------------------------------------------------------------------------
# T60 - the test interval follows the water temperature
# ---------------------------------------------------------------------------

def test_t60_test_interval_scales_with_temperature():
    """A fixed three-day reminder is too often in spring, too rare in a heatwave."""
    assert chem.test_interval_days(16.0)[0] == 5
    assert chem.test_interval_days(22.0)[0] == 3
    assert chem.test_interval_days(28.0)[0] == 2
    assert chem.test_interval_days(32.0)[0] == 1
    assert chem.test_interval_days(None)[0] == 3

    now = datetime(2026, 8, 3, 12, 0, tzinfo=TZ)
    tested = now - timedelta(days=3)

    _due, overdue_warm, _ = chem.next_test_due(tested, 29.0, now)
    _due, overdue_cool, _ = chem.next_test_due(tested, 17.0, now)
    assert overdue_warm is True
    assert overdue_cool is False


# ---------------------------------------------------------------------------
# T61 - the pool's own response is learned
# ---------------------------------------------------------------------------

def test_t61_dose_correction_is_learned():
    """Alkalinity and stabiliser shift the real response, and are not modelled.

    Rather than pretend otherwise, measure it: a pool that moved half as far as
    predicted needs twice the dose next time.
    """
    now = datetime(2026, 8, 3, 12, 0, tzinfo=TZ)

    def record(before, after, expected):
        return chem.DoseRecord(
            at=now,
            product="acid_15",
            amount=40,
            unit="ml",
            measured_before=before,
            measured_after=after,
            expected_change=expected,
        )

    # Not enough data yet: change nothing.
    assert chem.learn_correction([record(7.8, 7.6, -0.4)], "acid_15") == 1.0

    # Consistently moving half as far as predicted.
    weak = [record(7.8, 7.6, -0.4), record(7.9, 7.7, -0.4), record(7.8, 7.6, -0.4)]
    assert abs(chem.learn_correction(weak, "acid_15") - 2.0) < 0.01

    # An implausible outcome -- a dose that did essentially nothing -- is
    # rejected outright rather than being allowed to quadruple the next dose.
    # Something other than the chemistry was wrong there.
    barely_moved = [record(7.8, 7.79, -0.4), record(7.8, 7.79, -0.4)]
    assert chem.learn_correction(barely_moved, "acid_15") == 1.0

    # And a real but extreme response is capped at double.
    very_weak = [record(7.8, 7.71, -0.4), record(7.8, 7.71, -0.4)]
    assert chem.learn_correction(very_weak, "acid_15") == 2.0


# ---------------------------------------------------------------------------
# T62 - a dose without a follow-up reading teaches nothing
# ---------------------------------------------------------------------------

def test_t62_open_doses_are_ignored_when_learning():
    now = datetime(2026, 8, 3, 12, 0, tzinfo=TZ)
    open_dose = chem.DoseRecord(
        at=now, product="acid_15", amount=40, unit="ml", measured_before=7.8
    )
    assert open_dose.actual_change is None
    assert open_dose.effectiveness is None
    assert chem.learn_correction([open_dose, open_dose], "acid_15") == 1.0
