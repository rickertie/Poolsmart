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
    curve, _ = learning.update_cop_curve(curve, warm.measured_cop, warm.air_avg, config)
    curve, _ = learning.update_cop_curve(curve, cool.measured_cop, cool.air_avg, config)

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


# ---------------------------------------------------------------------------
# T111 - solar gain is modelled during idle periods, not just discarded
# (closes #12)
# ---------------------------------------------------------------------------

def test_t111_measured_irradiance_recovers_a_sunny_idle_period():
    """A real solar sensor can explain away a warming period entirely.

    Without the correction this period is indistinguishable from any other
    warming afternoon and gets thrown away. With a measured irradiance average
    it is recovered as a small, genuine heat-loss reading -- the sun explains
    most, but not all, of the observed rise.
    """
    config = make_config()
    rate = learning.heat_loss_from_idle(
        27.0, 27.9, duration_h=3.0, config=config, irradiance_w_m2=300.0
    )
    assert rate is not None and rate > 0


def test_t111b_daylight_estimate_recovers_only_mild_warming():
    """Without a sensor, only a conservative amount of warming is explained.

    A mildly-sunny period is recovered from the flat time-of-day estimate, but
    a strongly-sunny one -- an amount of warming the conservative estimate
    cannot plausibly account for -- is still discarded exactly as before. The
    estimate is deliberately low so it never manufactures heat loss that never
    happened.
    """
    config = make_config()
    mild = learning.heat_loss_from_idle(
        27.0, 27.2, duration_h=2.0, config=config, daytime=True
    )
    assert mild is not None and mild > 0

    strong = learning.heat_loss_from_idle(
        27.0, 28.0, duration_h=2.0, config=config, daytime=True
    )
    assert strong is None


def test_t111c_no_signal_reproduces_old_behaviour():
    """Neither a sensor reading nor a daylight flag: nothing changes."""
    config = make_config()
    assert (
        learning.heat_loss_from_idle(27.0, 27.6, duration_h=5.0, config=config)
        is None
    )
    rate = learning.heat_loss_from_idle(28.0, 27.0, duration_h=10.0, config=config)
    assert abs(rate - 0.1) < 1e-9


# ---------------------------------------------------------------------------
# T112 - a direct irradiance sensor outranks the scaled solar-power estimate
# ---------------------------------------------------------------------------

def test_t112_irradiance_sensor_preferred_over_solar_power_estimate():
    """A real W/m2 reading is never overridden by the coarser panel estimate.

    The guard lives in the coordinator's ``_irradiance``; this pins that the
    direct sensor is checked first, ahead of scaling the solar-power sensor
    against its configured peak.
    """
    source = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "poolsmart"
        / "coordinator.py"
    ).read_text()
    irradiance_method = source[source.index("def _irradiance(") :]
    irradiance_method = irradiance_method[: irradiance_method.index("\n    def ")]

    assert "if state.irradiance_w_m2 is not None:" in irradiance_method
    assert "return state.irradiance_w_m2" in irradiance_method
    # And it comes before the solar-power fallback, not after.
    assert irradiance_method.index("state.irradiance_w_m2") < irradiance_method.index(
        "state.solar_power_w"
    )


# ---------------------------------------------------------------------------
# T113 - a weather forecast scales the learned heat loss (closes #8)
# ---------------------------------------------------------------------------

def test_t113_colder_forecast_raises_scaled_loss():
    """A forecast colder than today's air should raise the loss figure.

    Water at 28, air at 18 today is a 10-degree gap; a forecast of 8 doubles
    it to 20, so the scaled figure should be noticeably higher than the base.
    """
    scaled = learning.forecast_scaled_heat_loss_c_per_h(
        base_c_per_h=0.1, water_temp=28.0, current_air_temp=18.0, forecast_air_temp=8.0
    )
    assert scaled > 0.1
    # Bounded at the ceiling rather than growing without limit.
    assert scaled <= 0.1 * learning.FORECAST_LOSS_CEILING + 1e-9


def test_t113b_warmer_forecast_lowers_scaled_loss_but_floors():
    """A forecast warmer than today's air lowers the figure, but not to zero.

    Under-estimating loss is the failure that shows up as a cold pool at swim
    time, so a warm forecast is trusted only down to the conservative floor.
    """
    scaled = learning.forecast_scaled_heat_loss_c_per_h(
        base_c_per_h=0.2, water_temp=28.0, current_air_temp=18.0, forecast_air_temp=27.0
    )
    assert 0.0 < scaled < 0.2
    assert scaled >= 0.2 * learning.FORECAST_LOSS_FLOOR - 1e-9


def test_t113c_small_current_gap_returns_base_unchanged():
    """A near-zero water/air gap today is too little baseline to scale from."""
    scaled = learning.forecast_scaled_heat_loss_c_per_h(
        base_c_per_h=0.15, water_temp=20.0, current_air_temp=19.8, forecast_air_temp=5.0
    )
    assert scaled == 0.15


def test_t113d_seasonal_projection_reacts_to_a_colder_forecast():
    """The same job takes longer, or becomes unreachable, on a colder forecast.

    ``optimizer.plan`` takes a single ``heat_loss_c_per_h`` -- exactly what
    :func:`learning.forecast_scaled_heat_loss_c_per_h` produces -- so scaling
    it before the call is enough to make Seasonal mode's projection forecast
    aware, with no change to the optimizer itself.
    """
    config = make_config()
    now = datetime(2026, 1, 5, 9, 0, tzinfo=TZ)
    est = heating.estimate(
        config, water_temp=20.0, target_temp=28.0, air_temp=5.0, hours_available=4.0
    )
    slots = price_day(now, [0.20, 0.22, 0.21, 0.23])

    mild_loss = learning.forecast_scaled_heat_loss_c_per_h(
        base_c_per_h=0.1, water_temp=20.0, current_air_temp=5.0, forecast_air_temp=8.0
    )
    cold_loss = learning.forecast_scaled_heat_loss_c_per_h(
        base_c_per_h=0.1, water_temp=20.0, current_air_temp=5.0, forecast_air_temp=-10.0
    )
    assert cold_loss > mild_loss

    mild_plan = optimizer.plan(
        now, config, est, slots, deadline=now + timedelta(hours=4),
        heat_loss_c_per_h=mild_loss,
    )
    cold_plan = optimizer.plan(
        now, config, est, slots, deadline=now + timedelta(hours=4),
        heat_loss_c_per_h=cold_loss,
    )

    assert mild_plan.mode is PlanMode.SEASONAL
    assert cold_plan.mode is PlanMode.SEASONAL
    # A colder forecast means less net progress per day, so either a later
    # ready date or an outright "cannot be reached" -- never an earlier one.
    if cold_plan.ready_at is None:
        assert "cannot be reached" in cold_plan.reason
    elif mild_plan.ready_at is not None:
        assert cold_plan.ready_at >= mild_plan.ready_at
