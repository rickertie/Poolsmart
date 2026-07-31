"""Diagnostics: a full state dump, including the decision log.

The decision log is the answer to "what is it doing and why". It is recorded at
the moment of deciding rather than reconstructed afterwards, which is the whole
reason this integration exists.
"""

from __future__ import annotations

from dataclasses import asdict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import PoolSmartCoordinator


def _water(coordinator: PoolSmartCoordinator) -> float | None:
    """Current water temperature, if known.

    The filtration requirement depends on it, because the time-based daily
    minimum rises as the water warms up.
    """
    state = coordinator.data.get("state") if coordinator.data else None
    if state is None or not state.water_temp.available:
        return None
    return state.water_temp.value


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    coordinator: PoolSmartCoordinator = hass.data[DOMAIN][entry.entry_id]
    config = coordinator.pool_config
    decision = coordinator.decision
    filtration = coordinator.filtration
    water = _water(coordinator)

    return {
        "derived": {
            "daily_filtration_hours": round(config.daily_filtration_hours(water), 3),
            "block_hours": round(config.block_hours(water), 3),
            "turnover_hours": round(config.turnover_hours, 3),
            "filtration_driver": config.filtration_driver(water),
            "kwh_thermal_per_degree": round(config.pool.kwh_thermal_per_degree, 3),
            "effective_flow_m3h": round(config.pump.effective_flow_m3h, 3),
        },
        "mode": coordinator.mode.value,
        "target_temp": coordinator.target_temp,
        "heat_pump_available": coordinator.heat_pump_available,
        "heat_pump_gate_reason": coordinator.heat_pump_gate_reason,
        "disabled_capabilities": sorted(coordinator.disabled_capabilities),
        "faults": [asdict(f) for f in coordinator.faults],
        "decision": {
            "branch": decision.branch.name if decision else None,
            "pump": decision.pump if decision else None,
            "heat_pump": decision.heat_pump if decision else None,
            "reason": decision.reason if decision else None,
            "hold_until": decision.hold_until.isoformat()
            if decision and decision.hold_until
            else None,
            "detail": decision.detail if decision else {},
        },
        "filtration": {
            "required_h": round(filtration.required_h, 3) if filtration else None,
            "done_h": round(filtration.done_h, 3) if filtration else None,
            "remaining_h": round(filtration.remaining_h, 3) if filtration else None,
            "available_h": round(filtration.available_h, 3) if filtration else None,
            "deadline_critical": filtration.deadline_critical if filtration else None,
        },
        "learned": coordinator.store.learned.as_dict(),
        "decision_log": coordinator.store.decision_log,
    }
