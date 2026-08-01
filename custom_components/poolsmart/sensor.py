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

from .const import DOMAIN
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
        if not state.heat_pump_on:
            return {
                "unavailable_because": "the heat pump is not running",
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
            if c.data
            and c.data["state"].delta_t is not None
            and not c.pool_config.is_aliased("hp_inlet", "hp_outlet")
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
                "available_h": round(c.filtration.available_h, 2),
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
    ),
)


def _next_action(coordinator: PoolSmartCoordinator) -> object | None:
    """The soonest thing that is going to happen, heating or filtration."""
    candidates = []
    if coordinator.plan and coordinator.plan.next_start:
        candidates.append(coordinator.plan.next_start)
    if coordinator.filtration and coordinator.filtration.next_block:
        candidates.append(coordinator.filtration.next_block.start)
    return min(candidates) if candidates else None


def _measured_cop(coordinator: PoolSmartCoordinator) -> float | None:
    """COP from measured thermal output divided by measured electrical input."""
    thermal = _thermal_power(coordinator)
    if thermal is None or not coordinator.data:
        return None
    electric = coordinator.data["state"].hp_power_w.value
    if not electric:
        return None
    cop = thermal / (electric / 1000.0)
    limits = coordinator.pool_config.heat_pump
    return round(max(limits.cop_clamp_min, min(limits.cop_clamp_max, cop)), 2)


def _thermal_power(coordinator: PoolSmartCoordinator) -> float | None:
    """Thermal output in kW from flow and temperature rise.

    1 m³/h of water carrying 1 K corresponds to about 1.163 kW.
    """
    if not coordinator.data:
        return None
    state = coordinator.data["state"]
    delta = state.delta_t
    flow = state.effective_flow_m3h
    if delta is None or flow is None or not state.heat_pump_on:
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
