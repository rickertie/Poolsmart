"""Tests for long-term trend retention: T101 - T110.

Issue #11: the session log (SESSION_LOG_SIZE=60) and the daily summaries
(DAILY_SUMMARY_MAX_DAYS=90) are both capped, so a slow drift across months --
a heat pump's COP sagging, a filter fouling gradually -- was invisible by the
time enough raw data had rolled off the end to notice it. core/aggregates.py
adds a second, unbounded tier of monthly running statistics; these tests cover
that module directly and PoolStore's use of it.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "poolsmart"))

from core.aggregates import (  # noqa: E402
    STANDARD_METRICS,
    TREND_MIN_MONTHS,
    MetricStat,
    MonthlyAggregate,
    all_trends,
    month_key,
    trend,
)

TZ = timezone.utc


# ---------------------------------------------------------------------------
# T101 - a running mean costs the same whether it is folding in the first
# sample or the thousandth
# ---------------------------------------------------------------------------


def test_t101_metric_stat_running_mean():
    stat = MetricStat()
    for value in (3.0, 4.0, 5.0, 2.0):
        stat.fold(value)

    assert stat.n == 4
    assert stat.mean == 3.5
    assert stat.min == 2.0
    assert stat.max == 5.0


def test_t101b_a_single_sample_is_its_own_mean_min_and_max():
    stat = MetricStat()
    stat.fold(7.25)
    assert (stat.mean, stat.min, stat.max, stat.n) == (7.25, 7.25, 7.25, 1)


# ---------------------------------------------------------------------------
# T102 - a monthly aggregate survives a save/load round trip
# ---------------------------------------------------------------------------


def test_t102_monthly_aggregate_round_trip():
    agg = MonthlyAggregate(month="2026-06", session_count=5, runtime_hours=40.0)
    agg.heating_rate.fold(1.1)
    agg.heating_rate.fold(1.3)
    agg.cop_stat("25-30").fold(3.4)
    agg.cop_stat("25-30").fold(3.6)

    restored = MonthlyAggregate.from_dict(agg.as_dict())

    assert restored.month == "2026-06"
    assert restored.session_count == 5
    assert restored.runtime_hours == 40.0
    assert round(restored.heating_rate.mean, 6) == 1.2
    assert restored.heating_rate.n == 2
    assert round(restored.cop_by_bucket["25-30"].mean, 6) == 3.5
    assert restored.cop_by_bucket["25-30"].n == 2


def test_t102b_month_key_reads_year_and_month():
    assert month_key(datetime(2026, 3, 17, tzinfo=TZ)) == "2026-03"
    assert month_key(date(2026, 11, 1)) == "2026-11"


# ---------------------------------------------------------------------------
# T103 - two points make a line through anything; a trend needs more
# ---------------------------------------------------------------------------


def test_t103_trend_needs_a_minimum_of_months():
    months = []
    for i, mean in enumerate((3.0, 2.9)):
        agg = MonthlyAggregate(month=f"2026-0{i + 1}")
        agg.heating_rate.fold(mean)
        months.append(agg)
    assert len(months) < TREND_MIN_MONTHS

    result = trend(months, "heating_rate", higher_is_better=True)
    assert result.direction == "insufficient_data"
    assert result.months_considered == 2


# ---------------------------------------------------------------------------
# T104 - a rising or falling mean is read correctly in both directions
# ---------------------------------------------------------------------------


def _months(values: list[float], field: str = "heating_rate") -> list[MonthlyAggregate]:
    months = []
    for i, value in enumerate(values):
        agg = MonthlyAggregate(month=f"2026-{i + 1:02d}")
        getattr(agg, field).fold(value)
        months.append(agg)
    return months


def test_t104_a_falling_cop_is_a_degradation():
    months = _months([3.8, 3.7, 3.6, 3.5], field="heating_rate")
    result = trend(months, "heating_rate", higher_is_better=True)
    assert result.direction == "degrading"
    assert result.pct_per_month < 0
    assert result.months_considered == 4


def test_t104b_a_rising_cop_is_an_improvement():
    months = _months([3.2, 3.4, 3.6, 3.8], field="heating_rate")
    result = trend(months, "heating_rate", higher_is_better=True)
    assert result.direction == "improving"
    assert result.pct_per_month > 0


def test_t104c_rising_heat_loss_is_a_degradation_because_lower_is_better():
    months = _months([0.20, 0.23, 0.26, 0.29], field="heat_loss")
    result = trend(months, "heat_loss", higher_is_better=False)
    assert result.direction == "degrading"
    assert result.pct_per_month > 0  # the mean really is rising...

    # ...but a falling heat loss is the improvement, not the other way round.
    improving = _months([0.29, 0.26, 0.23, 0.20], field="heat_loss")
    result = trend(improving, "heat_loss", higher_is_better=False)
    assert result.direction == "improving"


def test_t104d_a_flat_line_reads_as_stable_not_as_noise():
    months = _months([3.50, 3.501, 3.499, 3.502], field="heating_rate")
    result = trend(months, "heating_rate", higher_is_better=True)
    assert result.direction == "stable"


# ---------------------------------------------------------------------------
# T105 - only months that actually recorded the metric count, and only a
# trailing chronological run of them
# ---------------------------------------------------------------------------


def test_t105_months_without_the_metric_are_skipped():
    months = _months([3.0, 3.2, 3.4], field="heating_rate")
    # A month with nothing recorded for heat_loss must not read as a data point.
    result = trend(months, "heat_loss", higher_is_better=False)
    assert result.direction == "insufficient_data"
    assert result.months_considered == 0


def test_t105b_all_trends_discovers_cop_buckets_from_the_data():
    months = _months([3.0, 3.2, 3.4], field="heating_rate")
    for i, agg in enumerate(months):
        agg.cop_stat("20-25").fold(3.0 + i * 0.1)

    results = all_trends(months)
    assert set(STANDARD_METRICS) <= set(results)
    assert "cop_by_bucket.20-25" in results
    assert results["cop_by_bucket.20-25"].direction == "improving"


# ---------------------------------------------------------------------------
# T106 - PoolStore folds sessions and idle observations into the right month
# ---------------------------------------------------------------------------


def _new_store():
    import ha_stubs

    store_module = ha_stubs.load_store()
    store = store_module.PoolStore.__new__(store_module.PoolStore)
    store.monthly_aggregates = {}
    return store


def test_t106_record_monthly_metric_folds_into_the_right_month():
    store = _new_store()
    store.record_monthly_metric("heating_rate", 1.1, datetime(2026, 5, 3, tzinfo=TZ))
    store.record_monthly_metric("heating_rate", 1.3, datetime(2026, 5, 20, tzinfo=TZ))
    store.record_monthly_metric("heating_rate", 0.9, datetime(2026, 6, 1, tzinfo=TZ))

    assert set(store.monthly_aggregates) == {"2026-05", "2026-06"}
    assert round(store.monthly_aggregates["2026-05"].heating_rate.mean, 6) == 1.2
    assert store.monthly_aggregates["2026-05"].heating_rate.n == 2
    assert round(store.monthly_aggregates["2026-06"].heating_rate.mean, 6) == 0.9


def test_t106b_record_monthly_cop_uses_the_air_temperature_bucket():
    store = _new_store()
    store.record_monthly_cop(26.0, 3.4, datetime(2026, 7, 1, tzinfo=TZ))
    store.record_monthly_cop(27.0, 3.6, datetime(2026, 7, 15, tzinfo=TZ))
    store.record_monthly_cop(32.0, 4.1, datetime(2026, 7, 20, tzinfo=TZ))

    month = store.monthly_aggregates["2026-07"]
    assert round(month.cop_by_bucket["25-30"].mean, 6) == 3.5
    assert month.cop_by_bucket["25-30"].n == 2
    assert round(month.cop_by_bucket["30-35"].mean, 6) == 4.1


def test_t106c_bump_monthly_session_count():
    store = _new_store()
    store.bump_monthly_session_count(datetime(2026, 8, 1, tzinfo=TZ))
    store.bump_monthly_session_count(datetime(2026, 8, 15, tzinfo=TZ))
    assert store.monthly_aggregates["2026-08"].session_count == 2


# ---------------------------------------------------------------------------
# T107 - the monthly cap is purely defensive, but it does hold
# ---------------------------------------------------------------------------


def test_t107_oldest_months_are_dropped_past_the_cap():
    import ha_stubs

    store_module = ha_stubs.load_store()
    store = store_module.PoolStore.__new__(store_module.PoolStore)
    store.monthly_aggregates = {}
    store_module.MONTHLY_AGGREGATE_MAX_MONTHS = 3

    for month in range(1, 6):
        store.record_monthly_metric(
            "heating_rate", 1.0, datetime(2026, month, 1, tzinfo=TZ)
        )

    assert len(store.monthly_aggregates) == 3
    assert set(store.monthly_aggregates) == {"2026-03", "2026-04", "2026-05"}


# ---------------------------------------------------------------------------
# T108 - roll_day extends the daily summary into the monthly aggregate
# ---------------------------------------------------------------------------


def test_t108_roll_day_folds_runtime_energy_and_cost_into_the_month():
    store = _new_store()
    store.quota_date = date(2026, 4, 30)
    store.intervals = []
    store.daily_summaries = []
    store.energy_today_kwh = 12.5
    store.cost_today = 3.75
    store.active_block = None
    store._open_interval = None
    store._closed_hours = 0.0

    rolled = store.roll_day(datetime(2026, 5, 1, tzinfo=TZ))

    assert rolled is True
    assert store.daily_summaries[-1]["date"] == "2026-04-30"
    april = store.monthly_aggregates["2026-04"]
    assert april.energy_kwh == 12.5
    assert april.cost_euro == 3.75
    assert april.runtime_hours == 0.0


def test_t108b_roll_day_accumulates_across_the_whole_month():
    store = _new_store()
    store.intervals = []
    store.daily_summaries = []
    store.active_block = None
    store._open_interval = None
    store._closed_hours = 0.0

    store.quota_date = date(2026, 4, 1)
    store.energy_today_kwh = 5.0
    store.cost_today = 1.0
    store.roll_day(datetime(2026, 4, 2, tzinfo=TZ))

    store.energy_today_kwh = 7.0
    store.cost_today = 1.5
    store.roll_day(datetime(2026, 4, 3, tzinfo=TZ))

    april = store.monthly_aggregates["2026-04"]
    assert april.energy_kwh == 12.0
    assert april.cost_euro == 2.5
    assert len(store.daily_summaries) == 2


# ---------------------------------------------------------------------------
# T109 - the load/save round trip is the actual fix for issue #11: monthly
# history must survive a restart the way the session log's cap says it cannot
# ---------------------------------------------------------------------------


def test_t109_save_and_load_preserve_monthly_aggregates():
    store = _new_store()
    store.record_monthly_metric("heating_rate", 1.2, datetime(2026, 5, 3, tzinfo=TZ))
    store.record_monthly_cop(26.0, 3.4, datetime(2026, 5, 3, tzinfo=TZ))

    dumped = {
        key: agg.as_dict() for key, agg in store.monthly_aggregates.items()
    }

    reloaded = _new_store()
    from core.aggregates import MonthlyAggregate as MA

    reloaded.monthly_aggregates = {
        key: MA.from_dict(value) for key, value in dumped.items()
    }

    assert reloaded.monthly_aggregates["2026-05"].heating_rate.mean == 1.2
    assert reloaded.monthly_aggregates["2026-05"].cop_by_bucket["25-30"].mean == 3.4
    assert reloaded.monthly_summary() == store.monthly_summary()


def test_t109b_monthly_summary_is_sorted_oldest_first():
    store = _new_store()
    store.record_monthly_metric("heating_rate", 1.0, datetime(2026, 8, 1, tzinfo=TZ))
    store.record_monthly_metric("heating_rate", 1.0, datetime(2026, 3, 1, tzinfo=TZ))
    store.record_monthly_metric("heating_rate", 1.0, datetime(2026, 5, 1, tzinfo=TZ))

    months = [row["month"] for row in store.monthly_summary()]
    assert months == ["2026-03", "2026-05", "2026-08"]


# ---------------------------------------------------------------------------
# T110 - stats() and the websocket API know about the new tier
# ---------------------------------------------------------------------------


def test_t110_stats_counts_monthly_aggregates():
    store = _new_store()
    store.session_log = []
    store.dose_log = []
    store.decision_log = []
    store.daily_summaries = []
    store.last_water_test = None

    import types

    store.near_miss_log = types.SimpleNamespace(tallies={})
    store.record_monthly_metric("heating_rate", 1.0, datetime(2026, 1, 1, tzinfo=TZ))
    store.record_monthly_metric("heating_rate", 1.0, datetime(2026, 2, 1, tzinfo=TZ))

    assert store.stats()["monthly_aggregates"] == 2
