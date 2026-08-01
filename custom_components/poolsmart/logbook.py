"""Home Assistant logbook integration.

Decisions are fired as events and described here, so they appear in the standard
Logbook alongside everything else that happened in the house. That context is
most of the value: a pump that switched off at 20:00 means one thing on its own
and another thing next to "someone opened the shed door at 19:58".

Three kinds of entry are produced:

* **Decisions** -- what changed, and the reason recorded at the moment of
  deciding.
* **Obstacles** -- what the ladder wanted to do but could not, which is the
  question people actually have when a pool is not heating.
* **Faults** -- raised and cleared, so the duration is visible rather than
  inferred.
"""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.const import ATTR_DEVICE_ID, ATTR_NAME
from homeassistant.core import Event, HomeAssistant, callback

from .const import (
    ATTR_BRANCH,
    ATTR_BLOCKERS,
    ATTR_DURATION,
    ATTR_HEAT_PUMP,
    ATTR_MESSAGE,
    ATTR_PUMP,
    ATTR_REASON,
    DOMAIN,
    EVENT_DECISION,
    EVENT_FAULT,
    EVENT_OBSTACLE,
)

#: How a branch reads in a sentence.
BRANCH_PHRASES = {
    "EMERGENCY_STOP": "stopped everything",
    "FROST_PROTECTION": "started protecting against frost",
    "MANUAL": "followed a manual instruction",
    "CHEMISTRY": "started a chemistry cycle",
    "FILTRATION_DEADLINE": "started catching up on filtration",
    "FREE_POWER": "started heating on free electricity",
    "HEATING": "started heating",
    "FILTRATION_BLOCK": "started a filtration block",
    "PUMP_RUNDOWN": "started running down after heating",
    "IDLE": "went idle",
}


def _outputs(pump: bool, heat_pump: bool) -> str:
    if heat_pump and pump:
        return "heating and circulating"
    if pump:
        return "circulating"
    return "everything off"


def _duration(seconds: float | None) -> str:
    if not seconds:
        return ""
    minutes = seconds / 60
    if minutes < 60:
        return f" after {minutes:.0f} min"
    return f" after {minutes / 60:.1f} h"


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[[str, str, Callable[[Event], dict]], None],
) -> None:
    """Register descriptions for the events this integration fires."""

    @callback
    def describe_decision(event: Event) -> dict:
        data = event.data
        branch = data.get(ATTR_BRANCH, "")
        phrase = BRANCH_PHRASES.get(branch, f"switched to {branch.lower()}")
        outputs = _outputs(data.get(ATTR_PUMP, False), data.get(ATTR_HEAT_PUMP, False))
        previous = _duration(data.get(ATTR_DURATION))
        return {
            ATTR_NAME: data.get(ATTR_NAME, "Pool"),
            ATTR_MESSAGE: f"{phrase} — {outputs}{previous}. {data.get(ATTR_REASON, '')}",
            ATTR_DEVICE_ID: data.get(ATTR_DEVICE_ID),
        }

    @callback
    def describe_obstacle(event: Event) -> dict:
        data = event.data
        blockers = data.get(ATTR_BLOCKERS) or []
        joined = "; ".join(blockers) if isinstance(blockers, list) else str(blockers)
        return {
            ATTR_NAME: data.get(ATTR_NAME, "Pool"),
            ATTR_MESSAGE: f"could not do more: {joined}",
            ATTR_DEVICE_ID: data.get(ATTR_DEVICE_ID),
        }

    @callback
    def describe_fault(event: Event) -> dict:
        data = event.data
        cleared = data.get("cleared")
        if cleared:
            return {
                ATTR_NAME: data.get(ATTR_NAME, "Pool"),
                ATTR_MESSAGE: (
                    f"fault cleared: {data.get('code')}{_duration(data.get(ATTR_DURATION))}"
                ),
                ATTR_DEVICE_ID: data.get(ATTR_DEVICE_ID),
            }
        return {
            ATTR_NAME: data.get(ATTR_NAME, "Pool"),
            ATTR_MESSAGE: f"fault: {data.get(ATTR_MESSAGE, data.get('code'))}",
            ATTR_DEVICE_ID: data.get(ATTR_DEVICE_ID),
        }

    async_describe_event(DOMAIN, EVENT_DECISION, describe_decision)
    async_describe_event(DOMAIN, EVENT_OBSTACLE, describe_obstacle)
    async_describe_event(DOMAIN, EVENT_FAULT, describe_fault)
