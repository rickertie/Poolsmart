"""Acceptance tests T1 - T12 from HANDOFF.md.

T1 and T2 are regression tests for the two bugs that caused the rebuild:
the pump sitting idle before the filtration window closed, and the pump
oscillating on and off once the daily quota had been met.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "poolsmart"))

from core import filtration as filt  # noqa: E402
from core import heating, ladder, safety  # noqa: E402
from core.config import (  # noqa: E402
    ComfortSettings,
    EnergySettings,
    FiltrationSettings,
    HeatPumpSpec,
    PoolConfig,
    PoolSpec,
    PumpSpec,
)
from core.models import (  # noqa: E402
    Branch,
    Decision,
    Mode,
    PoolState,
    SensorReading,
    Severity,
)

TZ = timezone(timedelta(hours=2))


def make_config(**overrides) -> PoolConfig:
    """Rick's installation, used as a realistic fixture."""
    base = {
        "pool": PoolSpec(volume_l=3834, surface_m2=6.0, depth_m=0.66),
        "pump": PumpSpec(flow_m3h=3.596, flow_is_measured=True, power_kw=0.10),
        "heat_pump": HeatPumpSpec(
            input_kw=0.58,
            thermal_kw=3.0,
            cop_ref=5.17,
            cop_ref_temp=26.0,
            cop_low=4.18,
            cop_low_temp=15.0,
            air_temp_min=11.0,
            air_temp_max=43.0,
            flow_min_m3h=2.0,
        ),
        "filtration": FiltrationSettings(turnover_factor=3.0),
        "comfort": ComfortSettings(),
        "energy": EnergySettings(max_price=0.25),
    }
    base.update(overrides)
    return PoolConfig(**base)


def make_state(now: datetime, **overrides) -> PoolState:
    defaults = {
        "now": now,
        "mode": Mode.AUTO,
        "water_temp": SensorReading(27.0, 10, "water"),
        "air_temp": SensorReading(20.0, 10, "air"),
        "hp_inlet": SensorReading(27.0, 10, "hp_inlet"),
        "hp_outlet": SensorReading(30.0, 10, "hp_outlet"),
        "flow_m3h": SensorReading(3.5, 10, "flow"),
        "pump_power_w": SensorReading(100.0, 10, "pump_power"),
        "hp_power_w": SensorReading(0.0, 10, "hp_power"),
        "pump_on": False,
        "heat_pump_on": False,
        "target_temp": 28.0,
        "price_total": 0.30,
        "price_energy": 0.08,
    }
    defaults.update(overrides)
    return PoolState(**defaults)


def run_tick(state: PoolState, config: PoolConfig, done_h: float, previous=None,
             active_block=None) -> Decision:
    faults = safety.evaluate(state, config)
    status = filt.evaluate(
        state.now,
        config,
        done_h,
        active_block=active_block,
        water_temp=state.water_temp.value if state.water_temp.available else None,
    )
    available, reason = safety.heat_pump_available(state, config, faults)
    return ladder.decide(state, config, status, faults, available, reason, previous)


# ---------------------------------------------------------------------------
# T1 - the pump must circulate when the quota would otherwise go unmet
# ---------------------------------------------------------------------------

def test_t1_deadline_forces_circulation():
    config = make_config()
    required = config.daily_filtration_hours(28.0)
    now = datetime(2026, 7, 30, 20, 0, tzinfo=TZ)
    # 45 minutes still owed, last window closes at 21:00, price is high.
    state = make_state(now, price_total=0.45, water_temp=SensorReading(28.5, 10, "water"))
    decision = run_tick(state, config, done_h=required - 0.75)

    assert decision.pump is True, decision.reason
    assert decision.branch is Branch.FILTRATION_DEADLINE
    assert "Price is ignored" in decision.reason


# ---------------------------------------------------------------------------
# T2 - no oscillation once the quota has been met
# ---------------------------------------------------------------------------

def test_t2_no_oscillation_after_quota_met():
    config = make_config()
    required = config.daily_filtration_hours(28.0)
    now = datetime(2026, 7, 30, 14, 0, tzinfo=TZ)

    # Start from a decision that had the pump running, as if a block just ended.
    previous = Decision(
        pump=True,
        heat_pump=False,
        branch=Branch.FILTRATION_BLOCK,
        reason="block running",
        detail={"mode_at_decision": Mode.AUTO.value},
        hold_until=now,
    )

    switches = 0
    decisions = []
    for minute in range(0, 6 * 60, 1):  # 14:00 to 20:00, one tick per minute
        tick = now + timedelta(minutes=minute)
        state = make_state(tick, water_temp=SensorReading(28.4, 10, "water"), pump_on=previous.pump)
        decision = run_tick(state, config, done_h=required, previous=previous)
        if not decision.same_outputs(previous):
            switches += 1
        decisions.append(decision)
        previous = decision

    # Exactly one transition: the pump turning off when the quota was complete.
    assert switches == 1, f"expected a single switch, got {switches}"
    assert all(d.pump is False for d in decisions[1:]), "pump came back on"
    assert decisions[-1].branch is Branch.IDLE
    assert "filtration is complete" in decisions[-1].reason


# ---------------------------------------------------------------------------
# T3 - a restart mid-block preserves the quota and finishes the block
# ---------------------------------------------------------------------------

def test_t3_restart_midblock_preserves_quota():
    config = make_config()
    now = datetime(2026, 7, 30, 13, 30, tzinfo=TZ)
    block = filt.BlockPlan(
        index=1,
        start=now - timedelta(minutes=20),
        end=now + timedelta(minutes=22),
        rationale="restored after restart",
    )
    state = make_state(now, water_temp=SensorReading(28.4, 10, "water"))
    decision = run_tick(state, config, done_h=0.33, previous=None, active_block=block)

    assert decision.pump is True
    assert decision.branch is Branch.FILTRATION_BLOCK
    assert decision.hold_until == block.end, "the block must hold until its own end"


# ---------------------------------------------------------------------------
# T4 - below the operating envelope nothing heats, not even for free power
# ---------------------------------------------------------------------------

def test_t4_cold_air_blocks_heating_even_with_negative_price():
    config = make_config()
    now = datetime(2026, 7, 30, 13, 0, tzinfo=TZ)
    state = make_state(
        now,
        air_temp=SensorReading(9.0, 10, "air"),
        water_temp=SensorReading(20.0, 10, "water"),
        price_total=-0.05,
        price_energy=-0.12,
    )
    faults = safety.evaluate(state, config)
    available, reason = safety.heat_pump_available(state, config, faults)

    assert available is False
    assert "below the heat pump minimum" in reason

    decision = run_tick(state, config, done_h=0.0)
    assert decision.heat_pump is False, decision.reason


# ---------------------------------------------------------------------------
# T5 - flow below the datasheet minimum warns, and only stops if asked to
# ---------------------------------------------------------------------------

def test_t5_low_flow_warns_by_default():
    """Datasheet minima are conservative and the appliance protects itself.

    Plenty of installations run below the quoted figure without trouble, and the
    heat pump has its own flow switch as a hardware backstop. Overriding the
    owner's judgement on the strength of a brochure number is the wrong default,
    so this reports and carries on.
    """
    config = make_config()
    now = datetime(2026, 7, 30, 13, 0, tzinfo=TZ)
    state = make_state(
        now,
        flow_m3h=SensorReading(1.0, 10, "flow"),
        pump_on=True,
        heat_pump_on=True,
        water_temp=SensorReading(24.0, 10, "water"),
        price_total=0.10,
    )
    faults = safety.evaluate(state, config)
    flow_fault = next(f for f in faults if f.code == "flow_below_heat_pump_minimum")
    assert flow_fault.severity is Severity.WARNING

    decision = run_tick(state, config, done_h=0.0)
    assert decision.heat_pump is True, decision.reason


def test_t5b_low_flow_stops_when_configured_to():
    config = make_config(
        heat_pump=HeatPumpSpec(
            input_kw=0.58, thermal_kw=3.0,
            cop_ref=5.17, cop_ref_temp=26.0, cop_low=4.18, cop_low_temp=15.0,
            air_temp_min=11.0, air_temp_max=43.0,
            flow_min_m3h=2.0, flow_min_blocking=True,
        )
    )
    now = datetime(2026, 7, 30, 13, 0, tzinfo=TZ)
    state = make_state(
        now,
        flow_m3h=SensorReading(1.0, 10, "flow"),
        pump_on=True,
        heat_pump_on=True,
        water_temp=SensorReading(24.0, 10, "water"),
        price_total=0.10,
    )
    faults = safety.evaluate(state, config)
    flow_fault = next(f for f in faults if f.code == "flow_below_heat_pump_minimum")
    assert flow_fault.severity is Severity.HEATING_BLOCKED

    decision = run_tick(state, config, done_h=0.0)
    assert decision.heat_pump is False, decision.reason


def test_t5c_no_flow_at_all_is_still_critical():
    """Zero flow with the pump running can wreck the pump. That does stop."""
    config = make_config()
    now = datetime(2026, 7, 30, 13, 0, tzinfo=TZ)
    state = make_state(
        now,
        flow_m3h=SensorReading(0.0, 10, "flow"),
        pump_on=True,
        water_temp=SensorReading(24.0, 10, "water"),
    )
    faults = safety.evaluate(state, config)
    assert any(
        f.code == "no_flow_while_pump_running" and f.severity is Severity.CRITICAL
        for f in faults
    )
    decision = run_tick(state, config, done_h=0.0)
    assert decision.branch is Branch.EMERGENCY_STOP


# ---------------------------------------------------------------------------
# T6 - reaching target stops the heat pump immediately, hold or no hold
# ---------------------------------------------------------------------------

def test_t6_target_reached_overrides_hold():
    config = make_config()
    now = datetime(2026, 7, 30, 13, 0, tzinfo=TZ)
    previous = Decision(
        pump=True,
        heat_pump=True,
        branch=Branch.HEATING,
        reason="heating",
        detail={"mode_at_decision": Mode.AUTO.value},
        hold_until=now + timedelta(minutes=12),
    )
    state = make_state(
        now,
        water_temp=SensorReading(28.0, 10, "water"),
        pump_on=True,
        heat_pump_on=True,
        price_total=0.10,
    )
    decision = run_tick(state, config, done_h=config.daily_filtration_hours(28.0), previous=previous)
    assert decision.heat_pump is False, decision.reason


# ---------------------------------------------------------------------------
# T7 - a large temperature rise becomes a multi-day plan
# ---------------------------------------------------------------------------

def test_t7_large_rise_is_seasonal():
    config = make_config()
    est = heating.estimate(config, water_temp=22.0, target_temp=28.0, air_temp=20.0,
                           hours_available=4.0)
    assert est.plan_mode is heating.PlanMode.SEASONAL
    assert 8.0 < est.hours_needed < 14.0, est.hours_needed

    maintenance = heating.estimate(config, water_temp=27.0, target_temp=28.0, air_temp=20.0,
                                   hours_available=6.0)
    assert maintenance.plan_mode is heating.PlanMode.MAINTENANCE


# ---------------------------------------------------------------------------
# T8 - aliased sensors must not report a phantom fault
# ---------------------------------------------------------------------------

def test_t8_aliased_sensors_no_fault():
    config = make_config(sensor_aliases=frozenset({frozenset({"hp_inlet", "hp_outlet"})}))
    now = datetime(2026, 7, 30, 13, 0, tzinfo=TZ)
    state = make_state(
        now,
        hp_inlet=SensorReading(27.0, 10, "hp_inlet"),
        hp_outlet=SensorReading(27.0, 10, "hp_outlet"),
        heat_pump_on=True,
        pump_on=True,
        heat_pump_runtime_seconds=45 * 60,
    )
    faults = safety.evaluate(state, config)
    assert not any(f.code == "heat_pump_not_producing" for f in faults)

    # Without the alias the same readings must be flagged.
    strict = safety.evaluate(state, make_config())
    assert any(f.code == "heat_pump_not_producing" for f in strict)


# ---------------------------------------------------------------------------
# T9 - the engine never latches on an assumed switch state
# ---------------------------------------------------------------------------

def test_t9_no_latching_on_actual_state():
    config = make_config()
    now = datetime(2026, 7, 30, 23, 30, tzinfo=TZ)
    # The plug reports itself as on, but nothing justifies running.
    state = make_state(
        now,
        pump_on=True,
        heat_pump_on=True,
        water_temp=SensorReading(28.5, 10, "water"),
    )
    decision = run_tick(state, config, done_h=config.daily_filtration_hours(28.0))
    assert decision.pump is False and decision.heat_pump is False, decision.reason


# ---------------------------------------------------------------------------
# T10 - frost protection works even in OFF mode
# ---------------------------------------------------------------------------

def test_t10_frost_protection_in_off_mode():
    config = make_config()
    now = datetime(2026, 12, 15, 3, 0, tzinfo=TZ)
    state = make_state(
        now,
        mode=Mode.OFF,
        air_temp=SensorReading(2.0, 10, "air"),
        water_temp=SensorReading(6.0, 10, "water"),
    )
    decision = run_tick(state, config, done_h=0.0)
    assert decision.pump is True
    assert decision.branch is Branch.FROST_PROTECTION
    assert decision.heat_pump is False, "the heat pump may not run at 2 C"


# ---------------------------------------------------------------------------
# T11 - heating runtime counts towards the filtration quota
# ---------------------------------------------------------------------------

def test_t11_heating_credits_filtration():
    config = make_config()
    now = datetime(2026, 7, 30, 18, 0, tzinfo=TZ)
    status = filt.evaluate(now, config, done_h=9.0)
    assert status.satisfied
    assert status.deadline_critical is False

    state = make_state(now, water_temp=SensorReading(28.4, 10, "water"))
    decision = run_tick(state, config, done_h=9.0)
    assert decision.pump is False
    assert decision.branch is Branch.IDLE


# ---------------------------------------------------------------------------
# T12 - the integration works without a price source
# ---------------------------------------------------------------------------

def test_t12_works_without_price_data():
    config = make_config(energy=EnergySettings(max_price=None))
    now = datetime(2026, 7, 30, 14, 0, tzinfo=TZ)
    state = make_state(
        now,
        price_total=None,
        price_energy=None,
        solar_power_w=None,
        water_temp=SensorReading(25.0, 10, "water"),
    )
    decision = run_tick(state, config, done_h=0.0)
    assert decision.heat_pump is True, decision.reason
    assert decision.branch is Branch.HEATING


# ---------------------------------------------------------------------------
# Derived figures sanity check
# ---------------------------------------------------------------------------

def test_derived_filtration_figures():
    config = make_config()
    # Turnover alone: 3 x 3834 L at 3.596 m3/h.
    assert abs(config.turnover_hours - 3.198) < 0.01
    # At swimming temperature the time-based minimum is larger and wins.
    assert abs(config.daily_filtration_hours(28.0) - 5.0) < 0.01
    assert config.filtration_driver(28.0) == "daily minimum"
    assert abs(config.block_hours(28.0) - 1.667) < 0.01
    assert abs(config.pool.kwh_thermal_per_degree - 4.458) < 0.01
    assert abs(config.heat_pump.cop_at(26.0) - 5.17) < 0.001
    assert abs(config.heat_pump.thermal_kw_at(15.0) - 2.424) < 0.01


def test_datasheet_flow_is_derated():
    spec = PumpSpec(flow_m3h=3.596, flow_is_measured=False, power_kw=0.1)
    assert abs(spec.effective_flow_m3h - 2.517) < 0.01


# ---------------------------------------------------------------------------
# T23 - a steady sensor is not mistaken for a dead one
# ---------------------------------------------------------------------------

def test_t23_steady_reading_does_not_stop_the_pool():
    """Regression: a stable temperature used to trigger an emergency stop.

    Home Assistant's last_updated only moves when the value changes, so a pool
    holding 27.0 C looked frozen. The age now comes from last_reported, and even
    a genuinely old reading must not cut circulation.
    """
    config = make_config()
    now = datetime(2026, 7, 30, 14, 0, tzinfo=TZ)
    # 742 seconds is the age from the reported symptom.
    state = make_state(now, water_temp=SensorReading(27.0, 742, "water"))

    faults = safety.evaluate(state, config)
    assert not any(f.severity is Severity.CRITICAL for f in faults), [
        f.code for f in faults
    ]

    decision = run_tick(state, config, done_h=0.0)
    assert decision.branch is not Branch.EMERGENCY_STOP, decision.reason


# ---------------------------------------------------------------------------
# T24 - a genuinely dead sensor blocks heating but keeps filtering
# ---------------------------------------------------------------------------

def test_t24_dead_sensor_blocks_heating_not_circulation():
    config = make_config()
    now = datetime(2026, 7, 30, 9, 30, tzinfo=TZ)
    state = make_state(
        now,
        water_temp=SensorReading(None, None, "water"),
        price_total=0.05,
    )

    faults = safety.evaluate(state, config)
    codes = {f.code: f.severity for f in faults}
    assert codes.get("water_temp_unavailable") is Severity.HEATING_BLOCKED
    assert not any(s is Severity.CRITICAL for s in codes.values())

    decision = run_tick(state, config, done_h=0.0)
    assert decision.heat_pump is False
    assert decision.branch is not Branch.EMERGENCY_STOP
    # Filtration still has to happen.
    assert decision.pump is True, decision.reason


# ---------------------------------------------------------------------------
# T25 - staleness escalates from warning to blocking
# ---------------------------------------------------------------------------

def test_t25_staleness_escalates():
    config = make_config()
    now = datetime(2026, 7, 30, 14, 0, tzinfo=TZ)

    fresh = make_state(now, water_temp=SensorReading(27.0, 300, "water"))
    assert not safety.evaluate(fresh, config)

    warning = make_state(now, water_temp=SensorReading(27.0, 1200, "water"))
    severities = {f.severity for f in safety.evaluate(warning, config)}
    assert severities == {Severity.WARNING}

    blocking = make_state(now, water_temp=SensorReading(27.0, 5000, "water"))
    severities = {f.severity for f in safety.evaluate(blocking, config)}
    assert Severity.HEATING_BLOCKED in severities
    assert Severity.CRITICAL not in severities


# ---------------------------------------------------------------------------
# T26 - the daily minimum overrides turnover on an oversized pump
# ---------------------------------------------------------------------------

def test_t26_daily_minimum_beats_turnover():
    """A pump that turns the water over in an hour still cannot skim in an hour.

    Turnover is volume-based; skimming, sanitiser contact and avoiding stagnation
    are time-based. Taking only the turnover figure produced roughly two hours a
    day for this pool, which is well under what a pool of this kind needs.
    """
    config = make_config()
    assert config.turnover_hours < 4.0
    # Cold water: little algae pressure, the floor drops.
    assert config.daily_filtration_hours(12.0) == max(config.turnover_hours, 2.0)
    # Swimming temperature: the floor rises above turnover and wins.
    assert config.daily_filtration_hours(28.0) == 5.0
    assert config.daily_filtration_hours(32.0) == 6.0
    # Unknown temperature falls back to a safe middle value.
    assert config.daily_filtration_hours(None) == max(config.turnover_hours, 4.0)


# ---------------------------------------------------------------------------
# T27 - a big pool with a modest pump is still driven by turnover
# ---------------------------------------------------------------------------

def test_t27_large_pool_is_turnover_driven():
    config = make_config(
        pool=PoolSpec(volume_l=50000, surface_m2=32.0, depth_m=1.5),
        pump=PumpSpec(flow_m3h=8.0, flow_is_measured=True, power_kw=0.75),
    )
    # 3 x 50000 L at 8 m3/h is nearly 19 hours; the 5 hour floor is irrelevant.
    assert config.filtration_driver(28.0) == "turnover"
    assert config.daily_filtration_hours(28.0) > 18.0


# ---------------------------------------------------------------------------
# T28 - the requirement follows the water temperature through the engine
# ---------------------------------------------------------------------------

def test_t28_requirement_tracks_water_temperature():
    config = make_config()
    now = datetime(2026, 7, 30, 12, 0, tzinfo=TZ)

    warm = filt.evaluate(now, config, done_h=0.0, water_temp=30.5)
    cool = filt.evaluate(now, config, done_h=0.0, water_temp=16.0)

    assert warm.required_h > cool.required_h
    assert warm.detail["driver"] == "daily minimum"
    assert warm.detail["water_temp"] == 30.5
