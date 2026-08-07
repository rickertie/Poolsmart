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


def _live_session(coordinator) -> dict:
    from .sensor import _session

    return _session(coordinator)


def _heat_balance_snapshot(coordinator) -> dict:
    from .sensor import _heat_balance

    return _heat_balance(coordinator)


def _learning_insight(coordinator) -> list[dict]:
    """Each learned value with its confidence and, crucially, what reads it.

    A value nobody reads is not knowledge, it is storage — and for two of these
    that was literally the case until 1.0. Naming the consumer keeps it honest.
    """
    from .core import learning

    learned = coordinator.store.learned
    config = coordinator.pool_config
    state = coordinator.data.get("state") if coordinator.data else None
    air = state.air_temp.value if state and state.air_temp.available else None

    cop_in_use = learning.cop_for(
        learned.cop_by_air_bucket, learned.cop_sessions_by_bucket, air
    )
    rate_sessions = learned.heating_rate_sessions

    return [
        {
            "key": "heat_loss",
            "value": learned.heat_loss_c_per_h,
            "unit": "°C/h",
            "sessions": learned.session_count,
            "in_use": learned.heat_loss_c_per_h is not None,
            "used_for": "how long heating takes, and whether the target is reachable",
            "fallback": config.learning.initial_heat_loss_c_per_h,
        },
        {
            "key": "measured_flow",
            "value": learned.measured_flow_m3h,
            "unit": "m³/h",
            "in_use": learned.measured_flow_m3h is not None,
            "used_for": "how many hours of filtration the pool needs each day",
            "fallback": round(config.pump.effective_flow_m3h, 3),
        },
        {
            "key": "cop",
            "value": cop_in_use,
            "unit": "",
            "sessions": sum(learned.cop_sessions_by_bucket.values()),
            "in_use": cop_in_use is not None,
            "used_for": "the heating time and cost estimate",
            "fallback": round(config.heat_pump.cop_at(air), 2) if air else None,
            "confidence": learning.rate_confidence(
                max(learned.cop_sessions_by_bucket.values(), default=0)
            ),
            "by_bucket": learned.cop_by_air_bucket,
        },
        {
            "key": "heating_rate",
            "value": learned.heating_rate_c_per_h,
            "unit": "°C/h",
            "sessions": rate_sessions,
            "in_use": rate_sessions >= learning.COP_CONFIDENCE_SESSIONS,
            "used_for": "the heating time estimate, ahead of any COP calculation",
            "confidence": learning.rate_confidence(rate_sessions),
        },
    ]


def _branch_time_today(coordinator) -> list[dict]:
    """How much of today each branch spent in charge.

    Reconstructed from the decision log rather than tracked separately, so it
    cannot drift away from what was actually recorded.
    """
    from datetime import datetime

    entries = coordinator.store.decision_log
    totals: dict[str, float] = {}
    for item in entries:
        branch = item.get("branch")
        seconds = item.get("duration_seconds") or 0
        if branch:
            totals[branch] = totals.get(branch, 0) + seconds

    grand = sum(totals.values()) or 1
    return sorted(
        (
            {
                "branch": branch,
                "seconds": round(seconds),
                "share": round(seconds / grand, 3),
            }
            for branch, seconds in totals.items()
        ),
        key=lambda row: -row["seconds"],
    )


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
    water = state.water_temp.value if state and state.water_temp.available else None
    measured = coordinator.store.learned.measured_flow_m3h

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
                "daily_filtration_hours": round(config.daily_filtration_hours(water, measured), 3),
                "block_hours": round(config.block_hours(water, measured), 3),
                "turnover_hours": round(config.turnover_hours(measured), 3),
                "min_hours": round(config.filtration.min_hours_at(water), 3),
                "filtration_driver": config.filtration_driver(water, measured),
                "kwh_thermal_per_degree": round(config.pool.kwh_thermal_per_degree, 3),
                "effective_flow_m3h": round(config.effective_flow(measured), 3),
                "turnover_factor": config.filtration.turnover_factor,
                "volume_l": config.pool.volume_l,
            },
            "advisor": (
                {
                    **coordinator.advisor.last_result.as_dict(),
                    "last_run": (
                        coordinator.advisor.last_run.isoformat()
                        if coordinator.advisor.last_run
                        else None
                    ),
                }
                if coordinator.advisor.last_result
                else None
            ),
            "trace": coordinator.trace.as_list() if coordinator.trace else [],
            "blocked_by": (
                [e.describe() for e in coordinator.trace.blockers]
                if coordinator.trace
                else []
            ),
            "last_error": coordinator.last_error,
            "subsystem_errors": coordinator.subsystem_errors,
            "learned": coordinator.store.learned.as_dict(),
            "learning_insight": _learning_insight(coordinator),
            "session": _live_session(coordinator),
            "heat_balance": _heat_balance_snapshot(coordinator),
            "chemistry": coordinator.water_chemistry,
            "branch_time_today": _branch_time_today(coordinator),
            "near_misses": coordinator.near_misses.as_list(),
            "bridged_roles": sorted(coordinator.bridged_roles),
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
