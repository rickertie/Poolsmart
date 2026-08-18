"""Tests for the 1.10.0 batch: storage-load atomicity (#20, #18), the
dose-log learning loop (#9), and rain/weather awareness (#7).

Runs the real classes against the Home Assistant stubs in ha_stubs.py, the
same pattern test_maintenance.py and test_v12.py use for store.py.
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "poolsmart"))

import ha_stubs  # noqa: E402

from core import learning  # noqa: E402


# ---------------------------------------------------------------------------
# Issues #20 / #18 -- PoolStore.async_load must not let one bad field wipe
# unrelated state.
# ---------------------------------------------------------------------------


def _new_store():
    """A PoolStore with the same defaults __init__ would give it, without
    needing a real Home Assistant `hass` to construct one."""
    store_module = ha_stubs.load_store()
    store = store_module.PoolStore.__new__(store_module.PoolStore)
    store.quota_date = None
    store.intervals = []
    store._open_interval = None
    store._closed_hours = 0.0
    store.learned = store_module.LearnedValues()
    store.active_block = None
    store.active_session = None
    store.heat_pump_stopped_at = None
    store.heat_pump_started_at = None
    store.chemistry_until = None
    store.mode = None
    store.target_temp = None
    store.decision_log = []
    store.session_log = []
    store.dose_log = []
    store.last_water_test = None
    store.energy_today_kwh = 0.0
    store.cost_today = 0.0
    store.cost_baseline_today = 0.0
    store.near_miss_log = store_module.NearMissLog()
    store.daily_summaries = []
    store.monthly_aggregates = {}
    return store, store_module


class _FakeInnerStore:
    """Stands in for homeassistant.helpers.storage.Store."""

    def __init__(self, payload: dict):
        self._payload = payload

    async def async_load(self):
        return self._payload


def test_corrupt_heat_pump_timestamp_only_resets_that_group():
    """A malformed heat_pump_stopped_at must not wipe learned/session/dose
    data that parsed fine -- the exact #20/#18 symptom (12 sessions learned,
    Sessions/Doses showing 0, mode/target_temp reset)."""
    store, _ = _new_store()
    payload = {
        "data_version": 1,
        "learned": {
            "heating_rate_c_per_h": 1.2,
            "heating_rate_sessions": 12,
        },
        "heat_pump_stopped_at": "not-a-real-timestamp",
        "mode": "auto",
        "target_temp": 28.5,
        "session_log": [{"a": 1}, {"a": 2}],
        "dose_log": [{"b": 1}],
        "decision_log": [{"c": 1}],
    }
    store._store = _FakeInnerStore(payload)

    asyncio.run(store.async_load())

    # The corrupt timestamp group reset to its own default...
    assert store.heat_pump_stopped_at is None
    # ...but everything independently parseable survived, instead of also
    # being silently reset by the same swallowed exception.
    assert store.learned.heating_rate_sessions == 12
    assert len(store.session_log) == 2
    assert len(store.dose_log) == 1
    assert len(store.decision_log) == 1
    assert store.mode == "auto"
    assert store.target_temp == 28.5


def test_clean_payload_loads_every_group():
    store, _ = _new_store()
    payload = {
        "data_version": 1,
        "learned": {"heating_rate_sessions": 5},
        "session_log": [{"a": 1}],
        "dose_log": [{"b": 1}],
        "mode": "eco",
        "target_temp": 27.0,
    }
    store._store = _FakeInnerStore(payload)

    asyncio.run(store.async_load())

    assert store.learned.heating_rate_sessions == 5
    assert len(store.session_log) == 1
    assert len(store.dose_log) == 1
    assert store.mode == "eco"
    assert store.target_temp == 27.0


def test_corrupt_monthly_aggregates_do_not_touch_logs_or_learned():
    store, _ = _new_store()
    payload = {
        "data_version": 1,
        "learned": {"heating_rate_sessions": 3},
        "session_log": [{"a": 1}],
        "dose_log": [{"b": 1}],
        "monthly_aggregates": "not-a-dict-of-aggregates",
    }
    store._store = _FakeInnerStore(payload)

    asyncio.run(store.async_load())

    assert store.monthly_aggregates == {}
    assert store.learned.heating_rate_sessions == 3
    assert len(store.session_log) == 1
    assert len(store.dose_log) == 1
