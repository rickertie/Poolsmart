"""Persistent state for PoolSmart.

Filtration runtime is kept as a list of closed intervals rather than a running
counter. That distinction is what makes a restart survivable: a counter that
lives in an entity loses everything, whereas a list of intervals loses at most
the tick that was in flight, and an interval left open by a crash is closed at
the last timestamp that was written.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    DECISION_LOG_SIZE,
    DOSE_LOG_SIZE,
    SESSION_LOG_SIZE,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class RuntimeInterval:
    """A period during which the circulation pump was running."""

    start: datetime
    end: datetime | None = None

    @property
    def hours(self) -> float:
        if self.end is None:
            return 0.0
        return max(0.0, (self.end - self.start).total_seconds() / 3600.0)

    def as_dict(self) -> dict:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat() if self.end else None,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> RuntimeInterval:
        return cls(
            start=datetime.fromisoformat(raw["start"]),
            end=datetime.fromisoformat(raw["end"]) if raw.get("end") else None,
        )


@dataclass
class LearnedValues:
    """Values the system improves after each session."""

    heating_rate_c_per_h: float | None = None
    #: Heat loss with the pool open to the air.
    heat_loss_c_per_h: float | None = None
    #: Heat loss with the cover on, learned separately.
    #:
    #: Averaging the two would produce a figure that is wrong in both states, and
    #: wrong by a lot: a cover typically halves the loss or better. On a pool
    #: losing two thirds of its input to the air, that is the difference between
    #: a two degree rise taking fourteen hours and taking five.
    heat_loss_covered_c_per_h: float | None = None
    heat_loss_samples: int = 0
    heat_loss_covered_samples: int = 0
    measured_flow_m3h: float | None = None
    cop_by_air_bucket: dict[str, float] = field(default_factory=dict)
    #: Sessions behind each bucket, so a single measurement is not mistaken for
    #: a settled figure.
    cop_sessions_by_bucket: dict[str, int] = field(default_factory=dict)
    heating_rate_sessions: int = 0
    session_count: int = 0

    def as_dict(self) -> dict:
        return {
            "heating_rate_c_per_h": self.heating_rate_c_per_h,
            "heat_loss_c_per_h": self.heat_loss_c_per_h,
            "heat_loss_covered_c_per_h": self.heat_loss_covered_c_per_h,
            "heat_loss_samples": self.heat_loss_samples,
            "heat_loss_covered_samples": self.heat_loss_covered_samples,
            "measured_flow_m3h": self.measured_flow_m3h,
            "cop_by_air_bucket": self.cop_by_air_bucket,
            "cop_sessions_by_bucket": self.cop_sessions_by_bucket,
            "heating_rate_sessions": self.heating_rate_sessions,
            "session_count": self.session_count,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> LearnedValues:
        return cls(
            heating_rate_c_per_h=raw.get("heating_rate_c_per_h"),
            heat_loss_c_per_h=raw.get("heat_loss_c_per_h"),
            heat_loss_covered_c_per_h=raw.get("heat_loss_covered_c_per_h"),
            heat_loss_samples=raw.get("heat_loss_samples", 0),
            heat_loss_covered_samples=raw.get("heat_loss_covered_samples", 0),
            measured_flow_m3h=raw.get("measured_flow_m3h"),
            cop_by_air_bucket=raw.get("cop_by_air_bucket", {}),
            cop_sessions_by_bucket=raw.get("cop_sessions_by_bucket", {}),
            heating_rate_sessions=raw.get("heating_rate_sessions", 0),
            session_count=raw.get("session_count", 0),
        )


class PoolStore:
    """Wrapper around Home Assistant's Store helper."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry_id}")
        self.quota_date: date | None = None
        self.intervals: list[RuntimeInterval] = []
        self.learned = LearnedValues()
        self.active_block: dict | None = None
        self.heat_pump_stopped_at: datetime | None = None
        self.heat_pump_started_at: datetime | None = None
        self.chemistry_until: datetime | None = None
        self.mode: str | None = None
        self.target_temp: float | None = None
        self.decision_log: list[dict] = []
        self.session_log: list[dict] = []
        self.dose_log: list[dict] = []
        self.last_water_test: datetime | None = None
        self.energy_today_kwh: float = 0.0
        self.cost_today: float = 0.0
        self.cost_baseline_today: float = 0.0

    # -- Loading and saving ------------------------------------------------

    async def async_load(self) -> None:
        raw = await self._store.async_load() or {}
        try:
            if raw.get("quota_date"):
                self.quota_date = date.fromisoformat(raw["quota_date"])
            self.intervals = [
                RuntimeInterval.from_dict(item) for item in raw.get("intervals", [])
            ]
            self.learned = LearnedValues.from_dict(raw.get("learned", {}))
            self.active_block = raw.get("active_block")
            if raw.get("heat_pump_stopped_at"):
                self.heat_pump_stopped_at = datetime.fromisoformat(raw["heat_pump_stopped_at"])
            if raw.get("heat_pump_started_at"):
                self.heat_pump_started_at = datetime.fromisoformat(raw["heat_pump_started_at"])
            if raw.get("chemistry_until"):
                self.chemistry_until = datetime.fromisoformat(raw["chemistry_until"])
            self.mode = raw.get("mode")
            self.target_temp = raw.get("target_temp")
            self.decision_log = raw.get("decision_log", [])
            self.session_log = raw.get("session_log", [])
            self.dose_log = raw.get("dose_log", [])
            if raw.get("last_water_test"):
                self.last_water_test = datetime.fromisoformat(raw["last_water_test"])
            self.energy_today_kwh = raw.get("energy_today_kwh", 0.0)
            self.cost_today = raw.get("cost_today", 0.0)
            self.cost_baseline_today = raw.get("cost_baseline_today", 0.0)
        except (ValueError, KeyError, TypeError):
            _LOGGER.warning("Stored PoolSmart state was unreadable and has been reset")

        self._close_open_interval()
        if self.backfill_cop_counts():
            _LOGGER.info(
                "Recovered COP session counts for learned values that predate the "
                "confidence counter"
            )

    def _close_open_interval(self) -> None:
        """Close an interval that a crash or restart left open.

        The pump state after a restart is unknown until the first tick, so the
        interval is closed at its own start. At worst one tick of runtime is lost;
        the alternative -- assuming it kept running -- would silently inflate the
        quota and skip real filtration.
        """
        for interval in self.intervals:
            if interval.end is None:
                interval.end = interval.start
                _LOGGER.debug("Closed a filtration interval left open by a restart")

    async def async_save(self) -> None:
        await self._store.async_save(
            {
                "quota_date": self.quota_date.isoformat() if self.quota_date else None,
                "intervals": [i.as_dict() for i in self.intervals],
                "learned": self.learned.as_dict(),
                "active_block": self.active_block,
                "heat_pump_stopped_at": (
                    self.heat_pump_stopped_at.isoformat()
                    if self.heat_pump_stopped_at
                    else None
                ),
                "heat_pump_started_at": (
                    self.heat_pump_started_at.isoformat()
                    if self.heat_pump_started_at
                    else None
                ),
                "chemistry_until": (
                    self.chemistry_until.isoformat() if self.chemistry_until else None
                ),
                "mode": self.mode,
                "target_temp": self.target_temp,
                "decision_log": self.decision_log[-DECISION_LOG_SIZE:],
                "session_log": self.session_log[-SESSION_LOG_SIZE:],
                "dose_log": self.dose_log[-DOSE_LOG_SIZE:],
                "last_water_test": (
                    self.last_water_test.isoformat() if self.last_water_test else None
                ),
                "energy_today_kwh": self.energy_today_kwh,
                "cost_today": self.cost_today,
                "cost_baseline_today": self.cost_baseline_today,
            }
        )

    # -- Filtration quota --------------------------------------------------

    def roll_day(self, now: datetime) -> bool:
        """Reset the quota when the date changes. Returns True if it rolled."""
        if self.quota_date == now.date():
            return False
        self.quota_date = now.date()
        self.intervals = []
        self.active_block = None
        self.energy_today_kwh = 0.0
        self.cost_today = 0.0
        self.cost_baseline_today = 0.0
        return True

    def record_pump(self, now: datetime, running: bool) -> None:
        """Update the interval list from the pump's actual state."""
        open_interval = next((i for i in self.intervals if i.end is None), None)
        if running and open_interval is None:
            self.intervals.append(RuntimeInterval(start=now))
        elif running and open_interval is not None:
            # Keep the open interval open, but remember how far it has come so a
            # crash loses only the last tick.
            open_interval.end = None
        elif not running and open_interval is not None:
            open_interval.end = now

    def runtime_hours(self, now: datetime) -> float:
        """Filtration runtime credited today, including any open interval.

        Heating sessions run the pump too, so their runtime lands here
        automatically. Without that credit the system would filter substantially
        more than needed on heating days.
        """
        total = 0.0
        for interval in self.intervals:
            end = interval.end or now
            total += max(0.0, (end - interval.start).total_seconds() / 3600.0)
        return total

    # -- Decision log ------------------------------------------------------

    def log_decision(self, payload: dict) -> None:
        self.decision_log.append(payload)
        if len(self.decision_log) > DECISION_LOG_SIZE:
            self.decision_log = self.decision_log[-DECISION_LOG_SIZE:]

    def log_dose(self, payload: dict) -> None:
        """Record a dose that was applied."""
        self.dose_log.append(payload)
        if len(self.dose_log) > DOSE_LOG_SIZE:
            self.dose_log = self.dose_log[-DOSE_LOG_SIZE:]

    def log_session(self, payload: dict) -> None:
        """Record a finished heating session, usable or not.

        Rejected sessions are kept deliberately: when the model stops improving,
        the reasons things were rejected are the first place to look.
        """
        self.session_log.append(payload)
        if len(self.session_log) > SESSION_LOG_SIZE:
            self.session_log = self.session_log[-SESSION_LOG_SIZE:]

    # -- Learned values ----------------------------------------------------

    def backfill_cop_counts(self) -> bool:
        """Give pre-1.1 buckets a session count they were never given.

        `cop_by_air_bucket` has existed since 0.9; the counter that gates it was
        added in 1.1. Anyone who upgraded therefore has learned values sitting
        behind a gate that can never open, because the count starts at zero no
        matter how many sessions produced the value.

        Counting the recorded sessions per bucket recovers the real figure. Where
        the session log has been trimmed away, one is assumed: enough to show the
        value exists, not enough to trust it for planning, which is the honest
        position for a number whose provenance was lost.
        """
        if not self.learned.cop_by_air_bucket:
            return False
        if self.learned.cop_sessions_by_bucket:
            return False

        from .core.learning import recover_cop_counts

        self.learned.cop_sessions_by_bucket = recover_cop_counts(
            self.learned.cop_by_air_bucket, self.session_log
        )
        return True

    def adopt(self, history: dict) -> str:
        """Take on learned history from elsewhere.

        Merges rather than replaces where it can: an adopted heat loss is better
        than no heat loss, but if this pool has already learned something of its
        own since setup, that is measured on the actual installation and wins.
        """
        learned = history.get("learned") or {}
        if not learned:
            return "nothing to adopt"

        incoming = LearnedValues.from_dict(learned)
        taken: list[str] = []

        for field in (
            "heating_rate_c_per_h",
            "heat_loss_c_per_h",
            "heat_loss_covered_c_per_h",
            "measured_flow_m3h",
        ):
            if getattr(self.learned, field) is None:
                value = getattr(incoming, field)
                if value is not None:
                    setattr(self.learned, field, value)
                    taken.append(field)

        if not self.learned.cop_by_air_bucket and incoming.cop_by_air_bucket:
            self.learned.cop_by_air_bucket = dict(incoming.cop_by_air_bucket)
            self.learned.cop_sessions_by_bucket = dict(
                incoming.cop_sessions_by_bucket
            )
            taken.append("cop_by_air_bucket")

        for field in (
            "session_count",
            "heating_rate_sessions",
            "heat_loss_samples",
            "heat_loss_covered_samples",
        ):
            if not getattr(self.learned, field):
                setattr(self.learned, field, getattr(incoming, field))

        # The logs are the evidence the figures were derived from; adopting a
        # summary without them leaves numbers nothing can check or improve.
        if not self.session_log and history.get("session_log"):
            self.session_log = list(history["session_log"])
            taken.append("session_log")
        if not self.dose_log and history.get("dose_log"):
            self.dose_log = list(history["dose_log"])
            taken.append("dose_log")
        if self.last_water_test is None and history.get("last_water_test"):
            try:
                self.last_water_test = datetime.fromisoformat(
                    history["last_water_test"]
                )
            except (TypeError, ValueError):
                pass

        self.backfill_cop_counts()
        return ", ".join(taken) if taken else "nothing was missing"

    def reset_learned(self, name: str) -> bool:
        """Clear one learned value without discarding the rest.

        A single implausible figure should not cost someone their whole learning
        history -- particularly the heat loss, which takes days of idle periods
        to establish and is the hardest one to rebuild.
        """
        from .core.learning import RESETTABLE

        if name not in RESETTABLE:
            return False

        value_attr, count_attr = RESETTABLE[name]
        current = getattr(self.learned, value_attr)
        setattr(self.learned, value_attr, {} if isinstance(current, dict) else None)
        if count_attr:
            counter = getattr(self.learned, count_attr)
            setattr(self.learned, count_attr, {} if isinstance(counter, dict) else 0)
        return True

    def apply_learned(self, name: str, value: float, max_step_ratio: float) -> float:
        """Update a learned value with a capped step.

        A single strange session must not be able to wreck the model, so each
        update may move the value by at most ``max_step_ratio``.
        """
        current = getattr(self.learned, name, None)
        if current is None or current == 0:
            setattr(self.learned, name, value)
            return value
        limit = abs(current) * max_step_ratio
        delta = max(-limit, min(limit, value - current))
        updated = current + delta
        setattr(self.learned, name, updated)
        return updated
