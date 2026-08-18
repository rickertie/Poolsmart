"""Read-only sensors.

Source entities are deliberately not mirrored. Water temperature, outdoor
temperature and price stay the entities the user selected during setup; only
computed values get an entity of their own. Mirroring would create a second
place where the same number lives, which is how the previous design drifted.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, HP_STANDBY_WATTS, PROGRESS_EPSILON
from homeassistant.util import dt as dt_util

from .core import safety
from .coordinator import PoolSmartCoordinator
from .entity import PoolSmartEntity


@dataclass(frozen=True, kw_only=True)
class PoolSensorDescription(SensorEntityDescription):
    """A sensor plus how to derive its value from the coordinator."""

    value_fn: Callable[[PoolSmartCoordinator], object]
    attributes_fn: Callable[[PoolSmartCoordinator], dict] | None = None


def _why_unknown(coordinator: PoolSmartCoordinator, what: str) -> dict:
    """Explain an empty value.

    Most of these sensors are blank for a perfectly good reason -- the heat pump
    is off, or nothing has been learned yet. Saying so beats leaving someone to
    work out whether their installation is broken.
    """
    state = coordinator.data.get("state") if coordinator.data else None
    if state is None:
        return {"unavailable_because": "no measurement has been taken yet"}

    if what in ("delta_t", "cop_measured", "thermal_power"):
        if coordinator.pool_config.is_aliased("hp_inlet", "hp_outlet"):
            return {
                "unavailable_because": (
                    "the heat pump inlet and outlet are set to the same entity, so "
                    "there is no temperature difference to measure. Point them at "
                    "two different sensors under Configure, Entities."
                )
            }
        if not (state.hp_inlet.available and state.hp_outlet.available):
            return {
                "unavailable_because": (
                    "no heat pump inlet and outlet sensors are configured"
                )
            }
        if what == "cop_measured" and not state.heat_pump_on:
            return {
                "unavailable_because": (
                    "the heat pump is not running, so there is no duty point to "
                    "measure a COP at"
                ),
                "available_when": "the heat pump is heating",
            }
    if what == "cop_measured" and not state.hp_power_w.available:
        return {"unavailable_because": "no heat pump power sensor is configured"}
    if what == "flow" and not state.flow_m3h.available:
        return {"unavailable_because": "no flow meter is configured"}
    return {}


def _status_attributes(c: PoolSmartCoordinator) -> dict:
    decision = c.decision
    if decision is None:
        return {}
    state = c.data.get("state") if c.data else None
    return {
        "reason": decision.reason,
        # The measured temperatures ride along as attributes rather than getting
        # entities of their own. A dashboard needs them in the same card as the
        # reason, but duplicating a source sensor into the registry would mean
        # two entities holding one number, double the recorder storage, and a
        # device page that invites the question of which one is real.
        "water_temperature": (
            state.water_temp.value if state and state.water_temp.available else None
        ),
        "air_temperature": (
            state.air_temp.value if state and state.air_temp.available else None
        ),
        "target_temperature": c.target_temp,
        "branch": decision.branch.name,
        "branch_number": int(decision.branch),
        "pump": decision.pump,
        "heat_pump": decision.heat_pump,
        "hold_until": decision.hold_until.isoformat() if decision.hold_until else None,
        "heat_pump_available": c.heat_pump_available,
        "heat_pump_gate_reason": c.heat_pump_gate_reason,
        "faults": c.fault_codes(),
        "disabled_capabilities": sorted(c.disabled_capabilities),
        "last_error": c.last_error,
        "subsystem_errors": c.subsystem_errors,
        "price_forecast_slots": len(c._price_slots),
        "price_optimisation": (
            "active"
            if c._price_slots
            else "unavailable: no price forecast could be read, so heating waits "
            "for the price limit or the cheap period signal instead of choosing "
            "a cheap moment"
        ),
        **{f"detail_{k}": v for k, v in decision.detail.items()},
    }


SENSORS: tuple[PoolSensorDescription, ...] = (
    PoolSensorDescription(
        key="status",
        value_fn=lambda c: c.decision.branch.name.lower() if c.decision else None,
        attributes_fn=_status_attributes,
    ),
    PoolSensorDescription(
        key="ready_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda c: c.plan.ready_at if c.plan else None,
        attributes_fn=lambda c: (
            {
                "unavailable_because": (
                    None
                    if c.plan.ready_at
                    else "the pool is at or above its target, so no heating is planned"
                ),
                "plan_mode": c.plan.mode.value,
                "reason": c.plan.reason,
                "hours_needed": round(c.plan.hours_needed, 2),
                "hours_planned": round(c.plan.hours_planned, 2),
                "expected_cost": c.plan.expected_cost,
                # In seasonal mode this is a date several days out. Showing an
                # honest date beats showing a time that cannot be met.
                "is_multi_day": c.plan.mode.value == "seasonal",
                **{f"detail_{k}": v for k, v in c.plan.detail.items()},
            }
            if c.plan
            else {}
        ),
    ),
    PoolSensorDescription(
        key="next_action_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda c: _next_action(c),
        attributes_fn=lambda c: (
            {}
            if _next_action(c) is not None
            else {
                "unavailable_because": (
                    "nothing is scheduled: the pool is at temperature and today's "
                    "filtration blocks are either running or finished"
                )
            }
        ),
    ),
    PoolSensorDescription(
        key="heating_time_required",
        native_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=1,
        value_fn=lambda c: (
            round(c.estimate.hours_needed, 2)
            if c.estimate and c.estimate.hours_needed != float("inf")
            else None
        ),
        attributes_fn=lambda c: (
            {
                "readable": _readable_hours(
                    c.estimate.hours_needed
                    if c.estimate.hours_needed != float("inf")
                    else None
                ),
                "plan_mode": c.estimate.plan_mode.value,
                "degrees_needed": round(c.estimate.degrees_needed, 2),
                "kwh_electric": round(c.estimate.kwh_electric, 2),
            }
            if c.estimate
            else {}
        ),
    ),
    PoolSensorDescription(
        key="delta_t",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=2,
        value_fn=lambda c: (
            round(c.data["state"].delta_t, 2)
            if c.data and c.data["state"].delta_t is not None
            else None
        ),
        attributes_fn=lambda c: _why_unknown(c, "delta_t"),
    ),
    PoolSensorDescription(
        key="cop_expected",
        suggested_display_precision=2,
        value_fn=lambda c: round(c.estimate.cop, 2) if c.estimate else None,
    ),
    PoolSensorDescription(
        key="cop_measured",
        suggested_display_precision=2,
        value_fn=lambda c: _measured_cop(c),
    ),
    PoolSensorDescription(
        key="thermal_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        value_fn=lambda c: _thermal_power(c),
        attributes_fn=lambda c: _why_unknown(c, "thermal_power"),
    ),
    PoolSensorDescription(
        key="session_elapsed",
        native_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=2,
        value_fn=lambda c: _session(c).get("elapsed_h"),
        attributes_fn=lambda c: _session(c),
    ),
    PoolSensorDescription(
        key="session_gain",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=2,
        value_fn=lambda c: _session(c).get("gain"),
        attributes_fn=lambda c: _session(c),
    ),
    PoolSensorDescription(
        key="session_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=lambda c: _session(c).get("energy_kwh"),
        attributes_fn=lambda c: _session(c),
    ),
    PoolSensorDescription(
        key="heat_balance",
        native_unit_of_measurement="%",
        suggested_display_precision=0,
        value_fn=lambda c: _heat_balance(c).get("kept_percent"),
        attributes_fn=lambda c: _heat_balance(c),
    ),
    PoolSensorDescription(
        key="flow_adequacy",
        value_fn=lambda c: _flow_adequacy(c)[0],
        attributes_fn=lambda c: {
            "explanation": _flow_adequacy(c)[1],
            **_flow_adequacy(c)[2],
            "datasheet_minimum_m3h": c.pool_config.heat_pump.flow_min_m3h,
            "site_verified": c.pool_config.heat_pump.flow_min_site_verified,
        },
    ),
    PoolSensorDescription(
        key="solar_collector_advice",
        value_fn=lambda c: _collector_advice(c)[0],
        attributes_fn=lambda c: {
            "explanation": _collector_advice(c)[1],
            **_collector_advice(c)[2],
        },
    ),
    PoolSensorDescription(
        key="solar_surplus",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda c: (
            round(c.data["state"].solar_power_w)
            if c.data and c.data["state"].solar_power_w is not None
            else None
        ),
        attributes_fn=lambda c: _solar_attributes(c),
    ),
    PoolSensorDescription(
        key="flow_rate",
        native_unit_of_measurement="m³/h",
        suggested_display_precision=2,
        value_fn=lambda c: (
            round(c.data["state"].effective_flow_m3h, 2)
            if c.data and c.data["state"].effective_flow_m3h is not None
            else None
        ),
    ),
    PoolSensorDescription(
        key="filtration_required_today",
        native_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=2,
        value_fn=lambda c: round(c.filtration.required_h, 2) if c.filtration else None,
        attributes_fn=lambda c: dict(c.filtration.detail) if c.filtration else {},
    ),
    PoolSensorDescription(
        key="filtration_completed_today",
        native_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=2,
        value_fn=lambda c: round(c.filtration.done_h, 2) if c.filtration else None,
    ),
    PoolSensorDescription(
        key="filtration_remaining_today",
        native_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=2,
        value_fn=lambda c: round(c.filtration.remaining_h, 2) if c.filtration else None,
        attributes_fn=lambda c: (
            {
                "readable": _readable_hours(c.filtration.remaining_h),
                "available_h": round(c.filtration.available_h, 2),
                "available_readable": _readable_hours(c.filtration.available_h),
                "deadline_critical": c.filtration.deadline_critical,
                "next_block_start": (
                    c.filtration.next_block.start.isoformat()
                    if c.filtration.next_block
                    else None
                ),
            }
            if c.filtration
            else {}
        ),
    ),
    PoolSensorDescription(
        key="heating_rate",
        native_unit_of_measurement="°C/h",
        suggested_display_precision=3,
        value_fn=lambda c: c.store.learned.heating_rate_c_per_h,
        attributes_fn=lambda c: (
            {}
            if c.store.learned.heating_rate_c_per_h is not None
            else {
                "unavailable_because": (
                    "no complete heating session has been recorded yet; this fills "
                    "in after the first one"
                ),
                "sessions_recorded": len(c.store.session_log),
            }
        ),
    ),
    PoolSensorDescription(
        key="heat_loss_rate",
        native_unit_of_measurement="°C/h",
        suggested_display_precision=3,
        value_fn=lambda c: c.store.learned.heat_loss_c_per_h,
    ),
    PoolSensorDescription(
        key="energy_today",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda c: round(c.store.energy_today_kwh, 3),
    ),
    PoolSensorDescription(
        key="cost_today",
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        value_fn=lambda c: round(c.store.cost_today, 3),
    ),
    PoolSensorDescription(
        key="water_test_due",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda c: (
            dt_util.parse_datetime(c.water_chemistry["test_due_at"])
            if c.water_chemistry["test_due_at"]
            else None
        ),
        attributes_fn=lambda c: {
            k: v
            for k, v in c.water_chemistry.items()
            if k in ("test_interval_days", "test_interval_reason", "test_overdue")
        },
    ),
    PoolSensorDescription(
        key="simple_status",
        value_fn=lambda c: _simple_status(c)[0],
        attributes_fn=lambda c: _simple_status(c)[1],
    ),
    PoolSensorDescription(
        key="price_verdict",
        value_fn=lambda c: _price_verdict(c)[0],
        attributes_fn=lambda c: _price_verdict(c)[1],
    ),
    PoolSensorDescription(
        key="water_balance",
        value_fn=lambda c: _water_balance(c)[0],
        attributes_fn=lambda c: _water_balance(c)[1],
    ),
    PoolSensorDescription(
        key="dose_advice",
        value_fn=lambda c: _dose_summary(c),
        attributes_fn=lambda c: c.water_chemistry,
    ),
    PoolSensorDescription(
        key="ai_suggestion",
        value_fn=lambda c: (
            len(c.advisor.last_result.suggestions) if c.advisor.last_result else 0
        ),
        attributes_fn=lambda c: (
            {
                **c.advisor.last_result.as_dict(),
                "last_run": c.advisor.last_run.isoformat() if c.advisor.last_run else None,
            }
            if c.advisor.last_result
            else {"status": "not run yet"}
        ),
    ),
    PoolSensorDescription(
        key="cost_saved_today",
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        value_fn=lambda c: round(c.store.cost_baseline_today - c.store.cost_today, 3),
        attributes_fn=lambda c: _savings_note(c),
    ),
)


def _readable_hours(hours: float | None) -> str | None:
    """A duration as someone would say it.

    Hours with two decimals is precise and unreadable: "0.78 h" has to be
    converted in your head before it means anything. Every duration attribute
    carries this alongside the number, so a card can show it without repeating
    the arithmetic.
    """
    if hours is None:
        return None
    total = round(hours * 60)
    if total == 0:
        return "0 min"
    if total < 60:
        return f"{total} min"
    if total % 60 == 0:
        return f"{total // 60} h"
    return f"{total // 60} h {total % 60} min"


def _price_verdict(coordinator: PoolSmartCoordinator):
    """Is electricity cheap right now, in words.

    A figure of 0.24 means nothing to someone who does not follow tariffs daily.
    Where it sits within today's range does: the same price is a bargain in
    January and daylight robbery in a sunny week.
    """
    state = coordinator.data.get("state") if coordinator.data else None
    if state is None or state.price_total is None:
        return "unknown", {"reason": "no electricity price sensor is configured"}

    price = state.price_total
    numbers = {"price": round(price, 4)}

    slots = coordinator._price_slots
    if slots:
        prices = [p for _s, _e, p in slots]
        low, high = min(prices), max(prices)
        numbers.update({"today_low": round(low, 4), "today_high": round(high, 4)})
        span = high - low
        if span > 0:
            position = (price - low) / span
            numbers["position"] = round(position, 2)
            if position <= 0.25:
                return "cheap", numbers
            if position <= 0.6:
                return "normal", numbers
            return "expensive", numbers

    # An external cheap-period signal is a better answer than a bare comparison
    # against a fixed ceiling, because it knows the shape of the day.
    if state.cheap_price_now is True:
        return "cheap", numbers
    limit = coordinator.pool_config.energy.max_price
    if limit:
        numbers["limit"] = limit
        return ("cheap" if price <= limit * 0.8 else
                "normal" if price <= limit else "expensive"), numbers
    return "unknown", numbers


def _simple_status(coordinator: PoolSmartCoordinator):
    """Three answers, for the people who do not want the other forty.

    Is it warm enough, is it clean, and when can I swim. Everything that asks
    the reader to make a decision is left out on purpose -- a page someone
    consults before going outside should not present them with settings.
    """
    state = coordinator.data.get("state") if coordinator.data else None
    if state is None or not state.water_temp.available:
        return "unknown", {}

    water = state.water_temp.value
    target = state.target_temp
    chemistry = coordinator.water_chemistry
    bands = chemistry.get("bands") or []
    urgent = [b for b in bands if b["urgent"]]
    off = [b for b in bands if b["verdict"] != "ok"]

    warm_enough = water >= target - 1.0
    if not bands:
        water_state = "unknown"
    elif urgent:
        water_state = "needs attention"
    elif off:
        water_state = "slightly off"
    else:
        water_state = "fine"

    if warm_enough and water_state in ("fine", "unknown"):
        headline = "ready to swim"
    elif not warm_enough:
        headline = "warming up"
    else:
        headline = "check the water"

    ready = coordinator.estimate
    detail = {
        "water_temperature": round(water, 1),
        "target_temperature": target,
        "warm_enough": warm_enough,
        "water_quality": water_state,
        "water_note": (urgent or off)[0]["label"] if (urgent or off) else None,
        "price_verdict": _price_verdict(coordinator)[0],
    }
    if not warm_enough and ready and ready.hours_needed not in (0, float("inf")):
        detail["hours_to_target"] = round(ready.hours_needed, 1)
        detail["ready_readable"] = _readable_hours(ready.hours_needed)
    return headline, detail


def _water_balance(coordinator: PoolSmartCoordinator):
    """One word for the whole water picture, with everything behind it.

    "Balanced" is a real answer worth being able to see, and an urgent reading
    should not have to compete for attention with a routine one -- hence two
    levels rather than one.
    """
    chemistry = coordinator.water_chemistry
    bands = chemistry.get("bands") or []
    if not bands:
        return "no readings", {"advice": [], "bands": []}

    urgent = [b for b in bands if b["urgent"]]
    off = [b for b in bands if b["verdict"] != "ok"]

    if urgent:
        state = "action needed"
    elif off:
        state = "adjust"
    else:
        state = "balanced"

    return state, {
        "bands": bands,
        "off_range": [b["label"] for b in off],
        "urgent": [b["label"] for b in urgent],
        "combined_chlorine": chemistry.get("combined_chlorine"),
        "advice": chemistry.get("advice", []),
        "sanitiser": chemistry.get("sanitiser"),
    }


def _dose_summary(coordinator: PoolSmartCoordinator) -> str:
    """One line saying what, if anything, the water needs.

    "Balanced" is a real answer and worth stating, not an empty state.
    """
    chemistry = coordinator.water_chemistry
    parts = []
    for key in ("ph_dose", "chlorine_dose"):
        dose = chemistry.get(key)
        if dose:
            parts.append(f"{dose['amount']:.0f} {dose['unit']} {dose['label']}")
    if parts:
        return " and ".join(parts)
    if chemistry["ph"] is None and chemistry["chlorine"] is None:
        return "no readings"
    return "balanced"


def _session(coordinator: PoolSmartCoordinator) -> dict:
    """How the running session is going, against what was expected.

    Published while the session runs rather than after it finishes. The recorder
    was already collecting all of this; it just kept it to itself until the end,
    which is precisely when nobody needs it any more.
    """
    state = coordinator.data.get("state") if coordinator.data else None
    if state is None or state.session_started_at is None:
        return {"running": False}

    elapsed_h = (state.now - state.session_started_at).total_seconds() / 3600.0
    start_temp = state.session_start_temp
    now_temp = state.water_temp.value if state.water_temp.available else None
    gain = (
        round(now_temp - start_temp, 2)
        if now_temp is not None and start_temp is not None
        else None
    )

    result = {
        "running": True,
        "started_at": state.session_started_at.isoformat(),
        "elapsed_h": round(elapsed_h, 3),
        "elapsed_readable": _readable_hours(elapsed_h),
        "start_temp": start_temp,
        "current_temp": now_temp,
        "target_temp": state.target_temp,
        "gain": gain,
        "energy_kwh": round(state.session_energy_kwh, 3),
        "cost": round(state.session_cost, 3),
        "covered": state.covered,
    }

    # The comparison is the point. A rate on its own says nothing about whether
    # the session is going well.
    estimate = coordinator.estimate
    if estimate and estimate.hours_needed and elapsed_h > PROGRESS_EPSILON and gain is not None:
        expected_rate = (
            estimate.degrees_needed / estimate.hours_needed
            if estimate.hours_needed not in (0, float("inf"))
            else None
        )
        actual_rate = gain / elapsed_h
        result["actual_rate_c_per_h"] = round(actual_rate, 3)
        if expected_rate:
            result["expected_rate_c_per_h"] = round(expected_rate, 3)
            ratio = actual_rate / expected_rate
            result["on_schedule_ratio"] = round(ratio, 2)
            if ratio >= 1.05:
                result["verdict"] = "ahead of schedule"
            elif ratio >= 0.75:
                result["verdict"] = "on schedule"
            else:
                result["verdict"] = (
                    "behind schedule — check the flow, the cover, or whether "
                    "something is drawing heat away"
                )
    return result


def _heat_balance(coordinator: PoolSmartCoordinator) -> dict:
    """How much of the heat pump's output the pool actually keeps.

    The single most explanatory number on a poorly insulated pool. A system
    losing two thirds of its input to the air takes three times as long to warm
    up as the appliance rating suggests, and no amount of price optimisation
    changes that — a cover does.
    """
    state = coordinator.data.get("state") if coordinator.data else None
    estimate = coordinator.estimate
    if state is None or estimate is None or not estimate.thermal_kw:
        return {}

    config = coordinator.pool_config
    gross = estimate.thermal_kw / config.pool.kwh_thermal_per_degree
    loss = state.heat_loss_c_per_h
    net = gross - loss
    if gross <= 0:
        return {}

    learned = coordinator.store.learned
    result = {
        "gross_rise_c_per_h": round(gross, 3),
        "loss_c_per_h": round(loss, 3),
        "net_rise_c_per_h": round(net, 3),
        "kept_percent": round(max(0.0, net / gross) * 100, 1),
        "lost_percent": round(min(100.0, loss / gross * 100), 1),
        "covered": state.covered,
        "loss_open": learned.heat_loss_c_per_h,
        "loss_covered": learned.heat_loss_covered_c_per_h,
    }

    if state.covered is None:
        result["advice"] = (
            "No cover entity is configured, so the effect of a cover cannot be "
            "measured."
        )
    elif (
        not state.covered
        and learned.heat_loss_covered_c_per_h is not None
        and learned.heat_loss_c_per_h is not None
    ):
        saved = learned.heat_loss_c_per_h - learned.heat_loss_covered_c_per_h
        if saved > 0:
            result["advice"] = (
                f"The cover is off. With it on this pool loses {saved:.2f} °C/h "
                "less, measured on this installation."
            )
    elif result["lost_percent"] > 50:
        result["advice"] = (
            "More than half the heat pump's output is going straight back into "
            "the air. Reducing that loss is worth more than any change to "
            "heating times or prices."
        )
    return result


def _flow_adequacy(coordinator: PoolSmartCoordinator):
    """Whether the water is carrying the heat away.

    Kept as a sensor rather than only a fault, because the answer is usually
    "yes, comfortably" and that is worth being able to see. A warning that only
    appears when something is wrong cannot reassure anyone.
    """
    state = coordinator.data.get("state") if coordinator.data else None
    if state is None:
        return "unknown", "No measurement yet.", {}
    return safety.flow_adequacy(state, coordinator.pool_config)


def _collector_advice(coordinator: PoolSmartCoordinator):
    """Whether opening the solar collector valve is worth the walk outside.

    ``core.safety.solar_collector_advice`` existed since the collector-margin
    setting was added but was never actually wired to anything -- see #7,
    which needed a live hook to suppress "open the valve" advice while it is
    raining and found the function sitting unused.
    """
    state = coordinator.data.get("state") if coordinator.data else None
    if state is None:
        return "unknown", "No measurement yet.", {}
    worth_it, why, numbers = safety.solar_collector_advice(
        state, coordinator.pool_config, raining=bool(coordinator._is_raining_now)
    )
    return ("open" if worth_it else "closed"), why, numbers


def _solar_attributes(coordinator: PoolSmartCoordinator) -> dict:
    """Show the threshold next to the reading.

    A solar figure on its own does not answer the question people have, which is
    "is this enough". Putting the threshold and the shortfall beside it does.
    """
    config = coordinator.pool_config
    threshold = config.energy.solar_threshold_w
    draw_w = (config.heat_pump.input_kw + config.pump.power_kw) * 1000

    state = coordinator.data.get("state") if coordinator.data else None
    if state is None or state.solar_power_w is None:
        return {
            "threshold_w": threshold,
            "equipment_draw_w": round(draw_w),
            "unavailable_because": "no solar power sensor is configured",
        }

    surplus = state.solar_power_w
    enough = surplus >= threshold
    return {
        "threshold_w": threshold,
        "equipment_draw_w": round(draw_w),
        "eco_threshold_w": threshold + config.energy.solar_hysteresis_w,
        "enough_for_free_heating": enough,
        "shortfall_w": 0 if enough else round(threshold - surplus),
        "explanation": (
            "Above the threshold, heating is treated as free and the price limit "
            "is ignored. The threshold should be at least what the heat pump and "
            "pump draw together, plus a margin so a passing cloud does not start "
            "and stop a session."
        ),
    }


def _savings_note(coordinator: PoolSmartCoordinator) -> dict:
    """Explain a zero saving.

    Savings are the difference between what the energy cost and what it would
    have cost at the average price across the forecast. Zero is the honest answer
    in three common situations, and none of them is a fault.
    """
    state = coordinator.data.get("state") if coordinator.data else None
    if state is None or state.price_total is None:
        return {
            "unavailable_because": (
                "no electricity price sensor is configured, so there is nothing to "
                "compare against"
            )
        }
    if not coordinator._price_slots:
        return {
            "unavailable_because": (
                "the price sensor publishes a current price but no forecast, so "
                "there is no average to compare against. Savings appear once a "
                "forecast is available"
            )
        }
    if coordinator.store.energy_today_kwh <= 0:
        return {"unavailable_because": "nothing has run yet today"}
    return {
        "baseline_cost": round(coordinator.store.cost_baseline_today, 3),
        "actual_cost": round(coordinator.store.cost_today, 3),
        "explanation": (
            "what the same energy would have cost at the average price of the "
            "forecast, minus what it actually cost"
        ),
    }


def _next_action(coordinator: PoolSmartCoordinator) -> object | None:
    """The soonest thing that is going to happen, heating or filtration."""
    candidates = []
    if coordinator.plan and coordinator.plan.next_start:
        candidates.append(coordinator.plan.next_start)
    if coordinator.filtration and coordinator.filtration.next_block:
        candidates.append(coordinator.filtration.next_block.start)
    return min(candidates) if candidates else None


def _measured_cop(coordinator: PoolSmartCoordinator) -> float | None:
    """COP from measured thermal output divided by measured electrical input.

    Only meaningful while the heat pump is actually working. Dividing a near-zero
    output by a near-zero input produces a number, but not one that means
    anything, so this stays blank until the appliance is drawing real power.
    """
    thermal = _thermal_power(coordinator)
    if thermal is None or not coordinator.data:
        return None
    state = coordinator.data["state"]
    if not state.heat_pump_on:
        return None
    electric = state.hp_power_w.value
    # A heat pump idling on standby draws a few watts; that is not a duty point.
    if not electric or electric < HP_STANDBY_WATTS:
        return None
    cop = thermal / (electric / 1000.0)
    limits = coordinator.pool_config.heat_pump
    return round(max(limits.cop_clamp_min, min(limits.cop_clamp_max, cop)), 2)


def _thermal_power(coordinator: PoolSmartCoordinator) -> float | None:
    """Thermal output in kW from flow and temperature rise.

    1 m³/h of water carrying 1 K corresponds to about 1.163 kW.

    Reported whenever flow and a temperature difference are available, whether or
    not the heat pump is running. With it off the figure sits near zero, which is
    a real measurement and a useful one: it shows the sensors are alive and gives
    a baseline to compare a heating session against. Blanking it made a working
    installation look broken.
    """
    if not coordinator.data:
        return None
    state = coordinator.data["state"]
    delta = state.delta_t
    flow = state.effective_flow_m3h
    if delta is None or flow is None:
        return None
    if coordinator.pool_config.is_aliased("hp_inlet", "hp_outlet"):
        return None
    return round(flow * delta * 1.163, 3)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: PoolSmartCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(PoolSmartSensor(coordinator, d) for d in SENSORS)


class PoolSmartSensor(PoolSmartEntity, SensorEntity):
    """A computed value derived from the current decision."""

    _entity_domain = "sensor"
    entity_description: PoolSensorDescription

    def __init__(
        self, coordinator: PoolSmartCoordinator, description: PoolSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        return self.entity_description.value_fn(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict:
        if self.entity_description.attributes_fn is None:
            return {}
        return self.entity_description.attributes_fn(self.coordinator)
