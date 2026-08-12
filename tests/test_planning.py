"""Acceptance tests T13 - T22 for the planner and the learning modules."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "poolsmart"))

from core import heating, learning, optimizer  # noqa: E402
from core.heating import PlanMode  # noqa: E402

from test_acceptance import TZ, make_config  # noqa: E402


def price_day(start: datetime, prices: list[float]) -> tuple:
    """Build hourly price slots starting at ``start``."""
    return tuple(
        (start + timedelta(hours=i), start + timedelta(hours=i + 1), p)
        for i, p in enumerate(prices)
    )


# ---------------------------------------------------------------------------
# T13 - a small top-up is placed in the cheapest hours
# ---------------------------------------------------------------------------

def test_t13_maintenance_picks_cheapest_hours():
    config = make_config()
    now = datetime(2026, 7, 30, 8, 0, tzinfo=TZ)
    est = heating.estimate(config, water_temp=27.0, target_temp=28.0, air_temp=20.0,
                           hours_available=12.0)
    slots = price_day(now, [0.40, 0.35, 0.10, 0.09, 0.38, 0.42, 0.30, 0.11,
                            0.44, 0.45, 0.20, 0.21])
    plan = optimizer.plan(now, config, est, slots, deadline=now + timedelta(hours=12))

    assert plan.mode is PlanMode.MAINTENANCE
    chosen_prices = sorted(p for _s, _e, p in plan.slots)
    assert chosen_prices[0] == 0.09
    assert max(chosen_prices) <= 0.11, chosen_prices
    assert plan.hours_planned >= plan.hours_needed
    assert plan.ready_at is not None


# ---------------------------------------------------------------------------
# T14 - a large rise becomes a multi-day plan with a date, not a time
# ---------------------------------------------------------------------------

def test_t14_seasonal_projects_a_date():
    config = make_config()
    now = datetime(2026, 5, 1, 9, 0, tzinfo=TZ)
    est = heating.estimate(config, water_temp=18.0, target_temp=28.0, air_temp=18.0,
                           hours_available=6.0)
    slots = price_day(now, [0.10, 0.12, 0.11, 0.35, 0.40, 0.42])
    plan = optimizer.plan(now, config, est, slots, deadline=now + timedelta(hours=6))

    assert plan.mode is PlanMode.SEASONAL
    assert plan.ready_at is not None
    assert plan.ready_at > now + timedelta(days=1), plan.ready_at
    assert "several days" in plan.reason


# ---------------------------------------------------------------------------
# T15 - when the pool loses heat faster than it gains, say so
# ---------------------------------------------------------------------------

def test_t15_unreachable_target_is_reported():
    config = make_config()
    now = datetime(2026, 3, 1, 9, 0, tzinfo=TZ)
    est = heating.estimate(config, water_temp=12.0, target_temp=28.0, air_temp=12.0,
                           hours_available=2.0)
    slots = price_day(now, [0.20, 0.22])
    plan = optimizer.plan(now, config, est, slots, deadline=now + timedelta(hours=2),
                          heat_loss_c_per_h=0.6)

    assert plan.mode is PlanMode.SEASONAL
    assert plan.ready_at is None
    assert "cannot be reached" in plan.reason


# ---------------------------------------------------------------------------
# T16 - boost ignores prices entirely
# ---------------------------------------------------------------------------

def test_t16_boost_ignores_price():
    config = make_config()
    now = datetime(2026, 7, 30, 8, 0, tzinfo=TZ)
    est = heating.estimate(config, water_temp=26.0, target_temp=28.0, air_temp=22.0)
    slots = price_day(now, [0.90] * 12)
    plan = optimizer.plan(now, config, est, slots, boost=True)

    assert plan.is_active(now)
    assert plan.slots[0][0] == now


# ---------------------------------------------------------------------------
# T17 - without price data the plan still works
# ---------------------------------------------------------------------------

def test_t17_no_price_data_starts_now():
    config = make_config()
    now = datetime(2026, 7, 30, 8, 0, tzinfo=TZ)
    est = heating.estimate(config, water_temp=27.0, target_temp=28.0, air_temp=20.0)
    plan = optimizer.plan(now, config, est, slots=())

    assert plan.is_active(now)
    assert "No usable price forecast" in plan.reason
    # And the plan must admit no comparison took place, so nothing downstream
    # describes this as a chosen cheap moment.
    assert plan.price_informed is False


# ---------------------------------------------------------------------------
# T18 - an interrupted session is not learned from
# ---------------------------------------------------------------------------

def test_t18_interrupted_session_rejected():
    config = make_config()
    start = datetime(2026, 7, 30, 9, 0, tzinfo=TZ)
    record = learning.SessionRecord(
        start=start,
        end=start + timedelta(hours=3),
        water_start=24.0,
        water_end=26.0,
        energy_kwh=1.8,
        interrupted=True,
    )
    verdict = learning.assess(record, config)
    assert verdict.usable is False
    assert "interrupted" in verdict.reason


# ---------------------------------------------------------------------------
# T19 - an implausible COP is rejected
# ---------------------------------------------------------------------------

def test_t19_implausible_cop_rejected():
    config = make_config()
    start = datetime(2026, 7, 30, 9, 0, tzinfo=TZ)
    record = learning.SessionRecord(
        start=start,
        end=start + timedelta(hours=3),
        water_start=24.0,
        water_end=26.0,
        energy_kwh=1.0,
        thermal_kwh=12.0,  # COP of 12, well beyond the clamp
    )
    record.sample_air(22.0)
    assert learning.assess(record, config).usable is False

    plausible = learning.SessionRecord(
        start=start,
        end=start + timedelta(hours=3),
        water_start=24.0,
        water_end=26.0,
        energy_kwh=2.0,
        thermal_kwh=10.0,  # COP of 5
    )
    plausible.sample_air(22.0)
    assert learning.assess(plausible, config).usable is True


# ---------------------------------------------------------------------------
# T20 - one odd session cannot wreck a learned value
# ---------------------------------------------------------------------------

def test_t20_updates_are_capped():
    updated = learning.capped_update(current=0.10, proposed=5.0, max_step_ratio=0.15)
    assert abs(updated - 0.115) < 1e-9, updated

    # From nothing, the first observation is taken as is.
    assert learning.capped_update(None, 0.42, 0.15) == 0.42

    # Repeated consistent observations do converge, just slowly.
    value = 0.10
    for _ in range(40):
        value = learning.capped_update(value, 0.40, 0.15)
    assert 0.35 < value <= 0.40, value


# ---------------------------------------------------------------------------
# T21 - the COP curve is kept per air-temperature bucket
# ---------------------------------------------------------------------------

def test_t21_cop_curve_buckets():
    config = make_config()
    start = datetime(2026, 7, 30, 9, 0, tzinfo=TZ)

    warm = learning.SessionRecord(start=start, end=start + timedelta(hours=3),
                                  water_start=24.0, water_end=26.0,
                                  energy_kwh=2.0, thermal_kwh=10.4)
    warm.sample_air(26.0)
    cool = learning.SessionRecord(start=start, end=start + timedelta(hours=3),
                                  water_start=24.0, water_end=25.5,
                                  energy_kwh=2.0, thermal_kwh=8.4)
    cool.sample_air(16.0)

    curve = {}
    curve, _ = learning.update_cop_curve(curve, warm, config)
    curve, _ = learning.update_cop_curve(curve, cool, config)

    assert learning.bucket_key(26.0) == "25-30"
    assert learning.bucket_key(16.0) == "15-20"
    assert curve["25-30"] > curve["15-20"], curve


# ---------------------------------------------------------------------------
# T22 - heat loss is only measured over meaningful idle periods
# ---------------------------------------------------------------------------

def test_t22_heat_loss_measurement():
    assert learning.heat_loss_from_idle(28.0, 27.5, duration_h=5.0) is not None
    # Too short to be meaningful.
    assert learning.heat_loss_from_idle(28.0, 27.9, duration_h=0.5) is None
    # The pool warmed up on its own; that is sunshine, not loss.
    assert learning.heat_loss_from_idle(27.0, 27.6, duration_h=5.0) is None

    rate = learning.heat_loss_from_idle(28.0, 27.0, duration_h=10.0)
    assert abs(rate - 0.1) < 1e-9
