"""Tests for manual session review and rebuilding the learned values from it.

Mirrors what coordinator._finish_session actually logs, so these tests double
as a check that rebuild_learned's expectations of the payload shape match
what production code emits.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "poolsmart"))

from core import learning  # noqa: E402

from test_acceptance import TZ, make_config  # noqa: E402


def make_payload(
    start: datetime,
    *,
    hours: float = 2.0,
    water_start: float = 24.0,
    water_end: float = 25.0,
    air: float = 20.0,
    energy_kwh: float = 3.0,
    thermal_kwh: float = 9.0,
    interrupted: bool = False,
    faults: list[str] | None = None,
    review: str = "auto",
) -> dict:
    """Build a session_log entry the way _finish_session would."""
    config = make_config()
    record = learning.SessionRecord(
        start=start,
        end=start + timedelta(hours=hours),
        water_start=water_start,
        water_end=water_end,
        energy_kwh=energy_kwh,
        thermal_kwh=thermal_kwh,
        interrupted=interrupted,
        faults=list(faults or ()),
    )
    record.sample_air(air)
    measurements = learning.assess_measurements(record, config)
    payload = record.as_dict()
    payload["usable"] = measurements.anything_usable
    payload["measurements"] = measurements.as_dict()
    payload["needs_review"] = learning.needs_review(record, measurements)
    payload["review"] = review
    return payload


# ---------------------------------------------------------------------------
# rebuild_learned
# ---------------------------------------------------------------------------


def test_rebuild_matches_two_clean_sessions():
    config = make_config()
    start = datetime(2026, 8, 1, 9, 0, tzinfo=TZ)
    log = [
        make_payload(start, air=20.0),
        make_payload(start + timedelta(days=1), air=20.0),
    ]
    for entry in log:
        assert entry["usable"] is True, entry["measurements"]

    result = learning.rebuild_learned(log, config)

    assert result["session_count"] == 2
    assert result["heating_rate_sessions"] == 2
    assert result["heating_rate_c_per_h"] is not None
    assert result["cop_by_air_bucket"]


def test_excluded_session_is_dropped():
    config = make_config()
    start = datetime(2026, 8, 1, 9, 0, tzinfo=TZ)
    included = make_payload(start, air=20.0)
    excluded = make_payload(start + timedelta(days=1), air=20.0, review="excluded")
    log = [included, excluded]

    result = learning.rebuild_learned(log, config)

    assert result["session_count"] == 1
    assert result["heating_rate_sessions"] == 1
    # With only one session counted, the capped update has nothing to cap
    # against and lands exactly on that session's own rate.
    assert result["heating_rate_c_per_h"] == round(
        (included["water_end"] - included["water_start"]) / included["duration_h"], 4
    )


def test_manual_include_rescues_an_interrupted_session():
    config = make_config()
    start = datetime(2026, 8, 1, 9, 0, tzinfo=TZ)

    rejected = make_payload(start, air=20.0, interrupted=True)
    assert rejected["usable"] is False
    assert rejected["measurements"]["heating_rate"] is False

    # Left on "auto", it teaches nothing.
    auto_result = learning.rebuild_learned([rejected], config)
    assert auto_result["session_count"] == 0
    assert auto_result["heating_rate_c_per_h"] is None

    # Manually included, the raw measurement it still carries is used.
    rejected["review"] = "included"
    included_result = learning.rebuild_learned([rejected], config)
    assert included_result["session_count"] == 1
    assert included_result["heating_rate_sessions"] == 1
    assert included_result["heating_rate_c_per_h"] is not None


def test_manual_exclude_beats_a_clean_verdict():
    config = make_config()
    start = datetime(2026, 8, 1, 9, 0, tzinfo=TZ)
    clean = make_payload(start, air=20.0)
    assert clean["usable"] is True

    clean["review"] = "excluded"
    result = learning.rebuild_learned([clean], config)

    assert result["session_count"] == 0
    assert result["heating_rate_c_per_h"] is None


def test_rebuild_ignores_a_missing_review_field():
    """Logs written before this feature existed have no "review" key at all."""
    config = make_config()
    start = datetime(2026, 8, 1, 9, 0, tzinfo=TZ)
    entry = make_payload(start, air=20.0)
    del entry["review"]

    result = learning.rebuild_learned([entry], config)

    assert result["session_count"] == 1


# ---------------------------------------------------------------------------
# needs_review
# ---------------------------------------------------------------------------


def test_needs_review_flags_a_long_rejected_session():
    config = make_config()
    start = datetime(2026, 8, 1, 9, 0, tzinfo=TZ)
    record = learning.SessionRecord(
        start=start,
        end=start + timedelta(hours=2),
        water_start=24.0,
        water_end=26.0,
        interrupted=True,
    )
    measurements = learning.assess_measurements(record, config)
    assert learning.needs_review(record, measurements) is True


def test_needs_review_leaves_a_short_rejected_session_alone():
    config = make_config()
    start = datetime(2026, 8, 1, 9, 0, tzinfo=TZ)
    record = learning.SessionRecord(
        start=start,
        end=start + timedelta(minutes=2),
        water_start=24.0,
        water_end=24.1,
    )
    measurements = learning.assess_measurements(record, config)
    assert measurements.anything_usable is False
    assert learning.needs_review(record, measurements) is False


def test_needs_review_flags_a_usable_session_with_a_fault():
    config = make_config()
    start = datetime(2026, 8, 1, 9, 0, tzinfo=TZ)
    record = learning.SessionRecord(
        start=start,
        end=start + timedelta(hours=2),
        water_start=24.0,
        water_end=25.0,
        faults=["unrelated_fault_code"],
    )
    measurements = learning.assess_measurements(record, config)
    assert measurements.anything_usable is True
    assert learning.needs_review(record, measurements) is True


def test_needs_review_leaves_a_clean_session_alone():
    config = make_config()
    start = datetime(2026, 8, 1, 9, 0, tzinfo=TZ)
    record = learning.SessionRecord(
        start=start,
        end=start + timedelta(hours=2),
        water_start=24.0,
        water_end=25.0,
    )
    measurements = learning.assess_measurements(record, config)
    assert learning.needs_review(record, measurements) is False
