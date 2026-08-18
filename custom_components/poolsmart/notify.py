"""Notifications.

Two behaviours matter here. Faults repeat with a widening interval until they
clear, because a single message at three in the morning is easy to miss and a
message every minute is worse than none. Informational events fire once and are
never repeated -- nobody needs to be told twice that the pool reached
temperature.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from . import const as c
from .core.models import Branch, Decision, Fault, Mode, Severity

_LOGGER = logging.getLogger(__name__)

#: Repeat intervals for unresolved faults, in minutes. The last value repeats.
ESCALATION_MINUTES = (0, 15, 60, 240, 720)


#: Actions offered on a notification, per event type. Tapping one fires a
#: `poolsmart_action` event that the integration acts on, so a notification
#: becomes something you can answer rather than only read.
#:
#: Only mobile app targets render these; other notify platforms ignore the extra
#: data, so nothing breaks when they are sent regardless.
#:
#: Labels are kept short -- mobile notification buttons have limited space and
#: are truncated after roughly twenty characters in most apps.
EVENT_ACTIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "heating_postponed": (
        ("BOOST", "Heat now"),
        ("STANDBY", "Skip today"),
    ),
    "target_reached": (
        ("STANDBY", "Stop heating"),
        ("EXTEND_1C", "+1° warmer"),
    ),
    "flow_fault": (
        ("PUMP_ONLY", "Pump only"),
        ("OFF", "All off"),
    ),
    "sensor_fault": (("OFF", "All off"),),
    "filter_service": (("PUMP_ONLY", "Circulate"),),
    "high_energy_cost": (
        ("BOOST", "Use free power"),
        ("STANDBY", "Wait"),
    ),
    "ai_recommendation": (("ACCEPT_SUGGESTION", "Apply"),),
    "heating_started": (),
    "chemistry_alarm": (),
}


@dataclass
class _Repeat:
    """Bookkeeping for a repeating notification."""

    first_sent: datetime
    last_sent: datetime
    step: int = 0


@dataclass
class NotificationManager:
    """Decides what to send, and to whom."""

    hass: HomeAssistant
    coordinator: object
    _repeats: dict[str, _Repeat] = field(default_factory=dict)
    _seen_once: set[str] = field(default_factory=set)
    _previous: Decision | None = None
    _last_day: str | None = None

    # -- Configuration -----------------------------------------------------

    def _targets(self, event: str) -> list[str]:
        """Which notify services handle this event type.

        Returns a list of targets so a message can reach more than one person.
        Falls back to the default target if no event-specific one is set.
        """
        targets = self.coordinator._conf(c.CONF_NOTIFY_TARGETS, {}) or {}
        specific = targets.get(event)
        if specific:
            if isinstance(specific, list):
                return specific
            return [specific]
        default = targets.get("default")
        if default:
            if isinstance(default, list):
                return default
            return [default]
        return []

    def _target(self, event: str) -> str | None:
        """Legacy single-target lookup; returns the first target or None."""
        all_targets = self._targets(event)
        return all_targets[0] if all_targets else None

    async def _send(self, event: str, title: str, message: str) -> None:
        """Deliver one message to all configured targets.

        There are two kinds of notify target and they are not interchangeable.
        Older integrations register a *service* per device, called as
        `notify.mobile_app_phone`. Newer ones register an *entity* in the notify
        domain, which has no service of its own and is reached through
        `notify.send_message` with the entity id. An entity picker offers both,
        so both have to work: calling an entity as though it were a service is
        what produced "Could not deliver".
        """
        targets = self._targets(event)
        if not targets:
            _LOGGER.debug("No notify target configured for %s", event)
            return

        payload: dict = {"title": title, "message": message}
        actions = EVENT_ACTIONS.get(event)
        if actions:
            payload["data"] = {
                "actions": [
                    {"action": f"{c.ACTION_PREFIX}{key}", "title": label}
                    for key, label in actions
                ],
                "tag": f"{c.DOMAIN}_{event}",
            }

        for target in targets:
            self._send_one(target, payload, event)

    def _send_one(self, target: str, payload: dict, event: str) -> None:
        """Send to a single target."""
        service = target.split(".", 1)[-1]
        entity_exists = self.hass.states.get(target) is not None
        service_exists = self.hass.services.has_service("notify", service)

        try:
            if service_exists:
                self.hass.async_create_task(
                    self.hass.services.async_call(
                        "notify",
                        service,
                        payload,
                        blocking=False,
                    )
                )
            elif entity_exists:
                call_data = {
                    "entity_id": target,
                    "title": payload.get("title", ""),
                    "message": payload.get("message", ""),
                }
                if payload.get("data"):
                    # Action buttons (data.actions/tag) were being built and
                    # then silently dropped on this path -- the entity-based
                    # notify.send_message call never forwarded them, unlike
                    # the legacy per-device service call below. That is what
                    # actually made action buttons disappear on any device
                    # reached through a notify entity. See #19.
                    call_data["data"] = payload["data"]
                self.hass.async_create_task(
                    self.hass.services.async_call(
                        "notify",
                        "send_message",
                        call_data,
                        blocking=False,
                    )
                )
            else:
                _LOGGER.warning(
                    "Notification target %s no longer exists; %s not delivered",
                    target,
                    event,
                )
        except Exception as err:  # noqa: BLE001 -- a bad target must not break control
            _LOGGER.warning(
                "Could not deliver a %s notification via %s: %s", event, target, err
            )

    # -- Entry point -------------------------------------------------------

    async def async_process(
        self, decision: Decision, faults: list[Fault], now: datetime | None = None
    ) -> None:
        now = now or dt_util.now()
        self._roll_day(now)
        await self._process_faults(faults, now)
        await self._process_decision(decision)
        self._previous = decision

    def _roll_day(self, now: datetime) -> None:
        """Once-a-day events become eligible again after midnight."""
        today = now.date().isoformat()
        if self._last_day != today:
            self._last_day = today
            self._seen_once = {k for k in self._seen_once if not k.startswith("daily:")}

    # -- Faults ------------------------------------------------------------

    async def _process_faults(self, faults: list[Fault], now: datetime) -> None:
        active = {f.code: f for f in faults}

        for code in list(self._repeats):
            if code not in active:
                del self._repeats[code]

        for code, fault in active.items():
            event = self._event_for(fault)
            record = self._repeats.get(code)
            if record is None:
                self._repeats[code] = _Repeat(first_sent=now, last_sent=now)
                await self._send(event, self._title_for(fault), fault.message)
                continue

            step = min(record.step + 1, len(ESCALATION_MINUTES) - 1)
            wait = timedelta(minutes=ESCALATION_MINUTES[step])
            if now - record.last_sent >= wait:
                record.last_sent = now
                record.step = step
                elapsed = (now - record.first_sent).total_seconds() / 3600
                await self._send(
                    event,
                    self._title_for(fault),
                    f"{fault.message} Still unresolved after {elapsed:.1f} hours.",
                )

    @staticmethod
    def _event_for(fault: Fault) -> str:
        if "flow" in fault.code:
            return "flow_fault"
        if fault.code == "filter_service_needed":
            return "filter_service"
        return "sensor_fault"

    @staticmethod
    def _title_for(fault: Fault) -> str:
        if fault.severity is Severity.CRITICAL:
            return "Pool: everything stopped"
        if fault.severity is Severity.HEATING_BLOCKED:
            return "Pool: heating stopped"
        return "Pool: attention needed"

    # -- Decision transitions ---------------------------------------------

    async def _process_decision(self, decision: Decision) -> None:
        previous = self._previous
        if previous is None:
            return

        if decision.heat_pump and not previous.heat_pump:
            await self._send("heating_started", "Pool: heating started", decision.reason)

        if previous.heat_pump and not decision.heat_pump:
            coordinator = self.coordinator
            state = coordinator.data.get("state") if coordinator.data else None
            if state is not None and state.water_temp.available:
                if state.water_temp.value >= coordinator.target_temp - 0.1:
                    await self._send(
                        "target_reached",
                        "Pool: at temperature",
                        f"The pool has reached {state.water_temp.value:.1f} C.",
                    )

        if (
            decision.branch is Branch.IDLE
            and "Waiting for cheaper electricity" in decision.reason
            and previous.branch is not Branch.IDLE
        ):
            await self._send(
                "heating_postponed", "Pool: heating postponed", decision.reason
            )

        if (
            decision.branch is Branch.FREE_POWER
            and previous.branch is not Branch.FREE_POWER
        ):
            await self._send(
                "high_energy_cost",
                "Pool: free electricity",
                decision.reason,
            )

    # -- Called from elsewhere --------------------------------------------

    async def async_send_recommendation(self, message: str) -> None:
        await self._send("ai_recommendation", "Pool: suggestion", message)

    async def async_send_chemistry(self, message: str) -> None:
        await self._send("chemistry_alarm", "Pool: chemistry", message)


class ActionHandler:
    """Acts on a notification button.

    The mobile app fires `mobile_app_notification_action` when someone taps one
    of the buttons offered above. Without this, those buttons would be decoration.
    """

    def __init__(self, hass: HomeAssistant, coordinator) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self._unsub = None

    @callback
    def async_start(self) -> None:
        self._unsub = self.hass.bus.async_listen(
            "mobile_app_notification_action", self._async_handle
        )

    @callback
    def async_stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    async def _async_handle(self, event) -> None:
        action = event.data.get("action", "")
        if not action.startswith(c.ACTION_PREFIX):
            return
        key = action[len(c.ACTION_PREFIX) :]
        _LOGGER.info("Acting on notification action %s", key)

        if key == "BOOST":
            await self.coordinator.async_set_mode(Mode.BOOST.value)
        elif key == "STANDBY":
            await self.coordinator.async_set_mode(Mode.STANDBY.value)
        elif key == "PUMP_ONLY":
            await self.coordinator.async_set_mode(Mode.PUMP.value)
        elif key == "OFF":
            await self.coordinator.async_set_mode(Mode.OFF.value)
        elif key == "EXTEND_1C":
            await self.coordinator.async_set_target(self.coordinator.target_temp + 1.0)
        elif key == "ACCEPT_SUGGESTION":
            await self.coordinator.async_accept_suggestion(0)
        else:
            _LOGGER.debug("Unrecognised notification action: %s", key)
