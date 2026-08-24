"""Tests for the 1.11.0 batch: the notify action-buttons fix (#19), the swim
time dashboard tile (#17), the weather_entity air-temp fallback (#16), the
demand/power limiter (#13), and the AI feedback loop (#10).
"""

from __future__ import annotations

import asyncio
import sys
import types
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "poolsmart"))

import ha_stubs  # noqa: E402

from core import ladder  # noqa: E402
from core.config import EnergySettings  # noqa: E402
from core.models import Branch, SensorReading  # noqa: E402

from test_acceptance import TZ, make_config, make_state, run_tick  # noqa: E402

UTC = timezone.utc


# ---------------------------------------------------------------------------
# Issue #19 -- notify.send_message must forward data.actions/tag
# ---------------------------------------------------------------------------


class _FakeServices:
    def __init__(self):
        self.calls = []

    def has_service(self, domain, service):
        return False

    async def async_call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data))


class _FakeHass:
    def __init__(self, entity_state):
        self.services = _FakeServices()
        self.states = types.SimpleNamespace(get=lambda entity_id: entity_state)

    def async_create_task(self, coro):
        asyncio.run(coro)


def test_send_message_path_forwards_action_buttons():
    notify_module = ha_stubs.load("notify", "notify.py")
    hass = _FakeHass(entity_state=object())
    manager = notify_module.NotificationManager(hass=hass, coordinator=None)
    payload = {
        "title": "Heating postponed",
        "message": "Waiting for a cheaper slot.",
        "data": {
            "actions": [{"action": "POOLSMART_BOOST", "title": "Heat now"}],
            "tag": "poolsmart_heating_postponed",
        },
    }

    manager._send_one("notify.mobile_app_phone", payload, "heating_postponed")

    assert len(hass.services.calls) == 1
    domain, service, data = hass.services.calls[0]
    assert domain == "notify"
    assert service == "send_message"
    assert data["entity_id"] == "notify.mobile_app_phone"
    assert data["data"] == payload["data"]


def test_send_message_path_omits_data_key_when_there_are_no_actions():
    notify_module = ha_stubs.load("notify", "notify.py")
    hass = _FakeHass(entity_state=object())
    manager = notify_module.NotificationManager(hass=hass, coordinator=None)
    payload = {"title": "Target reached", "message": "Pool is at temperature."}

    manager._send_one("notify.mobile_app_phone", payload, "heating_started")

    assert len(hass.services.calls) == 1
    _domain, _service, data = hass.services.calls[0]
    assert "data" not in data


# ---------------------------------------------------------------------------
# Issue #17 -- swim time as a dashboard tile
# ---------------------------------------------------------------------------


def _fake_coordinator(mod, options, entity_states):
    """A duck-typed stand-in exposing just what _next_swim_deadline and the
    real (unstubbed) _conf/_read_binary it calls actually touch -- avoids
    constructing the full PoolSmartCoordinator, which needs a live hass/entry
    well beyond this method's scope."""

    class _Fake:
        pass

    fake = _Fake()
    fake.entry = types.SimpleNamespace(options=options, data={})
    fake.hass = types.SimpleNamespace(
        states=types.SimpleNamespace(get=lambda eid: entity_states.get(eid))
    )
    fake._conf = lambda key, default=None: mod.PoolSmartCoordinator._conf(
        fake, key, default
    )
    fake._read_binary = lambda key: mod.PoolSmartCoordinator._read_binary(fake, key)
    return fake


def test_swim_time_entity_replaces_the_static_fields_when_set():
    mod = ha_stubs.load("coordinator", "coordinator.py")
    const = ha_stubs.load("const", "const.py")
    now = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)  # a Monday, before both times
    fake = _fake_coordinator(
        mod,
        options={
            const.CONF_SWIM_TIME: "10:00",
            const.CONF_SWIM_TIME_ENTITY: "input_datetime.poolsmart_swim_time",
        },
        entity_states={
            "input_datetime.poolsmart_swim_time": types.SimpleNamespace(
                state="18:30:00"
            )
        },
    )

    deadline = mod.PoolSmartCoordinator._next_swim_deadline(fake, now)

    assert deadline.date() == now.date()
    assert deadline.time() == time(18, 30)


def test_swim_time_falls_back_to_static_when_entity_unset():
    mod = ha_stubs.load("coordinator", "coordinator.py")
    const = ha_stubs.load("const", "const.py")
    now = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)
    fake = _fake_coordinator(
        mod, options={const.CONF_SWIM_TIME: "17:00"}, entity_states={}
    )

    deadline = mod.PoolSmartCoordinator._next_swim_deadline(fake, now)

    assert deadline.time() == time(17, 0)


def test_swim_time_falls_back_to_static_when_entity_is_unavailable():
    mod = ha_stubs.load("coordinator", "coordinator.py")
    const = ha_stubs.load("const", "const.py")
    now = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)
    fake = _fake_coordinator(
        mod,
        options={
            const.CONF_SWIM_TIME: "17:00",
            const.CONF_SWIM_TIME_ENTITY: "input_datetime.poolsmart_swim_time",
        },
        entity_states={
            "input_datetime.poolsmart_swim_time": types.SimpleNamespace(
                state="unavailable"
            )
        },
    )

    deadline = mod.PoolSmartCoordinator._next_swim_deadline(fake, now)

    assert deadline.time() == time(17, 0)


def test_swim_skip_entity_excludes_today_even_before_the_time_has_passed():
    mod = ha_stubs.load("coordinator", "coordinator.py")
    const = ha_stubs.load("const", "const.py")
    now = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)  # Monday, 20:00 has not passed
    fake = _fake_coordinator(
        mod,
        options={
            const.CONF_SWIM_TIME: "20:00",
            const.CONF_SWIM_SKIP_ENTITY: "input_boolean.poolsmart_skip_swim_today",
        },
        entity_states={
            "input_boolean.poolsmart_skip_swim_today": types.SimpleNamespace(
                state="on"
            )
        },
    )

    deadline = mod.PoolSmartCoordinator._next_swim_deadline(fake, now)

    assert deadline.date() > now.date()
    assert deadline.time() == time(20, 0)


def test_swim_time_entity_with_a_date_is_a_one_off_appointment():
    """A helper with both date and time set -- "swim next Wednesday at
    14:00" -- must win outright, including on a day not in swim_days,
    rather than being read as a recurring time of day."""
    mod = ha_stubs.load("coordinator", "coordinator.py")
    const = ha_stubs.load("const", "const.py")
    now = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)  # Monday
    fake = _fake_coordinator(
        mod,
        options={
            const.CONF_SWIM_TIME: "10:00",
            const.CONF_SWIM_TIME_ENTITY: "input_datetime.poolsmart_swim_time",
            # Only Monday is a normal swim day; Wednesday is not.
            const.CONF_SWIM_DAYS: [0],
        },
        entity_states={
            "input_datetime.poolsmart_swim_time": types.SimpleNamespace(
                state="2026-06-03 14:00:00"
            )
        },
    )

    deadline = mod.PoolSmartCoordinator._next_swim_deadline(fake, now)

    assert deadline == datetime(2026, 6, 3, 14, 0, tzinfo=UTC)


def test_swim_time_entity_with_a_past_date_falls_back_like_an_unset_helper():
    """A one-off appointment that has already passed must not linger --
    it falls through to the static fields exactly as an empty helper would,
    without needing to be cleared by hand."""
    mod = ha_stubs.load("coordinator", "coordinator.py")
    const = ha_stubs.load("const", "const.py")
    now = datetime(2026, 6, 4, 8, 0, tzinfo=UTC)  # after last Wednesday's 14:00
    fake = _fake_coordinator(
        mod,
        options={
            const.CONF_SWIM_TIME: "10:00",
            const.CONF_SWIM_TIME_ENTITY: "input_datetime.poolsmart_swim_time",
        },
        entity_states={
            "input_datetime.poolsmart_swim_time": types.SimpleNamespace(
                state="2026-06-03 14:00:00"
            )
        },
    )

    deadline = mod.PoolSmartCoordinator._next_swim_deadline(fake, now)

    assert deadline.time() == time(10, 0)


def test_swim_skip_entity_cancels_a_one_off_appointment_set_for_today():
    mod = ha_stubs.load("coordinator", "coordinator.py")
    const = ha_stubs.load("const", "const.py")
    now = datetime(2026, 6, 3, 8, 0, tzinfo=UTC)  # Wednesday, before 14:00
    fake = _fake_coordinator(
        mod,
        options={
            const.CONF_SWIM_TIME: "10:00",
            const.CONF_SWIM_TIME_ENTITY: "input_datetime.poolsmart_swim_time",
            const.CONF_SWIM_SKIP_ENTITY: "input_boolean.poolsmart_skip_swim_today",
        },
        entity_states={
            "input_datetime.poolsmart_swim_time": types.SimpleNamespace(
                state="2026-06-03 14:00:00"
            ),
            "input_boolean.poolsmart_skip_swim_today": types.SimpleNamespace(
                state="on"
            ),
        },
    )

    deadline = mod.PoolSmartCoordinator._next_swim_deadline(fake, now)

    # Falls back to the static field on a later day, not today's appointment.
    assert deadline.date() > now.date()
    assert deadline.time() == time(10, 0)


# ---------------------------------------------------------------------------
# Issue #16 -- weather_entity as an outdoor-temperature fallback
# ---------------------------------------------------------------------------


def test_weather_current_temp_reads_the_entitys_own_temperature_attribute():
    mod = ha_stubs.load("coordinator", "coordinator.py")
    const = ha_stubs.load("const", "const.py")
    fake = _fake_coordinator(
        mod,
        options={const.CONF_WEATHER_ENTITY: "weather.home"},
        entity_states={
            "weather.home": types.SimpleNamespace(
                state="cloudy", attributes={"temperature": 12.5}
            )
        },
    )

    assert mod.PoolSmartCoordinator._weather_current_temp(fake) == 12.5


def test_weather_current_temp_is_none_without_a_mapped_entity():
    mod = ha_stubs.load("coordinator", "coordinator.py")
    fake = _fake_coordinator(mod, options={}, entity_states={})

    assert mod.PoolSmartCoordinator._weather_current_temp(fake) is None


def test_weather_current_temp_is_none_when_the_entity_is_unavailable():
    mod = ha_stubs.load("coordinator", "coordinator.py")
    const = ha_stubs.load("const", "const.py")
    fake = _fake_coordinator(
        mod,
        options={const.CONF_WEATHER_ENTITY: "weather.home"},
        entity_states={
            "weather.home": types.SimpleNamespace(state="unavailable", attributes={})
        },
    )

    assert mod.PoolSmartCoordinator._weather_current_temp(fake) is None


# ---------------------------------------------------------------------------
# Issue #13 -- demand/power limiter
# ---------------------------------------------------------------------------


def test_demand_allows_heating_without_a_configured_limit():
    config = make_config()  # power_limit_w defaults to None -- absent
    now = datetime(2026, 6, 1, 12, 0, tzinfo=TZ)
    state = make_state(now, grid_power_w=999999.0)

    allowed, _why = ladder._demand_allows_heating(state, config)

    assert allowed is True


def test_demand_allows_heating_without_a_grid_power_reading():
    config = make_config(energy=EnergySettings(max_price=0.25, power_limit_w=5000.0))
    now = datetime(2026, 6, 1, 12, 0, tzinfo=TZ)
    state = make_state(now, grid_power_w=None)

    allowed, _why = ladder._demand_allows_heating(state, config)

    assert allowed is True


def test_demand_blocks_when_starting_the_heat_pump_would_exceed_the_cap():
    config = make_config(energy=EnergySettings(max_price=0.25, power_limit_w=5000.0))
    now = datetime(2026, 6, 1, 12, 0, tzinfo=TZ)
    # 4500 W already, plus the ~680 W the heat pump + pump would add.
    state = make_state(now, grid_power_w=4500.0, heat_pump_on=False, pump_on=False)

    allowed, why = ladder._demand_allows_heating(state, config)

    assert allowed is False
    assert "5000" in why


def test_demand_allows_heating_with_headroom():
    config = make_config(energy=EnergySettings(max_price=0.25, power_limit_w=5000.0))
    now = datetime(2026, 6, 1, 12, 0, tzinfo=TZ)
    state = make_state(now, grid_power_w=4000.0, heat_pump_on=False, pump_on=False)

    allowed, _why = ladder._demand_allows_heating(state, config)

    assert allowed is True


def test_demand_pauses_an_already_running_session_over_the_cap():
    """Once running, the meter's own figure is used as-is (no equipment draw
    added again), which is what lets the rest of the house pushing the total
    over the cap pause an already-active session."""
    config = make_config(energy=EnergySettings(max_price=0.25, power_limit_w=5000.0))
    now = datetime(2026, 6, 1, 12, 0, tzinfo=TZ)
    state = make_state(now, grid_power_w=5200.0, heat_pump_on=True, pump_on=True)

    allowed, _why = ladder._demand_allows_heating(state, config)

    assert allowed is False


def test_heating_branch_is_blocked_by_the_demand_limiter_despite_a_cheap_price():
    """The ladder must not fall back to Heating (or Free Power) when the
    demand gate fails, even though price alone would otherwise say yes."""
    config = make_config(energy=EnergySettings(max_price=0.25, power_limit_w=1000.0))
    now = datetime(2026, 6, 1, 12, 0, tzinfo=TZ)
    state = make_state(
        now,
        water_temp=SensorReading(25.0, 10, "water"),
        air_temp=SensorReading(20.0, 10, "air"),
        target_temp=28.0,
        price_total=0.05,  # well under the price limit
        grid_power_w=990.0,  # + ~680 W equipment draw blows the 1000 W cap
        heat_pump_on=False,
        pump_on=False,
    )

    decision = run_tick(state, config, done_h=0.0)

    assert decision.branch is not Branch.HEATING
    assert decision.branch is not Branch.FREE_POWER
    assert decision.heat_pump is False


# ---------------------------------------------------------------------------
# Issue #10 -- AI feedback loop
# ---------------------------------------------------------------------------


class _FakeAdvisorConfigEntries:
    def async_update_entry(self, entry, options):
        entry.options = options


class _FakeAdvisorHass:
    def __init__(self):
        self.config_entries = _FakeAdvisorConfigEntries()


class _FakeAdvisorStore:
    def __init__(self):
        self.session_log = []
        self.accepted_suggestions = []
        self.cost_today = 1.23
        self.energy_today_kwh = 4.56
        self.saved = 0

    def log_accepted_suggestion(self, payload):
        self.accepted_suggestions.append(payload)

    async def async_save(self, force: bool = False):
        self.saved += 1


def _fake_advisor_coordinator():
    store = _FakeAdvisorStore()
    return types.SimpleNamespace(store=store, entry=types.SimpleNamespace(options={}))


def _load_advisor():
    ha_stubs.load("const", "const.py")
    ha_stubs.load("core", "core/__init__.py")
    ha_stubs.load("core.safety", "core/safety.py")
    ha_stubs.load("ai", "ai/__init__.py")
    return ha_stubs.load("ai.advisor", "ai/advisor.py")


def test_accepting_a_suggestion_persists_a_before_snapshot():
    ai_advisor = _load_advisor()
    hass = _FakeAdvisorHass()
    coordinator = _fake_advisor_coordinator()
    advisor = ai_advisor.Advisor(hass, coordinator)
    advisor.last_result = ai_advisor.AdvisorResult(
        suggestions=[
            ai_advisor.Suggestion(
                setting="max_price", value=0.3, why="test", created=datetime.now(UTC)
            )
        ]
    )

    accepted = asyncio.run(advisor.async_accept(0))

    assert accepted is True
    assert coordinator.entry.options["max_price"] == 0.3
    assert len(coordinator.store.accepted_suggestions) == 1
    record = coordinator.store.accepted_suggestions[0]
    assert record["setting"] == "max_price"
    assert record["new_value"] == 0.3
    assert record["before"]["cost_today"] == 1.23
    assert record["outcome"] is None
    assert coordinator.store.saved == 1
    # The suggestion is consumed once acted on.
    assert advisor.last_result.suggestions == []


def test_check_outcomes_fills_in_the_outcome_once_the_window_has_passed():
    ai_advisor = _load_advisor()
    hass = _FakeAdvisorHass()
    coordinator = _fake_advisor_coordinator()
    advisor = ai_advisor.Advisor(hass, coordinator)

    old_accepted_at = datetime.now(UTC) - timedelta(
        days=ai_advisor.OUTCOME_WINDOW_DAYS + 1
    )
    coordinator.store.accepted_suggestions.append(
        {
            "id": old_accepted_at.isoformat(),
            "setting": "max_price",
            "old_value": 0.25,
            "new_value": 0.30,
            "why": "test",
            "accepted_at": old_accepted_at.isoformat(),
            "before": {"average_cop": 3.5},
            "outcome": None,
            "outcome_at": None,
        }
    )
    recent_session_start = datetime.now(UTC) - timedelta(days=1)
    coordinator.store.session_log.append(
        {"start": recent_session_start.isoformat(), "measured_cop": 3.0}
    )

    asyncio.run(advisor.async_check_outcomes())

    entry = coordinator.store.accepted_suggestions[0]
    assert entry["outcome"] is not None
    assert "COP" in entry["outcome"]
    assert entry["outcome_at"] is not None
    assert coordinator.store.saved == 1


def test_check_outcomes_skips_entries_still_inside_the_window():
    ai_advisor = _load_advisor()
    hass = _FakeAdvisorHass()
    coordinator = _fake_advisor_coordinator()
    advisor = ai_advisor.Advisor(hass, coordinator)

    recent_accepted_at = datetime.now(UTC) - timedelta(days=1)
    coordinator.store.accepted_suggestions.append(
        {
            "id": recent_accepted_at.isoformat(),
            "setting": "max_price",
            "old_value": 0.25,
            "new_value": 0.30,
            "why": "test",
            "accepted_at": recent_accepted_at.isoformat(),
            "before": {},
            "outcome": None,
            "outcome_at": None,
        }
    )

    asyncio.run(advisor.async_check_outcomes())

    assert coordinator.store.accepted_suggestions[0]["outcome"] is None
    assert coordinator.store.saved == 0


def test_recent_outcomes_only_returns_resolved_entries_within_the_window():
    ai_advisor = _load_advisor()
    hass = _FakeAdvisorHass()
    coordinator = _fake_advisor_coordinator()
    advisor = ai_advisor.Advisor(hass, coordinator)

    now = datetime.now(UTC)
    coordinator.store.accepted_suggestions.extend(
        [
            {
                "setting": "max_price",
                "new_value": 0.3,
                "outcome": "COP improved from 3.50 to 3.80.",
                "outcome_at": (now - timedelta(days=2)).isoformat(),
            },
            {
                "setting": "solar_threshold_w",
                "new_value": 1000,
                "outcome": None,
                "outcome_at": None,
            },
            {
                "setting": "temp_hysteresis",
                "new_value": 0.5,
                "outcome": "COP essentially unchanged (was 3.50, now 3.52).",
                "outcome_at": (now - timedelta(days=30)).isoformat(),
            },
        ]
    )

    outcomes = advisor._recent_outcomes(within_days=14)

    assert len(outcomes) == 1
    assert outcomes[0]["setting"] == "max_price"
