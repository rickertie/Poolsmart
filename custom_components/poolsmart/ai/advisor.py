"""The advisory AI layer.

This module never switches anything. It reads the session history, asks a model
for observations, and produces suggestions that a human accepts or ignores. If
the AI is unavailable, slow, or talking nonsense, the pool carries on exactly as
before -- which is why it sits outside the tick rather than inside it.

Suggestions are returned as structured data, validated against the settings that
are actually adjustable, and anything unrecognised is discarded rather than
applied.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .. import const as c
from ..core import safety

_LOGGER = logging.getLogger(__name__)

#: Settings the advisor is allowed to suggest changes to. Anything outside this
#: list is dropped, so a confused model cannot propose altering a safety limit.
ADJUSTABLE = {
    c.CONF_TURNOVER_FACTOR: (0.5, 4.0),
    c.CONF_MAX_PRICE: (0.0, 2.0),
    c.CONF_SOLAR_THRESHOLD_W: (0.0, 20000.0),
    c.CONF_TEMP_HYSTERESIS: (0.1, 3.0),
    c.CONF_MIN_ON_MINUTES: (1.0, 120.0),
    c.CONF_MIN_OFF_MINUTES: (1.0, 120.0),
    c.CONF_PUMP_RUNDOWN_MINUTES: (0.0, 60.0),
}

PROMPT = """You are reviewing a week of operating data from a swimming pool controller.

IMPORTANT CONTEXT ABOUT FLOW
Do not recommend increasing water flow to reach a datasheet minimum. That figure
is written for a generic installation and takes no account of pipe length,
elbows, filters or a diverter valve; many systems settle below it and move heat
perfectly well. Telling the owner to reach a number their plumbing cannot produce
is not advice, it is noise.

Judge heat transfer by the temperature rise across the heat pump instead, which
measures directly what the flow figure stands for. A rise under about 3 C means
the water is carrying the heat away comfortably. Above 5 C means it is not, and
that is when a flow problem is worth raising. The field `flow_adequacy` below
already contains this verdict; trust it over any comparison you make yourself
between measured flow and the datasheet minimum.

Reply with JSON only. No prose, no markdown fences. Use this shape:
{"summary": "two or three plain sentences for a homeowner",
 "observations": ["short factual observations"],
 "suggestions": [{"setting": "<key>", "value": <number>, "why": "<one sentence>"}]}

Only suggest settings from this list: %(allowed)s
Suggest nothing if the data does not clearly support a change. An empty
suggestions list is a perfectly good answer.

Data:
%(data)s
"""


@dataclass
class Suggestion:
    """A proposed settings change, awaiting a human decision."""

    setting: str
    value: float
    why: str
    created: datetime

    def as_dict(self) -> dict:
        return {
            "setting": self.setting,
            "value": self.value,
            "why": self.why,
            "created": self.created.isoformat(),
        }


@dataclass
class AdvisorResult:
    """What a review produced."""

    summary: str = ""
    observations: list[str] = field(default_factory=list)
    suggestions: list[Suggestion] = field(default_factory=list)
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "summary": self.summary,
            "observations": self.observations,
            "suggestions": [s.as_dict() for s in self.suggestions],
            "error": self.error,
        }


class Advisor:
    """Asks a model to comment on the last week of operation."""

    def __init__(self, hass: HomeAssistant, coordinator) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self.last_result: AdvisorResult | None = None
        self.last_run: datetime | None = None

    # -- Gathering ---------------------------------------------------------

    def _payload(self) -> dict:
        store = self.coordinator.store
        config = self.coordinator.pool_config
        cutoff = dt_util.now() - timedelta(days=7)

        def recent(entries: list[dict]) -> list[dict]:
            out = []
            for item in entries:
                stamp = item.get("start") or item.get("at")
                if not stamp:
                    continue
                parsed = dt_util.parse_datetime(stamp)
                if parsed and parsed >= cutoff:
                    out.append(item)
            return out

        def strip_timestamps(entries: list[dict]) -> list[dict]:
            cleaned = []
            for item in entries:
                cleaned.append(
                    {k: v for k, v in item.items() if k not in ("start", "end", "at")}
                )
            return cleaned

        def summarize_sessions(entries: list[dict]) -> dict:
            if not entries:
                return {"count": 0}
            cops = [e.get("measured_cop") for e in entries if e.get("measured_cop") is not None]
            rates = [e.get("heating_rate") for e in entries if e.get("heating_rate") is not None]
            summary = {
                "count": len(entries),
                "average_cop": round(sum(cops) / len(cops), 3) if cops else None,
                "average_heating_rate_c_per_h": (
                    round(sum(rates) / len(rates), 4) if rates else None
                ),
            }
            return summary

        state = self.coordinator.data.get("state") if self.coordinator.data else None
        verdict, explanation, numbers = (
            safety.flow_adequacy(state, config) if state else ("unknown", "", {})
        )

        privacy_level = getattr(config, "privacy_level", "standard")

        payload: dict = {
            "flow_adequacy": {
                "verdict": verdict,
                "explanation": explanation,
                **numbers,
                "datasheet_minimum_m3h": config.heat_pump.flow_min_m3h,
                "site_verified": config.heat_pump.flow_min_site_verified,
                "note": (
                    "The datasheet minimum is a generic figure. This installation's "
                    "measured behaviour is what counts, and the verdict above is "
                    "based on it."
                ),
            },
            "pool_volume_l": config.pool.volume_l,
            "daily_filtration_hours": round(
                config.daily_filtration_hours(None, store.learned.measured_flow_m3h), 2
            ),
            "turnover_factor": config.filtration.turnover_factor,
            "target_temp": self.coordinator.target_temp,
        }

        sessions = recent(store.session_log)[-20:]
        decisions = recent(store.decision_log)[-40:]

        if privacy_level == "minimal":
            payload["sessions"] = summarize_sessions(sessions)
            payload["learned"] = store.learned.as_dict()
        elif privacy_level == "standard":
            payload["learned"] = store.learned.as_dict()
            payload["sessions"] = strip_timestamps(sessions)
            payload["decisions"] = strip_timestamps(decisions)
            payload["energy_today_kwh"] = round(store.energy_today_kwh, 2)
        else:
            payload["learned"] = store.learned.as_dict()
            payload["sessions"] = sessions
            payload["decisions"] = decisions
            payload["energy_today_kwh"] = round(store.energy_today_kwh, 2)
            payload["cost_today"] = round(store.cost_today, 2)

        return payload

    # -- Running -----------------------------------------------------------

    async def async_review(self) -> AdvisorResult:
        """Ask for a review. Any failure is contained here."""
        prompt = PROMPT % {
            "allowed": ", ".join(sorted(ADJUSTABLE)),
            "data": json.dumps(self._payload(), default=str)[:12000],
        }

        self.last_run = dt_util.now()

        if not self.hass.services.has_service("ai_task", "generate_data"):
            result = AdvisorResult(
                error=(
                    "No ai_task.generate_data service is available. Set up an AI task "
                    "entity first, under Settings, Devices and services, Helpers."
                )
            )
            _LOGGER.info("AI review skipped: %s", result.error)
            self.last_result = result
            return result

        try:
            response = await self.hass.services.async_call(
                "ai_task",
                "generate_data",
                {"task_name": "poolsmart_weekly_review", "instructions": prompt},
                blocking=True,
                return_response=True,
            )
        except Exception as err:  # noqa: BLE001 -- advisory only, must not propagate
            _LOGGER.info("AI review unavailable: %s", err)
            result = AdvisorResult(error=f"{type(err).__name__}: {err}")
            self.last_result = result
            return result

        result = self._parse(response)
        if not result.summary and not result.observations and not result.suggestions:
            result.error = result.error or (
                "The model replied, but with nothing usable in it."
            )
        self.last_result = result
        return result

    def _parse(self, response) -> AdvisorResult:
        raw = ""
        if isinstance(response, dict):
            raw = str(response.get("data") or response.get("text") or response)
        else:
            raw = str(response)

        cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        try:
            parsed = json.loads(cleaned)
        except (ValueError, TypeError):
            return AdvisorResult(
                summary=cleaned[:400],
                error="the model did not return usable JSON, so no suggestions were taken",
            )

        suggestions = []
        for item in parsed.get("suggestions", []) or []:
            setting = item.get("setting")
            if setting not in ADJUSTABLE:
                _LOGGER.debug("Discarded a suggestion for an unknown setting: %s", setting)
                continue
            try:
                value = float(item.get("value"))
            except (TypeError, ValueError):
                continue
            low, high = ADJUSTABLE[setting]
            if not low <= value <= high:
                _LOGGER.debug("Discarded an out-of-range suggestion for %s", setting)
                continue
            suggestions.append(
                Suggestion(
                    setting=setting,
                    value=value,
                    why=str(item.get("why", ""))[:200],
                    created=dt_util.now(),
                )
            )

        return AdvisorResult(
            summary=str(parsed.get("summary", ""))[:600],
            observations=[str(x)[:200] for x in (parsed.get("observations") or [])][:8],
            suggestions=suggestions,
        )

    # -- Applying ----------------------------------------------------------

    async def async_accept(self, index: int = 0) -> bool:
        """Apply a suggestion, only ever on explicit instruction."""
        if not self.last_result or index >= len(self.last_result.suggestions):
            return False
        suggestion = self.last_result.suggestions[index]
        options = dict(self.coordinator.entry.options)
        options[suggestion.setting] = suggestion.value
        self.hass.config_entries.async_update_entry(
            self.coordinator.entry, options=options
        )
        _LOGGER.info(
            "Applied an accepted suggestion: %s set to %s",
            suggestion.setting,
            suggestion.value,
        )
        self.last_result.suggestions.pop(index)
        return True
