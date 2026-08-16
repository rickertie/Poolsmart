"""Tests for the maintenance/diagnostics feature: storage stats, reprocessing,
and export/import with sections (recovery.py, PoolStore.stats/replace/rebuild_learned).

Runs the real classes against the Home Assistant stubs in ha_stubs.py, the same
pattern T84 uses for store.py -- parsing cleanly says nothing about whether the
attributes and imports actually exist at runtime.
"""

from __future__ import annotations

import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "poolsmart"))

import ha_stubs  # noqa: E402

from core import learning  # noqa: E402

from test_acceptance import TZ, make_config  # noqa: E402


def _new_store():
    store_module = ha_stubs.load_store()
    store = store_module.PoolStore.__new__(store_module.PoolStore)
    store.learned = store_module.LearnedValues()
    store.session_log = []
    store.dose_log = []
    store.decision_log = []
    store.daily_summaries = []
    store.last_water_test = None
    store.near_miss_log = types.SimpleNamespace(tallies={})
    return store


# ---------------------------------------------------------------------------
# PoolStore.stats
# ---------------------------------------------------------------------------


def test_stats_counts_each_log():
    store = _new_store()
    store.session_log = [{"a": 1}, {"a": 2}]
    store.dose_log = [{"b": 1}]
    store.decision_log = [{"c": 1}, {"c": 2}, {"c": 3}]
    store.daily_summaries = [{"d": 1}]
    store.near_miss_log = types.SimpleNamespace(tallies={"x": [1, 2.0], "y": [3, 4.0]})

    stats = store.stats()

    assert stats == {
        "sessions": 2,
        "doses": 1,
        "decisions": 3,
        "near_misses": 2,
        "daily_summaries": 1,
    }


# ---------------------------------------------------------------------------
# recovery.export_payload / validate_import
# ---------------------------------------------------------------------------


def _recovery():
    return ha_stubs.load("recovery", "recovery.py")


def test_export_payload_default_includes_everything():
    export_payload = _recovery().export_payload

    store = _new_store()
    store.learned.heating_rate_c_per_h = 0.5
    store.session_log = [{"start": "2026-08-01T09:00:00+02:00"}]
    store.dose_log = [{"amount": 100}]

    payload = export_payload(store)

    assert set(payload.keys()) >= {
        "version",
        "exported",
        "learned",
        "session_log",
        "dose_log",
        "last_water_test",
    }
    assert payload["session_log"] == [{"start": "2026-08-01T09:00:00+02:00"}]
    assert isinstance(payload["session_log"], list)


def test_export_payload_sections_narrows_output():
    export_payload = _recovery().export_payload

    store = _new_store()
    store.learned.heating_rate_c_per_h = 0.5
    store.session_log = [{"start": "x"}]
    store.dose_log = [{"amount": 100}]

    payload = export_payload(store, sections=["session_log"])

    assert "session_log" in payload
    assert "learned" not in payload
    assert "dose_log" not in payload
    assert "last_water_test" not in payload


def test_validate_import_accepts_a_partial_export():
    validate_import = _recovery().validate_import

    usable, why = validate_import(
        {"version": 1, "exported": "now", "session_log": [{"start": "x"}]}
    )
    assert usable is True, why


def test_validate_import_rejects_an_empty_payload():
    validate_import = _recovery().validate_import

    usable, why = validate_import({"version": 1, "exported": "now"})
    assert usable is False


def test_validate_import_still_checks_learned_bounds_when_present():
    validate_import = _recovery().validate_import

    usable, why = validate_import(
        {"version": 1, "learned": {"heating_rate_c_per_h": 999.0}}
    )
    assert usable is False
    assert "heating_rate_c_per_h" in why


# ---------------------------------------------------------------------------
# PoolStore.replace
# ---------------------------------------------------------------------------


def test_replace_overwrites_even_when_local_data_exists():
    store = _new_store()
    store.learned.heating_rate_c_per_h = 0.1
    store.session_log = [{"start": "local"}]

    history = {
        "version": 1,
        "learned": {"heating_rate_c_per_h": 0.9},
        "session_log": [{"start": "imported"}],
    }
    replaced = store.replace(history)

    assert store.learned.heating_rate_c_per_h == 0.9
    assert list(store.session_log) == [{"start": "imported"}]
    assert "learned" in replaced
    assert "session_log" in replaced


def test_replace_only_touches_chosen_sections():
    store = _new_store()
    store.learned.heating_rate_c_per_h = 0.1
    store.session_log = [{"start": "local"}]

    history = {
        "version": 1,
        "learned": {"heating_rate_c_per_h": 0.9},
        "session_log": [{"start": "imported"}],
    }
    replaced = store.replace(history, sections=["session_log"])

    assert store.learned.heating_rate_c_per_h == 0.1
    assert list(store.session_log) == [{"start": "imported"}]
    assert replaced == "session_log"


def test_replace_reports_nothing_when_sections_are_absent():
    store = _new_store()
    replaced = store.replace({"version": 1}, sections=["dose_log"])
    assert replaced == "nothing to replace"


# ---------------------------------------------------------------------------
# PoolStore.rebuild_learned
# ---------------------------------------------------------------------------


def test_close_open_interval_uses_synced_at_when_available():
    """A restart should lose only the unsaved tail, not the whole interval."""
    store_module = ha_stubs.load_store()
    store = store_module.PoolStore.__new__(store_module.PoolStore)
    start = datetime(2026, 8, 1, 8, 0, tzinfo=TZ)
    synced_at = datetime(2026, 8, 1, 13, 58, tzinfo=TZ)
    store.intervals = [store_module.RuntimeInterval(start=start, end=None)]

    store._close_open_interval(synced_at)

    assert store.intervals[0].end == synced_at


def test_close_open_interval_falls_back_without_synced_at():
    """An old file predating this field keeps the original conservative behaviour."""
    store_module = ha_stubs.load_store()
    store = store_module.PoolStore.__new__(store_module.PoolStore)
    start = datetime(2026, 8, 1, 8, 0, tzinfo=TZ)
    store.intervals = [store_module.RuntimeInterval(start=start, end=None)]

    store._close_open_interval(None)

    assert store.intervals[0].end == start


def test_close_open_interval_ignores_a_synced_at_before_the_interval_started():
    store_module = ha_stubs.load_store()
    store = store_module.PoolStore.__new__(store_module.PoolStore)
    start = datetime(2026, 8, 1, 8, 0, tzinfo=TZ)
    stale_synced_at = datetime(2026, 8, 1, 6, 0, tzinfo=TZ)
    store.intervals = [store_module.RuntimeInterval(start=start, end=None)]

    store._close_open_interval(stale_synced_at)

    assert store.intervals[0].end == start


def test_close_open_interval_leaves_already_closed_intervals_alone():
    store_module = ha_stubs.load_store()
    store = store_module.PoolStore.__new__(store_module.PoolStore)
    start = datetime(2026, 8, 1, 8, 0, tzinfo=TZ)
    end = datetime(2026, 8, 1, 9, 0, tzinfo=TZ)
    store.intervals = [store_module.RuntimeInterval(start=start, end=end)]

    store._close_open_interval(datetime(2026, 8, 1, 12, 0, tzinfo=TZ))

    assert store.intervals[0].end == end


def test_store_rebuild_learned_matches_the_core_function():
    config = make_config()
    start = datetime(2026, 8, 1, 9, 0, tzinfo=TZ)
    record = learning.SessionRecord(
        start=start,
        end=start + timedelta(hours=2),
        water_start=24.0,
        water_end=25.0,
        energy_kwh=3.0,
        thermal_kwh=9.0,
    )
    record.sample_air(20.0)
    measurements = learning.assess_measurements(record, config)
    payload = record.as_dict()
    payload["measurements"] = measurements.as_dict()
    payload["review"] = "auto"

    store = _new_store()
    store.session_log = [payload]

    store.rebuild_learned(config)

    expected = learning.rebuild_learned([payload], config)
    assert store.learned.heating_rate_c_per_h == expected["heating_rate_c_per_h"]
    assert store.learned.session_count == expected["session_count"]
