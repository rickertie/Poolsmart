"""Regression tests for two log-spam bugs reported against a live install:

- ``price.extract_forecast`` warned on *every* coordinator refresh (every ~30s)
  when the mapped price sensor had no recognisable forecast shape, instead of
  once -- the sensor's attribute shape does not change tick to tick, so
  thousands of identical warnings told the user nothing new.
- ``coordinator._PLAUSIBLE_RANGES["grid_power"]`` floored at 0.0, rejecting
  every reading from a signed "netto" smart-meter sensor (negative during
  solar export) as implausible -- which also silently disabled the demand
  limiter, since a rejected reading falls back to ``grid_power_w=None`` and
  :func:`core.ladder` treats that as "no demand limiter configured".
"""

from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "poolsmart"))

import ha_stubs  # noqa: E402

# The stub is missing ``as_local`` (only real HA needs it for the string-parsed
# path); adding an identity fallback -- only if it is not already there -- lets
# the "forecast recovers" case below exercise a real parsed entry too.
import homeassistant.util.dt as dt_util  # noqa: E402

if not hasattr(dt_util, "as_local"):
    dt_util.as_local = lambda value: value

import price  # noqa: E402

UTC = timezone.utc


def _state(entity_id: str, attributes: dict) -> types.SimpleNamespace:
    return types.SimpleNamespace(entity_id=entity_id, attributes=attributes)


# ---------------------------------------------------------------------------
# price.py -- "no forecast recognised" must warn once, not every refresh
# ---------------------------------------------------------------------------


def test_no_forecast_warning_is_not_repeated_on_every_refresh():
    price._warned_no_forecast.clear()
    state = _state("sensor.thuis_uurprijs_huidig", {"friendly_name": "Huidige prijs"})

    warnings = []
    price._LOGGER.warning = lambda *a, **k: warnings.append((a, k))
    try:
        for _ in range(50):
            assert price.extract_forecast(state) == ()
    finally:
        del price._LOGGER.warning

    assert len(warnings) == 1


def test_no_forecast_warning_fires_again_after_a_real_recovery():
    price._warned_no_forecast.clear()
    entity_id = "sensor.thuis_uurprijs_huidig"
    empty_state = _state(entity_id, {})
    start = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)
    populated_state = _state(
        entity_id,
        {
            "raw_today": [
                {"start": start, "price": 0.24},
                {"start": start.replace(hour=11), "price": 0.30},
            ]
        },
    )

    warnings = []
    price._LOGGER.warning = lambda *a, **k: warnings.append((a, k))
    try:
        assert price.extract_forecast(empty_state) == ()
        assert price.extract_forecast(empty_state) == ()
        assert len(warnings) == 1

        slots = price.extract_forecast(populated_state)
        assert len(slots) == 2
        assert entity_id not in price._warned_no_forecast

        assert price.extract_forecast(empty_state) == ()
        assert len(warnings) == 2
    finally:
        del price._LOGGER.warning


# ---------------------------------------------------------------------------
# coordinator.py -- grid_power's plausible range must allow net export
# ---------------------------------------------------------------------------


def test_grid_power_plausible_range_allows_negative_net_export():
    """Regression: sensor.grid_netto_p1 reporting -1755 W (solar export) was
    logged as "implausible" on every tick and silently disabled the demand
    limiter, because a signed net-meter reading can go well below zero.
    """
    source = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "poolsmart"
        / "coordinator.py"
    ).read_text(encoding="utf-8")

    assert '"grid_power": (-50000.0, 50000.0)' in source
