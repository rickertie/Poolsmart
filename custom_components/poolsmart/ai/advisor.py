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


def _parse_iso(value: str | None) -> datetime | None:
    """Parse a timestamp this module wrote itself (always via ``.isoformat()``).

    ``datetime.fromisoformat`` rather than ``dt_util.parse_datetime``: the
    latter is built for arbitrary/loosely-formatted strings from outside
    sources, which is not what is being parsed here.
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None

#: Settings the advisor is allowed to suggest changes to. Anything outside this
#: list is dropped, so a confused model cannot propose altering a safety limit.
ADJUSTABLE = {
    c.CONF_TURNOVER_FACTOR: (0.5, 4.0),
    c.CONF_MAX_PRICE: c.MAX_PRICE_BOUNDS,
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

If `trends` lists a metric moving consistently over several months, it is worth
a sentence -- that kind of gradual drift is easy for a human to miss session by
session.

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


#: How long to wait after acceptance before judging a suggestion's outcome.
#: Long enough for a representative handful of sessions, short enough that
#: the next weekly review can plausibly see the result. See issue #10.
OUTCOME_WINDOW_DAYS = 7


@dataclass
class AcceptedSuggestion:
    """A suggestion that was accepted, with what it was measured against.

    ``before`` is a snapshot of :meth:`Advisor._recent_metrics` taken at
    acceptance time; the same snapshot taken again once
    :data:`OUTCOME_WINDOW_DAYS` has passed becomes ``outcome`` -- a plain
    sentence, not a second metrics blob, since the whole point is something a
    human (and the next prompt) can read at a glance.
    """

    id: str
    setting: str
    old_value: float | None
    new_value: float
    why: str
    accepted_at: datetime
    before: dict = field(default_factory=dict)
    outcome: str | None = None
    outcome_at: datetime | None = None

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "setting": self.setting,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "why": self.why,
            "accepted_at": self.accepted_at.isoformat(),
            "before": self.before,
            "outcome": self.outcome,
            "outcome_at": self.outcome_at.isoformat() if self.outcome_at else None,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> AcceptedSuggestion:
        return cls(
            id=raw["id"],
            setting=raw["setting"],
            old_value=raw.get("old_value"),
            new_value=raw["new_value"],
            why=raw.get("why", ""),
            accepted_at=datetime.fromisoformat(raw["accepted_at"]),
            before=raw.get("before") or {},
            outcome=raw.get("outcome"),
            outcome_at=(
                datetime.fromisoformat(raw["outcome_at"])
                if raw.get("outcome_at")
                else None
            ),
        )


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
        trends = self._trends()

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
        if trends:
            # No timestamps or raw values in here, only a direction and a
            # rate -- sent at every privacy level, the same as `learned`.
            payload["trends"] = trends

        outcomes = self._recent_outcomes()
        if outcomes:
            # So the model can see what it recommended before and what
            # actually happened, instead of repeating the same suggestion
            # every week regardless of whether it helped. See issue #10.
            payload["past_suggestion_outcomes"] = outcomes

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

    def _trends(self) -> list[dict]:
        """Long-term drift worth a model's attention.

        Only metrics actually moving one way or the other are included --
        "stable" and "insufficient_data" have nothing for the model to
        comment on, and would only pad the prompt.
        """
        from ..core import aggregates

        months = list(self.coordinator.store.monthly_aggregates.values())
        out = []
        for metric, result in aggregates.all_trends(months).items():
            if result.direction not in ("improving", "degrading"):
                continue
            out.append(
                {
                    "metric": metric,
                    "direction": result.direction,
                    "pct_per_month": round(result.pct_per_month, 2),
                }
            )
        return out

    def _recent_metrics(self) -> dict:
        """A small snapshot of how things are going right now.

        Used both as the "before" figure recorded at acceptance time and, once
        :data:`OUTCOME_WINDOW_DAYS` has passed, recomputed as "after" to judge
        the outcome -- the same figures, the same window, so the two are
        actually comparable. Deliberately small: this is a v1 comparison, not
        a full metrics export.
        """
        store = self.coordinator.store
        cutoff = dt_util.now() - timedelta(days=7)
        sessions = []
        for entry in store.session_log:
            parsed = _parse_iso(entry.get("start"))
            if parsed and parsed >= cutoff:
                sessions.append(entry)
        cops = [e.get("measured_cop") for e in sessions if e.get("measured_cop") is not None]
        return {
            "average_cop": round(sum(cops) / len(cops), 3) if cops else None,
            "sessions": len(sessions),
            "cost_today": round(store.cost_today, 2),
            "energy_today_kwh": round(store.energy_today_kwh, 2),
        }

    def _recent_outcomes(self, within_days: int = 14) -> list[dict]:
        """Accepted suggestions whose outcome was judged recently."""
        cutoff = dt_util.now() - timedelta(days=within_days)
        out = []
        for entry in self.coordinator.store.accepted_suggestions:
            outcome = entry.get("outcome")
            outcome_at = entry.get("outcome_at")
            if not outcome or not outcome_at:
                continue
            parsed = _parse_iso(outcome_at)
            if not parsed or parsed < cutoff:
                continue
            out.append(
                {
                    "setting": entry.get("setting"),
                    "value": entry.get("new_value"),
                    "outcome": outcome,
                }
            )
        return out[-5:]

    def _describe_outcome(self, before: dict, after: dict) -> str:
        """A plain sentence a human (and the next prompt) can act on."""
        before_cop = before.get("average_cop")
        after_cop = after.get("average_cop")
        if before_cop is None or after_cop is None:
            return "Not enough sessions in the window to judge the outcome."
        delta = after_cop - before_cop
        if abs(delta) < 0.05:
            return f"COP essentially unchanged (was {before_cop:.2f}, now {after_cop:.2f})."
        direction = "improved" if delta > 0 else "worsened"
        return f"COP {direction} from {before_cop:.2f} to {after_cop:.2f}."

    async def async_check_outcomes(self) -> None:
        """Fill in the outcome for any accepted suggestion whose window has
        passed, so the next review can see what actually happened.

        Cheap to call on every review: entries with an outcome already, or
        not yet past the window, are skipped without recomputing anything.
        """
        store = self.coordinator.store
        now = dt_util.now()
        changed = False
        for entry in store.accepted_suggestions:
            if entry.get("outcome"):
                continue
            accepted_at = _parse_iso(entry.get("accepted_at"))
            if not accepted_at or now - accepted_at < timedelta(days=OUTCOME_WINDOW_DAYS):
                continue
            after = self._recent_metrics()
            entry["outcome"] = self._describe_outcome(entry.get("before") or {}, after)
            entry["outcome_at"] = now.isoformat()
            changed = True
        if changed:
            await store.async_save()

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
        old_value = options.get(suggestion.setting)
        options[suggestion.setting] = suggestion.value
        self.hass.config_entries.async_update_entry(
            self.coordinator.entry, options=options
        )
        _LOGGER.info(
            "Applied an accepted suggestion: %s set to %s",
            suggestion.setting,
            suggestion.value,
        )

        accepted_at = dt_util.now()
        record = AcceptedSuggestion(
            id=accepted_at.isoformat(),
            setting=suggestion.setting,
            old_value=old_value,
            new_value=suggestion.value,
            why=suggestion.why,
            accepted_at=accepted_at,
            before=self._recent_metrics(),
        )
        self.coordinator.store.log_accepted_suggestion(record.as_dict())
        await self.coordinator.store.async_save()

        self.last_result.suggestions.pop(index)
        return True
