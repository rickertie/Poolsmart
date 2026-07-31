"""Websocket API for the management panel.

The decision log and the session log are too large to hang off an entity
attribute, and putting them there would also mean recorder storing a hundred
entries on every state change. They are served on request instead.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .coordinator import PoolSmartCoordinator


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register the panel's websocket commands once."""
    websocket_api.async_register_command(hass, ws_entries)
    websocket_api.async_register_command(hass, ws_snapshot)
    websocket_api.async_register_command(hass, ws_clear_log)


def _coordinator(hass: HomeAssistant, entry_id: str | None) -> PoolSmartCoordinator | None:
    entries: dict[str, PoolSmartCoordinator] = hass.data.get(DOMAIN, {})
    if entry_id:
        return entries.get(entry_id)
    return next(iter(entries.values()), None)


@websocket_api.websocket_command({vol.Required("type"): "poolsmart/entries"})
@callback
def ws_entries(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """List the configured pools."""
    entries = hass.data.get(DOMAIN, {})
    connection.send_result(
        msg["id"],
        [
            {"entry_id": entry_id, "title": coordinator.entry.title}
            for entry_id, coordinator in entries.items()
        ],
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "poolsmart/snapshot",
        vol.Optional("entry_id"): str,
    }
)
@callback
def ws_snapshot(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Everything the panel needs, in one round trip."""
    coordinator = _coordinator(hass, msg.get("entry_id"))
    if coordinator is None:
        connection.send_error(msg["id"], "not_found", "No pool is configured")
        return

    config = coordinator.pool_config
    decision = coordinator.decision
    filtration = coordinator.filtration
    plan = coordinator.plan
    state = coordinator.data.get("state") if coordinator.data else None

    connection.send_result(
        msg["id"],
        {
            "title": coordinator.entry.title,
            "mode": coordinator.mode.value,
            "target_temp": coordinator.target_temp,
            "water_temp": (
                state.water_temp.value if state and state.water_temp.available else None
            ),
            "air_temp": (
                state.air_temp.value if state and state.air_temp.available else None
            ),
            "decision": (
                {
                    "branch": decision.branch.name,
                    "branch_number": int(decision.branch),
                    "pump": decision.pump,
                    "heat_pump": decision.heat_pump,
                    "reason": decision.reason,
                    "hold_until": (
                        decision.hold_until.isoformat() if decision.hold_until else None
                    ),
                    "detail": decision.detail,
                }
                if decision
                else None
            ),
            "heat_pump_available": coordinator.heat_pump_available,
            "heat_pump_gate_reason": coordinator.heat_pump_gate_reason,
            "disabled_capabilities": sorted(coordinator.disabled_capabilities),
            "faults": [
                {"code": f.code, "severity": f.severity.value, "message": f.message}
                for f in coordinator.faults
            ],
            "filtration": (
                {
                    "required_h": round(filtration.required_h, 3),
                    "done_h": round(filtration.done_h, 3),
                    "remaining_h": round(filtration.remaining_h, 3),
                    "available_h": round(filtration.available_h, 3),
                    "deadline_critical": filtration.deadline_critical,
                    "active_block": (
                        {
                            "index": filtration.active_block.index,
                            "start": filtration.active_block.start.isoformat(),
                            "end": filtration.active_block.end.isoformat(),
                            "rationale": filtration.active_block.rationale,
                        }
                        if filtration.active_block
                        else None
                    ),
                    "next_block": (
                        {
                            "index": filtration.next_block.index,
                            "start": filtration.next_block.start.isoformat(),
                            "end": filtration.next_block.end.isoformat(),
                            "rationale": filtration.next_block.rationale,
                        }
                        if filtration.next_block
                        else None
                    ),
                }
                if filtration
                else None
            ),
            "plan": (
                {
                    "mode": plan.mode.value,
                    "reason": plan.reason,
                    "hours_needed": round(plan.hours_needed, 2),
                    "hours_planned": round(plan.hours_planned, 2),
                    "expected_cost": plan.expected_cost,
                    "ready_at": plan.ready_at.isoformat() if plan.ready_at else None,
                    "slots": [
                        {
                            "start": s.isoformat(),
                            "end": e.isoformat(),
                            "price": p,
                        }
                        for s, e, p in plan.slots
                    ],
                    "detail": plan.detail,
                }
                if plan
                else None
            ),
            "derived": {
                "daily_filtration_hours": round(config.daily_filtration_hours, 3),
                "block_hours": round(config.block_hours, 3),
                "kwh_thermal_per_degree": round(config.pool.kwh_thermal_per_degree, 3),
                "effective_flow_m3h": round(config.pump.effective_flow_m3h, 3),
                "turnover_factor": config.filtration.turnover_factor,
                "volume_l": config.pool.volume_l,
            },
            "learned": coordinator.store.learned.as_dict(),
            "energy": {
                "today_kwh": round(coordinator.store.energy_today_kwh, 3),
                "cost_today": round(coordinator.store.cost_today, 3),
                "saved_today": round(
                    coordinator.store.cost_baseline_today - coordinator.store.cost_today, 3
                ),
            },
            "decision_log": list(reversed(coordinator.store.decision_log)),
            "session_log": list(reversed(coordinator.store.session_log)),
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "poolsmart/clear_log",
        vol.Optional("entry_id"): str,
    }
)
@websocket_api.require_admin
@callback
def ws_clear_log(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Empty the decision log."""
    coordinator = _coordinator(hass, msg.get("entry_id"))
    if coordinator is None:
        connection.send_error(msg["id"], "not_found", "No pool is configured")
        return
    coordinator.store.decision_log = []
    connection.send_result(msg["id"], {"cleared": True})
