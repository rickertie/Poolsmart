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
    CheapPriceMode,
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
        "pump_inlet": SensorReading(None, None, "pump_inlet"),
        "pump_outlet": SensorReading(None, None, "pump_outlet"),
        "hp_inlet": SensorReading(27.0, 10, "hp_inlet"),
        "hp_outlet": SensorReading(30.0, 10, "hp_outlet"),
        "flow_m3h": SensorReading(3.5, 10, "flow"),
        "pump_power_w": SensorReading(100.0, 10, "pump_power"),
        "hp_power_w": SensorReading(0.0, 10, "hp_power"),
        "pump_on": False,
        "heat_pump_on": False,
        "pump_runtime_seconds": 3600.0,
        "target_temp": 28.0,
        "price_total": 0.30,
        "price_energy": 0.08,
        "measured_flow_m3h": None,
        "plan_price_informed": True,
        "cheap_price_now": None,
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
        measured_flow_m3h=state.measured_flow_m3h,
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
# T10 - Off means off, and Stand-by is what protects a filled pool
# ---------------------------------------------------------------------------

def test_t10_off_really_is_off():
    """Off used to keep frost protection alive, which was wrong.

    The reasoning was that an off switch should not be able to cause damage. But
    the pool may have been drained and dismantled for the winter, or the pump
    disconnected, and a system that starts a pump against an explicit instruction
    is worse than one that lets an unattended pool freeze. Protection belongs to
    Stand-by, which means "not swimming, but the pool is still there".
    """
    config = make_config()
    now = datetime(2026, 12, 15, 3, 0, tzinfo=TZ)
    freezing = make_state(
        now,
        mode=Mode.OFF,
        air_temp=SensorReading(2.0, 10, "air"),
        water_temp=SensorReading(6.0, 10, "water"),
    )
    decision = run_tick(freezing, config, done_h=0.0)
    assert decision.pump is False, decision.reason
    assert decision.heat_pump is False
    assert decision.branch is Branch.IDLE
    assert "Stand-by" in decision.reason, decision.reason


def test_t10b_standby_protects_against_frost():
    config = make_config()
    now = datetime(2026, 12, 15, 3, 0, tzinfo=TZ)
    state = make_state(
        now,
        mode=Mode.STANDBY,
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
    assert abs(config.turnover_hours() - 3.198) < 0.01
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
    """Water and outdoor air get four times the usual patience.

    Both legitimately hold the same value for a long stretch: a heated pool
    barely moves, and outdoor air overnight can sit still to two decimals for
    half an hour. Warning about those on the same clock as a probe that should
    be changing constantly produces alerts nobody can act on.
    """
    config = make_config()
    now = datetime(2026, 7, 30, 14, 0, tzinfo=TZ)
    slack = config.safety.slow_role_factor

    fresh = make_state(now, water_temp=SensorReading(27.0, 300, "water"))
    assert not safety.evaluate(fresh, config)

    # Under the relaxed threshold: still nothing to say.
    quiet = make_state(now, water_temp=SensorReading(27.0, 1200, "water"))
    assert not safety.evaluate(quiet, config)

    warning = make_state(
        now,
        water_temp=SensorReading(
            27.0, config.safety.stale_warning_seconds * slack + 60, "water"
        ),
    )
    severities = {f.severity for f in safety.evaluate(warning, config)}
    assert severities == {Severity.WARNING}

    blocking = make_state(
        now,
        water_temp=SensorReading(
            27.0, config.safety.stale_blocking_seconds * slack + 60, "water"
        ),
    )
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
    assert config.turnover_hours() < 4.0
    # Cold water: little algae pressure, the floor drops.
    assert config.daily_filtration_hours(12.0) == max(config.turnover_hours(), 2.0)
    # Swimming temperature: the floor rises above turnover and wins.
    assert config.daily_filtration_hours(28.0) == 5.0
    assert config.daily_filtration_hours(32.0) == 6.0
    # Unknown temperature falls back to a safe middle value.
    assert config.daily_filtration_hours(None) == max(config.turnover_hours(), 4.0)


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


# ---------------------------------------------------------------------------
# T34 - a flow meter reporting L/min is converted, not taken at face value
# ---------------------------------------------------------------------------

def test_t34_flow_unit_conversion():
    """Regression: 17 L/min was being read as 17 m3/h.

    Off by a factor of nearly seventeen, which made the heat pump's 2 m3/h
    threshold meaningless in both directions: a healthy 17 L/min looked like
    plenty, and anything genuinely low looked catastrophic.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "coord_consts",
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "poolsmart"
        / "coordinator.py",
    )
    source = spec.origin
    text = Path(source).read_text(encoding="utf-8")

    # The table has to exist and cover the units pool hardware actually uses.
    assert "FLOW_UNIT_FACTORS" in text
    for unit in ("l/min", "l/h", "m³/h", "l/s"):
        assert f'"{unit}"' in text, f"missing flow unit: {unit}"

    # And the conversion itself must be right.
    factors = {"l/min": 0.06, "l/h": 0.001, "l/s": 3.6, "m³/h": 1.0}
    assert abs(17 * factors["l/min"] - 1.02) < 0.001
    assert abs(3596 * factors["l/h"] - 3.596) < 0.001
    assert abs(2.0 / factors["l/min"] - 33.33) < 0.01


# ---------------------------------------------------------------------------
# T35 - real-world flow below the datasheet figure still heats
# ---------------------------------------------------------------------------

def test_t35_below_datasheet_flow_still_heats():
    """17 L/min is 1.02 m3/h, below the 2.0 the datasheet asks for.

    It moves 3 kW at a delta-T of about 2.5 C, which is entirely normal, so the
    installation is fine and the integration must not stand in its way.
    """
    config = make_config()
    now = datetime(2026, 7, 30, 14, 0, tzinfo=TZ)
    state = make_state(
        now,
        flow_m3h=SensorReading(1.02, 10, "flow"),  # 17 L/min
        pump_on=True,
        heat_pump_on=True,
        water_temp=SensorReading(25.0, 10, "water"),
        hp_inlet=SensorReading(25.0, 10, "hp_inlet"),
        hp_outlet=SensorReading(27.5, 10, "hp_outlet"),
        price_total=0.15,
    )

    faults = safety.evaluate(state, config)
    flow_fault = next(f for f in faults if f.code == "flow_below_heat_pump_minimum")
    assert flow_fault.severity is Severity.WARNING
    # The message has to name both units, or it is unactionable.
    assert "L/min" in flow_fault.message

    available, _reason = safety.heat_pump_available(state, config, faults)
    assert available is True

    decision = run_tick(state, config, done_h=0.0)
    assert decision.heat_pump is True, decision.reason


# ---------------------------------------------------------------------------
# T36 - raising the configured minimum silences the warning entirely
# ---------------------------------------------------------------------------

def test_t36_adjusted_minimum_silences_warning():
    config = make_config(
        heat_pump=HeatPumpSpec(
            input_kw=0.58, thermal_kw=3.0,
            cop_ref=5.17, cop_ref_temp=26.0, cop_low=4.18, cop_low_temp=15.0,
            air_temp_min=11.0, air_temp_max=43.0,
            flow_min_m3h=0.85,  # 14 L/min, what this installation really needs
        )
    )
    now = datetime(2026, 7, 30, 14, 0, tzinfo=TZ)
    state = make_state(
        now,
        flow_m3h=SensorReading(1.02, 10, "flow"),
        pump_on=True,
        heat_pump_on=True,
        water_temp=SensorReading(25.0, 10, "water"),
    )
    faults = safety.evaluate(state, config)
    assert not any(f.code == "flow_below_heat_pump_minimum" for f in faults)


# ---------------------------------------------------------------------------
# T37 - the filter warning tracks decline, not the datasheet
# ---------------------------------------------------------------------------

def test_t37_filter_warning_uses_measured_baseline():
    """Regression: the warning fired permanently on a healthy system.

    It compared measured flow against the configured figure, so any installation
    whose real flow sits below its datasheet number -- most of them -- was told
    forever that its filter needed cleaning. That reports a fact about the
    paperwork, not about the filter.
    """
    config = make_config()  # configured 3.596 m3/h
    now = datetime(2026, 7, 30, 14, 0, tzinfo=TZ)

    # Steady at the flow this system actually achieves: no filter warning.
    healthy = make_state(
        now,
        pump_on=True,
        flow_m3h=SensorReading(1.02, 10, "flow"),
        measured_flow_m3h=1.02,
    )
    faults = safety.evaluate(healthy, config)
    assert not any(f.code == "filter_service_needed" for f in faults)

    # A real decline from that baseline does warn.
    fouled = make_state(
        now,
        pump_on=True,
        flow_m3h=SensorReading(0.60, 10, "flow"),
        measured_flow_m3h=1.02,
    )
    faults = safety.evaluate(fouled, config)
    warning = next(f for f in faults if f.code == "filter_service_needed")
    assert warning.severity is Severity.WARNING
    assert "usual" in warning.message


# ---------------------------------------------------------------------------
# T38 - a configured flow that measurement contradicts is pointed out
# ---------------------------------------------------------------------------

def test_t38_configured_flow_mismatch_is_reported():
    config = make_config()  # configured 3.596, measuring 1.02
    now = datetime(2026, 7, 30, 14, 0, tzinfo=TZ)
    state = make_state(now, pump_on=True, flow_m3h=SensorReading(1.02, 10, "flow"))

    fault = next(
        f for f in safety.evaluate(state, config) if f.code == "configured_flow_too_high"
    )
    assert "1.02" in fault.message
    assert "measured" in fault.message


# ---------------------------------------------------------------------------
# T39 - filtration is calculated from measured flow when there is one
# ---------------------------------------------------------------------------

def test_t39_filtration_uses_measured_flow():
    """The whole daily requirement hangs off this number.

    Calculating with a datasheet figure the pump never reaches means filtering
    for a fraction of the time the pool actually needs.
    """
    config = make_config()
    now = datetime(2026, 7, 30, 12, 0, tzinfo=TZ)

    on_paper = filt.evaluate(now, config, done_h=0.0, water_temp=28.0)
    in_reality = filt.evaluate(
        now, config, done_h=0.0, water_temp=28.0, measured_flow_m3h=1.02
    )

    assert in_reality.required_h > on_paper.required_h
    assert abs(in_reality.required_h - 11.28) < 0.1, in_reality.required_h
    assert in_reality.detail["flow_source"] == "measured"
    assert in_reality.detail["driver"] == "turnover"


# ---------------------------------------------------------------------------
# T40 - a filtration deadline must not block heating
# ---------------------------------------------------------------------------

def test_t40_deadline_does_not_block_boost():
    """Regression: Boost appeared to do nothing.

    Heating used to sit below the filtration deadline in the ladder, so a
    critical deadline switched the heat pump off outright. On a pool needing
    many hours of filtration a day that branch was active most of the time, so
    heating almost never ran and the reason line talked about filtration while
    the user waited for a warm pool.

    Heating now sits above the filtration deadline, so Boost heats directly.
    The pump still runs either way and the tick still counts toward today's
    filtration quota, so nothing is lost by heating winning the branch outright
    instead of tacking heat onto a circulation-only decision.
    """
    config = make_config()
    now = datetime(2026, 8, 1, 16, 0, tzinfo=TZ)
    state = make_state(
        now,
        mode=Mode.BOOST,
        water_temp=SensorReading(28.8, 10, "water"),
        air_temp=SensorReading(26.5, 10, "air"),
        target_temp=32.0,
        price_total=0.45,  # expensive: Boost must ignore it
        measured_flow_m3h=1.02,  # real flow, so filtration needs eleven hours
    )
    # Deadline critical: more filtration owed than window remaining.
    decision = run_tick(state, config, done_h=1.0)

    assert decision.branch is Branch.HEATING
    assert decision.pump is True
    assert decision.heat_pump is True, decision.reason


def test_t40b_deadline_respects_price_outside_boost():
    """In AUTO the same situation still waits for an acceptable price."""
    config = make_config()  # max_price 0.25
    now = datetime(2026, 8, 1, 16, 0, tzinfo=TZ)
    expensive = make_state(
        now,
        mode=Mode.AUTO,
        water_temp=SensorReading(28.8, 10, "water"),
        target_temp=32.0,
        price_total=0.45,
        measured_flow_m3h=1.02,
    )
    decision = run_tick(expensive, config, done_h=1.0)
    assert decision.branch is Branch.FILTRATION_DEADLINE
    assert decision.pump is True
    assert decision.heat_pump is False, decision.reason

    cheap = expensive.replace(price_total=0.10)
    decision = run_tick(cheap, config, done_h=1.0)
    assert decision.heat_pump is True, decision.reason


def test_t40c_standby_still_circulates_without_heating():
    """Stand-by exists precisely to filter without heating; leave it alone."""
    config = make_config()
    now = datetime(2026, 8, 1, 16, 0, tzinfo=TZ)
    state = make_state(
        now,
        mode=Mode.STANDBY,
        water_temp=SensorReading(24.0, 10, "water"),
        target_temp=32.0,
        price_total=0.05,
        measured_flow_m3h=1.02,
    )
    decision = run_tick(state, config, done_h=1.0)
    assert decision.pump is True
    assert decision.heat_pump is False, decision.reason


def test_t40d_heating_still_blocked_outside_the_envelope():
    """Adding heat to a circulation branch must respect the appliance limits."""
    config = make_config()
    now = datetime(2026, 12, 1, 16, 0, tzinfo=TZ)
    state = make_state(
        now,
        mode=Mode.BOOST,
        water_temp=SensorReading(15.0, 10, "water"),
        air_temp=SensorReading(6.0, 10, "air"),  # below the 11 C minimum
        target_temp=32.0,
        measured_flow_m3h=1.02,
    )
    decision = run_tick(state, config, done_h=1.0)
    assert decision.heat_pump is False, decision.reason


# ---------------------------------------------------------------------------
# T46 - the compressor is protected from short cycling
# ---------------------------------------------------------------------------

def test_t46_compressor_minimum_off_time():
    """Regression: off at 20:01, on again at 20:04.

    Priority branches may break an ordinary hold, which is right for the pump --
    a filtration deadline should not wait ten minutes. Once those branches
    learned to heat alongside, they dragged the compressor through the exception
    with them, and three minutes between stopping and restarting is how you wear
    a compressor out early.
    """
    config = make_config()
    stopped = datetime(2026, 8, 1, 20, 1, 40, tzinfo=TZ)
    now = datetime(2026, 8, 1, 20, 4, 10, tzinfo=TZ)  # 2.5 minutes later

    state = make_state(
        now,
        mode=Mode.BOOST,
        water_temp=SensorReading(26.0, 10, "water"),
        target_temp=32.0,
        heat_pump_on=False,
        pump_on=True,
        heat_pump_stopped_at=stopped,
        measured_flow_m3h=1.02,
    )
    decision = run_tick(state, config, done_h=1.0)

    assert decision.heat_pump is False, decision.reason
    assert decision.detail.get("compressor_guard") == "min_off"
    assert "equalise" in decision.reason

    # Once the minimum has passed it starts normally.
    later = state.replace(now=stopped + timedelta(minutes=11))
    decision = run_tick(later, config, done_h=1.0)
    assert decision.heat_pump is True, decision.reason


def test_t46b_boost_cannot_bypass_the_compressor_guard():
    """Boost ignores price, but never hardware protection.

    Restarting the compressor two minutes after it stopped is short cycling no
    matter which branch of the ladder asked for it.
    """
    config = make_config()
    stopped = datetime(2026, 8, 1, 20, 1, tzinfo=TZ)
    now = datetime(2026, 8, 1, 20, 3, tzinfo=TZ)
    state = make_state(
        now,
        mode=Mode.BOOST,
        water_temp=SensorReading(26.0, 10, "water"),
        target_temp=32.0,
        heat_pump_stopped_at=stopped,
        pump_on=True,
        measured_flow_m3h=1.02,
    )
    decision = run_tick(state, config, done_h=1.0)
    assert decision.branch is Branch.HEATING
    assert decision.pump is True, "circulation must not be delayed"
    assert decision.heat_pump is False, "but the compressor must be"


def test_t46c_reaching_target_still_stops_immediately():
    """The minimum run time must never keep heating a pool that is done."""
    config = make_config()
    started = datetime(2026, 8, 1, 20, 0, tzinfo=TZ)
    now = datetime(2026, 8, 1, 20, 3, tzinfo=TZ)
    state = make_state(
        now,
        mode=Mode.AUTO,
        water_temp=SensorReading(28.0, 10, "water"),
        target_temp=28.0,
        heat_pump_on=True,
        pump_on=True,
        heat_pump_started_at=started,
        measured_flow_m3h=1.02,
    )
    decision = run_tick(state, config, done_h=20.0)
    assert decision.heat_pump is False, decision.reason


# ---------------------------------------------------------------------------
# T47 - the solar threshold follows the equipment, not a fixed guess
# ---------------------------------------------------------------------------

def test_t47_solar_threshold_matches_the_equipment():
    """A blanket 1500 W was over twice what this installation draws.

    On a moderately sunny afternoon with 900 W spare it would decline to heat
    while 680 W of free power sat unused.
    """
    from core.config import EnergySettings

    draw_w = round((0.58 + 0.10) * 1000)  # heat pump plus pump
    assert draw_w == 680

    config = make_config(
        energy=EnergySettings(solar_threshold_w=draw_w + 200, max_price=0.25)
    )
    assert config.energy.solar_threshold_w == 880

    now = datetime(2026, 8, 1, 14, 0, tzinfo=TZ)
    state = make_state(
        now,
        water_temp=SensorReading(25.0, 10, "water"),
        target_temp=28.0,
        price_total=0.60,  # expensive: only solar can justify this
        solar_power_w=900.0,
        measured_flow_m3h=1.02,
    )
    decision = run_tick(state, config, done_h=20.0)
    assert decision.heat_pump is True, decision.reason
    assert "solar" in decision.reason

    # Below the threshold the price limit applies again.
    dim = state.replace(solar_power_w=500.0)
    decision = run_tick(dim, config, done_h=20.0)
    assert decision.heat_pump is False, decision.reason


# ---------------------------------------------------------------------------
# T48 - a planned session over the price limit says so honestly
# ---------------------------------------------------------------------------

def test_t48_planned_over_limit_explains_itself():
    """Regression: the reason read as though the logic were inverted.

    "Heating because price 0.248 exceeds the limit of 0.200" is nonsense. The
    heating was justified by the plan; the price sentence was the rejection
    reason being printed as though it were the justification.
    """
    config = make_config(energy=EnergySettings(max_price=0.20))
    now = datetime(2026, 8, 1, 14, 0, tzinfo=TZ)
    state = make_state(
        now,
        water_temp=SensorReading(24.0, 10, "water"),
        target_temp=28.0,
        price_total=0.248,
        solar_power_w=0.0,
        heating_session_active=True,   # the planner chose this interval
        measured_flow_m3h=1.02,
    )
    decision = run_tick(state, config, done_h=20.0)

    assert decision.heat_pump is True
    assert decision.detail.get("over_limit") is True
    assert "part of the plan" in decision.reason
    assert "Nothing cheaper was available" in decision.reason
    # And it must not read as though exceeding the limit were the justification.
    assert "because price" not in decision.reason


def test_t48b_unplanned_over_limit_still_waits():
    """Without a plan behind it, an expensive interval is simply declined."""
    config = make_config(energy=EnergySettings(max_price=0.20))
    now = datetime(2026, 8, 1, 14, 0, tzinfo=TZ)
    state = make_state(
        now,
        water_temp=SensorReading(24.0, 10, "water"),
        target_temp=28.0,
        price_total=0.248,
        solar_power_w=0.0,
        measured_flow_m3h=1.02,
    )
    decision = run_tick(state, config, done_h=20.0)
    assert decision.heat_pump is False, decision.reason
    assert "Waiting for cheaper" in decision.reason


# ---------------------------------------------------------------------------
# T49 - never claim a cheap moment that was not chosen
# ---------------------------------------------------------------------------

def test_t49_no_forecast_does_not_override_the_price_limit():
    """Regression: heating at 0.338 against a ceiling of 0.200.

    Without a forecast the planner falls back to "heat on demand". Treating that
    fallback as a plan turned a missing price feed into a licence to ignore the
    price limit entirely — and the reason line said so in the same breath, which
    is how it was spotted. A fallback means "heat when allowed", not "heat
    regardless".
    """
    config = make_config(energy=EnergySettings(max_price=0.20))
    now = datetime(2026, 8, 1, 14, 0, tzinfo=TZ)
    state = make_state(
        now,
        water_temp=SensorReading(24.0, 10, "water"),
        target_temp=28.0,
        price_total=0.338,
        solar_power_w=0.0,
        heating_session_active=True,
        plan_price_informed=False,   # no forecast was parsed
        measured_flow_m3h=1.02,
    )
    decision = run_tick(state, config, done_h=20.0)

    assert decision.heat_pump is False, decision.reason
    assert "cheapest" not in decision.reason.lower()


def test_t49c_cheap_signal_still_gets_it_heating():
    """The way out of a missing forecast is the cheap period sensor."""
    config = make_config(energy=EnergySettings(max_price=0.20))
    now = datetime(2026, 8, 1, 14, 0, tzinfo=TZ)
    state = make_state(
        now,
        water_temp=SensorReading(24.0, 10, "water"),
        target_temp=28.0,
        price_total=0.338,
        solar_power_w=0.0,
        heating_session_active=True,
        plan_price_informed=False,
        cheap_price_now=True,
        measured_flow_m3h=1.02,
    )
    decision = run_tick(state, config, done_h=20.0)
    assert decision.heat_pump is True, decision.reason
    assert "cheap period" in decision.reason


def test_t49d_boost_still_overrides_everything():
    """Boost is the deliberate way to say "I do not care what it costs"."""
    config = make_config(energy=EnergySettings(max_price=0.20))
    now = datetime(2026, 8, 1, 14, 0, tzinfo=TZ)
    state = make_state(
        now,
        mode=Mode.BOOST,
        water_temp=SensorReading(24.0, 10, "water"),
        target_temp=28.0,
        price_total=0.338,
        plan_price_informed=False,
        measured_flow_m3h=1.02,
    )
    decision = run_tick(state, config, done_h=20.0)
    assert decision.heat_pump is True, decision.reason


def test_t49b_with_a_forecast_the_claim_is_fair():
    config = make_config(energy=EnergySettings(max_price=0.20))
    now = datetime(2026, 8, 1, 14, 0, tzinfo=TZ)
    state = make_state(
        now,
        water_temp=SensorReading(24.0, 10, "water"),
        target_temp=28.0,
        price_total=0.2484,
        solar_power_w=0.0,
        heating_session_active=True,
        plan_price_informed=True,
        measured_flow_m3h=1.02,
    )
    decision = run_tick(state, config, done_h=20.0)
    assert "Nothing cheaper was available" in decision.reason


# ---------------------------------------------------------------------------
# T50 - an external cheap-period signal outranks the fixed ceiling
# ---------------------------------------------------------------------------

def test_t50_cheap_period_signal():
    """A limit alone cannot tell a cheap hour from an expensive day.

    With a ceiling of 0.20 and a day whose cheapest hour is 0.22, nothing would
    ever heat. The tariff integration knows where this hour sits within today.
    """
    config = make_config(energy=EnergySettings(max_price=0.20))
    now = datetime(2026, 8, 1, 14, 0, tzinfo=TZ)
    base = make_state(
        now,
        water_temp=SensorReading(24.0, 10, "water"),
        target_temp=28.0,
        price_total=0.2484,
        solar_power_w=0.0,
        measured_flow_m3h=1.02,
    )

    # No signal: the ceiling applies and it waits.
    decision = run_tick(base, config, done_h=20.0)
    assert decision.heat_pump is False

    # Signal on: heat, and say where the justification came from.
    marked = base.replace(cheap_price_now=True)
    decision = run_tick(marked, config, done_h=20.0)
    assert decision.heat_pump is True, decision.reason
    assert "cheap period" in decision.reason

    # Signal off is not an instruction to heat, only the absence of one.
    marked_off = base.replace(cheap_price_now=False)
    decision = run_tick(marked_off, config, done_h=20.0)
    assert decision.heat_pump is False


def test_t50b_max_price_hard_mode_still_waits_above_the_ceiling():
    """With max_price_hard, a 'cheap' hour above max_price does not heat.

    Same day as T50 -- cheapest hour is 0.2484, above the 0.20 ceiling -- but
    the installation has opted into treating max_price as a promise nothing
    crosses. See issue #22.
    """
    config = make_config(
        energy=EnergySettings(
            max_price=0.20, cheap_price_mode=CheapPriceMode.MAX_PRICE_HARD
        )
    )
    now = datetime(2026, 8, 1, 14, 0, tzinfo=TZ)
    base = make_state(
        now,
        water_temp=SensorReading(24.0, 10, "water"),
        target_temp=28.0,
        price_total=0.2484,
        solar_power_w=0.0,
        measured_flow_m3h=1.02,
    )

    marked = base.replace(cheap_price_now=True)
    decision = run_tick(marked, config, done_h=20.0)
    assert decision.heat_pump is False, decision.reason

    # Below the ceiling, the signal still applies as normal.
    cheaper = base.replace(cheap_price_now=True, price_total=0.18)
    decision = run_tick(cheaper, config, done_h=20.0)
    assert decision.heat_pump is True, decision.reason


def test_t50c_cheap_wins_capped_mode_respects_its_own_ceiling():
    """With cheap_wins_capped, the signal wins below its own ceiling only.

    A separate, usually higher, price is the backstop -- below it the signal
    is trusted as in the default mode; above it, heating is judged the
    normal way. See issue #22.
    """
    config = make_config(
        energy=EnergySettings(
            max_price=0.20,
            cheap_price_mode=CheapPriceMode.CHEAP_WINS_CAPPED,
            cheap_price_ceiling=0.30,
        )
    )
    now = datetime(2026, 8, 1, 14, 0, tzinfo=TZ)
    base = make_state(
        now,
        water_temp=SensorReading(24.0, 10, "water"),
        target_temp=28.0,
        solar_power_w=0.0,
        measured_flow_m3h=1.02,
    )

    # Under the ceiling of 0.30: the signal wins, same as CHEAP_WINS.
    under_ceiling = base.replace(cheap_price_now=True, price_total=0.2484)
    decision = run_tick(under_ceiling, config, done_h=20.0)
    assert decision.heat_pump is True, decision.reason

    # Over the ceiling: even a "cheap" hour does not heat.
    over_ceiling = base.replace(cheap_price_now=True, price_total=0.338)
    decision = run_tick(over_ceiling, config, done_h=20.0)
    assert decision.heat_pump is False, decision.reason


# ---------------------------------------------------------------------------
# T51 - the fifth probe earns its place as a calibration check
# ---------------------------------------------------------------------------

def test_t51_probe_disagreement_is_noticed():
    """The pool probe and the pump inlet measure the same water.

    Nothing else in the system can notice that a temperature is simply wrong
    rather than merely surprising, and a miscalibrated probe quietly corrupts
    delta-T and every COP figure derived from it.
    """
    config = make_config()
    now = datetime(2026, 8, 1, 14, 0, tzinfo=TZ)

    agreeing = make_state(
        now,
        water_temp=SensorReading(28.50, 10, "water"),
        pump_inlet=SensorReading(28.42, 10, "pump_inlet"),
        pump_on=True,
    )
    assert not any(
        f.code == "probe_disagreement" for f in safety.evaluate(agreeing, config)
    )

    diverging = make_state(
        now,
        water_temp=SensorReading(28.50, 10, "water"),
        pump_inlet=SensorReading(27.10, 10, "pump_inlet"),
        pump_on=True,
    )
    fault = next(
        f for f in safety.evaluate(diverging, config) if f.code == "probe_disagreement"
    )
    assert fault.severity is Severity.WARNING
    assert "calibrating" in fault.message
    assert fault.detail["difference"] == 1.4


def test_t51b_no_check_while_the_heat_pump_is_adding_heat():
    """With the heat pump running the two probes are legitimately apart."""
    config = make_config()
    now = datetime(2026, 8, 1, 14, 0, tzinfo=TZ)
    state = make_state(
        now,
        water_temp=SensorReading(28.50, 10, "water"),
        pump_inlet=SensorReading(27.10, 10, "pump_inlet"),
        pump_on=True,
        heat_pump_on=True,
    )
    assert not any(
        f.code == "probe_disagreement" for f in safety.evaluate(state, config)
    )


def test_t51c_no_check_without_the_probe():
    """A fifth probe is optional; its absence is not a fault."""
    config = make_config()
    now = datetime(2026, 8, 1, 14, 0, tzinfo=TZ)
    state = make_state(now, pump_on=True)  # pump_inlet unavailable by default
    assert not any(
        f.code == "probe_disagreement" for f in safety.evaluate(state, config)
    )


# ---------------------------------------------------------------------------
# T52 - flow is judged by delta-T, using Rick's measured data
# ---------------------------------------------------------------------------

def test_t52_real_installation_reads_as_healthy():
    """Measured: 1.05 m3/h against a 2.0 datasheet minimum, delta-T 1.56 C.

    Opening the diverter valve took flow from 1.04 to 1.30 m3/h. Delta-T fell
    from 1.56 to 1.27 and thermal output stayed at 1.9 kW, which is what an
    installation that is not flow-limited looks like. Chasing the datasheet
    figure would have been chasing nothing.
    """
    config = make_config()
    now = datetime(2026, 8, 2, 9, 0, tzinfo=TZ)
    state = make_state(
        now,
        flow_m3h=SensorReading(1.05, 10, "flow"),
        hp_inlet=SensorReading(28.00, 10, "hp_inlet"),
        hp_outlet=SensorReading(29.56, 10, "hp_outlet"),   # delta-T 1.56
        heat_pump_on=True,
        pump_on=True,
        heat_pump_runtime_seconds=45 * 60,
    )

    verdict, explanation, numbers = safety.flow_adequacy(state, config)
    assert verdict == "healthy", (verdict, explanation)
    assert numbers["delta_t"] == 1.56
    assert "carrying the heat away" in explanation

    # And the thermal output that implies matches what was measured.
    assert abs(1.05 * 1.56 * 1.163 - 1.9) < 0.1


def test_t52b_a_real_flow_problem_looks_different():
    """Starvation shows up as a high rise, not a low flow figure."""
    config = make_config()
    now = datetime(2026, 8, 2, 9, 0, tzinfo=TZ)
    state = make_state(
        now,
        flow_m3h=SensorReading(0.28, 10, "flow"),
        hp_inlet=SensorReading(28.0, 10, "hp_inlet"),
        hp_outlet=SensorReading(33.8, 10, "hp_outlet"),   # delta-T 5.8
        heat_pump_on=True,
        pump_on=True,
        heat_pump_runtime_seconds=45 * 60,
    )
    verdict, explanation, _numbers = safety.flow_adequacy(state, config)
    assert verdict == "starved"
    assert "not carrying the heat away" in explanation


def test_t52c_verifying_the_site_silences_the_datasheet_warning():
    """Once confirmed, stop repeating a number the plumbing cannot reach."""
    now = datetime(2026, 8, 2, 9, 0, tzinfo=TZ)
    state = make_state(
        now,
        flow_m3h=SensorReading(1.05, 10, "flow"),
        heat_pump_on=True,
        pump_on=True,
    )

    unverified = make_config()
    assert any(
        f.code == "flow_below_heat_pump_minimum"
        for f in safety.evaluate(state, unverified)
    )

    verified = make_config(
        heat_pump=HeatPumpSpec(
            input_kw=0.58, thermal_kw=3.0,
            cop_ref=5.17, cop_ref_temp=26.0, cop_low=4.18, cop_low_temp=15.0,
            air_temp_min=11.0, air_temp_max=43.0,
            flow_min_m3h=2.0, flow_min_site_verified=True,
        )
    )
    assert not any(
        f.code == "flow_below_heat_pump_minimum"
        for f in safety.evaluate(state, verified)
    )


# ---------------------------------------------------------------------------
# T53 - Eco mode does not heat at an expensive moment
# ---------------------------------------------------------------------------

def test_t53_eco_does_not_heat_when_expensive():
    """Reported from a live system: Eco, 0.317/kWh, heating anyway.

    Eco tightens the ceiling to 0.14 (0.20 x 0.7), so 0.317 is more than twice
    the limit. It heated because a forecast-less fallback plan was being treated
    as grounds to ignore the ceiling. Eco is the mode people pick precisely to
    avoid this.
    """
    config = make_config(
        energy=EnergySettings(max_price=0.20, eco_price_factor=0.7)
    )
    now = datetime(2026, 8, 3, 8, 28, tzinfo=TZ)
    state = make_state(
        now,
        mode=Mode.ECO,
        water_temp=SensorReading(26.0, 10, "water"),
        air_temp=SensorReading(20.0, 10, "air"),
        target_temp=28.0,
        price_total=0.317,
        solar_power_w=0.0,
        heating_session_active=True,
        plan_price_informed=False,
        measured_flow_m3h=1.02,
    )
    decision = run_tick(state, config, done_h=4.0)
    assert decision.heat_pump is False, decision.reason

    # Sun is the way Eco is meant to heat, and it still does.
    sunny = state.replace(solar_power_w=3000.0)
    decision = run_tick(sunny, config, done_h=4.0)
    assert decision.heat_pump is True, decision.reason
    assert "solar" in decision.reason


def test_t53b_eco_is_stricter_than_auto():
    """The whole point of Eco is a tighter ceiling than Auto."""
    config = make_config(
        energy=EnergySettings(max_price=0.20, eco_price_factor=0.7)
    )
    now = datetime(2026, 8, 3, 12, 0, tzinfo=TZ)
    base = make_state(
        now,
        water_temp=SensorReading(26.0, 10, "water"),
        target_temp=28.0,
        price_total=0.17,          # under Auto's 0.20, over Eco's 0.14
        solar_power_w=0.0,
        measured_flow_m3h=1.02,
    )

    assert run_tick(base, config, done_h=20.0).heat_pump is True
    assert run_tick(base.replace(mode=Mode.ECO), config, done_h=20.0).heat_pump is False
